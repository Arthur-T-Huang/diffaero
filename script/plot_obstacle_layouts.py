"""Render top-down (xy) obstacle layouts for each of the 20 simulation-suite
scenarios. For each scenario we rebuild env 0 using the same seed the
evaluation suite uses, read the obstacle positions/sizes/orientations and the
drone start / target positions out of the freshly-reset environment, and
render them in a 5x4 grid.

This script does NOT load any policy checkpoint or run any inference — it only
exercises the env's reset path to materialize one obstacle layout per
scenario. Runs fine on CPU.

Output: results/simulation_suite/obstacle_layouts.png
"""

import random
import sys
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import torch
from matplotlib.transforms import Affine2D
from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT.parent))

from script.run_simulation_suite import BATCHES, apply_overrides, find_latest_checkpoint


def build_layout(base_cfg, sim, device):
    """Build env 0 of `sim` and read out its obstacle layout."""
    from diffaero.env import build_env

    seed = sim["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)

    cfg = apply_overrides(base_cfg, sim, n_envs=1)
    env = build_env(cfg.env, device=device)
    env.reset()

    om = env.obstacle_manager
    n_spheres = om.n_spheres
    n_cubes = om.n_cubes

    p_obs = om.p_obstacles[0].detach().cpu().numpy()
    r_obs = om.r_obstacles[0].detach().cpu().numpy()
    lwh = om.lwh_cubes[0].detach().cpu().numpy()
    rpy = om.rpy_cubes[0].detach().cpu().numpy()

    init = env.init_pos[0].detach().cpu().numpy()
    target = env.target_pos[0].detach().cpu().numpy()
    L_val = env.L.value[0].item() if hasattr(env.L, "value") else float(env.L)

    safety_range = float(getattr(om, "safety_range", 1.7))

    if env.renderer is not None:
        env.renderer.close()

    return {
        "p_spheres":  p_obs[:n_spheres],
        "r_spheres":  r_obs[:n_spheres],
        "p_cubes":    p_obs[n_spheres:n_spheres + n_cubes],
        "lwh_cubes":  lwh,
        "rpy_cubes":  rpy,
        "init":       init,
        "target":     target,
        "L":          L_val,
        "safety":     safety_range,
    }


def plot_panel(ax, sim, data):
    L = data["L"]
    ax.set_xlim(-L - 1, L + 1)
    ax.set_ylim(-L - 1, L + 1)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(linestyle=":", alpha=0.4)

    # arena boundary
    boundary = mpatches.Rectangle((-L, -L), 2 * L, 2 * L, fill=False,
                                  edgecolor="#999", linewidth=0.8, linestyle="--")
    ax.add_patch(boundary)

    # safety circles around start and target (where no obstacle should spawn)
    for p, c in ((data["init"], "#43a047"), (data["target"], "#e53935")):
        ring = mpatches.Circle((p[0], p[1]), data["safety"], fill=False,
                               edgecolor=c, linewidth=0.7, alpha=0.5, linestyle=":")
        ax.add_patch(ring)

    # spheres
    for p, r in zip(data["p_spheres"], data["r_spheres"]):
        c = mpatches.Circle((p[0], p[1]), r, facecolor="#5c6bc0", alpha=0.55,
                            edgecolor="black", linewidth=0.4)
        ax.add_patch(c)

    # cubes — top-down xy footprint, rotated by yaw
    for p, lwh, rpy in zip(data["p_cubes"], data["lwh_cubes"], data["rpy_cubes"]):
        l, w, _ = lwh
        yaw = float(rpy[2])
        rect = mpatches.Rectangle((-l / 2, -w / 2), l, w,
                                  facecolor="#8d6e63", alpha=0.65,
                                  edgecolor="black", linewidth=0.4)
        rect.set_transform(Affine2D().rotate(yaw).translate(p[0], p[1]) + ax.transData)
        ax.add_patch(rect)

    # start/target markers + connecting line
    ax.plot([data["init"][0], data["target"][0]],
            [data["init"][1], data["target"][1]],
            "--", color="#1976d2", alpha=0.7, linewidth=1.0, zorder=3)
    ax.plot(data["init"][0],   data["init"][1],   "o", color="#43a047",
            markersize=9, markeredgecolor="black", zorder=4)
    ax.plot(data["target"][0], data["target"][1], "*", color="#e53935",
            markersize=14, markeredgecolor="black", zorder=4)

    dist = float(np.linalg.norm(data["init"][:2] - data["target"][:2]))
    n_sph = len(data["p_spheres"])
    n_cub = len(data["p_cubes"])
    title = (f"{sim['label']}\n"
             f"L={int(sim['length'])}  obs={n_sph}sph+{n_cub}cub  "
             f"vel=[{sim['min_vel']},{sim['max_vel']}]\n"
             f"start↔target={dist:.1f}m  randpos_std={sim['randpos']}")
    ax.set_title(title, fontsize=8)
    ax.set_xlabel("x (m)", fontsize=7)
    ax.set_ylabel("y (m)", fontsize=7)
    ax.tick_params(axis="both", labelsize=7)


def main():
    # Use the v1 training config as a base — apply_overrides will overwrite all
    # scenario-specific keys, so v1 vs v2 vs v3 base would be equivalent.
    candidates = [
        REPO_ROOT / "outputs" / "train" / "2026-04-09" / "19-45-56" / ".hydra" / "config.yaml",
    ]
    cfg_path = next((p for p in candidates if p.exists()), None)
    if cfg_path is None:
        ckpt = find_latest_checkpoint()
        cfg_path = ckpt.parent / ".hydra" / "config.yaml"
    base_cfg = OmegaConf.load(cfg_path)

    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
    print(f"[layouts] base cfg = {cfg_path}")
    print(f"[layouts] device   = {device}")

    sim_configs = BATCHES["all"]
    fig, axes = plt.subplots(5, 4, figsize=(18, 22), sharex=False, sharey=False)
    axes = axes.flatten()

    for ax, sim in zip(axes, sim_configs):
        print(f"  {sim['label']}")
        data = build_layout(base_cfg, sim, device)
        plot_panel(ax, sim, data)

    legend_handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#43a047",
                   markersize=10, markeredgecolor="black", label="drone start"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#e53935",
                   markersize=14, markeredgecolor="black", label="target"),
        plt.Line2D([0], [0], color="#1976d2", linestyle="--", linewidth=1.4,
                   label="straight-line start→target"),
        mpatches.Patch(facecolor="#5c6bc0", alpha=0.55, edgecolor="black",
                       label="sphere obstacle"),
        mpatches.Patch(facecolor="#8d6e63", alpha=0.65, edgecolor="black",
                       label="cube obstacle (xy footprint)"),
        mpatches.Patch(facecolor="white", edgecolor="#43a047", linestyle=":",
                       label="start/target safety radius (1.7 m, no spawn)"),
    ]
    fig.legend(handles=legend_handles, loc="upper center", ncol=6,
               fontsize=10, framealpha=0.9, bbox_to_anchor=(0.5, 1.005))

    fig.suptitle(
        "Obstacle layouts for each of the 20 evaluation scenarios "
        "(env 0, top-down xy view; reset with the suite's scenario seed)",
        fontsize=13, y=1.012)
    fig.tight_layout()

    out_path = REPO_ROOT / "results" / "simulation_suite" / "obstacle_layouts.png"
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    print(f"\n[layouts] wrote {out_path}")


if __name__ == "__main__":
    main()
