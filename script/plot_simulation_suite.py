"""Plot the simulation suite dataset as a stacked outcome bar chart and a
side panel showing mean arrive-time / episode length / avg-velocity.

Reads results/simulation_suite/simulation_suite.csv and writes
results/simulation_suite/simulation_suite.png.
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite.csv"


def load_rows(path: Path):
    with path.open() as f:
        reader = csv.DictReader(f)
        return list(reader)


def main():
    csv_arg = sys.argv[1] if len(sys.argv) > 1 else None
    csv_path = Path(csv_arg) if csv_arg else DEFAULT_CSV
    if not csv_path.is_absolute():
        csv_path = (REPO_ROOT / csv_path).resolve()
    out_path = csv_path.with_suffix(".png")
    rows = load_rows(csv_path)
    labels = [r["label"].replace("sim", "").lstrip("0") + ": " + r["label"].split("_", 1)[1] for r in rows]
    success = np.array([float(r["success_rate"]) for r in rows])
    collision = np.array([float(r["collision_rate"]) for r in rows])
    timeout = np.array([float(r["timeout_rate"]) for r in rows])
    n_episodes = np.array([int(r["n_episodes"]) for r in rows])
    arrive_time = np.array([float(r["mean_arrive_time"]) if r["mean_arrive_time"] not in ("", "None") else np.nan for r in rows])
    avg_vel = np.array([float(r["mean_avg_vel"]) if r["mean_avg_vel"] not in ("", "None") else np.nan for r in rows])

    x = np.arange(len(rows))

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [3, 2]})

    # Top: stacked outcome bar chart
    ax = axes[0]
    c_succ = "#4caf50"
    c_coll = "#e53935"
    c_time = "#fb8c00"
    ax.bar(x, success, color=c_succ, label="success", edgecolor="black", linewidth=0.4)
    ax.bar(x, collision, bottom=success, color=c_coll, label="collision",
           edgecolor="black", linewidth=0.4)
    ax.bar(x, timeout, bottom=success + collision, color=c_time, label="timeout",
           edgecolor="black", linewidth=0.4)

    for i, r in enumerate(success):
        ax.text(i, r / 2, f"{r:.2f}", ha="center", va="center", color="white",
                fontsize=9, fontweight="bold")
        if collision[i] > 0.04:
            ax.text(i, success[i] + collision[i] / 2, f"{collision[i]:.2f}",
                    ha="center", va="center", color="white", fontsize=9)
        if timeout[i] > 0.04:
            ax.text(i, success[i] + collision[i] + timeout[i] / 2, f"{timeout[i]:.2f}",
                    ha="center", va="center", color="white", fontsize=9)
        ax.text(i, 1.02, f"n={n_episodes[i]}", ha="center", va="bottom", fontsize=8,
                color="#444")

    mean_success = success.mean()
    ax.axhline(mean_success, color="#1565c0", linestyle="--", linewidth=1.2,
               label=f"mean success rate = {mean_success:.3f}")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylim(0, 1.10)
    ax.set_ylabel("episode outcome rate")
    ax.set_title("Simulation suite: per-scenario outcomes\n"
                 "(model: pmc__oa__sha2c__rcnn, ckpt 2026-04-09/19-45-56, 64 envs × 2000 steps each)")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # Bottom: mean arrive time + mean avg velocity grouped bars
    ax2 = axes[1]
    width = 0.38
    b1 = ax2.bar(x - width / 2, arrive_time, width, color="#1976d2", label="mean arrive time (s)")
    ax2b = ax2.twinx()
    b2 = ax2b.bar(x + width / 2, avg_vel, width, color="#8e24aa", label="mean avg velocity (m/s)")

    for bar, v in zip(b1, arrive_time):
        if not np.isnan(v):
            ax2.text(bar.get_x() + bar.get_width() / 2, v + 0.2, f"{v:.1f}",
                     ha="center", va="bottom", fontsize=8, color="#1976d2")
    for bar, v in zip(b2, avg_vel):
        if not np.isnan(v):
            ax2b.text(bar.get_x() + bar.get_width() / 2, v + 0.05, f"{v:.2f}",
                      ha="center", va="bottom", fontsize=8, color="#8e24aa")

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right")
    ax2.set_ylabel("mean arrive time (s)", color="#1976d2")
    ax2b.set_ylabel("mean avg velocity (m/s)", color="#8e24aa")
    ax2.tick_params(axis="y", labelcolor="#1976d2")
    ax2b.tick_params(axis="y", labelcolor="#8e24aa")
    ax2.set_title("Successful-episode trajectory metrics")
    ax2.grid(axis="y", linestyle=":", alpha=0.5)

    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2b.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc="upper left", framealpha=0.9, fontsize=9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
