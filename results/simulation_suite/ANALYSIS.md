# DiffAero obstacle-avoidance policy — 20-scenario evaluation suite

Two policies were evaluated against an identical 20-scenario obstacle-avoidance
suite:

- **v1**: original SHA2C policy `pmc__oa__sha2c__rcnn`, checkpoint
  `outputs/train/2026-04-09/19-45-56/checkpoints` (3000 updates, training
  distribution: 30 obstacles, 3–6 m/s target velocity, `randpos_std` 6–7,
  baseline `oa_loss`).
- **v2**: retrained policy `outputs/train/2026-05-08/15-35-56/checkpoints`
  (3000 updates, training distribution widened to 50 obstacles, 0.5–10 m/s
  target velocity, `randpos_std` 3–7, with a new velocity-aware proximity loss
  `‖v‖ · dangerous_factor²` added to `oa_loss`).

Each scenario runs 64 parallel environments × 2000 simulation steps
(≈ 66 s of sim time per env) with the IMU and pose randomizers disabled and
`max_time` pinned to 30 s so v1 and v2 are directly comparable.

## Folder contents

| File | Description |
|---|---|
| `simulation_suite.csv` | v1 per-scenario dataset (20 rows) |
| `simulation_suite.json` | v1 dataset + run metadata + aggregate |
| `simulation_suite.png` | v1 outcome and trajectory plots |
| `simulation_suite_v2.csv` | v2 per-scenario dataset (20 rows) |
| `simulation_suite_v2.json` | v2 dataset + run metadata + aggregate |
| `simulation_suite_v2.png` | v2 outcome and trajectory plots |
| `simulation_suite_compare.png` | side-by-side v1 vs v2 comparison plots |
| `ANALYSIS.md` | this document |

Reproduce with:

```bash
# v1 evaluation
python3 script/run_simulation_suite.py n_envs=64 n_steps=2000 batch=all

# v2 evaluation against the retrained checkpoint
python3 script/run_simulation_suite.py n_envs=64 n_steps=2000 batch=all \
    checkpoint=outputs/train/2026-05-08/15-35-56/checkpoints out_suffix=_v2

# plots
python3 script/plot_simulation_suite.py            # v1
python3 script/plot_simulation_suite.py results/simulation_suite/simulation_suite_v2.csv  # v2
python3 script/plot_simulation_suite_compare.py    # v1 vs v2
```

---

## Part 1 — v1 baseline characterization

Headline numbers across the 20 scenarios (4 880 episodes total): success
**63.1 %**, collision **17.7 %**, timeout **19.2 %**. The mean masks a wide
spread (1.4 % – 94.6 %), and the spread is structured — different stress axes
fail in different ways.

### 1.1 Generalization, ranked by how badly it breaks

| Axis varied | In-distribution success | Worst-case success | Δ |
|---|---|---|---|
| Velocity (3–6 m/s in training) | 0.79 (sim11) | 0.014 (sim19, 0.5–1.5 m/s) / 0.27 (sim18, 7–10 m/s) | **−77 pp** |
| Obstacle density (30 obs in training) | 0.79 (sim11) | 0.35 (sim12, 80 obs) | −44 pp |
| Obstacle clustering (`randpos_std` 6–7 in training) | 0.79 (sim11) | 0.36 (sim20, std 3–4, 50 obs) | −43 pp |
| Arena scale (L=25 in training) | 0.79 (sim11) | 0.71 (sim16, L=40, 70 obs) | −9 pp |
| Shape composition (33 % spheres in training) | 0.75 (sim01) | 0.74 (sim04, 70 % spheres) | −1 pp |
| Seed (held everything else fixed) | 0.75 (sim01) vs 0.79 (sim11) | — | **±2–4 pp** |

The hierarchy is unambiguous: **velocity is the most fragile axis**, density
and clustering are the next two, and the policy is essentially indifferent to
obstacle shape and only mildly sensitive to arena size. Seed variance (~3 pp)
is small enough that the structural deltas are real and not noise.

### 1.2 Failure modes are anti-correlated with target velocity

| Scenario | target vel | collision | timeout | achieved avg vel |
|---|---|---|---|---|
| sim19 ultra_slow | 0.5–1.5 | 0.027 | **0.959** | 1.24 |
| sim08 slow_targets | 1.5–3 | 0.040 | **0.383** | 2.02 |
| sim01 baseline | 3–6 | 0.127 | 0.118 | 3.28 |
| sim09 fast_targets | 5–8 | **0.398** | 0.041 | 4.15 |
| sim18 ultra_fast | 7–10 | **0.720** | 0.012 | 5.04 |

Two things are happening:

1. **The drone never tracks the upper bound of its velocity command** —
   achieved velocity is ~50–55 % of the ceiling in every band. So at target
   0.5–1.5 m/s the drone *does* fly slowly (1.24 m/s), but a 25 m course at
   that speed exceeds the 30 s `max_time` budget once obstacle deviations are
   added → ~96 % timeout.
2. **At high target velocities the policy will not brake for obstacles.**
   Collisions scale almost linearly with target velocity (13 % → 40 % → 72 %).
   The trained loss balances target tracking against an exponential proximity
   term, but with a velocity ceiling in training of 6 m/s, the policy was
   never forced to learn an aggressive deceleration response. Pushed past
   that ceiling, it cuts straight through the obstacle field.

This is the most actionable finding: at training time the policy saw a
**single 3–6 m/s velocity band**. Outside that band the failure rates aren't
just elevated — they invert direction (collision-dominant above,
timeout-dominant below).

### 1.3 Density and clustering act on the same lever

Holding everything else at the training distribution and varying only
obstacle count:

| n_obs | success | collision | timeout |
|---|---|---|---|
|  5 | 0.946 | 0.022 | 0.031 |
| 10 | 0.907 | 0.023 | 0.070 |
| 30 | 0.79 (mean of sim01, sim11) | 0.13 | 0.10 |
| 60 | 0.537 | 0.249 | 0.215 |
| 80 | 0.345 | 0.288 | 0.367 |

Each ×2 in obstacle count costs roughly 15–20 percentage points of success,
and the failure mode shifts from "almost never fails" to "fails roughly
equally as collision and timeout" once density passes the trained
30-obstacle level.

The clustering scenarios (sim10 at `randpos_std`=4–5, sim20 at 3–4) reproduce
the same drop with the same failure-mode mix even at lower nominal counts —
i.e. **what the policy actually struggles with is local obstacle density
along its path, not absolute count**. sim20 (50 obstacles tightly clustered)
performs *worse* than sim03 (60 obstacles more spread out), consistent with
this.

### 1.4 Things the policy generalizes well over

- **Obstacle shape composition.** Pure cubes (sim15, 0 % spheres → 0.82) and
  pure spheres (sim14, 95 % → 0.79) are both within 4 pp of the training
  mix. This is unsurprising given the depth-camera observation feeds the
  policy a uniform geometric representation.
- **Arena scale at proportional density.** sim17 (L=10, 12 obs) → 0.72;
  sim07 (L=35, 50 obs) → 0.78. As long as obstacles-per-unit-volume stays
  close to training, the path length doesn't matter much — but average
  velocity drops in the tight arena (2.68 m/s vs 3.28 m/s baseline), so the
  policy is implicitly slowing in cramped space, just not enough.
- **Modest within-distribution seed variance** (~±2–4 pp on success rate).

### 1.5 Recommendations from the v1 analysis

1. **Widen the training velocity range** to ~0.5–10 m/s.
2. **Add a curriculum on obstacle density** (or train at higher density).
3. **Train on tighter clustering distributions** (lower `randpos_std_min`).
4. **Add a velocity-aware proximity loss** (e.g. `v · dangerous_factor²`) to
   force deceleration in cluttered space.
5. **Extend `max_time` or compute success differently for low-velocity
   scenarios** — sim19's 96 % "timeout" is partly a measurement artifact.

Recommendations 1–4 were implemented in the v2 retrain. Recommendation 5
was deliberately *not* applied so v1 and v2 stay directly comparable.

---

## Part 2 — v2 retrain and comparison

### 2.1 Changes applied

- `cfg/env/oa.yaml`:
  - `min_target_vel: 3.0 → 0.5`, `max_target_vel: 6.0 → 10.0`
  - `n_obstacles: 30 → 50`
  - `max_time: 30 → 45` s (training only; eval pinned to 30 s)
  - New `loss_weights.pointmass.speed_oa: 0.3`
- `cfg/env/obstacles/outdoor.yaml`:
  - `randpos_std_min: 6 → 3`
- `env/obstacle_avoidance.py`:
  - Added a velocity-aware proximity term
    `speed_proximity_loss = (‖v‖ · dangerous_factor²).max(over obstacles)`
    to the pointmass `total_loss`, weighted by `speed_oa`.
- `script/run_simulation_suite.py`:
  - Pinned eval `max_time = 30` so v1 and v2 are directly comparable.
  - Added `out_suffix` so v2 results land in `_v2`-suffixed files.

Training took ~73 minutes (3000 SHA2C updates, 1024 envs). Final rolling
success on the *training* distribution finished around 0.55 — lower than v1's
training-time number (~0.85) because the v2 training distribution is harder
(50 obstacles, 0.5–10 m/s, tighter clusters).

### 2.2 Aggregate v1 vs v2

| metric | v1 | v2 | Δ |
|---|---|---|---|
| success rate | 0.631 | 0.632 | +0.001 |
| collision rate | **0.177** | **0.047** | **−0.130 (−73 %)** |
| timeout rate | 0.192 | 0.321 | +0.129 |
| mean avg velocity (m/s) | 3.19 | 2.74 | −0.45 |
| mean arrive time (s) | 14.0 | 15.8 | +1.8 |
| mean episode length (s) | 15.6 | 17.4 | +1.7 |

Headline success is statistically unchanged, but the failure profile
inverted. **Where v1 crashed, v2 stalls.** The velocity-aware proximity loss
did exactly what it was designed to do — collisions dropped 3.7× — but its
weight (0.3) was tuned slightly too aggressively. The policy now
over-decelerates in dense scenes, converting collisions into timeouts at
roughly 1:1.

### 2.3 Where v2 won

| scenario | v1 | v2 | Δ |
|---|---|---|---|
| sim18 ultra_fast (7–10 m/s) | 0.27 | **0.55** | **+0.28** |
| sim09 fast_targets (5–8 m/s) | 0.56 | 0.69 | +0.13 |
| sim10 clustered | 0.51 | 0.57 | +0.06 |
| sim20 tight_cluster | 0.36 | 0.40 | +0.04 |
| sim02 sparse | 0.91 | 0.93 | +0.03 |
| sim16 wide_arena | 0.71 | 0.72 | +0.01 |

The biggest weakness identified in the v1 analysis — high-velocity OOD
collisions — is largely fixed: sim18 collision rate fell from 0.72 to 0.19,
and success doubled. The two clustered scenarios (sim10, sim20) also
improved because v2 saw `randpos_std=3–7` during training instead of 6–7.

### 2.4 Where v2 regressed

| scenario | v1 | v2 | Δ | failure-mode story |
|---|---|---|---|---|
| sim15 pure_cubes | 0.82 | 0.74 | −0.08 | collision 0.06→0.04 (good), timeout 0.12→0.22 |
| sim17 tight_arena | 0.72 | 0.65 | −0.07 | collision 0.06→0.03, timeout 0.21→0.31 |
| sim03 dense (60 obs) | 0.54 | 0.47 | −0.07 | collision 0.25→0.08 (huge), timeout 0.21→0.45 |
| sim05 cubes_heavy | 0.82 | 0.76 | −0.07 | collision 0.07→0.05, timeout 0.11→0.20 |
| sim08 slow_targets | 0.58 | 0.52 | −0.06 | collision 0.04→0.03, timeout 0.38→0.46 |
| sim07 long_dist | 0.78 | 0.73 | −0.05 | collision 0.09→0.02, timeout 0.13→0.25 |

In every regression, **collision rate dropped** but **timeout rate rose by a
larger margin**. The trade is most stark in `sim03_dense`: collision
0.25→0.085 (a 3× safety improvement) while timeouts went 0.21→0.45.

### 2.5 Recommendations that did not move the needle, and why

- **sim19 ultra_slow** (target 0.5–1.5 m/s): v1 = 1.4 % success, v2 = 0.7 %.
  Because eval `max_time` was pinned at 30 s for the fair A/B, the budget is
  still too tight at 1 m/s through 25 m of obstacles. Recommendation #5
  (decouple eval `max_time` from training, or score per-metre-travelled) is
  the only thing that would help here.
- **sim12 very_dense (80 obstacles)**: v1 = 0.35, v2 = 0.30. Training at a
  fixed 50 obstacles wasn't enough; a true curriculum on density (or per-env
  density randomization) is still missing.

### 2.6 Net assessment

The retrain delivered a **safer** policy (collision rate cut 73 %) at the
cost of average flight speed (~14 % slower). Headline success rate is
statistically unchanged, but the v2 model is a better behavioral foundation:

- It decelerates in clutter.
- It generalizes much further along the velocity axis (the worst OOD
  scenario went from 27 % to 55 % success).
- Its residual failures are dominated by timeouts rather than collisions,
  and timeouts are easier to fix downstream than collisions.

### 2.7 Next iteration

1. **Lower `speed_oa` from 0.3 to ~0.1.** Tame the over-deceleration so
   dense-scenario timeouts come back down without re-introducing collisions.
2. **Decouple eval `max_time` from training, or score per metre travelled.**
   This is mostly a benchmarking change — it would unblock fair evaluation
   of low-velocity scenarios.
3. **Per-env randomized `n_obstacles`** (true density curriculum) rather than
   a fixed bump from 30 to 50, so the policy sees the full density range.
4. **Loss-weight ablation on `oa_loss` vs `speed_oa`** to find the
   collision-vs-timeout Pareto frontier instead of guessing a single weight.

### Caveats

- Both runs use a single training seed; no estimate of inter-seed training
  variance.
- The base randomizer and IMU noise are disabled in evaluation to keep
  variance low across scenarios, so absolute numbers are slightly optimistic
  relative to the training-time tensorboard.
- 64 parallel envs × 2000 steps yields 145–650 episodes per scenario; the
  resulting standard error on success rate is ~2 pp, well below the
  structural deltas discussed above.
