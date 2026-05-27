"""Compare v1 (original checkpoint) and v2 (retrained with widened velocity,
density, clustering, and speed-aware proximity loss) simulation suites.

Reads results/simulation_suite/{simulation_suite.csv,simulation_suite_v2.csv}
and writes results/simulation_suite/simulation_suite_compare.png.
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
V1_CSV = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite.csv"
V2_CSV = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite_v2.csv"
OUT_PATH = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite_compare.png"


def load(path: Path):
    with path.open() as f:
        return list(csv.DictReader(f))


def col(rows, k, cast=float):
    out = []
    for r in rows:
        v = r[k]
        out.append(None if v in ("", "None") else cast(v))
    return out


def main():
    v1 = load(V1_CSV)
    v2 = load(V2_CSV)
    # align by label
    by_label = {r["label"]: r for r in v2}
    v2_aligned = [by_label[r["label"]] for r in v1]

    labels = [r["label"].replace("sim", "").lstrip("0") + ": " + r["label"].split("_", 1)[1] for r in v1]

    s1 = np.array(col(v1, "success_rate"))
    c1 = np.array(col(v1, "collision_rate"))
    t1 = np.array(col(v1, "timeout_rate"))
    s2 = np.array(col(v2_aligned, "success_rate"))
    c2 = np.array(col(v2_aligned, "collision_rate"))
    t2 = np.array(col(v2_aligned, "timeout_rate"))
    av1 = np.array(col(v1, "mean_avg_vel"))
    av2 = np.array(col(v2_aligned, "mean_avg_vel"))

    x = np.arange(len(v1))

    fig, axes = plt.subplots(3, 1, figsize=(13, 11),
                             gridspec_kw={"height_ratios": [3, 2, 2]})

    # 1) Success rate, side-by-side
    ax = axes[0]
    width = 0.4
    bars_v1 = ax.bar(x - width / 2, s1, width, color="#7e57c2",
                     label=f"v1 (mean {s1.mean():.3f})", edgecolor="black", linewidth=0.4)
    bars_v2 = ax.bar(x + width / 2, s2, width, color="#43a047",
                     label=f"v2 (mean {s2.mean():.3f})", edgecolor="black", linewidth=0.4)
    delta = s2 - s1
    for i, (b1, b2, d) in enumerate(zip(bars_v1, bars_v2, delta)):
        sign = "+" if d >= 0 else ""
        col_ = "#1b5e20" if d >= 0 else "#b71c1c"
        ax.text(i, max(s1[i], s2[i]) + 0.02, f"{sign}{d:.2f}", ha="center", fontsize=8.5, color=col_)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("success rate")
    ax.set_title("v1 vs v2: per-scenario success rate (Δ above bars)")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # 2) Collision-vs-timeout shift
    ax2 = axes[1]
    ax2.bar(x - width / 2, c1, width, color="#e53935", edgecolor="black", linewidth=0.4,
            label=f"v1 collision (mean {c1.mean():.3f})")
    ax2.bar(x - width / 2, t1, width, bottom=c1, color="#fb8c00", edgecolor="black", linewidth=0.4,
            label=f"v1 timeout (mean {t1.mean():.3f})")
    ax2.bar(x + width / 2, c2, width, color="#c62828", edgecolor="black", linewidth=0.4,
            hatch="//", label=f"v2 collision (mean {c2.mean():.3f})")
    ax2.bar(x + width / 2, t2, width, bottom=c2, color="#ef6c00", edgecolor="black", linewidth=0.4,
            hatch="//", label=f"v2 timeout (mean {t2.mean():.3f})")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right")
    ax2.set_ylabel("failure rate")
    ax2.set_title("Failure-mode shift (left bar v1, hatched right bar v2)")
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=8, ncol=2)
    ax2.grid(axis="y", linestyle=":", alpha=0.5)

    # 3) avg-velocity comparison
    ax3 = axes[2]
    ax3.bar(x - width / 2, av1, width, color="#1976d2", edgecolor="black", linewidth=0.4,
            label=f"v1 mean avg vel (m/s, mean {np.nanmean(av1):.2f})")
    ax3.bar(x + width / 2, av2, width, color="#388e3c", edgecolor="black", linewidth=0.4,
            label=f"v2 mean avg vel (m/s, mean {np.nanmean(av2):.2f})")
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels, rotation=25, ha="right")
    ax3.set_ylabel("mean avg velocity (m/s)")
    ax3.set_title("Successful-episode flight speed (lower v2 = more cautious policy)")
    ax3.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax3.grid(axis="y", linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
