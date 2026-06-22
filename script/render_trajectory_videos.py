"""Render MP4 videos of the v3 vs v4 drone trajectories.

For each of the 3 captured scenarios, build a side-by-side 2D top-down
animation (v3 left, v4 right). Each frame shows the obstacle field, the
drone start, the target, the drone's current xy position, a fading trail
of the last ~1.5 s of motion, and a small inset showing altitude (z) vs
time. When an episode ends, the panel holds its final state and shows the
outcome label until the longer of the two trajectories finishes.

Reads:
  results/simulation_suite/trajectories_v3.pkl
  results/simulation_suite/trajectories_v4.pkl

Writes:
  results/simulation_suite/trajectory_{sim_label}.mp4   (3 files)
"""

import pickle
from pathlib import Path

import imageio.v2 as imageio
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.transforms import Affine2D

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT = REPO_ROOT / "results" / "simulation_suite"
V3_PKL = ROOT / "trajectories_v3.pkl"
V4_PKL = ROOT / "trajectories_v4.pkl"

TRAIL_STEPS = 45  # ~1.5 s at dt=0.0333
OUTCOME_COLOR = {
    "success":   "#2e7d32",
    "collision": "#c62828",
    "timeout":   "#ef6c00",
    "ongoing":   "#1976d2",
}


def draw_static(ax, obs):
    L = obs["L"]
    ax.set_xlim(-L - 1, L + 1)
    ax.set_ylim(-L - 1, L + 1)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(linestyle=":", alpha=0.3)
    boundary = mpatches.Rectangle((-L, -L), 2 * L, 2 * L,
                                  fill=False, edgecolor="#999",
                                  linewidth=0.8, linestyle="--")
    ax.add_patch(boundary)
    for p, r in zip(obs["p_spheres"], obs["r_spheres"]):
        ax.add_patch(mpatches.Circle((p[0], p[1]), r,
                                     facecolor="#5c6bc0", alpha=0.55,
                                     edgecolor="black", linewidth=0.4))
    for p, lwh, rpy in zip(obs["p_cubes"], obs["lwh_cubes"], obs["rpy_cubes"]):
        l, w, _ = lwh
        rect = mpatches.Rectangle((-l / 2, -w / 2), l, w,
                                  facecolor="#8d6e63", alpha=0.65,
                                  edgecolor="black", linewidth=0.4)
        rect.set_transform(Affine2D().rotate(float(rpy[2])).translate(p[0], p[1]) + ax.transData)
        ax.add_patch(rect)
    init = obs["init"]; target = obs["target"]
    ax.plot([init[0], target[0]], [init[1], target[1]],
            "--", color="#1976d2", alpha=0.55, linewidth=1.0)
    ax.plot(init[0], init[1], "o", color="#43a047",
            markersize=8, markeredgecolor="black")
    ax.plot(target[0], target[1], "*", color="#e53935",
            markersize=13, markeredgecolor="black")


def render_one(label, v3, v4):
    out_path = ROOT / f"trajectory_{label}.mp4"
    dt = v3["dt"]
    fps = int(round(1.0 / dt))

    n_v3 = v3["positions"].shape[0]
    n_v4 = v4["positions"].shape[0]
    n_frames = max(n_v3, n_v4)

    fig = plt.figure(figsize=(13, 7.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[5, 1], hspace=0.18, wspace=0.05)
    ax3 = fig.add_subplot(gs[0, 0])
    ax4 = fig.add_subplot(gs[0, 1])
    axz3 = fig.add_subplot(gs[1, 0])
    axz4 = fig.add_subplot(gs[1, 1])

    fig.suptitle(f"{label} — v3 (left) vs v4 (right) — env 0, first episode",
                 fontsize=13, y=0.97)

    for ax, ver, data in ((ax3, "v3", v3), (ax4, "v4", v4)):
        draw_static(ax, data["obstacles"])
        ax.set_title(f"{ver}", fontsize=11, loc="left")
        ax.set_xlabel("x (m)", fontsize=8)
        ax.set_ylabel("y (m)", fontsize=8)
        ax.tick_params(axis="both", labelsize=8)

    # altitude subplots
    for axz, data in ((axz3, v3), (axz4, v4)):
        t = np.arange(data["positions"].shape[0]) * dt
        axz.plot(t, data["positions"][:, 2], color="#888", linewidth=0.6, alpha=0.4)
        axz.set_xlim(0, n_frames * dt)
        z_min = float(min(v3["positions"][:, 2].min(), v4["positions"][:, 2].min())) - 0.5
        z_max = float(max(v3["positions"][:, 2].max(), v4["positions"][:, 2].max())) + 0.5
        axz.set_ylim(z_min, z_max)
        axz.set_xlabel("time (s)", fontsize=8)
        axz.set_ylabel("z (m)", fontsize=8)
        axz.grid(linestyle=":", alpha=0.3)
        axz.tick_params(axis="both", labelsize=8)

    # dynamic artists per panel
    artists = {}
    for ax, axz, ver, data in ((ax3, axz3, "v3", v3), (ax4, axz4, "v4", v4)):
        trail_line, = ax.plot([], [], "-", color="#1976d2", linewidth=1.4, alpha=0.75)
        head_marker, = ax.plot([], [], "o", color="#0d47a1",
                               markersize=8, markeredgecolor="black",
                               markeredgewidth=0.6)
        z_line, = axz.plot([], [], color="#0d47a1", linewidth=1.4)
        z_head, = axz.plot([], [], "o", color="#0d47a1", markersize=4)
        text = ax.text(0.02, 0.97, "", transform=ax.transAxes,
                       fontsize=10, va="top", ha="left",
                       bbox=dict(boxstyle="round,pad=0.3",
                                 facecolor="white", alpha=0.85,
                                 edgecolor="#bbb"))
        artists[ver] = dict(trail=trail_line, head=head_marker,
                            zline=z_line, zhead=z_head, text=text,
                            ax=ax, axz=axz, data=data)

    print(f"  rendering {label}: {n_frames} frames @ {fps} fps -> {out_path.name}")
    with imageio.get_writer(str(out_path), fps=fps, codec="libx264",
                            quality=8, macro_block_size=1) as writer:
        for frame in range(n_frames):
            for ver, art in artists.items():
                data = art["data"]
                n_here = data["positions"].shape[0]
                step = min(frame, n_here - 1)
                pos = data["positions"]

                trail_start = max(0, step - TRAIL_STEPS)
                art["trail"].set_data(pos[trail_start:step + 1, 0],
                                      pos[trail_start:step + 1, 1])
                art["head"].set_data([pos[step, 0]], [pos[step, 1]])
                t = np.arange(step + 1) * dt
                art["zline"].set_data(t, pos[:step + 1, 2])
                art["zhead"].set_data([t[-1]], [pos[step, 2]])

                if frame >= n_here - 1:
                    # episode is done — show outcome
                    art["head"].set_color(OUTCOME_COLOR.get(data["outcome"], "#0d47a1"))
                    art["text"].set_text(
                        f"t = {(n_here * dt):5.2f} s\n"
                        f"outcome: {data['outcome'].upper()}"
                    )
                    art["text"].set_color(OUTCOME_COLOR.get(data["outcome"], "#000"))
                else:
                    art["head"].set_color("#0d47a1")
                    art["text"].set_text(
                        f"t = {((step + 1) * dt):5.2f} s\n"
                        f"|v|: {np.linalg.norm(pos[step] - pos[max(step - 1, 0)]) / dt:5.2f} m/s"
                    )
                    art["text"].set_color("#000")

            fig.canvas.draw()
            img = np.array(fig.canvas.buffer_rgba())[..., :3]
            writer.append_data(img)

    plt.close(fig)
    print(f"  wrote {out_path} ({out_path.stat().st_size / (1024*1024):.1f} MB)")


def main():
    with V3_PKL.open("rb") as f:
        v3 = pickle.load(f)
    with V4_PKL.open("rb") as f:
        v4 = pickle.load(f)
    for label in v3.keys():
        render_one(label, v3[label], v4[label])


if __name__ == "__main__":
    main()
