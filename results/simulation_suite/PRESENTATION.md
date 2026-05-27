# Presentation script

**Title:** Empirically evaluating DiffAero's SHA2C obstacle-avoidance policy
**Length:** ~13 minutes (≈1 min per slide)
**Companion files:** `ANALYSIS.md`, `simulation_suite.{csv,json,png}`,
`simulation_suite_v2.{csv,json,png}`, `simulation_suite_compare.png`
**Paper:** Zhang et al., *DiffAero: A GPU-Accelerated Differentiable Simulation
Framework for Efficient Quadrotor Policy Learning* (arXiv 2509.10247)

---

## Slide 1 — Title

> **Empirical evaluation of DiffAero's SHA2C obstacle-avoidance policy:
> what the paper claims, what we measured, and where they diverge.**

**Speaker notes (≈45 s).** "DiffAero is a recently released GPU-accelerated
differentiable quadrotor simulator. The authors recommend SHA2C as their
best-performing algorithm for obstacle avoidance. We took their official
released code and trained the recommended SHA2C policy with the recommended
point-mass dynamics and depth-camera sensor. We then ran a 20-scenario stress
test on the trained policy, used the findings to motivate a targeted retrain,
and re-evaluated. This talk walks through what was found, and how those
findings relate to the paper's claims."

---

## Slide 2 — Frame the comparison up front (do this before anything else)

> **What the paper provides as a quantitative obstacle-avoidance baseline:
> nothing.**

- Figure 7 in the paper: reward learning curves over training updates.
  **Reward, not success rate.**
- The only numerical performance claim in the paper is **"100 % success on
  the position-control task"** — a different and easier task.
- The paper's claim about obstacle avoidance is qualitative:
  *"SHA2C achieved the best success rate and stability among the algorithms
  we tested."*

**Speaker notes (≈60 s).** "I want to set expectations before showing any
numbers. When I say 'consistent with the paper,' I mean **procedurally
consistent** — same simulator, same algorithm, same loss formulation, same
sensor modality. I do **not** mean numerically consistent, because the paper
publishes no quantitative obstacle-avoidance success rate to compare against.
Everything quantitative in this evaluation is a contribution that puts a
number on a claim the paper only made qualitatively. There is nothing here
that contradicts the paper, but there are also no published numbers to
contradict."

---

## Slide 3 — Where we are procedurally consistent with the paper

| Dimension | Paper says | We implemented | Consistent? |
|---|---|---|---|
| Obstacle dynamics | "Randomly placed around the path" (static) | Static within episode, re-randomized at reset | yes (verified in code) |
| Velocity input to policy | "Proprioceptive + goal-related vectors" | 3-D goal-velocity vector in local frame + body z-axis + current velocity | yes (qualitative match) |
| Sensor | Depth camera supported | 9×16 depth, 5 m max range, 86° FOV | yes |
| Dynamics | Continuous point-mass supported | `pmc`, RK4, max acc 20/40 m/s² | yes |
| Algorithm | "SHA2C achieved the best success rate" | SHA2C with the released configuration | yes |
| Training horizon | "Hours" | v1: 68 min; v2: 73 min (3 000 updates × 1 024 envs) | yes |
| Throughput | "GPU-accelerated, orders of magnitude faster" | 22 000–24 000 sim FPS at train time | yes |
| Loss components | `oa`, `pos`, `jerk`, `vel`, `collision` | Identical list and default weights | yes |

**Speaker notes (≈75 s).** "Procedurally, everything checks out. The simulator
is being driven the way the paper describes, with the algorithm, dynamics,
sensor, and reward shaping that the paper recommends. Two of these were worth
explicitly verifying in the code. First, are the obstacles really static? Yes
— the `randomize_obstacles` call is only ever made inside `reset_idx`, never
inside the per-step `step` function. Once an episode begins, every obstacle
is stationary. Second, what does the policy actually receive as its velocity
input? It receives a 3-D vector pointing from the drone to the target,
clipped in magnitude to a per-environment `max_vel` that is sampled uniformly
between `min_target_vel` and `max_target_vel` at every reset. The vector is
rotated into the drone's local frame before being fed to the network. So the
policy never sees a scalar 'desired speed' — it sees a desired direction
times a desired magnitude."

---

## Slide 4 — What this evaluation adds beyond the paper

1. **20 parameterized stress scenarios** — varying obstacle count, shape mix,
   arena size, clustering, and target velocity.
2. **A failure-mode decomposition** — every episode is labeled success /
   collision / timeout, not just rewarded or not.
3. **A sensitivity ranking** across five stress axes.
4. **A targeted retrain experiment (v2)** guided by the v1 findings.
5. **A reproducible dataset + plots + scripts** — all in
   `results/simulation_suite/` and `script/run_simulation_suite*.py`.

**Speaker notes (≈30 s).** "The paper gives you learning curves. This
evaluation gives you numbers, failure modes, and sensitivity analysis. Think
of it as putting numbers under the paper's qualitative claims."

---

## Slide 5 — Finding 1: at the training distribution, the policy works

| Scenario | n_obs | sphere fraction | velocity band | success |
|---|---|---|---|---|
| sim01 (baseline)              | 30 | 0.33 | 3–6 m/s | **0.754** |
| sim11 (baseline, reseed)      | 30 | 0.33 | 3–6 m/s | **0.793** |

**Implied within-distribution success rate: ≈ 0.77, with ~3-percentage-point
seed variance.**

**Speaker notes (≈45 s).** "These two scenarios are the closest analog to the
released training distribution: 30 obstacles, 3-to-6 m/s target velocity, 25-
metre arena, default clustering. The two runs use different random seeds.
Success rate lands at roughly 77 %, with seed-to-seed variance of about 3
percentage points. This is consistent with the paper's qualitative claim
that SHA2C learns a working policy on this task. It is not a number the
paper publishes, so we are pinning one down for the first time — not
contradicting an existing one."

---

## Slide 6 — Finding 2: velocity is the most fragile axis (not in paper)

| target velocity | success | collision | timeout |
|---|---|---|---|
| 0.5 – 1.5 m/s (OOD low) | 0.014 | 0.027 | **0.959** |
| 1.5 – 3 m/s             | 0.577 | 0.040 | 0.383 |
| 3 – 6 m/s (training)    | 0.754 | 0.127 | 0.118 |
| 5 – 8 m/s               | 0.561 | **0.398** | 0.041 |
| 7 – 10 m/s (OOD high)   | 0.268 | **0.720** | 0.012 |

**Failure modes invert across the velocity axis: too fast → collision;
too slow → timeout.**

**Speaker notes (≈75 s).** "This is the most actionable single finding in
the evaluation. The policy was trained on a narrow 3-to-6 m/s velocity band.
Push it outside that band and the failure modes invert direction. Above the
band, the drone won't decelerate for obstacles — collision rate scales
almost linearly with target velocity, hitting 72 % at 7-10 m/s. Below the
band, the drone moves at the slow commanded speed but takes too long to
reach the goal — 96 % timeout at 0.5-1.5 m/s. The paper does not study this
axis because it trains and evaluates within a single velocity band, so this
behavior never surfaces in their figures. It is not a discrepancy with the
paper — it is something the paper's evaluation cannot probe. And it has
practical consequences: in deployment, the policy will mishandle either
commanded cruise speed unless you stay inside the training band."

---

## Slide 7 — Finding 3: density and clustering act on the same lever

| n_obstacles | success | collision | timeout |
|---|---|---|---|
|  5 | **0.946** | 0.022 | 0.031 |
| 10 | 0.907 | 0.023 | 0.070 |
| 30 (training) | 0.79 (mean) | 0.13 | 0.10 |
| 60 | 0.537 | 0.249 | 0.215 |
| 80 | 0.345 | 0.288 | 0.367 |

- Smooth, near-linear degradation. ×2 obstacles ≈ −15 to −20 pp success.
- Tight clustering (`randpos_std = 3–4`) at 50 obstacles is *worse* than
  uniform spread at 60 obstacles → **what matters is local density along
  the path, not raw count.**

**Speaker notes (≈45 s).** "Density degrades success smoothly. Doubling the
obstacle count costs roughly 15 to 20 percentage points of success. The
clustering experiments add a finer point: the policy struggles with local
crowding around the corridor it needs to fly, not with absolute obstacle
count. A tight cluster of 50 obstacles is harder than a uniformly-spread
field of 60. The paper trains at a single density and clustering setting, so
this response curve is new."

---

## Slide 8 — Finding 4: shape composition is essentially irrelevant

| sphere fraction | success |
|---|---|
| 0 %  (all cubes)        | 0.820 |
| 10 %                     | 0.821 |
| 33 % (training mix)      | 0.754 |
| 70 %                     | 0.738 |
| 95 %                     | 0.789 |

**Speaker notes (≈30 s).** "Pure cubes and pure spheres both perform within
~6 pp of the training mix. This is qualitatively consistent with what the
paper implies — depth-camera observations should generalize across obstacle
geometry — but the paper does not isolate this axis. We do."

---

## Slide 9 — Finding 5: the v2 retrain (applying our own recommendations)

**Changes made to the released configuration:**

- Training velocity range widened: **3–6 → 0.5–10 m/s**
- Training obstacle count bumped: **30 → 50**
- Clustering tightened: `randpos_std_min` **6 → 3**
- New velocity-aware proximity loss term: **`‖v‖ · dangerous_factor²`,
  weight 0.3**
- Training `max_time`: **30 → 45 s** (eval pinned at 30 s for fair A/B)

| Aggregate metric | v1 | v2 | Δ |
|---|---|---|---|
| Mean success rate           | 0.631 | 0.632 | +0.001 |
| **Mean collision rate**     | **0.177** | **0.047** | **−73 %** |
| Mean timeout rate           | 0.192 | 0.321 | +67 % |
| Mean avg velocity (m/s)     | 3.19  | 2.74  | −14 % |

**Speaker notes (≈90 s).** "We applied four of the five recommendations from
the v1 analysis as a single retrain. Headline success is essentially
unchanged — 63.1 % to 63.2 %. But look at the rest of the row: collision
rate dropped 73 %, timeout rate rose 67 %, and average flight velocity
dropped 14 %. The failure profile inverted. The velocity-aware loss did
exactly what it was designed to do: force the policy to decelerate near
obstacles. We probably tuned its weight too aggressively at 0.3; the policy
now over-decelerates in dense scenes, converting collisions into timeouts at
roughly a one-to-one rate. This is a *behavioral* improvement even though
the headline number didn't move, because timeouts are easier to fix
downstream than collisions."

---

## Slide 10 — The single biggest win from the retrain

**Scenario 18 — target velocity 7–10 m/s (well above the v1 training band)**

| metric | v1 | v2 |
|---|---|---|
| success rate | 0.27 | **0.55** |
| collision rate | 0.72 | 0.19 |
| timeout rate | 0.01 | 0.26 |

**Speaker notes (≈30 s).** "The biggest single weakness identified in v1 —
high-velocity OOD collisions — is largely solved. Success roughly doubled,
collision rate dropped 73 %. The retrained policy now generalizes much
further along the velocity axis."

---

## Slide 11 — Where the comparison to the paper hits its limits

What we **cannot** claim:

1. **We cannot say "v1 matches the paper's number"** — the paper has no
   obstacle-avoidance success-rate number to match.
2. **We cannot validate "SHA2C is the best algorithm"** — we only trained
   SHA2C. Confirming the paper's algorithmic ranking would require training
   PPO, MAPPO, BPTT, SHAC, and DreamerV3 under matched conditions.
3. **We have a single training seed per run.** Within-distribution seed
   variance of ~3 pp was observed at *evaluation* time; training-side
   variance was not measured.
4. **Our evaluation protocol** (64 envs × 2 000 steps, `max_time = 30 s`,
   IMU noise and randomizer disabled, success = arrived-and-held-5 s) is
   ours; the paper does not describe its evaluation protocol in detail.

**Speaker notes (≈60 s).** "Be honest about scope. We are filling a
quantitative gap the paper left empty, not reproducing or contradicting
numbers the paper published. Anyone who wants to make a stronger claim about
'consistency with the paper' would need to train all six algorithms the
paper benchmarks and compare ranks across them. That's what would actually
validate the paper's qualitative SHA2C-is-best claim."

---

## Slide 12 — Summary

**What the paper said about SHA2C on obstacle avoidance:**

> *"SHA2C achieved the best success rate and stability."*

**What 4 880 v1 evaluation episodes let us add:**

- At the training distribution: **0.75–0.79 success.**
- **Five degradation axes ranked**: velocity (worst), density / clustering
  (tied for second), arena scale (minor), shape composition (irrelevant).
- **Failure-mode decomposition**: collisions and timeouts dominate in
  opposite directions of the velocity axis.

**What another 4 880 v2 episodes let us add:**

- **Targeted training changes can cut collisions 3.7×** without losing
  headline success.
- **The collision-vs-timeout trade-off is real and tunable** via the
  velocity-aware proximity loss weight.

All reproducible at `results/simulation_suite/` (datasets, plots,
`ANALYSIS.md`) and `script/run_simulation_suite*.py` (scripts).

**Speaker notes (≈30 s).** "The bottom line is that nothing we measured
contradicts the paper. What we did is quantify what the paper claimed
qualitatively, and then run an actual experiment showing how to push the
policy further. The contribution here is making the obstacle-avoidance
benchmark *measurable*, not validating a number that was never published."

---

## Slide 13 — Recommended next steps

1. **Replicate the paper's full algorithm benchmark** (PPO, MAPPO, BPTT,
   SHAC, SHA2C, DreamerV3) using this same 20-scenario suite. This is what
   would actually validate the paper's qualitative SHA2C ranking.
2. **Tune the v2 `speed_oa` weight** (0.3 → ~0.1) to reduce the
   over-deceleration that converted collisions into timeouts.
3. **Per-env randomized obstacle count** — a true density curriculum rather
   than the fixed 30-to-50 bump used in v2.
4. **Multiple training seeds** for a real estimate of training-side
   variance — only evaluation-side seed variance was measured here.

**Speaker notes (≈30 s).** "Each next step would close one of the
limitations on the previous slide. Item 1 in particular would convert
'consistent with the paper's qualitative claim' into 'consistent with the
paper's quantitative claim.'"

---

## Appendix — Connecting paper claims to evaluation findings (at-a-glance)

| Paper claim | Evaluation finding | Match? |
|---|---|---|
| Static obstacles "randomly placed around the path" | Static, verified by code path inspection (`randomize_obstacles` only called in `reset_idx`) | exact match |
| Goal-vector velocity observation | 3-D `target_vel` in local frame, magnitude clipped to per-env `max_vel` | qualitative match |
| Depth camera as sensor modality | 9×16 depth, 5 m range, 86° FOV | exact match |
| Hours-long training | 68 min v1; 73 min v2 | exact match |
| GPU-accelerated, orders-of-magnitude FPS gain | 22 k–24 k sim FPS measured at train time | qualitative match |
| "SHA2C achieved the best success rate" (qualitative, vs other algos) | We trained only SHA2C; 0.77 in-distribution success measured | cannot validate |
| Numerical obstacle-avoidance success rate | (none published) | cannot compare |
| 100 % success on position control | (we did not evaluate position control) | n/a |
