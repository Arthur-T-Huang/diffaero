"""Cleaner per-scenario velocity-vs-time plot: instead of overlaying ~30
individual episode traces per panel, show the median trace per outcome
(success / collision / timeout) with a shaded interquartile band.

Reads results/simulation_suite/velocity_traces{,_v2,_v3}.pkl and writes
velocity_traces_clean{,_v2,_v3}.png alongside.
"""

import pickle
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PKL = REPO_ROOT / "results" / "simulation_suite" / "velocity_traces.pkl"

OUTCOME_COLOR = {
    "success":   "#2e7d32",
    "collision": "#c62828",
    "timeout":   "#ef6c00",
}
MIN_SAMPLES_FOR_LINE = 3  # don't draw a time-step that only has 1-2 episodes


def pad_to_matrix(traces):
    """Stack variable-length 1-D traces into (T_max, N) with NaN padding."""
    if not traces:
        return np.zeros((0, 0))
    T = max(len(t) for t in traces)
    mat = np.full((T, len(traces)), np.nan, dtype=np.float32)
    for j, t in enumerate(traces):
        mat[:len(t), j] = t
    return mat


def main():
    pkl_arg = sys.argv[1] if len(sys.argv) > 1 else None
    pkl_path = Path(pkl_arg) if pkl_arg else DEFAULT_PKL
    if not pkl_path.is_absolute():
        pkl_path = (REPO_ROOT / pkl_path).resolve()
    suffix = pkl_path.stem.replace("velocity_traces", "")  # "" or "_v2" / "_v3"
    out_path = pkl_path.parent / f"velocity_traces_clean{suffix}.png"

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

        # background: commanded target-velocity band
        ax.axhspan(vmin, vmax, color="#90caf9", alpha=0.18,
                   label="target vel band")

        counts = {o: 0 for o in OUTCOME_COLOR}
        for outcome, color in OUTCOME_COLOR.items():
            traces = [t for t, o in zip(data["traces"], data["outcomes"]) if o == outcome]
            counts[outcome] = len(traces)
            if not traces:
                continue
            mat = pad_to_matrix(traces)
            n_per_step = np.sum(~np.isnan(mat), axis=1)
            valid = n_per_step >= MIN_SAMPLES_FOR_LINE
            if not valid.any():
                continue
            q25 = np.nanpercentile(mat, 25, axis=1)
            q50 = np.nanpercentile(mat, 50, axis=1)
            q75 = np.nanpercentile(mat, 75, axis=1)
            t = np.arange(mat.shape[0]) * dt
            t_v = t[valid]
            ax.fill_between(t_v, q25[valid], q75[valid], color=color, alpha=0.18, linewidth=0)
            ax.plot(t_v, q50[valid], color=color, linewidth=1.6,
                    label=f"{outcome} (n={counts[outcome]})")

        title = f"{label}   S={counts['success']}  C={counts['collision']}  T={counts['timeout']}"
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("episode time (s)", fontsize=8)
        ax.set_ylabel("|v| (m/s)", fontsize=8)
        ax.grid(linestyle=":", alpha=0.4)
        ax.set_xlim(0, 30)
        ax.tick_params(axis="both", labelsize=8)

    for ax in axes[n:]:
        ax.set_visible(False)

    legend_handles = [
        plt.Line2D([0], [0], color=OUTCOME_COLOR["success"],   linewidth=2.5, label="success: median ± IQR"),
        plt.Line2D([0], [0], color=OUTCOME_COLOR["collision"], linewidth=2.5, label="collision (terminal): median ± IQR"),
        plt.Line2D([0], [0], color=OUTCOME_COLOR["timeout"],   linewidth=2.5, label="timeout: median ± IQR"),
        plt.Rectangle((0, 0), 1, 1, color="#90caf9", alpha=0.45, label="commanded target-vel band"),
    ]
    fig.legend(handles=legend_handles, loc="upper center", ncol=4,
               fontsize=11, framealpha=0.9, bbox_to_anchor=(0.5, 1.005))

    pretty = pkl_path.stem.replace("velocity_traces", "policy").replace("_", " ").strip() or "policy v1"
    fig.suptitle(
        f"Drone velocity vs. episode time — {pretty}\n"
        f"(median over surviving episodes; shaded = 25th–75th percentile; "
        f"S/C/T counts = total episodes observed in the 2000-step capture window)",
        fontsize=12, y=1.025)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
