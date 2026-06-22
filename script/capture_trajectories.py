"""Capture full xyz position trajectories for a small set of evaluation
scenarios, for plotting and video rendering.

Each capture stores env 0's position trajectory (one full episode), the
scenario's obstacle layout (env 0), the drone start, the target, and the
final episode outcome (success / collision / timeout).

Usage:
    python3 script/capture_trajectories.py \
        checkpoint=/path/to/ckpt out_suffix=_v3 [n_steps=2000]

Output: results/simulation_suite/trajectories{out_suffix}.pkl
"""

import pickle
import random
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch
from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT.parent))

from script.run_simulation_suite import BATCHES, apply_overrides, find_latest_checkpoint

SIMS_TO_CAPTURE = ["sim01_baseline", "sim03_dense", "sim17_tight_arena"]


def capture(base_cfg, sim, ckpt_path, device, n_envs: int, n_steps: int) -> Dict:
    from diffaero.env import build_env
    from diffaero.algo import build_agent

    seed = sim["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)

    cfg = apply_overrides(base_cfg, sim, n_envs)
    env = build_env(cfg.env, device=device)
    agent = build_agent(cfg.algo, env, device)
    agent.agent.actor.load(str(ckpt_path))

    # capture env 0's obstacle layout immediately after reset
    obs = env.reset()
    om = env.obstacle_manager
    obstacles = {
        "p_spheres":  om.p_obstacles[0, :om.n_spheres].detach().cpu().numpy().copy(),
        "r_spheres":  om.r_obstacles[0, :om.n_spheres].detach().cpu().numpy().copy(),
        "p_cubes":    om.p_obstacles[0, om.n_spheres:om.n_spheres+om.n_cubes].detach().cpu().numpy().copy(),
        "lwh_cubes":  om.lwh_cubes[0].detach().cpu().numpy().copy(),
        "rpy_cubes":  om.rpy_cubes[0].detach().cpu().numpy().copy(),
        "init":       env.init_pos[0].detach().cpu().numpy().copy(),
        "target":     env.target_pos[0].detach().cpu().numpy().copy(),
        "L":          env.L.value[0].item() if hasattr(env.L, "value") else float(env.L),
    }

    positions = []  # list of [3] per step
    outcome = "ongoing"
    end_step = n_steps

    with torch.no_grad():
        for step in range(n_steps):
            # capture pre-step position (i.e. the position the policy reacted to this step)
            positions.append(env._p[0].detach().cpu().numpy().copy())

            action, _ = agent.act(obs, test=True)
            if cfg.algo.name not in ("yopo", "yopot"):
                action = env.rescale_action(action)
            obs, _, terminated, info = env.step(action)
            if cfg.algo.name != "world" and hasattr(agent, "reset"):
                agent.reset(info["reset"])

            if info["reset"][0].item():
                if info["success"][0].item():
                    outcome = "success"
                elif terminated[0].item():
                    outcome = "collision"
                elif info["truncated"][0].item():
                    outcome = "timeout"
                end_step = step + 1
                break

    if env.renderer is not None:
        env.renderer.close()

    positions = np.stack(positions, axis=0)  # [T, 3]
    return {
        "positions": positions,
        "end_step":  end_step,
        "outcome":   outcome,
        "dt":        float(cfg.env.dt),
        "obstacles": obstacles,
        "vel_band":  (float(sim["min_vel"]), float(sim["max_vel"])),
    }


def main():
    cli = OmegaConf.from_cli(sys.argv[1:])
    n_steps = int(cli.get("n_steps", 2000))
    n_envs = int(cli.get("n_envs", 4))  # only env 0 is captured, but >1 helps GPU batching
    out_suffix = str(cli.get("out_suffix", ""))
    ckpt_arg = cli.get("checkpoint", None)

    if ckpt_arg is None:
        ckpt_path = find_latest_checkpoint()
    else:
        ckpt_path = Path(str(ckpt_arg))
        if not ckpt_path.is_absolute():
            ckpt_path = (REPO_ROOT / ckpt_path).resolve()
    cfg_path = ckpt_path.parent / ".hydra" / "config.yaml"
    base_cfg = OmegaConf.load(cfg_path)
    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")

    print(f"[traj] checkpoint = {ckpt_path}")
    print(f"[traj] device     = {device}")
    print(f"[traj] sims       = {SIMS_TO_CAPTURE}")

    out_dir = REPO_ROOT / "results" / "simulation_suite"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"trajectories{out_suffix}.pkl"

    by_label = {s["label"]: s for s in BATCHES["all"]}
    all_traj: Dict[str, Dict] = {}
    for label in SIMS_TO_CAPTURE:
        sim = by_label[label]
        print(f"\n[traj] {label}: vel=[{sim['min_vel']},{sim['max_vel']}], n_obs={sim['n_obstacles']}, L={sim['length']}")
        data = capture(base_cfg, sim, ckpt_path, device, n_envs, n_steps)
        T = data["positions"].shape[0]
        print(f"[traj]   {T} steps  outcome={data['outcome']}")
        all_traj[label] = data

    with out_path.open("wb") as f:
        pickle.dump(all_traj, f)
    print(f"\n[traj] wrote {out_path}")


if __name__ == "__main__":
    main()
