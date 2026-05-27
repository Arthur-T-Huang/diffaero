"""Run a suite of 10 obstacle-avoidance simulations against the latest trained
checkpoint, varying obstacle counts, obstacle layouts, start positions and
destination positions, and aggregate per-simulation outcomes into a CSV
dataset.

Usage:
    python script/run_simulation_suite.py \
        [checkpoint=/path/to/ckpt] [n_envs=64] [n_steps=2000]

If `checkpoint` is omitted, the most recent train run under outputs/train/ is
used. If a relative path is given, it is resolved against the repo root.
"""

import csv
import json
import random
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch
from omegaconf import DictConfig, OmegaConf

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT.parent))


def find_latest_checkpoint() -> Path:
    train_root = REPO_ROOT / "outputs" / "train"
    days = sorted([p for p in train_root.iterdir() if p.is_dir()])
    if not days:
        raise FileNotFoundError(f"No training runs found under {train_root}")
    for day in reversed(days):
        runs = sorted([p for p in day.iterdir() if p.is_dir()])
        for run in reversed(runs):
            ckpt = run / "checkpoints"
            if ckpt.exists() and (ckpt / "actor.pth").exists():
                return ckpt
    raise FileNotFoundError("No checkpoints/actor.pth under outputs/train/")


BATCH_1: List[Dict] = [
    # baseline matches the training distribution
    {"label": "sim01_baseline",        "seed":  1, "n_obstacles": 30, "sphere_pct": 0.33,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # sparse obstacle field
    {"label": "sim02_sparse",          "seed":  2, "n_obstacles": 10, "sphere_pct": 0.33,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # dense obstacle field
    {"label": "sim03_dense",           "seed":  3, "n_obstacles": 60, "sphere_pct": 0.33,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # mostly spherical obstacles
    {"label": "sim04_spheres_heavy",   "seed":  4, "n_obstacles": 30, "sphere_pct": 0.70,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # mostly cuboid obstacles
    {"label": "sim05_cubes_heavy",     "seed":  5, "n_obstacles": 30, "sphere_pct": 0.10,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # small env -> short start-to-target distance
    {"label": "sim06_short_dist",      "seed":  6, "n_obstacles": 20, "sphere_pct": 0.33,
     "length": 15, "min_vel": 3.0, "max_vel": 6.0, "randpos": (4, 5)},
    # large env -> long start-to-target distance
    {"label": "sim07_long_dist",       "seed":  7, "n_obstacles": 50, "sphere_pct": 0.33,
     "length": 35, "min_vel": 3.0, "max_vel": 6.0, "randpos": (8, 9)},
    # low target velocity profile
    {"label": "sim08_slow_targets",    "seed":  8, "n_obstacles": 30, "sphere_pct": 0.33,
     "length": 25, "min_vel": 1.5, "max_vel": 3.0, "randpos": (6, 7)},
    # high target velocity profile
    {"label": "sim09_fast_targets",    "seed":  9, "n_obstacles": 30, "sphere_pct": 0.33,
     "length": 25, "min_vel": 5.0, "max_vel": 8.0, "randpos": (6, 7)},
    # clustered obstacles (small randpos std) with mixed shape
    {"label": "sim10_clustered",       "seed": 10, "n_obstacles": 40, "sphere_pct": 0.50,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (4, 5)},
]

BATCH_2: List[Dict] = [
    # baseline reseeded — variance check vs sim01
    {"label": "sim11_baseline_reseed", "seed": 21, "n_obstacles": 30, "sphere_pct": 0.33,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # extreme density
    {"label": "sim12_very_dense",      "seed": 22, "n_obstacles": 80, "sphere_pct": 0.33,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # extreme sparsity
    {"label": "sim13_very_sparse",     "seed": 23, "n_obstacles":  5, "sphere_pct": 0.33,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # almost pure spheres (close-to-100%)
    {"label": "sim14_pure_spheres",    "seed": 24, "n_obstacles": 30, "sphere_pct": 0.95,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # almost pure cubes (0% spheres)
    {"label": "sim15_pure_cubes",      "seed": 25, "n_obstacles": 30, "sphere_pct": 0.0,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (6, 7)},
    # extra-wide arena, longer travel distance, larger randpos spread
    {"label": "sim16_wide_arena",      "seed": 26, "n_obstacles": 70, "sphere_pct": 0.33,
     "length": 40, "min_vel": 3.0, "max_vel": 6.0, "randpos": (10, 11)},
    # very tight arena
    {"label": "sim17_tight_arena",     "seed": 27, "n_obstacles": 12, "sphere_pct": 0.33,
     "length": 10, "min_vel": 3.0, "max_vel": 5.0, "randpos": (3, 4)},
    # ultra-fast target velocities (above training max)
    {"label": "sim18_ultra_fast",      "seed": 28, "n_obstacles": 30, "sphere_pct": 0.33,
     "length": 25, "min_vel": 7.0, "max_vel": 10.0, "randpos": (6, 7)},
    # very slow target velocities (well below training)
    {"label": "sim19_ultra_slow",      "seed": 29, "n_obstacles": 30, "sphere_pct": 0.33,
     "length": 25, "min_vel": 0.5, "max_vel": 1.5, "randpos": (6, 7)},
    # tightly clustered obstacles, mixed shapes, dense
    {"label": "sim20_tight_cluster",   "seed": 30, "n_obstacles": 50, "sphere_pct": 0.5,
     "length": 25, "min_vel": 3.0, "max_vel": 6.0, "randpos": (3, 4)},
]

BATCHES = {"1": BATCH_1, "2": BATCH_2, "all": BATCH_1 + BATCH_2}


def apply_overrides(cfg: DictConfig, sim: Dict, n_envs: int) -> DictConfig:
    """Return a fresh DictConfig copy with the per-simulation overrides applied."""
    cfg = OmegaConf.create(OmegaConf.to_container(cfg, resolve=True))
    cfg.n_envs = n_envs
    cfg.env.n_envs = n_envs
    cfg.dynamics.n_envs = n_envs
    cfg.sensor.n_envs = n_envs
    # after resolve(), env.dynamics / env.sensor are independent copies — sync them
    cfg.env.dynamics.n_envs = n_envs
    cfg.env.sensor.n_envs = n_envs

    cfg.env.n_obstacles = sim["n_obstacles"]
    cfg.env.obstacles.n_obstacles = sim["n_obstacles"]
    cfg.env.obstacles.sphere_percentage = sim["sphere_pct"]
    cfg.env.obstacles.randpos_std_min = sim["randpos"][0]
    cfg.env.obstacles.randpos_std_max = sim["randpos"][1]

    L = sim["length"]
    cfg.env.length.default = L
    cfg.env.length.min = L
    cfg.env.length.max = L

    cfg.env.min_target_vel = sim["min_vel"]
    cfg.env.max_target_vel = sim["max_vel"]

    # pin eval-time max_time to 30s regardless of training config, so the v1 and
    # v2 sim datasets stay directly comparable.
    cfg.env.max_time = 30

    # disable the ad-hoc randomizer + IMU drift so eval is reproducible across sims
    cfg.env.randomizer.enabled = False
    cfg.env.imu.enable_drift = False
    cfg.env.imu.enable_noise = False

    # rendering off, no video
    cfg.env.render.headless = True
    cfg.env.render.record_video = False
    cfg.env.render.n_envs = n_envs
    return cfg


def run_single_simulation(
    base_cfg: DictConfig,
    sim: Dict,
    ckpt_path: Path,
    device: torch.device,
    n_envs: int,
    n_steps: int,
) -> Dict:
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
    # only the actor is needed for inference. The critic's input dim depends on
    # n_obstacles, so loading it would fail when sims vary obstacle counts.
    agent.agent.actor.load(str(ckpt_path))

    n_episodes = 0
    n_success = 0
    n_collision = 0
    n_truncated = 0
    arrive_times: List[float] = []
    avg_vels: List[float] = []
    episode_lengths: List[float] = []

    obs = env.reset()
    with torch.no_grad():
        for step in range(n_steps):
            action, _ = agent.act(obs, test=True)
            if cfg.algo.name not in ("yopo", "yopot"):
                action = env.rescale_action(action)
            obs, _losses, terminated, info = env.step(action)
            if cfg.algo.name != "world" and hasattr(agent, "reset"):
                agent.reset(info["reset"])

            reset = info["reset"]
            if reset.any():
                reset_idx = reset.nonzero().flatten()
                success_mask = info["success"][reset_idx]
                term_mask = terminated[reset_idx]
                trunc_mask = info["truncated"][reset_idx]

                n_resets = reset_idx.numel()
                n_episodes += n_resets
                n_success += int(success_mask.sum().item())
                n_collision += int(term_mask.sum().item())
                # truncated-but-not-success = timeout / out-of-bound
                n_truncated += int((trunc_mask & ~success_mask).sum().item())

                if success_mask.any():
                    succ_idx = reset_idx[success_mask]
                    arrive_times.extend(info["arrive_time"][succ_idx].cpu().tolist())
                    # avg_vel computed at every step inside _step; pull from stats_raw
                    if "avg_vel" in info.get("stats_raw", {}):
                        v = info["stats_raw"]["avg_vel"]
                        if v.numel() > 0:
                            avg_vels.extend(v.cpu().tolist())
                episode_lengths.extend(info["l"][reset_idx].cpu().float().mul(env.dt).tolist())

    # tear down
    if env.renderer is not None:
        env.renderer.close()

    success_rate = n_success / n_episodes if n_episodes else 0.0
    collision_rate = n_collision / n_episodes if n_episodes else 0.0
    timeout_rate = n_truncated / n_episodes if n_episodes else 0.0

    return {
        "label": sim["label"],
        "seed": seed,
        "n_obstacles": sim["n_obstacles"],
        "sphere_pct": sim["sphere_pct"],
        "env_length": sim["length"],
        "min_target_vel": sim["min_vel"],
        "max_target_vel": sim["max_vel"],
        "randpos_std_min": sim["randpos"][0],
        "randpos_std_max": sim["randpos"][1],
        "n_envs": n_envs,
        "n_steps": n_steps,
        "n_episodes": n_episodes,
        "n_success": n_success,
        "n_collision": n_collision,
        "n_timeout": n_truncated,
        "success_rate": round(success_rate, 4),
        "collision_rate": round(collision_rate, 4),
        "timeout_rate": round(timeout_rate, 4),
        "mean_arrive_time": round(float(np.mean(arrive_times)), 3) if arrive_times else None,
        "mean_avg_vel": round(float(np.mean(avg_vels)), 3) if avg_vels else None,
        "mean_episode_length_s": round(float(np.mean(episode_lengths)), 3) if episode_lengths else None,
    }


def main():
    # tiny CLI: key=value overrides
    cli = OmegaConf.from_cli(sys.argv[1:])
    n_envs = int(cli.get("n_envs", 64))
    n_steps = int(cli.get("n_steps", 2000))
    ckpt_arg = cli.get("checkpoint", None)
    batch_key = str(cli.get("batch", "1"))
    append = bool(cli.get("append", False))
    out_suffix = str(cli.get("out_suffix", ""))
    if batch_key not in BATCHES:
        raise ValueError(f"Unknown batch '{batch_key}'. Choose from {sorted(BATCHES)}.")
    sim_configs = BATCHES[batch_key]

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
    print(f"[suite] checkpoint = {ckpt_path}")
    print(f"[suite] training config = {cfg_path}")
    print(f"[suite] batch = {batch_key} (append={append})")
    print(f"[suite] n_envs={n_envs}, n_steps={n_steps}, n_simulations={len(sim_configs)}")

    device_idx = base_cfg.get("device", 0)
    device = torch.device(f"cuda:{device_idx}") if torch.cuda.is_available() else torch.device("cpu")
    print(f"[suite] device = {device}")

    out_dir = REPO_ROOT / "results" / "simulation_suite"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"simulation_suite{out_suffix}.csv"
    json_path = out_dir / f"simulation_suite{out_suffix}.json"

    rows: List[Dict] = []
    for i, sim in enumerate(sim_configs, start=1):
        print(f"\n[suite] ({i}/{len(sim_configs)}) running {sim['label']}: "
              f"n_obstacles={sim['n_obstacles']}, sphere_pct={sim['sphere_pct']}, "
              f"length={sim['length']}, vel=[{sim['min_vel']},{sim['max_vel']}], "
              f"randpos={sim['randpos']}, seed={sim['seed']}")
        row = run_single_simulation(base_cfg, sim, ckpt_path, device, n_envs, n_steps)
        rows.append(row)
        print(f"[suite]   -> episodes={row['n_episodes']}, success_rate={row['success_rate']}, "
              f"collision_rate={row['collision_rate']}, timeout_rate={row['timeout_rate']}")

    # CSV (append-aware)
    fieldnames = list(rows[0].keys())

    def _coerce(r: Dict) -> Dict:
        out = dict(r)
        for k in ("seed", "n_obstacles", "n_envs", "n_steps",
                  "n_episodes", "n_success", "n_collision", "n_timeout"):
            if k in out and out[k] is not None and not isinstance(out[k], (int, float)):
                out[k] = int(out[k])
        for k in ("sphere_pct", "env_length", "min_target_vel", "max_target_vel",
                  "randpos_std_min", "randpos_std_max",
                  "success_rate", "collision_rate", "timeout_rate",
                  "mean_arrive_time", "mean_avg_vel", "mean_episode_length_s"):
            if k in out and out[k] not in (None, "", "None"):
                out[k] = float(out[k])
            elif out.get(k) in ("", "None"):
                out[k] = None
        return out

    if append and csv_path.exists():
        existing_rows: List[Dict] = []
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            for r in reader:
                existing_rows.append(_coerce(r))
        existing_labels = {r["label"] for r in existing_rows}
        new_rows = [r for r in rows if r["label"] not in existing_labels]
        skipped = [r["label"] for r in rows if r["label"] in existing_labels]
        if skipped:
            print(f"[suite] skipping rows whose label already exists in CSV: {skipped}")
        with csv_path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            for r in new_rows:
                writer.writerow(r)
        rows_for_json = existing_rows + new_rows
    else:
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        rows_for_json = rows
    rows = rows_for_json

    # JSON (with metadata)
    payload = {
        "checkpoint": str(ckpt_path),
        "training_config": str(cfg_path),
        "n_envs": n_envs,
        "n_steps_per_sim": n_steps,
        "device": str(device),
        "simulations": rows,
        "aggregate": {
            "mean_success_rate": round(float(np.mean([r["success_rate"] for r in rows])), 4),
            "mean_collision_rate": round(float(np.mean([r["collision_rate"] for r in rows])), 4),
            "mean_timeout_rate": round(float(np.mean([r["timeout_rate"] for r in rows])), 4),
            "total_episodes": int(sum(r["n_episodes"] for r in rows)),
            "total_success": int(sum(r["n_success"] for r in rows)),
            "total_collision": int(sum(r["n_collision"] for r in rows)),
            "total_timeout": int(sum(r["n_timeout"] for r in rows)),
        },
    }
    with json_path.open("w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[suite] wrote {csv_path}")
    print(f"[suite] wrote {json_path}")
    print(f"[suite] mean success_rate across all 10 sims = {payload['aggregate']['mean_success_rate']}")


if __name__ == "__main__":
    main()
