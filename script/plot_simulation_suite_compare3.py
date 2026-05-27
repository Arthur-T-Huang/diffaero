"""Compare v1 / v2 / v3 simulation suites side by side.

Reads results/simulation_suite/{simulation_suite,simulation_suite_v2,simulation_suite_v3}.csv
and writes results/simulation_suite/simulation_suite_compare3.png.
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
V1_CSV = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite.csv"
V2_CSV = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite_v2.csv"
V3_CSV = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite_v3.csv"
OUT_PATH = REPO_ROOT / "results" / "simulation_suite" / "simulation_suite_compare3.png"

C_V1 = "#7e57c2"   # purple
C_V2 = "#43a047"   # green
C_V3 = "#1976d2"   # blue
C_COLL_V1 = "#e53935"
C_COLL_V2 = "#c62828"
C_COLL_V3 = "#b71c1c"
C_TIME_V1 = "#fb8c00"
C_TIME_V2 = "#ef6c00"
C_TIME_V3 = "#e65100"


def load(p): return list(csv.DictReader(p.open()))
def col(rows, k):
    out = []
    for r in rows:
        v = r[k]
        out.append(None if v in ("", "None") else float(v))
    return out


def main():
    v1 = load(V1_CSV)
    v2 = {r["label"]: r for r in load(V2_CSV)}
    v3 = {r["label"]: r for r in load(V3_CSV)}
    v2 = [v2[r["label"]] for r in v1]
    v3 = [v3[r["label"]] for r in v1]

    labels = [r["label"].replace("sim", "").lstrip("0") + ": " + r["label"].split("_", 1)[1] for r in v1]

    s1 = np.array(col(v1, "success_rate"))
    s2 = np.array(col(v2, "success_rate"))
    s3 = np.array(col(v3, "success_rate"))
    c1 = np.array(col(v1, "collision_rate"))
    c2 = np.array(col(v2, "collision_rate"))
    c3 = np.array(col(v3, "collision_rate"))
    t1 = np.array(col(v1, "timeout_rate"))
    t2 = np.array(col(v2, "timeout_rate"))
    t3 = np.array(col(v3, "timeout_rate"))
    av1 = np.array(col(v1, "mean_avg_vel"))
    av2 = np.array(col(v2, "mean_avg_vel"))
    av3 = np.array(col(v3, "mean_avg_vel"))

    x = np.arange(len(v1))
    width = 0.27

    fig, axes = plt.subplots(3, 1, figsize=(14, 12),
                             gridspec_kw={"height_ratios": [3, 2, 2]})

    # 1) Success rate
    ax = axes[0]
    ax.bar(x - width, s1, width, color=C_V1, edgecolor="black", linewidth=0.4,
           label=f"v1 (mean {s1.mean():.3f})")
    ax.bar(x,        s2, width, color=C_V2, edgecolor="black", linewidth=0.4,
           label=f"v2 (mean {s2.mean():.3f})")
    ax.bar(x + width, s3, width, color=C_V3, edgecolor="black", linewidth=0.4,
           label=f"v3 (mean {s3.mean():.3f})")
    for i in range(len(x)):
        ax.text(i + width, s3[i] + 0.02, f"{s3[i]-s2[i]:+.2f}",
                ha="center", fontsize=8,
                color="#0d47a1" if s3[i] >= s2[i] else "#b71c1c")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("success rate")
    ax.set_title("v1 vs v2 vs v3: success rate per scenario (Δ above v3 bar = v3 - v2)")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # 2) Failure-mode shift: stacked (collision + timeout) per version
    ax2 = axes[1]
    ax2.bar(x - width, c1, width, color=C_COLL_V1, edgecolor="black", linewidth=0.4,
            label=f"v1 collision (mean {c1.mean():.3f})")
    ax2.bar(x - width, t1, width, bottom=c1, color=C_TIME_V1, edgecolor="black", linewidth=0.4,
            label=f"v1 timeout (mean {t1.mean():.3f})")
    ax2.bar(x,        c2, width, color=C_COLL_V2, edgecolor="black", linewidth=0.4, hatch="//",
            label=f"v2 collision (mean {c2.mean():.3f})")
    ax2.bar(x,        t2, width, bottom=c2, color=C_TIME_V2, edgecolor="black", linewidth=0.4, hatch="//",
            label=f"v2 timeout (mean {t2.mean():.3f})")
    ax2.bar(x + width, c3, width, color=C_COLL_V3, edgecolor="black", linewidth=0.4, hatch="..",
            label=f"v3 collision (mean {c3.mean():.3f})")
    ax2.bar(x + width, t3, width, bottom=c3, color=C_TIME_V3, edgecolor="black", linewidth=0.4, hatch="..",
            label=f"v3 timeout (mean {t3.mean():.3f})")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right")
    ax2.set_ylabel("failure rate")
    ax2.set_title("Failure-mode shift across the three policies (collision = solid bottom, timeout = stacked top)")
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=8, ncol=3)
    ax2.grid(axis="y", linestyle=":", alpha=0.5)

    # 3) avg-velocity comparison
    ax3 = axes[2]
    ax3.bar(x - width, av1, width, color=C_V1, edgecolor="black", linewidth=0.4,
            label=f"v1 mean avg vel (m/s, mean {np.nanmean(av1):.2f})")
    ax3.bar(x,        av2, width, color=C_V2, edgecolor="black", linewidth=0.4,
            label=f"v2 mean avg vel (m/s, mean {np.nanmean(av2):.2f})")
    ax3.bar(x + width, av3, width, color=C_V3, edgecolor="black", linewidth=0.4,
            label=f"v3 mean avg vel (m/s, mean {np.nanmean(av3):.2f})")
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels, rotation=25, ha="right")
    ax3.set_ylabel("mean avg velocity (m/s)")
    ax3.set_title("Successful-episode flight speed across the three policies")
    ax3.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax3.grid(axis="y", linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=160, bbox_inches="tight")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
