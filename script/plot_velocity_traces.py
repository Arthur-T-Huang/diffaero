"""Plot per-episode velocity time-series for each of the 20 evaluation
scenarios, grouped by outcome (success / collision / timeout).

Reads results/simulation_suite/velocity_traces{,_v2}.pkl and writes
velocity_traces{,_v2}.png alongside.
"""

import pickle
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PKL = REPO_ROOT / "results" / "simulation_suite" / "velocity_traces.pkl"

OUTCOME_COLOR = {
    "success":   "#43a047",
    "collision": "#e53935",
    "timeout":   "#fb8c00",
}
PER_OUTCOME_SAMPLE = 10  # cap traces per outcome per scenario to keep plots readable


def main():
    pkl_arg = sys.argv[1] if len(sys.argv) > 1 else None
    pkl_path = Path(pkl_arg) if pkl_arg else DEFAULT_PKL
    if not pkl_path.is_absolute():
        pkl_path = (REPO_ROOT / pkl_path).resolve()
    out_path = pkl_path.with_suffix(".png")

    with pkl_path.open("rb") as f:
        all_traces = pickle.load(f)

    labels = list(all_traces.keys())
    n = len(labels)
    cols = 4
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(20, 3.2 * rows),
                             sharex=False, sharey=False)
    axes = axes.flatten()

    for ax, label in zip(axes, labels):
        data = all_traces[label]
        dt = data["dt"]
        vmin, vmax = data["vel_band"]

        # background shading: target-velocity band (the "desired speed" the
        # policy was commanded to track on this scenario)
        ax.axhspan(vmin, vmax, color="#90caf9", alpha=0.15,
                   label="target vel band")

        plotted = {o: 0 for o in OUTCOME_COLOR}
        for trace, outcome in zip(data["traces"], data["outcomes"]):
            if outcome not in OUTCOME_COLOR:
                continue
            if plotted[outcome] >= PER_OUTCOME_SAMPLE:
                continue
            t = np.arange(len(trace)) * dt
            ax.plot(t, trace, color=OUTCOME_COLOR[outcome],
                    alpha=0.45, linewidth=1.0)
            plotted[outcome] += 1

        counts = {o: data["outcomes"].count(o) for o in OUTCOME_COLOR}
        sub = f"S={counts['success']}  C={counts['collision']}  T={counts['timeout']}"
        ax.set_title(f"{label}\n{sub}", fontsize=9)
        ax.set_xlabel("episode time (s)", fontsize=8)
        ax.set_ylabel("|v| (m/s)", fontsize=8)
        ax.grid(linestyle=":", alpha=0.4)
        ax.set_xlim(0, 30)
        ax.tick_params(axis="both", labelsize=8)

    for ax in axes[n:]:
        ax.set_visible(False)

    handles = [
        plt.Line2D([0], [0], color=OUTCOME_COLOR["success"],   linewidth=2, label="success"),
        plt.Line2D([0], [0], color=OUTCOME_COLOR["collision"], linewidth=2, label="collision (terminal)"),
        plt.Line2D([0], [0], color=OUTCOME_COLOR["timeout"],   linewidth=2, label="timeout"),
        plt.Rectangle((0, 0), 1, 1, color="#90caf9", alpha=0.4, label="target-velocity band"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=4, fontsize=11,
               framealpha=0.9, bbox_to_anchor=(0.5, 1.005))

    fig.suptitle(
        f"Drone velocity vs. episode time — {pkl_path.stem}\n"
        f"(up to {PER_OUTCOME_SAMPLE} episodes per outcome per scenario; "
        f"S/C/T counts = total episodes observed in the 2000-step capture window)",
        fontsize=12, y=1.025)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
