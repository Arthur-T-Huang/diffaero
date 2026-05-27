"""Capture per-step drone velocity magnitude across each of the 20 evaluation
scenarios for a given checkpoint, slice into episodes, label outcomes
(success / collision / timeout), and pickle the result for plotting.

Usage:
    python3 script/run_velocity_traces.py \
        [checkpoint=/path/to/ckpt] [n_envs=64] [n_steps=2000] [out_suffix=]

Outputs results/simulation_suite/velocity_traces{out_suffix}.pkl, structured as
    {
      scenario_label: {
        "traces":    [np.ndarray(L_i,) for each episode],
        "outcomes":  ["success"|"collision"|"timeout"|... for each episode],
        "dt":        float (simulator timestep, seconds),
        "vel_band":  (min_target_vel, max_target_vel) for the scenario,
      },
      ...
    }
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

from script.run_simulation_suite import (
    BATCHES,
    apply_overrides,
    find_latest_checkpoint,
)


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
    # only the actor is needed for inference; critic depends on n_obstacles
    agent.agent.actor.load(str(ckpt_path))

    vel_buf = np.empty((n_steps, n_envs), dtype=np.float32)
    ep_start = np.zeros(n_envs, dtype=np.int64)
    records: List[Dict] = []

    obs = env.reset()
    with torch.no_grad():
        for step in range(n_steps):
            # capture velocity entering this step (i.e. pre-action state)
            vel_buf[step] = env._v.norm(dim=-1).detach().cpu().numpy()

            action, _ = agent.act(obs, test=True)
            if cfg.algo.name not in ("yopo", "yopot"):
                action = env.rescale_action(action)
            obs, _, terminated, info = env.step(action)
            if cfg.algo.name != "world" and hasattr(agent, "reset"):
                agent.reset(info["reset"])

            reset = info["reset"]
            if reset.any():
                reset_idx_t = reset.nonzero().flatten().cpu().numpy()
                success_arr = info["success"].cpu().numpy()
                term_arr = terminated.cpu().numpy()
                trunc_arr = info["truncated"].cpu().numpy()
                for env_i in reset_idx_t:
                    if success_arr[env_i]:
                        outcome = "success"
                    elif term_arr[env_i]:
                        outcome = "collision"
                    elif trunc_arr[env_i]:
                        outcome = "timeout"
                    else:
                        outcome = "other"
                    records.append({
                        "env_idx": int(env_i),
                        "start": int(ep_start[env_i]),
                        "end": int(step + 1),  # vel_buf[start:end] is the trace
                        "outcome": outcome,
                    })
                    ep_start[env_i] = step + 1

    if env.renderer is not None:
        env.renderer.close()

    traces = []
    outcomes = []
    for r in records:
        seg = vel_buf[r["start"]:r["end"], r["env_idx"]]
        if seg.shape[0] < 3:
            continue
        traces.append(seg.copy())
        outcomes.append(r["outcome"])
    return {
        "traces": traces,
        "outcomes": outcomes,
        "dt": float(cfg.env.dt),
        "vel_band": (float(sim["min_vel"]), float(sim["max_vel"])),
    }


def main():
    cli = OmegaConf.from_cli(sys.argv[1:])
    n_envs = int(cli.get("n_envs", 64))
    n_steps = int(cli.get("n_steps", 2000))
    out_suffix = str(cli.get("out_suffix", ""))
    ckpt_arg = cli.get("checkpoint", None)

    if ckpt_arg is None:
        ckpt_path = find_latest_checkpoint()
    else:
        ckpt_path = Path(str(ckpt_arg))
        if not ckpt_path.is_absolute():
            ckpt_path = (REPO_ROOT / ckpt_path).resolve()

    cfg_path = ckpt_path.parent / ".hydra" / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Could not find training config at {cfg_path}")
    base_cfg = OmegaConf.load(cfg_path)

    device_idx = base_cfg.get("device", 0)
    device = torch.device(f"cuda:{device_idx}") if torch.cuda.is_available() else torch.device("cpu")

    print(f"[traces] checkpoint = {ckpt_path}")
    print(f"[traces] device = {device}")
    print(f"[traces] n_envs={n_envs}, n_steps={n_steps}, n_simulations=20")

    out_dir = REPO_ROOT / "results" / "simulation_suite"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"velocity_traces{out_suffix}.pkl"

    all_traces = {}
    for i, sim in enumerate(BATCHES["all"], start=1):
        print(f"\n[traces] ({i}/20) {sim['label']}: vel=[{sim['min_vel']},{sim['max_vel']}], "
              f"n_obs={sim['n_obstacles']}, L={sim['length']}, seed={sim['seed']}")
        data = capture(base_cfg, sim, ckpt_path, device, n_envs, n_steps)
        all_traces[sim["label"]] = data
        counts = {o: data["outcomes"].count(o) for o in ("success", "collision", "timeout", "other")}
        print(f"[traces]   captured {len(data['traces'])} episodes  {counts}")

    with out_path.open("wb") as f:
        pickle.dump(all_traces, f)
    print(f"\n[traces] wrote {out_path}")


if __name__ == "__main__":
    main()
