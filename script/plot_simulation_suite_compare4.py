"""Compare v1 / v2 / v3 / v4 simulation suites side by side.

Reads results/simulation_suite/simulation_suite{,_v2,_v3,_v4}.csv and writes
simulation_suite_compare4.png alongside.
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT = REPO_ROOT / "results" / "simulation_suite"
OUT_PATH = ROOT / "simulation_suite_compare4.png"

VERSIONS = [
    ("v1", "simulation_suite.csv",    "#7e57c2", "#e53935", "#fb8c00"),
    ("v2", "simulation_suite_v2.csv", "#43a047", "#c62828", "#ef6c00"),
    ("v3", "simulation_suite_v3.csv", "#1976d2", "#b71c1c", "#e65100"),
    ("v4", "simulation_suite_v4.csv", "#fbc02d", "#7f0000", "#bf360c"),
]


def load(p): return list(csv.DictReader(p.open()))
def col(rows, k):
    out = []
    for r in rows:
        v = r[k]
        out.append(np.nan if v in ("", "None") else float(v))
    return np.array(out)


def main():
    v1 = load(ROOT / "simulation_suite.csv")
    labels = [r["label"].replace("sim", "").lstrip("0") + ": " + r["label"].split("_", 1)[1] for r in v1]

    by_label = {}
    for name, fname, _, _, _ in VERSIONS:
        rows = load(ROOT / fname)
        by_label[name] = {r["label"]: r for r in rows}

    # Align by v1's ordering
    aligned = {name: [by_label[name][r["label"]] for r in v1] for name, *_ in VERSIONS}

    successes = {name: col(aligned[name], "success_rate") for name, *_ in VERSIONS}
    collisions = {name: col(aligned[name], "collision_rate") for name, *_ in VERSIONS}
    timeouts = {name: col(aligned[name], "timeout_rate") for name, *_ in VERSIONS}
    avg_vels = {name: col(aligned[name], "mean_avg_vel") for name, *_ in VERSIONS}

    x = np.arange(len(v1))
    n = len(VERSIONS)
    width = 0.85 / n  # total bar group width = 0.85

    fig, axes = plt.subplots(3, 1, figsize=(14, 12),
                             gridspec_kw={"height_ratios": [3, 2, 2]})

    # 1) Success rate per scenario
    ax = axes[0]
    for i, (name, _, c_succ, _, _) in enumerate(VERSIONS):
        offset = (i - (n - 1) / 2) * width
        ax.bar(x + offset, successes[name], width, color=c_succ,
               edgecolor="black", linewidth=0.4,
               label=f"{name} (mean {np.nanmean(successes[name]):.3f})")
    # delta annotation: v4 vs v3
    for i in range(len(x)):
        d = successes["v4"][i] - successes["v3"][i]
        sign = "+" if d >= 0 else ""
        color = "#0d47a1" if d >= 0 else "#b71c1c"
        ymax = max(successes[name][i] for name, *_ in VERSIONS)
        ax.text(i + (n - 1) / 2 * width, ymax + 0.02, f"{sign}{d:.2f}",
                ha="center", fontsize=7, color=color)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("success rate")
    ax.set_title("v1 vs v2 vs v3 vs v4: success rate per scenario (Δ above = v4 − v3)")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # 2) Failure-mode shift: collision (solid) + timeout (stacked above)
    ax2 = axes[1]
    hatches = [None, "//", "..", "xx"]
    for i, (name, _, _, c_coll, c_time) in enumerate(VERSIONS):
        offset = (i - (n - 1) / 2) * width
        ax2.bar(x + offset, collisions[name], width, color=c_coll,
                edgecolor="black", linewidth=0.4, hatch=hatches[i],
                label=f"{name} collision (mean {np.nanmean(collisions[name]):.3f})")
        ax2.bar(x + offset, timeouts[name], width, bottom=collisions[name],
                color=c_time, edgecolor="black", linewidth=0.4, hatch=hatches[i],
                label=f"{name} timeout (mean {np.nanmean(timeouts[name]):.3f})")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right")
    ax2.set_ylabel("failure rate")
    ax2.set_title("Failure-mode shift across the four policies "
                  "(collision = solid bottom, timeout = stacked top)")
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=7, ncol=4)
    ax2.grid(axis="y", linestyle=":", alpha=0.5)

    # 3) avg-velocity comparison
    ax3 = axes[2]
    for i, (name, _, c_succ, _, _) in enumerate(VERSIONS):
        offset = (i - (n - 1) / 2) * width
        ax3.bar(x + offset, avg_vels[name], width, color=c_succ,
                edgecolor="black", linewidth=0.4,
                label=f"{name} mean avg vel (m/s, mean {np.nanmean(avg_vels[name]):.2f})")
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels, rotation=25, ha="right")
    ax3.set_ylabel("mean avg velocity (m/s)")
    ax3.set_title("Successful-episode flight speed across the four policies")
    ax3.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax3.grid(axis="y", linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
