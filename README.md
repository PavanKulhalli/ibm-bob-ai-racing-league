# TORCS Autonomous Racing — IBM Challenge

## Project Description

This project develops an autonomous racing controller for the **TORCS** (The Open Racing Car Simulator) using the Snakeoil SCR Python client. The controller is a hand-engineered `drive_example()` function that reads real-time sensor data — track distance sensors, speed, position, angle, wheel spin — and outputs steering, throttle, brake, and gear commands at 50 Hz to complete the **Corkscrew circuit** cleanly and as fast as possible. The problem being solved is iterative control-loop optimisation under hard constraints: zero damage and a completed lap, with every experiment changing exactly one variable at a time, measuring the result, and feeding it back into the next iteration — a disciplined scientific method applied to embedded real-time control without any machine learning.

---

## Current Status

| Metric | Value |
|--------|-------|
| **Best lap time** | **01:54:60** (exp-39, run 1) |
| **Confirmed baseline** | **01:54:66** (exp-39, run 4 — 4 consecutive clean laps) |
| **Lap time range** | 01:54:60 – 01:55:72 across 4 runs (mean ~01:54:90) |
| **Damage** | **0** on all 4 runs |
| **Top speed** | **206 km/h** |
| **Track** | Corkscrew (TORCS built-in) |
| **Experiments completed** | 39 |
| **Telemetry rows logged** | ~915k rows (12 runs) · **3.9 MB** (`lap_data.csv.gz`) |

---

## Repository Structure

```
gym_torcs/
│
├── snakeoil3_gym.py          # Original reference — NEVER modified
├── snakeoil3_v1.py           # Safe baseline (currently exp-39, promoted after clean lap)
├── snakeoil3_v2.py           # Working copy — all experiments run here
│
├── CHANGELOG.md              # Full experiment log: change / result / kept?
├── lap_data.csv.gz           # Per-step telemetry (~50 Hz, 11 best runs, gzip-compressed)
├── lap_summary.csv           # Per-lap summary (time, damage, max speed)
│
├── find_corners.py           # Offline telemetry analysis tool
├── autostart.sh              # TORCS GUI automation (handles race reset)
├── practice.xml              # TORCS race configuration
│
├── gym_torcs.py              # OpenAI-Gym-compatible wrapper (original)
├── example_experiment.py     # RL agent example
├── sample_agent.py           # Sample RL agent
│
└── reports/                  # Per-experiment analysis reports
```

### File roles

| File | Role |
|------|------|
| `snakeoil3_gym.py` | Unmodified upstream reference. Never touched. |
| `snakeoil3_v1.py` | Promoted baseline — the last experiment confirmed clean. Run this to verify the baseline hasn't regressed. |
| `snakeoil3_v2.py` | Active working copy. Change ONE thing, update `EXP_TAG`, run, record in `CHANGELOG.md`. |
| `CHANGELOG.md` | The scientific notebook — every experiment has a hypothesis, change, prediction, and measured result. |
| `lap_data.csv.gz` | Gzip-compressed, ~50 Hz telemetry: `distFromStart`, `speedX`, `trackPos`, `angle`, `steer`, `accel`, `brake`, `gear`, `forward_track`, `min_valid_track`, `damage` per step. Read with `gzip.open('lap_data.csv.gz', 'rt')`. |
| `lap_summary.csv` | One row per lap: lap time, damage, max speed, experiment tag, SHA-256 of the code that produced it. |

---

## Architecture — How the Controller Works

The controller runs a **single `drive_example()` function** called at every simulator tick (~50 Hz). There is no neural network, no learned policy, and no external state beyond the sensor values delivered each tick.

### Sensor inputs used

| Sensor | What it measures |
|--------|-----------------|
| `track[0..18]` | Distance to road boundary at 19 angles from −45° to +45° |
| `speedX` | Forward speed (km/h) |
| `trackPos` | Lateral position (−1 = left edge, 0 = centre, +1 = right edge, >±1 = off-road) |
| `angle` | Car heading relative to track direction (radians) |
| `wheelSpinVel[0..3]` | Wheel angular velocity (traction control) |
| `distFromStart` | Distance from lap start (metres) — used for zone detection |

### Control outputs

`steer` (−1 to +1), `accel` (0 to 1), `brake` (0 to 1), `gear` (1–7), `clutch`, `meta`

### Control logic (exp-39 baseline)

```
1. Forward clearance
   ahead = max(track[6:15], 0)          # wide ±4° cone

2. Steering
   steer  = angle × 5/π                 # yaw correction
   steer -= trackPos × 0.40             # centre-pull
   steer -= trackPos × 0.15             # extra pull in Corkscrew run-in (dist 2290–2450 m)

3. Lookahead speed target
   safe_kmh     = √(2 × 16 × ahead) × 3.6
   target_speed = clip(safe_kmh × 0.89, 10, 250)

4. Zone-specific hard caps (three corners where wide-cone over-reads clearance)
   Zone A  dist 2305–2450 m : cap 40 km/h   (Corkscrew apex)
   Zone C  dist 2450–2510 m : cap 55 km/h   (Corkscrew exit chicane)
   Zone B  dist 3200–3340 m : cap 60 km/h   (back-section hairpin)

5. Throttle / brake
   if speed ≤ target    → throttle (full when >10% below target, proportional in final band)
   elif inside zone cap → active brake ∝ (speed − target) / 35
   elif speed ≤ safe    → coast
   else                 → brake ∝ (speed − safe) / 35

6. Traction control
   if rear_spin − front_spin > 5 → accel −= 0.2

7. Automatic gearbox (7-gear car1-ow1)
   2nd >30 / 3rd >55 / 4th >80 / 5th >110 / 6th >150 / 7th >175 km/h

8. Wall-escape recovery  (fires only when genuinely off-road: trackPos > ±1.0)
   gear = −1, accel = 0.5, steer = clip(−trackPos × 0.5, −0.7, 0.7)

9. Post-recovery yaw realignment  (fires when back on-road but still yawed >0.3 rad)
   crawl forward at accel = 0.3 and steer toward zero angle
   if rolling backward first: brake to stop, then crawl
   if no forward clearance: reverse until track[9] > 3 m
```

---

## Experiment Workflow

```
1. Run snakeoil3_v1.py       → confirm baseline still produces a clean lap
2. In snakeoil3_v2.py        → make ONE change in drive_example()
                             → update EXP_TAG  (e.g. "exp-40-margin090")
3. python3 snakeoil3_v2.py   → telemetry auto-writes to lap_data.csv / lap_summary.csv
4. Record in CHANGELOG.md    → hypothesis / change / prediction / result / kept?
5a. If clean                 → copy drive_example + main loop to snakeoil3_v1.py
5b. If crash / DNF           → revert drive_example to v1 baseline, reset EXP_TAG
```

**Rule:** one variable changed per experiment. Compound changes (multiple variables at once) are forbidden unless individual variables have already been validated separately.

---

## Experiment History — Key Milestones

| Exp | Change | Lap time | Damage | Verdict |
|-----|--------|----------|--------|---------|
| v0 | Unmodified baseline | DNF | — | Crashes every lap — no brakes |
| exp-4 | Lookahead braking formula `v=√(2ad)` | 2:19:52 | 0 | ✅ First clean lap |
| exp-9 | `decel_g=15`, margin 9% | 2:01:99 | 0 | ✅ Sub-2:02 clean |
| exp-15 | Off-track threshold + steer direction fixed | 2:21:24 | 0 | ✅ Recovery logic working |
| exp-20 | Off-track guard raised to `trackPos > 1.0` | 2:25:58 | 0 | ✅ False-recovery eliminated |
| exp-21 | Zone A cap 40 km/h (Corkscrew) | 2:05:54 | 0 | ✅ Corkscrew solved |
| exp-28 | Recovery steer arc capped ±0.7 | 2:21:62 | 0 | ✅ No more spin in recovery |
| exp-29 | Yaw-gate backward-roll brake | 2:04:70 | 0 | ✅ Recovery 24s → 5 steps |
| exp-30 | Speed guard on yaw-recovery (`<15 km/h`) | **1:55:24** | 0 | ✅ **Sub-1:56** |
| exp-33 | Active braking in cap zones + correct zone sizes | 1:57:99 | 0 | ✅ Cap zones braking correctly |
| exp-35 | `trackPos` steer gain 0.25 → 0.40 | DNF | 2 | ❌ Zone A exit spin |
| exp-37 | Zone C cap 55 km/h (exit chicane) | DNF (max_steps) | 0 | ✅ All zones survive — loop bug found |
| **exp-39** | **Restore all caps + fix shutdown loop** | **1:54:60** | **0** | ✅ **New best — confirmed ×2** |

Full history with root-cause analysis for every DNF is in [`CHANGELOG.md`](CHANGELOG.md).

---

## Telemetry System

`snakeoil3_v2.py` includes a production-grade `Recorder` class that runs automatically on every execution. It produces two append-only CSV files:

### `lap_data.csv.gz` — per-step (~50 Hz), gzip-compressed

| Column | Description |
|--------|-------------|
| `run_id` | UTC timestamp + random hex — unique per process start |
| `experiment_id` | `EXP_TAG` value set at top of file |
| `code_sha256` | SHA-256 of the script — links every row to exact code version |
| `step` | Simulator tick counter |
| `distFromStart` | Position on lap (m) |
| `distRaced` | Total distance driven this session (m) |
| `speedX` | Forward speed (km/h) |
| `trackPos` | Lateral position (−1 to +1, >±1 = off-road) |
| `angle` | Heading error (rad) |
| `steer / accel / brake / gear` | Control outputs sent to simulator |
| `forward_track` | `track[9]` — dead-ahead clearance (m) |
| `min_valid_track` | Minimum of all valid (>0, finite) track sensor readings |
| `damage` | Cumulative damage from TORCS |

### `lap_summary.csv` — per lap

| Column | Description |
|--------|-------------|
| `lap_time` | Authoritative lap time from `lastLapTime` sensor |
| `status` | `completed` / `partial` / `interrupted` |
| `damage_start / damage_end` | Damage at lap start and end |
| `max_speed` | Peak `speedX` during the lap |
| `completion_reason` | `finish_line_crossing` / `max_steps_or_interrupt` / `simulator_reset` |

> **Note:** The recorder detects lap crossings from `distFromStart` wrapping. When the car reverses near the finish line (Zone A recovery), `distRaced` is non-monotonic and the crossing is missed. The TORCS race-results screen is always the authoritative source for lap time.

---

## Setup & Running

### Requirements

- Python 3.6+
- TORCS with SCR patch (vtorcs or vtorcs-RL-color)
- `xautomation` (for GUI automation on Linux)

### Run the baseline (read-only, no telemetry)

```bash
python3 snakeoil3_v1.py
```

### Run an experiment (with full telemetry recording)

```bash
# 1. Edit EXP_TAG and drive_example() in snakeoil3_v2.py
# 2. Start TORCS (Practice → New Race)
# 3. In a second terminal:
python3 snakeoil3_v2.py
```

Telemetry appends to `lap_data.csv` and `lap_summary.csv` automatically. The process exits cleanly when TORCS sends `***shutdown***` at race end.

### Analyse a run

```bash
python3 find_corners.py          # offline corner detection from lap_data.csv
```

---

## Key Design Decisions

**Why no machine learning?** This project is the IBM Challenge submission — the goal is to demonstrate a complete, reproducible, instrumented engineering workflow. The car navigates a full lap in under 2 minutes with zero damage using only classical control and physics-based reasoning, with full telemetry traceability to exact code versions via SHA-256.

**Why one variable at a time?** Compound changes make it impossible to attribute a result (improvement or crash) to a specific cause. Every crash in the experiment history was diagnosed by comparing the one changed variable against the clean baseline. See CHANGELOG entries exp-13 (4 changes → crash, root cause unclear) and exp-38 (dual sensor → top speed 209→173 km/h, immediately reverted).

**Why hard zone caps instead of a better sensor?** exp-38 tested a dual-layer sensor (`straight_read` + `corner_warning`) as a principled alternative to zone caps. It reduced top speed from 209 to 173 km/h and still failed to prevent Corkscrew drift — the problem is geometric (the road curves faster than any dead-ahead sensor can see). The zone caps are the correct fix for that corner geometry.

---

## References

- TORCS SCR manual: [Loiacono et al., arXiv 1304.1672](https://arxiv.org/pdf/1304.1672.pdf)
- Snakeoil Python client: [xed.ch/project/snakeoil](http://xed.ch/project/snakeoil/index.html)
- vtorcs-RL-color: [github.com/giuse/vtorcs](https://github.com/giuse/vtorcs)
- OpenAI Gym interface (original gym_torcs): [ugo-nama-kun/gym_torcs](https://github.com/ugo-nama-kun/gym_torcs)
- DDPG + Keras on TORCS (great application): [yanpanlau.github.io](https://yanpanlau.github.io/2016/10/11/Torcs-Keras.html)
