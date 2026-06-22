"""Static comparison of v3 and v4 drone trajectories on the three captured
scenarios (sim01_baseline, sim03_dense, sim17_tight_arena).

For each scenario, three panels (one row):
  1. Top-down xy view with both trajectories overlaid on the obstacle field
  2. Distance to goal vs. time (clearly shows when v4 stalls)
  3. Speed |v| vs. time (clearly shows over-deceleration / heading oscillation)

Reads:
  results/simulation_suite/trajectories_v3.pkl
  results/simulation_suite/trajectories_v4.pkl

Writes:
  results/simulation_suite/trajectories_v3_vs_v4.png
"""

import pickle
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.transforms import Affine2D

ROOT = Path("/home/arthur-huang/Desktop/diffaero/results/simulation_suite")

V3_COLOR = "#1976d2"  # blue
V4_COLOR = "#d81b60"  # magenta
OUTCOME_COLOR = {
    "success":   "#2e7d32",
    "collision": "#c62828",
    "timeout":   "#ef6c00",
}


def draw_obstacles(ax, obs):
    L = obs["L"]
    ax.set_xlim(-L - 1, L + 1)
    ax.set_ylim(-L - 1, L + 1)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(linestyle=":", alpha=0.3)
    boundary = mpatches.Rectangle((-L, -L), 2 * L, 2 * L,
                                  fill=False, edgecolor="#999",
                                  linewidth=0.7, linestyle="--")
    ax.add_patch(boundary)
    for p, r in zip(obs["p_spheres"], obs["r_spheres"]):
        ax.add_patch(mpatches.Circle((p[0], p[1]), r,
                                     facecolor="#5c6bc0", alpha=0.45,
                                     edgecolor="black", linewidth=0.3))
    for p, lwh, rpy in zip(obs["p_cubes"], obs["lwh_cubes"], obs["rpy_cubes"]):
        l, w, _ = lwh
        rect = mpatches.Rectangle((-l / 2, -w / 2), l, w,
                                  facecolor="#8d6e63", alpha=0.55,
                                  edgecolor="black", linewidth=0.3)
        rect.set_transform(Affine2D().rotate(float(rpy[2]))
                           .translate(p[0], p[1]) + ax.transData)
        ax.add_patch(rect)
    init = obs["init"]; target = obs["target"]
    ax.plot([init[0], target[0]], [init[1], target[1]],
            "--", color="#888", alpha=0.55, linewidth=0.9)
    ax.plot(init[0], init[1], "o", color="#43a047",
            markersize=8, markeredgecolor="black", zorder=4)
    ax.plot(target[0], target[1], "*", color="#e53935",
            markersize=12, markeredgecolor="black", zorder=4)


def plot_scenario(axes_row, label, d3, d4):
    obs = d3["obstacles"]
    target = obs["target"]
    dt = d3["dt"]

    # Top-down xy with both trajectories
    ax_xy = axes_row[0]
    draw_obstacles(ax_xy, obs)
    p3 = d3["positions"]; p4 = d4["positions"]
    ax_xy.plot(p3[:, 0], p3[:, 1], "-", color=V3_COLOR, linewidth=2.0,
               label=f"v3 ({d3['outcome']}, t={p3.shape[0]*dt:.1f}s)")
    ax_xy.plot(p4[:, 0], p4[:, 1], "-", color=V4_COLOR, linewidth=2.0,
               label=f"v4 ({d4['outcome']}, t={p4.shape[0]*dt:.1f}s)")
    # endpoint markers
    ax_xy.plot(p3[-1, 0], p3[-1, 1], "x", color=OUTCOME_COLOR[d3["outcome"]],
               markersize=10, markeredgewidth=2.0, zorder=5)
    ax_xy.plot(p4[-1, 0], p4[-1, 1], "x", color=OUTCOME_COLOR[d4["outcome"]],
               markersize=10, markeredgewidth=2.0, zorder=5)
    ax_xy.set_title(f"{label} — top-down xy", fontsize=10)
    ax_xy.set_xlabel("x (m)", fontsize=9)
    ax_xy.set_ylabel("y (m)", fontsize=9)
    ax_xy.legend(loc="lower right", fontsize=8, framealpha=0.85)

    # Distance to goal vs time
    ax_d = axes_row[1]
    t3 = np.arange(p3.shape[0]) * dt
    t4 = np.arange(p4.shape[0]) * dt
    dist3 = np.linalg.norm(p3 - target, axis=-1)
    dist4 = np.linalg.norm(p4 - target, axis=-1)
    ax_d.plot(t3, dist3, color=V3_COLOR, linewidth=1.8, label="v3")
    ax_d.plot(t4, dist4, color=V4_COLOR, linewidth=1.8, label="v4")
    ax_d.axhline(0.5, color="grey", linestyle=":", linewidth=0.9,
                 alpha=0.7, label="goal radius (0.5m)")
    ax_d.set_xlim(0, max(t3[-1], t4[-1]) + 0.5)
    ax_d.set_ylim(0, max(dist3.max(), dist4.max()) * 1.05)
    ax_d.set_xlabel("time (s)", fontsize=9)
    ax_d.set_ylabel("distance to goal (m)", fontsize=9)
    ax_d.set_title(f"{label} — progress toward goal", fontsize=10)
    ax_d.grid(linestyle=":", alpha=0.4)
    ax_d.legend(loc="upper right", fontsize=8, framealpha=0.85)

    # Speed |v| vs time (finite-difference of position)
    ax_v = axes_row[2]
    sp3 = np.linalg.norm(np.diff(p3, axis=0), axis=-1) / dt
    sp4 = np.linalg.norm(np.diff(p4, axis=0), axis=-1) / dt
    ax_v.plot(np.arange(sp3.shape[0]) * dt, sp3, color=V3_COLOR,
              linewidth=1.4, alpha=0.95, label="v3")
    ax_v.plot(np.arange(sp4.shape[0]) * dt, sp4, color=V4_COLOR,
              linewidth=1.4, alpha=0.95, label="v4")
    ax_v.set_xlim(0, max(t3[-1], t4[-1]) + 0.5)
    ax_v.set_ylim(0, max(sp3.max(), sp4.max()) * 1.05)
    ax_v.set_xlabel("time (s)", fontsize=9)
    ax_v.set_ylabel("|v| (m/s)", fontsize=9)
    ax_v.set_title(f"{label} — flight speed", fontsize=10)
    ax_v.grid(linestyle=":", alpha=0.4)
    ax_v.legend(loc="upper right", fontsize=8, framealpha=0.85)


def main():
    with (ROOT / "trajectories_v3.pkl").open("rb") as f:
        v3 = pickle.load(f)
    with (ROOT / "trajectories_v4.pkl").open("rb") as f:
        v4 = pickle.load(f)

    labels = list(v3.keys())
    n = len(labels)
    fig, axes = plt.subplots(n, 3, figsize=(16, 4.2 * n))
    if n == 1:
        axes = axes[None, :]

    for row, label in enumerate(labels):
        plot_scenario(axes[row], label, v3[label], v4[label])

    fig.suptitle(
        "v3 vs v4 — drone trajectory on three captured scenarios "
        "(env 0, first episode)\n"
        "blue = v3 (yaw-smoothing-free), magenta = v4 (with the misapplied "
        "yaw-align-to-command loss). X = endpoint, colored by outcome",
        fontsize=13, y=1.005)
    fig.tight_layout()

    out = ROOT / "trajectories_v3_vs_v4.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
