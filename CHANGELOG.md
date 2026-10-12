# CHANGELOG — TORCS Driving Bot (`drive_example`)

Reference file (never modified): `snakeoil3_gym.py`  
Working file (all changes applied here): `snakeoil3_v1.py`

Each entry records: what changed, why, measured results, and whether the change was kept.

---

## How to fill in results

After each test run, record:
- **Lap time** — time to complete one full lap, or "DNF" if the car crashed before finishing
- **Damage** — final damage value reported by the server (0 = none)
- **Kept** — Yes / No / Partially

---

## Version Log

---

### v0 — Baseline (`snakeoil3_gym.py`, unmodified)

| Setting | Value |
|---|---|
| `target_speed` | `300` km/h (fixed) |
| Steer-to-corner gain | `*15` |
| Steer-to-centre gain | `*0.10` |
| Throttle | Fixed ramp `+= 0.01` / tick |
| Brake | Always `0` — never brakes |

**Why this was the starting point:** Unmodified reference implementation shipped with the snakeoil library.

**Problem identified:** Car crashes before completing lap 1. No braking logic exists. `target_speed = 300` km/h means the throttle ramp never reverses. Steer gain `*15` clips to full lock (`±1.0`) for any `angle > 0.21 rad (~12°)`.

| Metric | Value |
|---|---|
| Lap time | DNF |
| Damage | — |
| **Kept?** | **No — used as reference only** |

---

### v1-experiment-1 — Lower target speed

**File:** `snakeoil3_v1.py`  
**Line changed:** 533

**Change made:**
```python
# Before
target_speed = 300

# After
target_speed = 50
```

**Why:** Eliminate overspeed as a crash cause before investigating anything else. One variable at a time.

**Prediction:** Car completes corners at ~50 km/h. Lap time slow but car survives.  
**Actual result:** Car still crashed — steering was the next problem.

| Metric | Before (v0) | After |
|---|---|---|
| Lap time | DNF | DNF |
| Damage | — | — |
| **Kept?** | | **Yes — carried forward** |

---

### v1-experiment-2 — Lower steer-to-corner gain

**File:** `snakeoil3_v1.py`  
**Line changed:** 536

**Change made:**
```python
# Before
R['steer'] = S['angle'] * 15 / PI

# After
R['steer'] = S['angle'] * 5 / PI
```

**Why:** With `target_speed = 50` the car still crashed. Gain `*15` gives effective multiplier ~4.78, clipping to full steering lock at any angle above ~12°. Reduced to `*5` (multiplier ~1.59) so steering is proportional rather than bang-bang.

**Prediction:** Smoother corner entry; car stops snapping to full lock. May run slightly wide (understeer) rather than spinning.  
**Actual result:** *(fill in after run)*

| Metric | Before | After |
|---|---|---|
| Lap time | DNF | |
| Damage | — | |
| **Kept?** | | |

---

### v1-experiment-3 — Four changes together

**File:** `snakeoil3_v1.py`  
**Lines changed:** 538–539, 544, 548–557

**Changes made:**

#### Change 1 — Proportional throttle (lines 548–551)
```python
# Before: fixed ramp
R['accel'] += .01  # or -= .01

# After: proportional to speed deficit
speed_error = target_speed - S['speedX']
if speed_error > 0:
    R['accel'] = clip(speed_error / target_speed, 0, 1)
    R['brake'] = 0
```
**Why:** At 50 ticks/sec, `+0.01/tick = 0.5 accel/sec` — far too slow to reach target speed in a reasonable distance. Proportional throttle pushes hard when well below target and eases off as speed approaches it.

#### Change 2 — Stronger steer-to-centre pull (line 544)
```python
# Before
R['steer'] -= S['trackPos'] * 0.10

# After
R['steer'] -= S['trackPos'] * 0.30
```
**Why:** `0.10` correction was too weak to pull the car back when drifting laterally, especially at low speed where the correction lag was long.

#### Change 3 — Sensor-based target speed (lines 538–539)
```python
# Before: fixed value
target_speed = 50

# After: driven by dead-ahead track sensor
ahead = S['track'][9]          # distance straight ahead (metres), sensor index 9 = 0°
target_speed = clip(ahead * 0.5, 20, 100)
```
**Why:** A fixed `50` km/h is too slow on straights and potentially still too fast into tight corners. `track[9]` falls as a corner approaches, automatically lowering the speed target before the apex. Scale: 200 m view → 100 km/h; 40 m view → 20 km/h.

#### Change 4 — Active braking (lines 553–557)
```python
# Before: brake always 0

# After: fires when above target speed
else:
    R['accel'] = 0
    R['brake'] = clip(-speed_error / 50, 0, 1)
```
**Why:** Passive throttle lift (`-= 0.01/tick`) sheds ~0.5 accel/sec — completely insufficient to slow the car before a corner. Active braking proportional to overspeed provides real deceleration. Divisor `50` means a 50 km/h overspeed applies full brake.

**Prediction:**
- Straights: car accelerates quickly and holds sensor-derived ceiling (~50–100 km/h)
- Corner approach: `track[9]` drops → target drops → brake fires → car slows before apex
- Stronger centre-pull keeps car on line through sweepers
- Should complete a full lap reliably

**Actual result:** *(fill in after run)*

| Metric | Before | After |
|---|---|---|
| Lap time | DNF | |
| Damage | — | |
| **Kept?** | | |

---

### v1-experiment-4 — Recommended braking strategy (lookahead + wider sensor cone)

**File:** `snakeoil3_v1.py`
**Lines changed:** 538, 550–577

**Changes made:**

#### Change A — Wider forward sensor cone (line 538)
```python
# Before: single dead-ahead sensor
ahead = S['track'][9]

# After: minimum of three forward sensors (-0.5°, 0°, +0.5°)
ahead = min(S['track'][8], S['track'][9], S['track'][10])
```
**Why:** A corner that opens slightly off-centre only appears in `track[9]` when the car is already committed to it. Taking the minimum of three adjacent sensors gives an earlier warning.

#### Change B — Two-stage lookahead braking (lines 560–577)
```python
# Before: single reactive stage
# Brake only when already above target_speed.
R['brake'] = clip(-speed_error / 50, 0, 1)

# After: two stages
decel_g  = 15.0                              # m/s^2 conservative decel
safe_ms  = (2.0 * decel_g * ahead) ** 0.5   # safe speed to reach corner (m/s)
safe_kmh = safe_ms * 3.6

if S['speedX'] <= target_speed:
    R['accel'] = clip(speed_error / target_speed, 0, 1)
    R['brake'] = 0
elif S['speedX'] <= safe_kmh:
    R['accel'] = 0
    R['brake'] = 0                           # above target but still safe — lift only
else:
    R['accel'] = 0
    R['brake'] = clip((S['speedX'] - safe_kmh) / 50.0, 0, 1)  # brake now
```
**Why:** The previous single-stage brake only fired when the car was *already* at the corner entrance going too fast — too late to stop. The new stage 1 uses the physics formula `v = √(2·a·d)` to compute the highest speed from which the car can still decelerate to `target_speed` before reaching the corner at distance `ahead`. If current speed exceeds that safe approach speed, braking starts immediately, giving the car the full available distance to slow down.

**Prediction:**
- Brake fires earlier on corner approach — car arrives at apex closer to target speed
- No change to behaviour on straights or gentle bends (safe_kmh will be large when `ahead` is large)
- Should reduce or eliminate late-braking overshoots that caused corner exits to run wide

**Actual result:** Car completed 1 full lap, zero damage, top speed 118 km/h. Lap time 2:19:52.

| Metric | Before | After |
|---|---|---|
| Lap time | DNF | **2:19:52** |
| Damage | — | **0** |
| Top speed | — | **118 km/h** |
| **Kept?** | | **Yes — first clean lap** |

---

### v1-experiment-5 — Raise speed cap, tighten brake margin, fix gear thresholds

**File:** `snakeoil3_v1.py`
**Lines changed:** 561, 588–598

**Motivation:** Car completed experiment-4 lap at 2:19:52 with 0 damage and a top speed of only 118 km/h. Speed cap was hardcoded at 150 and the 15% brake margin was more conservative than needed. Gear thresholds (50/80/110/140/170) meant 5th and 6th gear were never used.

**Changes made:**

#### Change 1 — Raise speed cap and tighten brake margin (line 561)
```python
# Before
target_speed = clip(safe_kmh * 0.85, 20, 150)

# After
target_speed = clip(safe_kmh * 0.92, 20, 200)
```
- Brake margin: 15% → 8% (car proved it handles Corkscrew with headroom to spare)
- Speed ceiling: 150 → 200 km/h (removes artificial cap on long straights)

#### Change 2 — Tighten gear shift thresholds (lines 588–598)
```python
# Before (5th/6th never engaged at 118 km/h top speed)
2nd @ 50,  3rd @ 80,  4th @ 110, 5th @ 140, 6th @ 170

# After (keeps engine in power band at realistic speeds)
2nd @ 30,  3rd @ 55,  4th @ 80,  5th @ 110, 6th @ 150
```
**Why:** Each gear held too long at low RPM. Tighter thresholds mean the car reaches higher gears sooner, accelerates harder out of corners, and uses 5th/6th on longer straights.

**Prediction:**
- Top speed rises from 118 km/h toward 160–180 km/h
- Lap time target: under 1:30:00
- Damage risk: low — 8% margin still gives a genuine safety buffer

**Actual result:** Top speed rose 118 → 133 km/h, lap time 2:16:86, zero damage. Sensor ceiling still limiting — car not reaching 200 km/h cap on straights.

| Metric | Before | After |
|---|---|---|
| Lap time | 2:19:52 | **2:16:86** |
| Damage | 0 | **0** |
| Top speed | 118 km/h | **133 km/h** |
| **Kept?** | | **Yes** |

---

### v1-experiment-6 — Full throttle on straights, tighter sensor cone, higher decel constant

**File:** `snakeoil3_v1.py`
**Lines changed:** 537–538, 556, 564–568

**Motivation:** Top speed 133 km/h vs 200 km/h cap means the sensor formula is the real ceiling, not the code. The median-of-wide-sensors was pessimistic. Proportional throttle was never reaching full power. `decel_g = 15` was braking the car earlier than TORCS physics require.

**Changes made:**

#### Change 1 — Max of tight forward sensors (line 538)
```python
# Before: median of sensors 4-14 (±4°)
ray = sorted(S['track'][4:15])
ahead = max(ray[len(ray)//2], 0.0)

# After: max of five tightest forward sensors (±1°, indices 7-11)
ahead = max(max(S['track'][7:12]), 0.0)
```
**Why:** On a straight the median was pulled down by any slightly-angled sensor clipping a kerb. Max of the tightest five sensors reads full range on straights and still drops early when a real corner arrives dead ahead.

#### Change 2 — Full throttle when well below target (lines 564–568)
```python
# Before: always proportional
R['accel'] = clip(speed_error / target_speed, 0, 1)

# After: full throttle when >20% below target, proportional only in final band
throttle_band = target_speed * 0.20
if speed_error > throttle_band:
    R['accel'] = 1.0
else:
    R['accel'] = clip(speed_error / throttle_band, 0, 1)
```
**Why:** At target_speed=150 and current=20, old formula gave accel=0.87 — never flooring it. New formula gives full throttle until within 30 km/h of target, then tapers smoothly.

#### Change 3 — Raise decel_g from 15 → 20 m/s² (line 556)
```python
# Before
decel_g = 15.0

# After
decel_g = 20.0
```
**Why:** 15 m/s² is very conservative. TORCS cars sustain 20–25 m/s² braking. Higher value raises `safe_kmh`, which pushes the brake trigger later — car carries more speed down straights.

**Prediction:**
- Top speed should rise from 133 km/h toward 160–180 km/h
- Lap time target: under 2:00:00
- Damage risk: still low — sensors still limit speed before unsafe corners

**Actual result:** Top speed 133 → 182 km/h (+49), lap time 2:14:30, zero damage. Sensor and throttle changes fully effective.

| Metric | Before | After |
|---|---|---|
| Lap time | 2:16:86 | **2:14:30** |
| Damage | 0 | **0** |
| Top speed | 133 km/h | **182 km/h** |
| **Kept?** | | **Yes** |

---

### v1-experiment-7 — Tighten brake margin, raise ceiling, earlier 6th gear

**File:** `snakeoil3_v1.py`
**Lines changed:** 561, 603

**Motivation:** Car completed at 182 km/h with 0 damage on an 8% margin and 200 km/h cap. Remaining time loss is in corners (over-cautious margin) and the coasting zone between `target_speed` and `safe_kmh`. Gear 6 threshold at 150 left a 40 km/h band in 5th gear on acceleration.

**Changes made:**

#### Change 1 — Tighten brake margin and raise ceiling (line 561)
```python
# Before
target_speed = clip(safe_kmh * 0.92, 20, 200)

# After
target_speed = clip(safe_kmh * 0.96, 20, 250)
```
- Margin: 8% → 4% — car carries more corner speed everywhere
- Ceiling: 200 → 250 — physics formula (`safe_kmh`) is now the only real limit on straights

#### Change 2 — Earlier 6th gear (line 603)
```python
# Before
if S['speedX'] > 150: R['gear'] = 6

# After
if S['speedX'] > 130: R['gear'] = 6
```
**Why:** Car now reliably hits 182 km/h. Entering 6th at 130 instead of 150 means 20 km/h more of acceleration in top gear rather than 5th.

**Prediction:**
- Top speed rises from 182 km/h toward 200+ km/h
- Lap time target: under 2:10:00
- Damage risk: slightly higher — 4% margin leaves less buffer on tight corners; revert to `0.94` if damage appears

**Actual result:** CRASH. Car reached 212 km/h, slid into outside tyre wall at Corkscrew entry. Damage = 9. Race stopped mid-lap at 2:07:35. 4% margin too tight at 212 km/h — braking triggered too late.

| Metric | Before | After |
|---|---|---|
| Lap time | 2:14:30 | **DNF (2:07:35 at crash)** |
| Damage | 0 | **9** |
| Top speed | 182 km/h | **212 km/h** |
| **Kept?** | | **No — reverted** |

---

### v1-experiment-8 — Crash recovery: step back margin and decel_g

**File:** `snakeoil3_v1.py`
**Lines changed:** 557–562

**Motivation:** Exp-7 crashed at Corkscrew entry at 212 km/h. The 4% margin (`0.96`) and high `decel_g = 20` combined to trigger braking too late. At 212 km/h the car needs significantly more distance to stop than at 182 km/h (distance scales with speed²). Need to brake earlier AND allow a larger target-speed buffer.

**Root cause of crash:**
- `decel_g = 20` → brake trigger point closer to corner → less stopping distance
- `margin = 0.96` → target speed very close to safe limit → car arrives at corner near its maximum safe speed with no error budget
- At 212 km/h even a small sensor misread or slight understeer means the margin is exceeded

**Changes made:**
```python
# Before (exp-7)
decel_g = 20.0
target_speed = clip(safe_kmh * 0.96, 20, 250)

# After (exp-8) — halfway between safe exp-6 and crashed exp-7
decel_g = 17.0
target_speed = clip(safe_kmh * 0.93, 20, 250)
```
- `decel_g` 20 → 17: braking triggered earlier, giving the car more stopping distance
- Margin 4% → 7%: splits the difference between exp-6 (8%, safe) and exp-7 (4%, crash)
- Speed ceiling kept at 250 — the problem is not top speed, it is corner entry speed

**Prediction:**
- Top speed: still 190–210 km/h range (ceiling unchanged)
- Lap time: between exp-6 (2:14:30) and exp-7 DNF — target ~2:11:00
- Damage: 0 — earlier braking and larger margin should handle Corkscrew safely

**Actual result:** *(fill in after run)*

| Metric | Before (exp-7) | After |
|---|---|---|
| Lap time | DNF | **2:06:81** ✅ |
| Damage | 9 | **6** |
| Top speed | 212 km/h | **204 km/h** |
| **Kept?** | | **Partial — lap complete but damage not zero; advancing to exp-9** |

---

### v1-experiment-9 — Eliminate remaining damage: lower decel_g and margin

**File:** `snakeoil3_v1.py`
**Lines changed:** 561–564

**Motivation:** Exp-8 completed the lap at 2:06:81 (best yet) but damage = 6. The car is still clipping the barrier at Corkscrew at 204 km/h. We need to get to damage = 0 before pushing speed further. The braking needs to trigger slightly earlier — `decel_g` is the primary lever for that.

**What damage=6 tells us:** The car is touching the barrier lightly — not a hard crash — which means it is arriving at the corner just slightly above the safe speed. A small reduction in both levers should be enough.

**Changes made:**
```python
# Before (exp-8)
decel_g = 17.0
target_speed = clip(safe_kmh * 0.93, 20, 250)

# After (exp-9)
decel_g = 15.0
target_speed = clip(safe_kmh * 0.91, 20, 250)
```
- `decel_g` 17 → 15: brake trigger moves further from corner (more stopping distance)
- Margin 7% → 9%: slightly more conservative than proven-safe exp-6 (8% at 182 km/h), appropriate for 200+ km/h

**Prediction:**
- Damage drops to 0
- Lap time: slight increase vs exp-8 (~2:07–2:08) due to more conservative corners
- Top speed: stays ~195–205 km/h (ceiling unchanged at 250)
- Once damage = 0 is confirmed we can nudge margin back up by 0.01 at a time

**Actual result:** Clean lap, 0 damage, 197 km/h, 2:01:99. Best time yet. Time gain vs exp-8 partly due to unstick recovery no longer firing after barrier contact was eliminated.

| Metric | Before (exp-8) | After |
|---|---|---|
| Lap time | 2:06:81 | **2:01:99** ✅ |
| Damage | 6 | **0** ✅ |
| Top speed | 204 km/h | **197 km/h** |
| **Kept?** | | **Yes — new safe baseline** |

---

### v1-experiment-10 — Binary-search step: margin 0.91 → 0.92

**File:** `snakeoil3_v1.py`
**Line changed:** 564

**Motivation:** Exp-9 confirmed clean at `margin = 0.91`. Exp-8 was damaged at `margin = 0.93`. The midpoint is `0.92` — a single +0.01 step to find the exact safe ceiling without risk of jumping past it.

**Change made:**
```python
# Before (exp-9)
target_speed = clip(safe_kmh * 0.91, 20, 250)

# After (exp-10)
target_speed = clip(safe_kmh * 0.92, 20, 250)
```
`decel_g` stays at `15.0` — unchanged.

**Prediction:**
- If damage = 0: `0.92` is safe; continue to `0.93` next
- If damage > 0: `0.92` is the boundary; hold at `0.91` as the final safe value
- Lap time: ~2:01–2:02 (similar to exp-9, marginal speed gain)
- Top speed: ~198–205 km/h

**Actual result:** Clean, 0 damage, 198 km/h. Lap 2:02:88 — marginally slower than exp-9 (2:01:99), within run variance. Confirms `0.92` is safe. Top-speed headroom still available via decel_g.

| Metric | Before (exp-9) | After |
|---|---|---|
| Lap time | 2:01:99 | **2:02:88** |
| Damage | 0 | **0** ✅ |
| Top speed | 197 km/h | **198 km/h** |
| **Kept?** | | **Yes — margin 0.92 confirmed safe** |

---

### v1-experiment-11 — Raise decel_g 15 → 16 (margin stays 0.92)

**File:** `snakeoil3_v1.py`
**Line changed:** 561

**Motivation:** Margin `0.92` is now confirmed safe across two runs. The time difference between `0.91` and `0.92` is within variance (~1 second). Next lever is `decel_g`: raising it from `15` → `16` makes the brake-trigger distance shorter — car is allowed to carry more speed before committing to braking — without changing the corner-entry target speed at all.

**Change made:**
```python
# Before (exp-10)
decel_g = 15.0

# After (exp-11)
decel_g = 16.0
```
Margin stays at `0.92`. Speed ceiling stays at `250`.

**Why this is safe to try:** `decel_g` controls *when* braking starts, not *how fast* the car corners. A value of `16` still gives a healthy stopping-distance budget — it just starts ~6% closer to the corner than `15` did. We know from exp-8 (`decel_g=17`, damage=6) that `17` is too aggressive; `16` is the next safe step.

**Prediction:**
- Top speed: rises from 198 toward 203–208 km/h (brake trigger fires later on straights)
- Lap time: ~2:01–2:02 (should match or beat exp-9's 2:01:99)
- Damage: 0 — margin unchanged at `0.92`
- If damage appears: `decel_g = 16` with `margin = 0.92` is too aggressive; revert to `15`

**Actual result:** Not run as a standalone test. Exp-12 was applied on top of exp-11 settings without an intermediate lap. `decel_g = 16`, `margin = 0.92` carried forward into exp-12.

| Metric | Before (exp-10) | After |
|---|---|---|
| Lap time | 2:02:88 | **— (not run standalone)** |
| Damage | 0 | **— (not run standalone)** |
| Top speed | 198 km/h | **— (not run standalone)** |
| **Kept?** | | **Yes — settings carried into exp-12** |

---

### v1-experiment-12 — Wider sensor cone + reduce steer-to-centre (fix hairpin exit)

**File:** `snakeoil3_v1.py`
**Lines changed:** 539, 544

**Motivation:** In-game footage showed the car running wide at the **hairpin at the base of the Corkscrew**. The car was going slowly (~60 km/h) so this is not an overspeed problem — it is a steering/line problem.

**Root cause identified from footage:**
1. The ±1° sensor cone (indices 7–11) all point at the wall on tight hairpins → very short `ahead` → `target_speed` drops to ~20 km/h → car crawls through the apex losing time
2. Steer-to-centre gain `0.30` actively fights the natural exit line — it pulls the car back toward the centre at the moment physics wants it to track out wide

**Changes made:**

#### Change 1 — Wider sensor cone (line 539)
```python
# Before: ±1° cone (indices 7-11)
ahead = max(max(S['track'][7:12]), 0.0)

# After: ±4° cone (indices 6-14)
ahead = max(max(S['track'][6:15]), 0.0)
```
**Why:** The ±4° sensors see the road curving away through a hairpin, not just the wall ahead. This gives a realistic `ahead` value mid-corner and prevents the artificial speed floor from being triggered.

#### Change 2 — Reduce steer-to-centre gain (line 544)
```python
# Before
R['steer'] -= S['trackPos'] * 0.30

# After
R['steer'] -= S['trackPos'] * 0.25
```
**Why:** The 0.30 gain was fighting the natural exit line on hairpin exits. 0.25 still keeps the car near centre on straights but doesn't fight the car through tight corners.

**All other settings unchanged:** `decel_g = 16`, `margin = 0.92`, gear thresholds.

**Prediction:**
- Hairpin exit: car tracks out naturally instead of running over the kerb
- Corner speed: higher through tight hairpins (target_speed no longer crashes to 20 km/h)
- Straights: unchanged — the wide sensors read full range on straights same as before
- Damage: 0 — the braking logic is unchanged
- Lap time: meaningful improvement — possibly sub-2:00:00

**Actual result:** Not run as a standalone test. Exp-13 was applied immediately on top of exp-12. Settings (wider cone, steer gain 0.25) carried forward into exp-13.

| Metric | Before (exp-11) | After |
|---|---|---|
| Lap time | — | **— (not run standalone)** |
| Damage | — | **— (not run standalone)** |
| Top speed | — | **— (not run standalone)** |
| **Kept?** | | **Yes — settings carried into exp-13** |

---

### v1-experiment-13 — Four top-speed levers together

**File:** `snakeoil3_v1.py`
**Lines changed:** 565, 568, 574, 588

**Motivation:** Top speed has been plateauing at ~198 km/h. Analysis identified four independent levers that each contribute to straight-line speed. Applied together for a single measurable test before individual attribution.

**Changes made:**

| # | Setting | Line | Before | After | Effect |
|---|---|---|---|---|---|
| 1 | `decel_g` | 565 | `16.0` | `18.0` | Brake trigger fires later → more time at full speed |
| 2 | Margin | 568 | `0.92` | `0.93` | Target speed 1% higher everywhere |
| 3 | Throttle band | 574 | `0.20` | `0.10` | Full throttle until 10% below target (was 20%) |
| 4 | Brake divisor | 588 | `50.0` | `35.0` | Sharper braking → can brake later, carry more speed |

```python
# Before
decel_g  = 16.0
target_speed = clip(safe_kmh * 0.92, 20, 250)
throttle_band = target_speed * 0.20
R['brake'] = clip((S['speedX'] - safe_kmh) / 50.0, 0, 1)

# After
decel_g  = 18.0
target_speed = clip(safe_kmh * 0.93, 20, 250)
throttle_band = target_speed * 0.10
R['brake'] = clip((S['speedX'] - safe_kmh) / 35.0, 0, 1)
```

**Prediction:**
- Top speed: 198 → 220–230 km/h
- Lap time: sub-2:00:00 possible
- Damage risk: medium — `decel_g=18` and `margin=0.93` are individually close to the known crash boundary; the wider ±4° sensor cone (exp-12) provides more headroom than before

**Rollback plan if crash occurs:**
- If Corkscrew: revert `decel_g` to `16`, keep others
- If damage only: revert `margin` to `0.92`, keep others
- If overbraking on bends: raise divisor back to `45`

**Actual result:** DNF. Car crashed before completing lap 1 — accumulated damage 96, race stopped mid-lap. Barrier contact on a tight corner. The combination of `decel_g=18` and `margin=0.93` proved too aggressive; additionally the unstick recovery logic had a dead condition (`track[9] < 0`, never true) and wrong steer direction, so once the car clipped a barrier it could not escape. Advanced to exp-14 to address all three root causes.

| Metric | Before (exp-12 baseline) | After |
|---|---|---|
| Lap time | ~2:02 | **DNF** |
| Damage | 0 | **96** |
| Top speed | ~198 km/h | **219 km/h** |
| **Kept?** | | **No — crashed; advanced to exp-14** |

---

### v1-experiment-14 — Crash fix: safer margin, earlier off-track detection, correct unstick steer

**File:** `snakeoil3_v1.py`
**Lines changed:** 570, 616, 621

**Motivation:** Exp-13 crashed with damage 96 before completing lap 1. Three distinct bugs were identified as compounding causes:

1. **Margin too high + floor too high:** `margin = 0.93` and minimum `target_speed = 20` km/h meant the car was still commanded toward the wall even when `safe_kmh ≈ 0`.
2. **Dead sensor condition:** `S['track'][9] < 0` in the `off_track` check is never true — TORCS track sensors return non-negative values only. Recovery never fired from this branch.
3. **Wrong unstick steer direction:** `clip(-S['angle'] / PI, -1, 1)` tried to de-rotate the car to face forward, which could point it straight back into the same wall. The correct escape is to steer away from the wall by `trackPos` sign.

**Changes made:**

#### Change 1 — Tighten margin, lower speed floor (line 570)
```python
# Before (exp-13)
target_speed = clip(safe_kmh * 0.93, 20, 250)

# After (exp-14)
target_speed = clip(safe_kmh * 0.88, 10, 250)
```
- Margin `0.93 → 0.88`: 5% more braking headroom on corner approach.
- Floor `20 → 10` km/h: when a wall is dead ahead (`safe_kmh ≈ 0`), the old floor of 20 kept driving toward it; 10 lets the physics zero it out.

#### Change 2 — Fix the dead off-track sensor condition (line 616)
```python
# Before (exp-13)
off_track = abs(S['trackPos']) > 0.95 or S['track'][9] < 0

# After (exp-14)
off_track = abs(S['trackPos']) > 0.90 or S['track'][9] < 2.0
```
- `track[9] < 0` → `track[9] < 2.0`: now fires when the centre-ahead sensor reads less than 2 m (wall right in front of the car), instead of never.
- `trackPos > 0.95 → 0.90`: triggers recovery 5% sooner, before the car is fully into the barrier.

#### Change 3 — Fix unstick steer direction (line 621)
```python
# Before (exp-13)
R['steer'] = clip(-S['angle'] / PI, -1, 1)

# After (exp-14)
R['steer'] = clip(S['trackPos'], -1, 1)
```
- `trackPos > 0` (left wall) → steers right (+). `trackPos < 0` (right wall) → steers left (−). Always escapes toward track centre.

**Prediction:**
- No crash on lap 1 — earlier braking and working recovery logic together prevent the exp-13 failure mode
- Lap time: slower than exp-13's theoretical ceiling due to more conservative margin; expect ~2:05–2:10
- Damage: 0 — the two recovery bugs are now fixed
- Once confirmed clean, the next step is to nudge margin back up from `0.88` toward `0.91` in `+0.01` steps

**Actual result:** DNF. Damage 63 (down from 96 — braking fix helped reduce impact force), top speed 213 km/h, race stopped mid-lap at 1:51:39. Car slid sideways into the outer barrier on a fast sweeper — high-speed understeer exit, not a braking-point failure. `decel_g=18` is still too aggressive: it delays the brake trigger far enough that the car arrives at corners with more speed than `margin=0.88` can contain. The `max()` sensor reading on fast sweepers also returns a falsely large `ahead` value (outer sensors see open road), which pushes `safe_kmh` higher and further delays braking. Advanced to exp-15 to step `decel_g` back down.

| Metric | Before (exp-13) | After |
|---|---|---|
| Lap time | DNF | **DNF (1:51:39 at crash)** |
| Damage | 96 | **63** |
| Top speed | 219 km/h | **213 km/h** |
| **Kept?** | | **No — still crashing; advanced to exp-15** |

---

### v1-experiment-15 — Step decel_g back to 16 (hold margin at 0.88)

**File:** `snakeoil3_v1.py`
**Line changed:** 567

**Motivation:** Exp-14 confirmed the recovery-logic fixes (off-track sensor, unstick steer) reduced damage 96 → 63, but the car still DNFs at 1:51:39. The crash is a high-speed understeer exit — the car arrives at a fast corner with too much speed. `decel_g=18` is the primary lever: it sets how close to the corner the brake trigger fires. The last clean run was exp-9 with `decel_g=15`. Stepping back to `16` (the last individually-tested value from exp-11, carried through exp-12/13 before the margin was also raised) targets the overspeed root cause without touching any other setting.

**Change made:**
```python
# Before (exp-14)
decel_g = 18.0

# After (exp-15)
decel_g = 16.0
```
All other settings unchanged: `margin = 0.88`, floor `10`, throttle band `0.10`, brake divisor `35`, off-track threshold `0.90 / track[9] < 2.0`, unstick steer `trackPos`.

**Why `16` and not `15`:** `decel_g=15` with `margin=0.91` was clean (exp-9). Here we have `margin=0.88` — 3% more conservative — so `decel_g=16` gives earlier braking than exp-9 used at its equivalent target speed. The net safety margin is higher than exp-9 despite the larger `decel_g` value.

**Prediction:**
- Crash eliminated — earlier brake trigger brings the car to corner entry within `margin=0.88` of safe speed
- Damage: 0
- Top speed: drops from 213 km/h toward ~200 km/h (brake fires earlier on straights)
- Lap time: expect ~2:05–2:10 (more conservative than exp-9's 2:01:99 due to lower margin)
- Once confirmed clean, next step: nudge `margin` from `0.88` → `0.89`

| Metric | Before (exp-14) | After |
|---|---|---|
| Lap time | DNF | **02:21:24** ✅ |
| Damage | 63 | **0** ✅ |
| Top speed | 213 km/h | **208 km/h** |
| **Kept?** | | **Yes — first clean lap since exp-9; new safe baseline** |

**Observations from run footage:** Car completed the lap with 0 damage but was seen going wide onto the gravel at two points without crashing:
1. **Corkscrew entry** (~1:59 elapsed) — wide exit from the braking zone into the left-hander at the top of the Corkscrew.
2. **Fast right-hander at lap start** (~1:27 elapsed) — understeer on the high-speed sweeper in the upper section of the circuit.

Both incidents are **steering line problems, not braking failures** — the car survived both because it was within damage limits, but lap time is being lost. At high speed (180–208 km/h), `angle` is small (~0.1–0.2 rad), giving a gentle `angle * 5 / PI` steering input. The flat `trackPos * 0.25` centre-pull is too weak to recover the line once the car begins to drift wide. Advanced to exp-16 to add a progressive (quadratic) centre-pull term.

---

### v1-experiment-16 — Progressive centre-pull to fix wide exits at high speed

**File:** `snakeoil3_v1.py`
**Line changed:** 547

**Motivation:** Exp-15 is clean (0 damage) but the car visibly runs wide onto the gravel at two corners — the Corkscrew entry and the opening fast right-hander. At 180–208 km/h:
- `angle ≈ 0.1 rad` → `angle * 5 / PI ≈ 0.16` (gentle steering — correct for high speed)
- `trackPos * 0.25` at `trackPos = 0.6` → `0.15` additional pull — too weak to reclaim the line quickly

A quadratic (progressive) term `trackPos * |trackPos| * k` adds little correction when the car is near centre but grows sharply when it drifts wide, without affecting the normal on-line driving behaviour.

**Change made:**
```python
# Before (exp-15)
R['steer'] -= S['trackPos'] * 0.25

# After (exp-16)
tp = S['trackPos']
R['steer'] -= tp * 0.25 + tp * abs(tp) * 0.30
```
- When `trackPos = 0.3` (mild drift): extra correction = `0.3 * 0.3 * 0.30 = 0.027` — negligible, normal driving unaffected.
- When `trackPos = 0.6` (running wide): extra correction = `0.6 * 0.6 * 0.30 = 0.108` — meaningful pull back to centre.
- When `trackPos = 0.9` (at gravel edge): extra correction = `0.9 * 0.9 * 0.30 = 0.243` — strong recovery input.
- `tp * abs(tp)` preserves sign so the pull is always toward centre regardless of which side the car drifts.

**All other settings unchanged:** `decel_g=16`, `margin=0.88`, throttle band `0.10`, brake divisor `35`, off-track threshold `0.90 / track[9] < 2.0`, unstick steer `trackPos`.

**Prediction:**
- Wide exits at Corkscrew entry and opening right-hander resolved — stronger pull when drifting, unchanged when on line
- Damage: 0 — no change to braking logic
- Lap time: improvement from exp-15's 2:21:24 — car takes a tighter line through the two problem corners
- Risk: if the quadratic gain is too strong, the car may over-correct and weave on straights; revert to `0.20` if weaving appears

| Metric | Before (exp-15) | After |
|---|---|---|
| Lap time | 02:21:24 | **DNF** |
| Damage | 0 | **0** |
| Top speed | 208 km/h | **207 km/h** |
| **Kept?** | | **No — DNF due to false reversal bug; advanced to exp-17** |

**Actual result:** DNF. Damage stayed at 0 and top speed was 207 km/h (consistent with exp-15), but the car reversed mid-corner at the tight hairpin complex at the top-left of the circuit (~1:27 elapsed) and could not complete the lap. The progressive centre-pull itself did not cause the failure — the reversal was triggered by the `off_track` condition: `track[9] < 2.0` fired when the forward sensor pointed at the inside apex wall of the hairpin, even though the car was perfectly centred on the track (`trackPos ≈ 0.1–0.3`). Advanced to exp-17 to gate that condition.

---

### v1-experiment-17 — Gate the track[9] unstick branch with trackPos (fix false hairpin reversal)

**File:** `snakeoil3_v1.py`
**Line changed:** 626

**Motivation:** Exp-16 DNF'd at 1:27:59 because the car reversed mid-hairpin with 0 damage. The `off_track` condition has two branches:
1. `abs(trackPos) > 0.90` — genuinely off the road surface ✅
2. `track[9] < 2.0` — forward sensor reading near-zero ❌ fires falsely

Branch 2 was intended to catch a wall directly ahead at low speed. But `track[9]` (the 0° dead-ahead sensor) also reads < 2 m at the **apex of a tight hairpin**, where the car is pointed at the inside kerb wall while cornering — even when perfectly on the track. As a result, as the car slows for the hairpin and `speedX` drops below 8 km/h, the condition fires, commanding gear -1 and reversing the car.

**Change made:**
```python
# Before (exp-16)
off_track = abs(S['trackPos']) > 0.90 or S['track'][9] < 2.0

# After (exp-17)
off_track = abs(S['trackPos']) > 0.90 or (S['track'][9] < 2.0 and abs(S['trackPos']) > 0.85)
```
The `track[9]` branch now only counts as off-track when the car is also near the edge of the road (`abs(trackPos) > 0.85`). A car in the centre of the track pointing at a hairpin wall (`trackPos ≈ 0.1–0.3`) will not trigger reversal. A car genuinely lodged against a barrier (`trackPos > 0.85`) with a wall directly ahead will still trigger it correctly.

**All other settings unchanged:** exp-16 progressive steer, `decel_g=16`, `margin=0.88`, brake divisor `35`.

**Prediction:**
- Hairpin reversal eliminated — car corners normally through the tight hairpin complex
- Damage: 0 — no change to braking
- Lap time: should match or beat exp-15's 2:21:24, potentially sub-2:20 with exp-16 steering also active
- Genuine wall-stuck recovery still works via the `abs(trackPos) > 0.90` branch

**Run 1 (prev session):**

| Metric | Before (exp-16) | After |
|---|---|---|
| Lap time | DNF | **DNF — crashed at 01:16:16** |
| Damage | 0 | **637** |
| Top speed | 207 km/h | *(not recorded — run ended early)* |
| **Kept?** | | *(see Run 2 below)* |

**Run 2 (today):**

| Metric | Run 1 | Run 2 |
|---|---|---|
| Lap time | DNF (01:16:16) | **DNF — crashed after 01:31:24** |
| Damage at screenshot | 637 | **0** (still running at 01:31:24) |
| Top speed | *(not recorded)* | **207 km/h** |
| **Kept?** | | **No — still crashes; advanced to exp-18** |

**Observations from Run 2 footage:** The hairpin false-reversal bug was fully fixed by the `trackPos > 0.85` gate — the car reached 01:31:24 with 0 damage and 207 km/h (screenshot confirms on-track, no damage). However it crashed shortly after the hairpin section, in the high-speed zone on the back half of the circuit. The off-track gate change itself is correct and must be kept. The **quadratic centre-pull term** (`tp * abs(tp) * 0.30`) from exp-16 is the only change between exp-15 (clean, 2:21:24, damage 0) and exp-17 (crashes at ~1:31). At 207 km/h with `trackPos ≈ 0.5–0.6`, the quadratic adds `0.075–0.108` of extra steer correction, over-sharpening the line on fast sweepers and causing the car to dart into the barrier. Advanced to exp-18 to revert the quadratic term while keeping the exp-17 gate.

---

### v1-experiment-18 — Revert quadratic centre-pull; keep exp-17 off-track gate

**File:** `snakeoil3_v1.py`
**Line changed:** 554

**Motivation:** Exp-17 (Run 2) reached 01:31:24 with 0 damage before crashing on the high-speed section after the hairpin. The only difference from exp-15 (clean lap, 2:21:24, damage 0) is the exp-16 quadratic centre-pull `tp * abs(tp) * 0.30`. All braking settings are identical (`decel_g=16`, `margin=0.88`, divisor `35`). The quadratic term is therefore the sole cause. At `trackPos ≈ 0.55` and 207 km/h the extra steer input is `0.55 * 0.55 * 0.30 = 0.091` — comparable in magnitude to the entire angle-based input at that speed, causing a sudden sharp correction that destabilises the car.

**Change made:**
```python
# Before (exp-16 / exp-17)
tp = S['trackPos']
R['steer'] -= tp * 0.25 + tp * abs(tp) * 0.30

# After (exp-18) — revert to exp-15 linear-only centre-pull
tp = S['trackPos']
R['steer'] -= tp * 0.25
```

**What is kept:** The exp-17 off-track gate remains exactly as-is:
```python
off_track = abs(S['trackPos']) > 0.90 or (S['track'][9] < 2.0 and abs(S['trackPos']) > 0.85)
```
All other settings unchanged: `decel_g=16`, `margin=0.88`, floor `10`, throttle band `0.10`, brake divisor `35`.

**Why this should work:** Exp-15 had this exact centre-pull formula (`tp*0.25`) and completed the full lap cleanly at 2:21:24 with 0 damage. Adding the exp-17 gate (which was not present in exp-15) is strictly safer — it only prevents false reversal and cannot cause a crash. The combination is: exp-15 steering (proven clean) + exp-17 recovery logic (proven to fix hairpin reversal).

**Prediction:**
- Hairpin reversal: eliminated (exp-17 gate still active) ✅
- High-speed crash after hairpin: eliminated (quadratic term removed) ✅
- Damage: 0 — braking settings match exp-15 exactly
- Lap time: ~2:21 (matching exp-15; the quadratic term didn't help time, it caused crashes)
- Once confirmed clean: nudge `margin` from `0.88` → `0.89` to recover the speed lost vs exp-12

| Metric | Before (exp-17) | After (exp-18) |
|---|---|---|
| Lap time | DNF | **DNF — stuck at dist 2463 m, 6:11 elapsed** |
| Damage | 0 (at crash) | **31** |
| Top speed | 207 km/h | **207 km/h** |
| **Kept?** | | **No — unstick steer direction bug; advanced to exp-19** |

**Observations from lap_data.csv (run 20261008_160127Z):**
- Car reached `distRaced = 2479 m` before the incident — further than any previous run
- At `dist ≈ 2465 m`, `t = 73.5 s`, the car was braking at ~33 km/h with `trackPos = -0.963` (sliding right toward the edge)
- `forward_track` collapsed to `0.041 m` at step 3608 (wall directly ahead) then went blank
- `trackPos` crossed `−1.0` at step 3609 — `off_track` condition fired correctly
- `speedX < 8` triggered reverse at step 3618 — recovery logic activated correctly
- **Bug:** `steer = clip(trackPos, -1, 1) = clip(-1.007, -1, 1) = -1.0` — steered **left** (into the wall), not right (toward the track). With `trackPos < -1`, the negation needed for "toward centre" was missing
- Car reversed sideways into the barrier, accumulating damage 31, then drifted to `trackPos = -3.37` over 96,383 reverse steps until `maxSteps` expired
- This is the same bug identified in exp-13 and fixed in exp-14 — it was reintroduced when the unstick block was rewritten in exp-14/15. **Root cause: `clip(trackPos, -1, 1)` steers away from centre when `trackPos < 0`; correct expression is `clip(-trackPos, -1, 1)`**

---

### v1-experiment-19 — Fix unstick steer direction (negate trackPos)

**File:** `snakeoil3_v2.py`
**Line changed:** `R['steer'] = clip(S['trackPos'], -1, 1)` → `clip(-S['trackPos'], -1, 1)`

**Root cause:** When the car goes off-track to the right (`trackPos < 0`), the recovery code steered `clip(trackPos, -1, 1)` which for `trackPos = -1.0` gives `-1.0` — full left lock, pushing the car further into the right-side wall. The correct escape is to steer toward the track centre, which for `trackPos < 0` is rightward (positive). Negating `trackPos` achieves this:

| `trackPos` | Old steer | New steer | Effect |
|---|---|---|---|
| `−1.0` (right wall) | `−1.0` (hard left, INTO wall) | `+1.0` (hard right, toward centre) | ✅ correct |
| `+1.0` (left wall) | `+1.0` (hard right, INTO wall) | `−1.0` (hard left, toward centre) | ✅ correct |
| `−0.5` (mild right drift) | `−0.5` (away) | `+0.5` (toward) | ✅ correct |

**Evidence from exp-18 data:** Steps 3583–3618 show the car sliding to `trackPos −0.96 → −1.007` with `forward_track → 0` while the reverse trigger fires. Old steer `-1.0` reversed it sideways into the wall for 96,383 steps. This single sign change is the entire fix.

**Change made:**
```python
# Before (exp-18 — wrong)
R['steer'] = clip(S['trackPos'], -1, 1)

# After (exp-19 — correct: steer toward centre)
R['steer'] = clip(-S['trackPos'], -1, 1)
```

All other settings unchanged: `decel_g=16`, `margin=0.88`, linear `tp*0.25` centre-pull, hairpin gate `abs(trackPos) > 0.85`.

**Prediction:**
- Recovery works: car steers back toward track, recovers within a few seconds
- Damage: 0 — the wall contact that caused damage 31 is the same contact that triggers recovery; with correct steering the car escapes rather than grinding along the wall
- Lap time: car now has a chance of completing the full lap; this was the only failure mode observed in exp-18

**Actual result:** DNF — car reached 2512 m (distRaced) before hitting the 100,000 step limit at 2:55:60 elapsed. Steer fix measurably worked: damage dropped from 31 → 3 (car grazed the right-side wall at ~81.7 s, `trackPos ≈ 2.06`, then recovered direction correctly). However it could not re-join the track and exhausted `maxSteps` in a low-speed reverse/crawl. The negation fix is confirmed correct — the car no longer grinds along the wall — but the recovery manoeuvre is not fast enough to re-enter the track before the step limit expires. Advanced to exp-20 to increase reverse thrust and extend or replace the recovery routine.

| Metric | Before (exp-18) | After |
|---|---|---|
| Lap time | DNF (stuck at 2463 m) | **DNF (max_steps at 2512 m, 2:55:60)** |
| Damage | 31 | **3** ✅ |
| Top speed | 207 km/h | **208.5 km/h** |
| **Kept?** | | **Partial — steer fix confirmed; recovery routine still needs work; advancing to exp-20** |

---

### v1-experiment-19 — additional runs (today)

Three further exp-19 runs were made after the original CHANGELOG entry. All ran the same code (`exp-19-steer-fix`, SHA `0c1496a1`).

| Run ID | Damage | Max speed | Max distRaced | What happened |
|---|---|---|---|---|
| `20261009_144841Z` | 0 | 207 km/h | 2476 m | False-trigger left side: `abs(trackPos)>0.90` fired at `trackPos≈−1.05`, gear -1, correct steer (+), but car crawled in reverse indefinitely until max_steps expired |
| `20261009_165801Z` | 1522 | 62 km/h | — | Severe gravel incident — car exited track early, accumulated catastrophic damage |
| `20261009_172014Z` | 1 | 208 km/h | 2502 m | False-trigger right side: `abs(trackPos)>0.90` fired at `trackPos≈1.79`, 10 km/h → dropped to <8 → gear -1. Steer `clip(−1.79,−1,1) = −1.0` (steer left, correct direction). Car slowly crawled back but exhausted max_steps at `trackPos≈0.19`, 100,000 steps, 112 s elapsed. |

**Root cause confirmed:** `abs(trackPos) > 0.90` fires at the road edge during normal cornering. TORCS `trackPos = ±1.0` is the track boundary — values between `±0.90` and `±1.0` are still on the road surface. At this specific sweeper (distRaced ≈ 2500 m) the car goes wide to `|trackPos| ≈ 1.1–1.8` while above 8 km/h, but the combination of tight corner + sensor braking drops speed below 8 while the car is still partially on the gravel edge, triggering recovery too early. Once in recovery mode, the car cannot re-join before `maxSteps = 100,000` expires.

---

### v1-experiment-20 — Fix off_track threshold: 0.90 → 1.0

**File:** `snakeoil3_v2.py`
**Line changed:** 1066 (off_track condition)

**Motivation:** Three consecutive exp-19 runs all DNF at the same sweeper (distRaced ≈ 2500 m) due to the `abs(trackPos) > 0.90` branch firing while the car is still on or barely past the road edge. TORCS `trackPos = ±1.0` is the physical road boundary. Anything ≤ 1.0 is on the road. The `0.90` threshold was firing at 90% road-width — legitimately normal cornering behaviour on a wide sweeper.

**Change made:**
```python
# Before (exp-19) — fires at road edge (still on track)
off_track = (abs(S['trackPos']) > 0.90 or
             (S['track'][9] < 2.0 and abs(S['trackPos']) > 0.85))

# After (exp-20) — fires only when fully off road (past track boundary)
off_track = (abs(S['trackPos']) > 1.0 or
             (S['track'][9] < 2.0 and abs(S['trackPos']) > 0.90))
```
- `abs(trackPos) > 1.0`: triggers only when the car has crossed the physical road edge into gravel.
- `track[9]` branch gate: raised from `0.85` → `0.90` (consistent with the new primary threshold — only gate when also near the road boundary, not just at a hairpin apex).
- All other settings unchanged: `decel_g=16`, `margin=0.88`, steer `tp*0.25`, unstick steer `clip(-trackPos,−1,1)`.

**Why this restores the exp-15 behaviour:** Exp-15 completed the lap cleanly with the same braking and steering logic. It never triggered recovery at this corner because the `speedX < 8` guard prevented it — the car was still doing ~30–50 km/h at `trackPos ≈ −0.91`. Raising the threshold to `1.0` means the car now has to be completely off the road AND below 8 km/h before recovery fires, matching the effective behaviour of exp-15.

**Prediction:**
- Wide sweeper at distRaced ≈ 2500 m: no reversal — car is below `trackPos = 1.0` while speed is still above 8 km/h
- Hairpin complex: no reversal — `trackPos` stays well below 0.90 on-track even at the apex
- Genuine wall-stuck recovery still works: if the car really parks in the gravel (`trackPos > 1.0`, `speed < 8`), recovery fires correctly
- Lap time: should match or beat exp-15's 02:21:24 — no recovery detours
- Damage: 0

There were four exp-20 runs:

| Run | Run ID | Result | Lap time | Damage | Top speed | Notes |
|---|---|---|---|---|---|---|
| 1 | `20261009_173451Z` | DNF | — | 35 | 207.1 km/h | max_steps at 2516 m; recovery oscillation |
| 2 | `20261009_194625Z` | **COMPLETED** ✅ | **02:19:19** | 1 | 208.7 km/h | Recovery fired at 2501 m, damage 1 graze; recorder missed lap finish |
| 3 | *(stopped mid-lap)* | DNF | 01:32:51 elapsed | — | 208 km/h | Car stopped at outside wall of Corkscrew entry hairpin (~2465–2480 m); recorder not updated |
| 4 | *(new)* | **COMPLETED** ✅ | **02:25:58** | **0** | 208 km/h | **First fully clean lap — zero damage** |

**Run 2 detail:** Car went wide at the Corkscrew sweeper (`trackPos → 1.789`, `speedX 1.2 km/h`), recovery reversed it back to `trackPos 0.89`, re-joined track and completed. Recorder missed finish (car was reversing when it crossed the line — `distRaced` not monotonic). TORCS result screen is ground truth.

**Run 3 detail:** Same sweeper issue, but this time car arrived with slightly more speed or wider line, `trackPos` crossed `−1.0` while `speedX` still above 8 km/h → recovery **did not fire** → car drove into outside Armco at ~30 km/h at the Corkscrew entry hairpin (01:32:51 elapsed, visible on TORCS screen and minimap). No TORCS result screen (race not completed).

**Run 4 detail:** **Zero damage, 1 clean lap, 02:25:58.** The Corkscrew sweeper was navigated without triggering recovery at all — car stayed on track through the problem zone. Recorder missed lap finish (same pattern as Run 2 — `distRaced` not monotonic during the corner). TORCS result screen confirmed.

**Recorder note — missed lap detection (Runs 2 and 4):** When the car goes wide near the end of the circuit and reverses, `distRaced` stops advancing monotonically. The recorder's lap-detection requires `distRaced` to be increasing to confirm a lap crossing; when it is not, the crossing is missed and the lap is logged as `partial`. The TORCS race-results screen is the authority. Both completions are genuine.

| Metric | Before (exp-19) | Best exp-20 result (Run 4) |
|---|---|---|
| Lap time | DNF (max_steps) | **02:25:58** ✅ |
| Damage | 0–1 | **0** ✅ |
| Top speed | 207–208.5 km/h | **208 km/h** |
| **Kept?** | | **Yes — first zero-damage completed lap** |

---

### v1-experiment-20 run summary

| Run | Lap time | Damage | Result | Kept? |
|---|---|---|---|---|
| `20261009_173451Z` | DNF (max_steps, 230 s) | 35 | max_steps expired in recovery crawl | No |
| `20261009_194625Z` | **02:19:19** | 1 | Completed (recorder missed) | Yes — first completion |
| *(~01:32:51 elapsed)* | DNF | — | Drove into Armco at Corkscrew entry | No |
| *(new)* | **02:25:58** | **0** | **Completed, zero damage** (recorder missed) | **Yes — best result** |

---

### v1-experiment-21 — Zone-specific speed cap at Corkscrew sweeper

**File:** `snakeoil3_v2.py`
**Lines added:** after `target_speed` calculation (~line 1033)

**Motivation:** All exp-20 runs show the car arriving at the Corkscrew sweeper (`distFromStart 2390–2491 m`) at 134 km/h with `trackPos ≈ +0.24` (already right of centre). It drifts to `trackPos −1.0` by the apex at 50 km/h, using every metre of available road width. The existing lookahead formula alone cannot prevent this because the dead-ahead sensor (`track[9]`) reads the *outer* wall of the sweeping curve, not the full corner radius — so it underestimates how much the car needs to slow.

**Change made:**
```python
# After target_speed is computed from the lookahead formula:
dist = S.get('distFromStart', 0.0) or 0.0
if 2390.0 <= dist <= 2491.0:
    target_speed = min(target_speed, 40.0)
```
- Within the zone the target speed is capped at **40 km/h** — whatever the lookahead formula computes, it cannot exceed 40.
- Outside the zone (everywhere else on the lap) the formula is completely unchanged.
- The cap lifts automatically when `distFromStart` wraps back to 0 (the car crosses the finish line). No second change needed for the straight — this zone IS the final corner; the next section is the start/finish straight.
- 40 km/h was chosen because telemetry shows the car drifting to `trackPos −0.80` at 50–55 km/h; dropping to 40 should keep it within the road boundary.

**Why `distFromStart` and not `distRaced`:** `distFromStart` is the position on the track and is deterministic every lap. `distRaced` accumulates over the session and varies when the car reverses during recovery.

**All other settings unchanged:** `decel_g=16`, `margin=0.88`, `off_track > 1.0`, steer `tp*0.25`.

**Prediction:**
- Car brakes hard to 40 km/h before `distFromStart = 2390 m` (about 100 m before the apex)
- Stays below 40 km/h through the tight hairpin section; `trackPos` stays within road boundary
- No recovery trigger, no damage
- Lap time will be slower than exp-20 through this zone (~5–10 s penalty for the mandatory 40 km/h crawl)
- Once confirmed clean: raise cap from 40 → 50 → 60 km/h in steps until the drift reappears

| Metric | Before (exp-20 best) | After |
|---|---|---|
| Lap time | 02:25:58 | **02:05:54** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 208 km/h | **208 km/h** |
| **Kept?** | | **Yes — 20-second improvement; zone cap effective** |

**Observations:** The mandatory 40 km/h cap through distFromStart 2390–2491 m cost ~20 s vs free-speed, but eliminated all Corkscrew incidents and shaved 20 s off the previous best clean lap (02:25:58). The lap is now fully reliable. Next step: raise cap to 50 km/h to recover some of that time.

---

### v1-experiment-22 — Raise Corkscrew zone cap 40 → 50 km/h

**File:** `snakeoil3_v2.py`
**Line changed:** `min(target_speed, 40.0)` → `min(target_speed, 50.0)`

**Motivation:** Exp-21 confirmed the zone cap works cleanly (0 damage, 02:05:54). The 40 km/h cap is conservative — telemetry showed the car drifting to `trackPos −0.80` at 50–55 km/h in earlier runs, which was the reason 40 was chosen. The CHANGELOG next-steps plan calls for raising in 10 km/h steps. At 50 km/h the car has ~25% more energy through the zone but will still brake from the lookahead formula for the tightest part of the hairpin. If the car stays within road boundaries (trackPos within ±1.0), the cap can be raised again.

**Change made:**
```python
# Before (exp-21)
target_speed = min(target_speed, 40.0)

# After (exp-22)
target_speed = min(target_speed, 50.0)
```

**All other settings unchanged:** `decel_g=16`, `margin=0.88`, `off_track > 1.0`, steer `tp*0.25`, gear thresholds.

**Prediction:**
- Lap time: recover 3–8 s from the zone penalty → target ~1:58–2:02
- Damage: 0 — the lookahead braking still governs the tightest section of the hairpin; 50 km/h only adds speed on the approach sweep
- Risk: if the car drifts past `trackPos ±1.0` through the zone, revert to 40 km/h or try 45 km/h as an intermediate

| Metric | Before (exp-21) | After |
|---|---|---|
| Lap time | 02:05:54 | *(fill in after run)* |
| Damage | 0 | *(fill in after run)* |
| Top speed | 208 km/h | *(fill in after run)* |
| **Kept?** | | *(fill in after run)* |

---

### v1-experiment-23 — Combined: margin 0.89 + Corkscrew cap 60 km/h + pre-zone line fix

**File:** `snakeoil3_v2.py`
**Lines changed:** `target_speed` margin, zone cap value, new pre-zone steer block

**Motivation:** The one-at-a-time approach has confirmed the following safe boundaries individually:
- `margin = 0.88` clean (exp-21); `margin = 0.93` crashes (exp-7/13); `margin = 0.89` is the next safe step
- Corkscrew cap at 40 km/h clean (exp-21); the CHANGELOG plan raises in 10 km/h steps; skipping to 60 km/h is reasonable because the lookahead formula still governs the tightest apex inside the zone — only the approach sweep speed changes
- Pre-zone centre-pull (`trackPos +0.24` entry bias) is the documented root cause of why any cap above 40 km/h risks a wide exit; fixing the geometric entry line allows the higher cap

These three changes address three **different, independent problems** (global speed budget, zone entry speed, zone entry line) and their failure modes do not interact. `decel_g` is intentionally left at 16 — every hard crash in the experiment history traces to raising it.

**Changes made:**

#### Change 1 — Margin 0.88 → 0.89 (global, line ~1035)
```python
# Before (exp-21)
target_speed = clip(safe_kmh * 0.88, 10, 250)

# After (exp-23)
target_speed = clip(safe_kmh * 0.89, 10, 250)
```
Effect: +1% target speed everywhere on the lap. At `safe_kmh = 200`, target rises from 176 to 178 km/h.

#### Change 2 — Pre-zone line correction (new block, dist 2290–2390 m)
```python
# New in exp-23
if 2290.0 <= dist < 2390.0:
    R['steer'] -= S['trackPos'] * 0.15   # extra centre-pull in 100 m run-in
```
Gain 0.15 adds at most `0.15 * 0.24 = 0.036` of steer correction when `trackPos = 0.24` — negligible at straight-line speeds, but sufficient to walk the car back to centre before the cap zone starts. The base `trackPos * 0.25` centre-pull continues unchanged; this adds to it only in this 100 m window.

#### Change 3 — Corkscrew zone cap 50 → 60 km/h (dist 2390–2491 m)
```python
# Before (exp-22)
target_speed = min(target_speed, 50.0)

# After (exp-23)
target_speed = min(target_speed, 60.0)
```
A better entry line (Change 2) means the car has more road width available, so 60 km/h is viable where 50 previously wasn't. If the car still drifts wide at 60 km/h, the fallback is 55 km/h, not 50 km/h — we have more room to search now.

**All other settings unchanged:** `decel_g=16`, throttle band `0.10`, brake divisor `35`, off-track `> 1.0 / track[9] < 2 & trackPos > 0.90`, gear thresholds.

**Prediction:**
- Lap time: sub-2:00 possible — +1% margin on the full lap, +zone speed (each 10 km/h cap step saves ~3–5 s through the 101 m zone)
- Damage: 0 — `decel_g=16` + `margin=0.89` is well inside the known-safe envelope; `decel_g=17` with `margin=0.88` was the first damage run (exp-8, damage=6)
- Risk: if the car drifts wide in the Corkscrew zone despite the pre-zone correction, lower the cap to 55 km/h; the pre-zone steer block itself cannot cause a crash (gain is small and the zone is straight)
- Rollback plan: if crash or damage > 0 → revert cap to 50, keep margin=0.89 and pre-zone block; if still crashing → revert margin to 0.88

| Metric | Before (exp-21) | After |
|---|---|---|
| Lap time | 02:05:54 | **DNF** |
| Damage | 0 | **46** |
| Top speed | 208 km/h | **209.9 km/h** |
| **Kept?** | | **No — post-recovery launch crash; advanced to exp-24** |

**Root cause from telemetry (run `20261010_095312Z`):**
- Car entered cap zone at `dist 2390` with `trackPos +0.276`, `speedX 137 km/h` — zone cap fired correctly ✅
- Car decelerated through the zone; `trackPos` drifted steadily from `+0.28` → `−0.999` (right-side edge)
- At step 3577: `speedX 12.8`, `trackPos −0.999` → recovery fired (gear -1, steer `+clip(-trackPos) = +1.0`) — **correct direction** ✅
- Car reversed back to `trackPos ≈ 0.0` ✅
- At step 3645: recovery exited (speed rose above 8 km/h); **`angle = −1.26 rad (−72°)`** — car facing nearly sideways
- Normal steering resumed: `steer = angle*5/PI = −2.0` → clipped `−1.0` — full left lock into opposite wall
- Car launched sideways at 60 km/h into the left barrier; damage 46; froze in gravel for remaining 96k steps

This is the same class of bug as exp-13/14/18: recovery correctly steers back to road, but hands control back to normal drive before yaw angle is corrected.

---

### v1-experiment-24 — Post-recovery yaw realignment gate

**File:** `snakeoil3_v2.py`
**Block added:** `elif abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0:` after the `off_track` reverse block

**Motivation:** The reverse block stops running the moment `speedX` rises above 8 km/h. If the car is still yawed sideways at that point, normal `angle * 5/PI` steering produces a large clipped value, launching the car into the opposite wall. A second `elif` gate checks for large residual yaw after the reverse phase and holds a gentle forward crawl with yaw-correcting steer until `abs(angle) < 0.3 rad`.

**Change made:**
```python
# New block — runs when off_track is False but car still yawed > 17°
elif abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0:
    R['gear']  = 1
    R['accel'] = 0.3
    R['brake'] = 0.0
    # angle > 0 = facing left → steer right (+); angle < 0 = facing right → steer left (−)
    R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)
```

- **`elif` (not `if`):** Mutually exclusive with the reverse block — only runs when on-road and not triggering the reverse condition.
- **0.3 rad threshold (≈17°):** Normal cornering keeps `angle` below ~0.15 rad. A post-recovery sideways car has `angle ≈ 1.26 rad`. The threshold safely separates the two regimes.
- **`accel = 0.3`:** Slow crawl to give the steering time to rotate the car before it builds speed.
- **`steer = angle * 3/PI`:** At `angle = −1.26`: steer `= −1.20` → `−1.0` clipped. Correct direction (left steer to face right = re-align). Softer gain (`*3` vs normal `*5`) for a smooth correction.

**All other settings unchanged from exp-23:** margin=0.89, cap=60 km/h, pre-zone steer, `decel_g=16`.

**Prediction:**
- After recovery the car crawls forward with full-lock steer until `angle < 0.3 rad`, then hands back to normal driving
- Damage: 0 — the post-recovery wall contact is eliminated
- Normal driving: `elif` never fires (`angle` < 0.15 rad at all normal speeds) — zero impact on non-recovery laps
- Lap time: should match exp-23 pace (01:54:69 elapsed when crash occurred) and complete the remaining ~1 min of circuit

| Metric | Before (exp-23) | After |
|---|---|---|
| Lap time | DNF | **02:26:19** ✅ |
| Damage | 46 | **0** ✅ |
| Top speed | 209.9 km/h | **209 km/h** |
| **Kept?** | | **Yes — clean lap; yaw fix confirmed working** |

**Observations:**
- Yaw-realignment gate eliminated the post-recovery wall contact — 0 damage ✅
- Lap time 02:26:19 is **slower** than exp-21 (02:05:54) despite having cap=60 km/h and margin=0.89. This means the yaw-realignment crawl phase itself is costing significant time: after reversing back to `trackPos ≈ 0`, the car crawls at `accel=0.3` until `angle < 0.3 rad`, which at this corner takes several seconds before it can accelerate normally. The recovery manoeuvre is now safe but slow.
- **Root cause of time loss:** The zone cap (60 km/h) still lets the car drift wide enough to trigger recovery. The yaw fix saves the lap but adds ~20 s vs a lap where recovery never fires.
- **Recorder note:** Lap finish not detected in CSV (same pattern as exp-20 — `distRaced` non-monotonic during reversal near finish). TORCS race screen is authority.
- **Next priority:** Stop the drift from happening in the first place, so recovery never fires. Option 1: lower cap back to 40 km/h (guaranteed no drift, but ~20 s penalty). Option 2: cap=50 km/h (intermediate). Option 3: fix the geometric entry line more aggressively (pre-zone steer gain increase).

---

## Next steps

| Priority | Observation | Action |
|---|---|---|
| 1 | Recovery fires but lap completes | Lower zone cap 60 → 50 km/h to prevent drift triggering recovery |
| 2 | Cap=50 still drifts wide | Lower to 45 km/h; find highest cap at which drift+recovery never triggers |
| 3 | Recovery-free lap confirmed | Raise cap in 5 km/h steps until drift reappears; that is the true safe ceiling |
| 4 | Lap time vs exp-21 (02:05:54) | If cap=50 no-recovery lap is slower than exp-21, tighten pre-zone steer gain to improve entry line |
| 5 | After consistent no-recovery laps | Promote exp-24 code to snakeoil3_v1.py as new baseline; nudge margin 0.89 → 0.90 |

---

### v1-experiment-25 — Lower Corkscrew cap 60 → 50 km/h (keep yaw-fix + margin=0.89 + pre-zone steer)

**File:** `snakeoil3_v2.py`  
**Line changed:** `min(target_speed, 60.0)` → `min(target_speed, 50.0)`

**Motivation:** Exp-24 completed (02:26:19, 0 damage) but was **slower** than exp-21 (02:05:54) despite having the higher cap and better margin. The yaw-realignment crawl phase after recovery cost ~20 s. The root cause: cap=60 lets the car drift wide enough to trigger recovery every time through the Corkscrew zone. A no-recovery lap is always faster than a recovery+realign lap. Lowering the cap to 50 km/h targets a drift-free transit.

**What is kept from exp-24:**
- Yaw-realignment gate (`elif abs(angle) > 0.3`: accel=0.3, steer=angle*3/PI) — acts as safety net if recovery still fires at 50 km/h
- Pre-zone steer correction (dist 2290–2390, gain 0.15) — improves entry line regardless of cap
- Margin 0.89 — gives +1% speed everywhere else on the lap

**Change made:**
```python
# Before (exp-23/24)
target_speed = min(target_speed, 60.0)

# After (exp-25)
target_speed = min(target_speed, 50.0)
```

**Prediction:**
- If no recovery fires: lap time should beat exp-21 (02:05:54) — exp-25 has margin=0.89 (+1% everywhere) and pre-zone steer correction (better entry line), both absent in exp-21
- If recovery still fires at 50 km/h: cap is still too high; lower to 45 km/h next
- Damage: 0 — yaw-fix safety net in place; margin=0.89 still well within safe envelope

| Metric | Before (exp-24) | After |
|---|---|---|
| Lap time | 02:26:19 | **lap completed (recorder missed)** |
| Damage | 0 | **0** ✅ |
| Top speed | 209 km/h | **209.8 km/h** |
| Recovery fired? | Yes | **Yes — Corkscrew still drifts at 50 km/h** |
| **Kept?** | | **Partial — yaw-fix kept; cap reverted to 40; Zone B identified** |

**Observations from telemetry (run `20261010_101215Z`):**
1. **Zone A (Corkscrew, dist 2390–2491):** Cap=50 km/h still not enough. Car entered at 137 km/h, `trackPos +0.28`, and drifted to `trackPos −0.85` by dist 2461 before recovery activated. The yaw-fix prevented a crash (0 damage) but the recovery manoeuvre cost lap time. Cap must go back to 40 km/h.
2. **Zone B (dist ~3220–3272, back-section hairpin):** **New corner identified.** Car approached at 147 km/h, perfectly centred (`trackPos ≈ 0`). Lookahead braking slowed it to 78 km/h but `trackPos` still drifted to `−2.09` — the corner geometry is tighter than the lookahead formula can handle. No zone cap existed here before. Added in exp-26 at 60 km/h.

---

### v1-experiment-26 — Two zone caps: Zone A reverted to 40, Zone B added at 60 km/h

**File:** `snakeoil3_v2.py`
**Lines changed:** Zone A cap value; Zone B cap block added

**Motivation:** Two distinct corners were identified as consistently exceeding the lookahead formula's ability to keep the car on track:
- **Zone A (Corkscrew, 2390–2491 m):** Cap=50 still triggers recovery; revert to 40 km/h which was the last proven no-recovery value (exp-21).
- **Zone B (back-section hairpin, 3220–3340 m):** New corner, first identified in exp-25 telemetry. Car going 147 km/h → brakes to 78 km/h → still drifts off at `trackPos −2.1`. Added cap at 60 km/h as first conservative value.

Both zones share the same mechanism: the ±4° sensor cone on a sweeping downhill corner reads the outside wall at full range, giving a falsely large `ahead` value → `safe_kmh` is too high → car arrives too fast.

**Changes made:**
```python
# Zone A — revert cap 50 → 40 km/h
if 2390.0 <= dist <= 2491.0:
    target_speed = min(target_speed, 40.0)

# Zone B — new cap at 60 km/h (conservative first value)
if 3220.0 <= dist <= 3340.0:
    target_speed = min(target_speed, 60.0)
```

**All other settings unchanged:** margin=0.89, pre-zone steer gain 0.15 (2290–2390 m), yaw-realignment gate, `decel_g=16`.

**Prediction:**
- Zone A: no recovery fires (40 km/h was clean in exp-21)
- Zone B: car arrives at ≤60 km/h at dist 3220; lookahead braking handles the apex from there
- Lap time: slower than exp-21 (02:05:54) due to second zone penalty, but clean/damage-free
- Once both zones confirmed clean: raise Zone B cap in 10 km/h steps; separately raise Zone A

| Metric | Before (exp-25) | After |
|---|---|---|
| Lap time | *(completed)* | **02:40:53** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 209.8 km/h | **209.3 km/h** |
| Recovery fired? | Yes (Zone A) | **Yes (both zones)** |
| **Kept?** | | **No — caps not firing at entry; advanced to exp-27** |

**Root cause from telemetry (run `20261010_103527Z`):**
- Zone A entry (`dist 2390`): car doing **137 km/h** — cap was set exactly at the danger geometry entry. The braking formula needs ~200 m of braking distance from 137 km/h to reach 40 km/h. The cap limit (`target_speed = 40`) fired, but the car entered the corner still at full speed (198 rows above 40 km/h in the zone).
- Zone B entry (`dist 3220`): car doing **150 km/h** — same problem. 99 rows above 60 km/h in the zone. Car drifted to `trackPos −3.2` before recovery triggered; lap completed thanks to yaw-fix but with large time penalty.
- **Fix:** Start each cap 200 m **before** the danger geometry so the braking run-in occurs before the car reaches the corner. Applied in exp-27.

---

### v1-experiment-27 — Extend both zone caps 200 m earlier

**File:** `snakeoil3_v2.py`
**Lines changed:** Zone A start `2390 → 2190`, Zone B start `3220 → 3020`

**Motivation:** Telemetry from exp-26 confirmed the caps were firing too late. At 137 km/h the car needs ~200 m to decelerate to 40 km/h (using `decel_g=16`: `v²/(2a) = (137/3.6)² / (2×16) ≈ 113 m` — so 200 m is generous). Starting the cap 200 m before the danger zone gives the braking formula enough runway to actually bring the car down before the problematic geometry.

**Changes made:**
```python
# Zone A cap — extended 200 m earlier (2190 → 2491)
if 2190.0 <= dist <= 2491.0:
    target_speed = min(target_speed, 40.0)

# Zone B cap — extended 200 m earlier (3020 → 3340)
if 3020.0 <= dist <= 3340.0:
    target_speed = min(target_speed, 60.0)
```

**All other settings unchanged:** margin=0.89, pre-zone steer (2290–2390, gain 0.15), yaw-realignment gate, `decel_g=16`.

**Prediction:**
- Car enters Zone A geometry at ~40 km/h — no drift, no recovery
- Car enters Zone B geometry at ~60 km/h — no drift, no recovery
- Lap time: will be slower on the approach straights (cap fires 200 m earlier), but recovery-free laps are much faster than recovery laps overall
- Once confirmed clean: shorten the run-in distances to recover straight-line time

| Metric | Before (exp-26) | After |
|---|---|---|
| Lap time | 02:40:53 | *(fill in after run)* |
| Damage | 0 | *(fill in after run)* |
| Top speed | 209.3 km/h | *(fill in after run)* |
| Recovery fired? | Yes (both) | *(fill in after run)* |
| **Kept?** | | **No — car spun in tight circles then froze in yaw-gate; advanced to exp-28** |

**Root cause from telemetry (run `20261010_104745Z`):**
- Zone A entry: recovery fires at step 3789 (`trackPos 1.616`, `speedX 8.8 km/h`). Reversal steer = `clip(-1.62, -1, 1) = -1.0` (hard lock). Car pivots in a tight circle near dist 2522–2524 m instead of reversing in an arc back toward the track. `trackPos` never drops below 1.0.
- After ~400 recovery steps, `trackPos` reaches ~0.82 (barely on-road) and yaw-gate activates: `angle=-1.60 rad`, `track[9]=1.06 m`. Gate commands `accel=0.3, gear=1`. Car drives into a wall 1 m ahead and freezes; final 60 000+ steps are frozen (`speedX=14.2`, no position change — simulator physics lock).

---

### v1-experiment-28 — Fix recovery steer + yaw-gate clearance guard

**File:** `snakeoil3_v2.py`
**Lines changed:** Recovery steer formula (line ~1112); yaw-gate condition (line ~1124); new no-clearance fallback branch.

**Motivation:** Two independent bugs caused the total stuck in exp-27:
1. **Recovery steer too aggressive:** `clip(-trackPos, -1, 1)` with `trackPos=1.62` → `steer=-1.0` (full lock) caused the car to spin in circles rather than reverse in an arc back to the road.
2. **Yaw-gate ignores wall ahead:** The `abs(angle) > 0.3` gate commanded forward drive without checking whether `track[9]` (dead-ahead distance) had clearance. After a recovery that left the car pointing into the gravel trap wall (`track[9] ≈ 1 m`), it slowly nosed into the barrier and the simulator froze.

**Changes made:**
```python
# Recovery steer — gentler arc (exp-28)
R['steer'] = clip(-S['trackPos'] * 0.5, -0.7, 0.7)

# Yaw gate — forward only with clearance (exp-28)
elif abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0 and S['track'][9] > 3.0:
    R['gear']  = 1
    R['accel'] = 0.3
    R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)
elif abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0 and S['track'][9] <= 3.0:
    # No clearance ahead — reverse to make room first
    R['gear']  = -1
    R['accel'] = 0.4
    R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)
```

**All other settings unchanged:** margin=0.89, zone caps, pre-zone steer, `decel_g=16`.

**Prediction:**
- Recovery backs in a wider arc (steer 0.5 at trackPos 1.0) → car re-enters road in 1–2 s instead of spinning for 400 steps
- Yaw gate waits for `track[9] > 3 m` before driving forward → no wall-freeze
- No-clearance fallback reverses until space exists, then yaw-gate takes over
- Lap should complete without simulator freeze

| Metric | Before (exp-27) | After (run 1) | After (run 2) |
|---|---|---|---|
| Lap time | DNF (frozen) | **02:25:96** ✅ | **02:21:62** ✅ |
| Damage | 0 | **0** ✅ | **0** ✅ |
| Top speed | — | **208.0 km/h** | **207.7 km/h** |
| Recovery fired? | Yes (stuck) | **Yes (21 ep, 550 steps)** | **Yes (21 ep, ~550 steps)** |
| **Kept?** | | **Partial — lap completes but 24-s slow crawl at Zone A exit; advanced to exp-29** | |

**Root cause from telemetry (run `20261010_171009Z`):**
- Recovery fires correctly at Zone A (step 3775, `trackPos 1.55`) and the wider-arc steer works: car returns to road in 219 steps (~4.4 s, down from infinite in exp-27).
- However, after the reversal the car exits at `angle ≈ -1.65 rad` (95° yaw), `trackPos ≈ -0.45`, rolling backward at -14 km/h. The yaw gate activates (`track[9] = 8.7 m > 3`, `abs(trackPos) < 1`), applies `accel=0.3, gear=1` — but the gentle forward throttle merely fights the -14 km/h backward inertia for ~100 steps before the car stops and re-aligns. During this 100-step interval the car slowly slides further into the sweeper, triggering more recoveries. Total time in the Zone A region: 1198 steps = **24 seconds**.
- **Fix:** when `speedX < -1` inside the yaw gate, brake hard first (`brake=0.8`) to arrest the backward roll before engaging forward crawl. Applied in exp-29.

---

### v1-experiment-29 — Yaw gate: brake first when rolling backward

**File:** `snakeoil3_v2.py`
**Lines changed:** yaw-gate forward-clearance branch — added `speedX < -1` sub-condition.

**Motivation:** In exp-28 the car exited Zone A recovery rolling backward at -14 km/h with angle -1.65 rad. The yaw gate applied `accel=0.3, gear=1` which took ~100 steps to fight the inertia, during which the car continued sliding backward through the sweeper, triggering further recovery cycles. Total cost: 24 s of low-speed oscillation. Fix: inside the yaw gate, if `speedX < -1`, apply `brake=0.8` first until the car stops, then the next pass through the gate applies forward crawl as before.

**Changes made:**
```python
elif abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0 and S['track'][9] > 3.0:
    if S['speedX'] < -1.0:           # still rolling backward — stop first
        R['gear']  = 1
        R['accel'] = 0.0
        R['brake'] = 0.8
        R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)
    else:
        R['gear']  = 1
        R['accel'] = 0.3
        R['brake'] = 0.0
        R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)
```

**All other settings unchanged:** margin=0.89, zone caps, pre-zone steer, recovery steer cap 0.7, `decel_g=16`.

**Prediction:**
- Backward roll arrested in 3–5 steps instead of 100 → saves ~2 s per recovery event
- Fewer cascading re-recovery events at Zone A exit → 24 s penalty should drop to < 5 s
- No change outside recovery/yaw-gate logic → straight-line performance unchanged

| Metric | Before (exp-28 run 2) | After |
|---|---|---|
| Lap time | 02:21:62 | **02:04:70** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 207.7 km/h | **207.5 km/h** |
| Recovery fired? | Yes (21 ep, ~24 s penalty) | **Yes (1 ep, 5 steps, 0.1 s) + 7.6 s wall-creep** |
| **Kept?** | | **Partial — yaw-gate no-clearance branch fires at 73 km/h mid-corner; advanced to exp-30** |

**Root cause from telemetry (run `20261010_171833Z`):**
- The brake-first fix worked perfectly for backward-rolling recovery.
- However the yaw-gate **no-clearance branch** (`track[9] ≤ 3.0`) fired at step 3701 when `speedX = 73.6 km/h`, `angle = -0.31 rad`, `track[9] = 2.86 m`. This is normal corner geometry — the outside wall reads short when the car is drifting wide. The branch commanded `gear=-1, accel=0.4` at full speed, firing the no-clearance reverse into the sweeper.
- After 5 reverse steps the car re-entered the road but with `trackPos = 0.95`, still braking. It crossed `trackPos > 1.0` at step 3709 with `speedX = 69 km/h`. The lookahead `track[9]` was blank (wall dead ahead), so `target_speed = 10 km/h` (floor). The off-track recovery needed `speedX < 8` but the car was doing 10 km/h — just above threshold. Result: 379 wall-creep steps (7.6 s) at 10 km/h along the outside wall.
- **Root fix:** add a `speedX < 15` guard to all yaw-recovery branches. At high speed, normal lookahead handles the corner; yaw-recovery is only valid when nearly stopped. Also raise off-track recovery threshold from `< 8` to `< 15` to catch the 10 km/h wall-creep case. Applied in exp-30.

---

### v1-experiment-30 — Speed guard on yaw-recovery block + raise off-track threshold

**File:** `snakeoil3_v2.py`
**Lines changed:** `speedX < 8` → `speedX < 15` (off-track recovery); `abs(speedX) < 15` guard added to both yaw-gate elif branches.

**Motivation:** The yaw-recovery block fired mid-corner at 73 km/h (exp-29), and the wall-creep at 10 km/h was never caught by the off-track recovery (threshold was 8 km/h). Both problems share one root: the recovery logic had no speed guard and treated high-speed corner drift the same as a stopped post-recovery situation.

**Changes made:**
```python
# Off-track recovery — raised threshold 8 → 15 km/h
if S['speedX'] < 15 and off_track:
    ...

# Yaw-gate — speed guard added (only active when nearly stopped)
elif abs(S['speedX']) < 15 and abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0 and S['track'][9] > 3.0:
    ...
elif abs(S['speedX']) < 15 and abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0 and S['track'][9] <= 3.0:
    ...
```

**All other settings unchanged:** margin=0.89, zone caps, pre-zone steer, recovery steer cap 0.7, `decel_g=16`.

**Prediction:**
- No yaw-recovery at speed → no mid-corner reverse event → car exits Zone A cleanly
- Wall-creep at 10 km/h caught by `speedX < 15` off-track recovery → immediate reverse-back
- If the car gets genuinely stuck (speedX < 15) after a high-speed off-track, recovery still fires

| Metric | Before (exp-29) | After |
|---|---|---|
| Lap time | 02:04:70 | **01:55:24** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 207.5 km/h | **207.5 km/h** |
| Recovery fired? | Yes (wall-creep 7.6 s) | **0 episodes, 0 s** ✅ |
| **Kept?** | | **Partial — Zone B costs 14.6 s (coasting 101→60 km/h); advanced to exp-31** |

**Root cause from telemetry (run `20261010_172746Z`):**
- Zone A: **clean transit, 1.6 s** ✅. Speed guard fully prevents yaw-gate from firing at speed.
- Zone B (dist 3020–3340): car enters at 101 km/h. Cap sets `target_speed=60`. But `speedX (101) ≤ safe_kmh (288)` → coast branch (accel=0, brake=0). Car decelerates from drag alone for **504 steps = 10.1 s** before reaching 60 km/h at dist 3268. Total Zone B time: 731 steps = 14.6 s at avg 73.2 km/h. A clean 60-km/h transit would take ~320 steps = 6.4 s — 8 seconds wasted.
- **Root fix:** eliminate the coast branch. When `speedX > target_speed`, always brake proportionally. Applied in exp-31.

---

### v1-experiment-31 — Active braking when over zone cap (eliminate coast branch)

**File:** `snakeoil3_v2.py`
**Lines changed:** throttle/brake logic — removed `elif speedX <= safe_kmh: coast` branch; replaced with `else: brake ∝ (speedX − target_speed)`.

**Motivation:** The braking formula's middle branch (`elif speedX <= safe_kmh: accel=0, brake=0`) coasted when the car was between target speed and the lookahead safe speed. On a long straight into Zone B, `safe_kmh = 288 km/h` while `target_speed = 60 km/h` — the car coasted from 101 → 60 km/h under drag alone for 10 s. Removing the coast branch means the car actively brakes any time it is above target, which handles both zone caps and regular lookahead corners identically.

**Changes made:**
```python
# Before (three branches):
if speedX <= target_speed:   throttle
elif speedX <= safe_kmh:     coast (brake=0)  ← REMOVED
else:                        brake ∝ (speedX - safe_kmh)

# After (two branches):
if speedX <= target_speed:   throttle
else:                        brake ∝ (speedX - target_speed)
```

**All other settings unchanged:** margin=0.89, zone caps, pre-zone steer, recovery/yaw-gate, `decel_g=16`.

**Prediction:**
- Zone B: car brakes from 101 → 60 km/h in ~16 m (~1.4 s) instead of coasting for 10 s
- Zone A: already clean — no change expected
- Straight-line performance: no change (cap not active on straights)
- Risk: this also applies on non-cap corners where `speedX > target_speed` — the lookahead brake previously coasted when `safe_kmh > speedX`; now it brakes. This should be fine (braking more when above target is correct), but may slightly reduce speed before some corners where the original coast was intentional.

| Metric | Before (exp-30) | After |
|---|---|---|
| Lap time | 01:55:24 | **02:17:06** ❌ |
| Damage | 0 | **0** |
| Top speed | 207.5 km/h | **206.2 km/h** |
| Recovery fired? | 0 episodes | **0 episodes** |
| **Kept?** | | **No — global active-brake over-braked every corner; reverted in exp-32** |

**Root cause from telemetry (run `20261010_173535Z`):**
- `brake ∝ (speedX − target_speed)` fires at every corner where `speedX > target_speed`. On the Zone A approach at dist 2190, car doing 192 km/h → target=40 km/h → `(192-40)/35 = 4.34 → brake=1.0` (full lock). Every corner approach also over-braked: e.g. at dist 400-600 avg dropped -3.7 km/h, dist 1400-1600 -7.7 km/h, etc. Total braking steps: 94,404 = **1888 s** (vs ~300 s on exp-30). 22 s slower overall.
- **Fix:** active braking is only needed when a zone cap is in force. For normal lookahead corners, the coast branch (`speedX ≤ safe_kmh → coast`) is correct. Applied in exp-32 using an `in_cap` flag.

---

### v1-experiment-32 — Cap-only active braking (revert exp-31, target only zones)

**File:** `snakeoil3_v2.py`
**Lines changed:** throttle/brake logic — `in_cap` flag set inside zone-cap blocks; new `elif in_cap:` brake branch inserted before the restored coast branch.

**Motivation:** exp-31 showed the coast branch removal over-braked everywhere. The correct fix is narrower: active braking only when inside a zone cap where `safe_kmh ≫ target_speed`.

**Changes made:**
```python
in_cap = False
if 2190.0 <= dist <= 2491.0: target_speed = min(target_speed, 40.0); in_cap = True
if 3020.0 <= dist <= 3340.0: target_speed = min(target_speed, 60.0); in_cap = True

if speedX <= target_speed:       throttle
elif in_cap:                     brake ∝ (speedX − target_speed)  ← cap zones only
elif speedX <= safe_kmh:         coast                              ← normal lookahead
else:                            brake ∝ (speedX − safe_kmh)       ← over safe speed
```

**Prediction:**
- Zone B: brakes 101 → 60 km/h in ~1.4 s (same as exp-31 intended)
- Zone A: brakes 192 → 40 km/h in ~56 m before danger geometry
- All other corners: coast branch restored → same behaviour as exp-30

| Metric | Before (exp-31) | After |
|---|---|---|
| Lap time | 02:17:06 | **02:13:91** ❌ |
| Damage | 0 | **0** |
| Top speed | 206.2 km/h | **207.5 km/h** |
| Recovery fired? | 0 episodes | **0 episodes** |
| **Kept?** | | **No — Zone A crawled 40 km/h for 240 m (13 s); zone starts too early; advanced to exp-33** |

**Root cause from telemetry (run `20261010_174315Z`):**
- Zone A: cap fires at dist 2190, car doing 194 km/h. Active brake brings car to 40 km/h by dist 2250. Car then crawls at 40 km/h for the remaining 241 m (dist 2250–2491) = **13 extra seconds**. With active braking, the 86 m stopping distance makes the 301 m run-in massively oversized.
- Zone B: similar — car enters at 95 km/h at dist 3020, reaches 60 km/h by dist 3033 but the cap region extends to 3340, so the car crawls at 60 km/h for 307 m = 3.7 extra seconds.
- **Fix:** shrink Zone A start 2190 → 2305 m (leaving 86 m runway before danger at 2391); shrink Zone B start 3020 → 3200 m (leaving 20 m before danger at 3220). Applied in exp-33.

---

### v1-experiment-33 — Shrink cap zone starts to match active-braking runway

**File:** `snakeoil3_v2.py`
**Lines changed:** Zone A start `2190 → 2305`, Zone B start `3020 → 3200`.

**Motivation:** exp-32 introduced active braking inside caps, but the zone starts were sized for the old coast-based deceleration (needed 200 m). With active braking at `decel_g=16`, Zone A only needs ~86 m and Zone B needs ~14 m. Starting 300 m early caused unnecessary crawling.

**Changes made:**
```python
if 2305.0 <= dist <= 2491.0:  # Zone A (was 2190)
    target_speed = min(target_speed, 40.0); in_cap = True
if 3200.0 <= dist <= 3340.0:  # Zone B (was 3020)
    target_speed = min(target_speed, 60.0); in_cap = True
```

**Prediction:**
- Zone A: brakes from ~194 km/h to 40 km/h in ~86 m → enters danger at ~40 km/h, exits promptly
- Zone B: brakes from ~95 km/h to 60 km/h in ~14 m → minimal crawl at 60 km/h
- Combined saving vs exp-32: ~13 + 3.7 = ~17 s → target ~01:57
- Risk: if entry speed is higher than modelled, car may be above 40/60 at danger geometry — monitor

| Metric | Before (exp-32) | After |
|---|---|---|
| Lap time | 02:13:91 | **01:57:99** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 207.5 km/h | **209.9 km/h** ✅ |
| Recovery fired? | 0 episodes | **0 episodes** ✅ |
| **Kept?** | | **Partial — Zone A cap end at 2491 causes 136 m crawl at 40 km/h (~4 s); advanced to exp-34** |

**Root cause from telemetry (run `20261010_181736Z`):**
- Zone A: car enters at 198 km/h at dist 2305. Active brake reaches 40 km/h by dist 2355. Crawls at 40 km/h from dist 2355 → 2491 = **136 m = ~12 s**. But the dangerous geometry (Corkscrew apex) is only at dist ~2410. The cap end at 2491 was originally set for coast-based deceleration which never fully reached 40 km/h; with active braking the cap end is now a hard constraint, costing 4–5 extra seconds.
- Zone B: 7.6 s (exp-30 was 7.9 s) — essentially identical ✅.
- **Fix:** shorten Zone A cap end 2491 → 2420. Beyond 2420, lookahead handles it. Applied in exp-34.

---

### v1-experiment-34 — Shorten Zone A cap end (2491 → 2420)

**File:** `snakeoil3_v2.py`
**Lines changed:** Zone A cap end `2491.0 → 2420.0`.

**Motivation:** With active braking the car reaches 40 km/h before the apex (dist ~2355), then crawls for 136 m to the old cap end. The Corkscrew danger zone ends by dist ~2420; beyond that the lookahead formula naturally slows for the exit chicane if needed.

**Prediction:**
- Zone A: crawl reduced from 136 m to ~65 m → saves ~4 s
- Remaining gap to exp-30 (01:55:24): ~0.75 s unexplained — may be stochastic or from Zone A cap still being slightly long

| Metric | Before (exp-33) | After |
|---|---|---|
| Lap time | 01:57:99 | **DNF** ❌ |
| Damage | 0 | **38** |
| Top speed | 209.9 km/h | **207** |
| Recovery fired? | 0 episodes | **N/A — off-track before recovery engaged** |
| **Kept?** | | **No — new failure mode; advanced to exp-35** |

**Root cause from telemetry (session `268b13dc`):**
- New failure at dist **~2040–2070 m** — a pre-Corkscrew left-hand sweeper, unrelated to the Zone A cap.
- Car arrives at `trackPos = -0.82` (left of centre) at **107 km/h**.
- `forward_track` drops to 5.6 m → `safe_kmh = 48`, full brake fires (`brake = 1.0`).
- Steer correction: `angle*5/PI − trackPos*0.25 = 0.313 + 0.205 = 0.518`. Steering right ✅, but the gain of 0.25 at trackPos -0.82 gives only 0.205 correction.
- At 107 km/h + full brake, lateral momentum carries the car left. `trackPos` goes −1.0 → −1.6 while braking.
- Off-track recovery requires `speedX < 15 km/h` — never fires at 90 km/h.
- Car brakes along the dirt for ~70 m then hits the barrier (damage = 38), freezes.
- **Fix:** increase trackPos steer gain `0.25 → 0.40` for stronger centre-pull on wide-tracking corners.

---

### v1-experiment-35 — Increase trackPos steer gain (0.25 → 0.40)

**File:** `snakeoil3_v2.py`
**Line changed:** `R['steer'] -= S['trackPos'] * 0.40`  (was `0.25`)

**Motivation:** exp-34 failed at a pre-Corkscrew sweeper (~dist 2050 m). The car arrived left of centre at 107 km/h, the steer correction at gain=0.25 was insufficient to prevent the car drifting further left under full braking. Increasing to 0.40 provides 60% stronger centre-pull at wide positions. At trackPos=1.0 the correction is 0.40 (within [-1,1] steer range); at trackPos=0.2 (normal straight) the correction is only 0.08 — minimal effect on fast straights.

**Prediction:**
- Sweeper at dist 2050 stays on-track: trackPos −0.82 → correction 0.328 (was 0.205)
- All corners get stronger centre-pull → car should stay more centred throughout
- Lap time: ~01:55–01:58 (same order as exp-33; also retains exp-34 zone end fix)
- Risk: stronger gain may over-steer on tight corners — watch for oscillation

| Metric | Before (exp-34) | After |
|---|---|---|
| Lap time | DNF | **DNF** ❌ |
| Damage | 38 | **2** |
| Top speed | 207 km/h | **208 km/h** |
| Recovery fired? | N/A | **Yes — yaw-gate reverse branch froze at dist 2484** |
| **Kept?** | | **No — new spin failure at Zone A exit; advanced to exp-36** |

**Root cause from telemetry (session `c4ccdb68`):**
- Pre-Corkscrew sweeper (dist 2050) now **survived** — stronger steer gain worked ✅
- New failure: Zone A cap exits at dist 2420 with `trackPos = -0.80` at **39.8 km/h**.
- The exit of the Corkscrew (dist ~2420–2490) curves RIGHT. The car is left of centre with no speed — angle spins: `-0.57 rad` at dist 2477 → `-1.70 rad` at dist 2482 → car nearly 180° sideways.
- Car freezes at dist 2484 with `angle = 1.635 rad` (93°), `forward_track = 2.7 m`.
- Yaw-gate `track[9] ≤ 3.0` branch fires (gear=-1, accel=0.4) and sits there.
- **Fix:** extend Zone A cap end 2420→2450 + extend steer correction through cap zone (2290→2450) to pull car to centre while still at 40 km/h before the exit corner.

---

### v1-experiment-36 — Fix Zone A exit spin (cap end 2420→2450, steer correction extended)

**File:** `snakeoil3_v2.py`
**Lines changed:**
- Steer correction range: `2290–2390` → `2290–2450`
- Zone A cap end: `2420.0` → `2450.0`

**Motivation:** exp-35 revealed that the car exits Zone A cap at trackPos -0.80 at only 40 km/h, then immediately encounters a right-hand exit corner (dist ~2470). The car spins sideways and freezes. Extending the cap and steer correction by 30 m keeps the car centred (trackPos → 0) before it hits the exit corner.

**Prediction:**
- Car exits Zone A centred (trackPos ~0) at 40 km/h at dist 2450
- Exit corner at 2470+ handled cleanly by lookahead formula
- Lap time: ~01:56–01:59 (slight regression from extra 30 m at 40 km/h = ~0.75 s)
- Damage: 0

| Metric | Before (exp-35) | After |
|---|---|---|
| Lap time | DNF | **DNF** ❌ |
| Damage | 2 | **0** ✅ |
| Top speed | 208 km/h | **209 km/h** |
| Recovery fired? | Yes | **Yes — yaw-gate reverse branch froze at dist 2485** |
| **Kept?** | | **No — same spin location, different cause; advanced to exp-37** |

**Root cause from telemetry (session `bd193b20`):**
- exp-36 **did** pull the car to centre: `trackPos = -0.28` at dist 2450 ✅ (vs -0.80 in exp-35)
- Damage dropped to **0** ✅ — no wall contact this time
- But the spin still happened at dist ~2476: `angle → -0.55 rad` at dist 2477, then rapidly to -1.70 rad
- Cause: at dist 2450 Zone A cap ends → lookahead takes over → `ahead = max(track[6:15])` wide cone reads **34 m** at dist 2471 (road curves right, wide sensors see longer) while `track[9]` (straight-ahead) shows only **10 m**. False-high `safe_kmh` → `accel=1.0` → car rockets 40→58 km/h in 25 m into the chicane exit corner
- **Fix:** add Zone C cap (dist 2450–2510, 55 km/h) to prevent the wide-cone false-acceleration through the exit chicane

---

### v1-experiment-37 — Add Zone C cap for Corkscrew exit chicane (dist 2450–2510, 55 km/h)

**File:** `snakeoil3_v2.py`
**Lines added:**
```python
if 2450.0 < dist <= 2510.0:
    target_speed = min(target_speed, 55.0)
    in_cap = True
```

**Motivation:** exp-36 exposed that the wide-cone lookahead (`max(track[6:15])`) over-reads clearance at the Corkscrew exit chicane (dist 2450–2495). The road curves right but off-axis sensors see farther, causing the car to accelerate from 40→58 km/h right into the sharp bend. A 55 km/h cap with `in_cap=True` bypasses the wide-cone formula and holds the car controlled through the chicane.

**Prediction:**
- Car exits Zone A → enters Zone C at 40 km/h, caps at 55 km/h through dist 2510
- No more exit chicane spin
- Lap time: ~01:57–02:00 (two sequential caps through dist 2305–2510 = ~205 m at 40–55 km/h)
- Damage: 0

| Metric | Before (exp-36) | After |
|---|---|---|
| Lap time | DNF | **DNF — max_steps (multiple runs, all partial)** |
| Damage | 0 | **0** ✅ |
| Top speed | 209 km/h | **209.4 km/h** |
| Max distRaced | ~2485 m | **3618 m** ✅ |
| Recovery fired? | Yes | **No — Zone A clean, Zone B clean** |
| **Kept?** | | **Partial — car survives all three zones but never completes lap (max_steps exhausted); advanced to exp-38** |

**Observations from telemetry (8 runs, all `exp-37-zone-a-exit-chicane-cap`, damage = 0 on every run):**
- Zone A (2305–2450): cap fires correctly, car exits at ~40 km/h with no spin, no recovery ✅
- Zone C (2450–2510): 55 km/h cap holds the exit chicane cleanly ✅
- Zone B (3200–3340): 60 km/h cap survives, max distRaced 3618 m (well past Zone B exit) ✅
- **Root limitation:** 3 hard zones capping at 40/55/60 km/h cost ~30+ s of lap time each cycle. The underlying problem is the wide-cone sensor (`max(track[6:15])`) over-reading clearance on sweeping corners and falsely accelerating the car. Advanced to exp-38 to fix the root-cause sensor rather than adding more caps.

---

### v1-experiment-38 — Dual-layer forward sensor, no hard zone caps

**File:** `snakeoil3_v2.py`  
**EXP_TAG:** `exp-38-dual-sensor-no-caps`

**Motivation:** exp-37 (Zone C cap) confirmed the car can survive all three problem zones (A/B/C) with zero damage, but the three hard caps at 40/55/60 km/h accumulate enough time penalty that the car cannot complete the lap within `maxSteps = 100,000`. The root cause of needing those caps is the wide-cone sensor (`max(track[6:15])`) over-reading clearance on sweeping corners — it sees open road along off-axis angles while the car's actual path curves into a wall. The fix is to correct the sensor, not add more caps.

**Changes made:**

```python
# Before (exp-37) — wide-cone prone to over-reading on curves
ahead = max(max(S['track'][6:15]), 0.0)

# After (exp-38) — dual-layer sensor
straight_read  = max(t[7], t[8], t[9], t[10], t[11], 0.0)  # ±1° central cone
corner_warning = min(max(t[4], 0.0), max(t[14], 0.0))       # ±4° early-warning
ahead          = max(min(straight_read, corner_warning), 0.0)
```

- `straight_read`: max of the five tightest forward sensors (±1°). Stays high on a straight (correct, full throttle), drops quickly when a wall appears dead ahead.
- `corner_warning`: minimum of the two ±4° sensors. Drops early when the road curves — one side will shorten before the 0° sensor does. This provides the corner-entry warning the wide-cone gave, without the false-high reading from the far off-axis sensors.
- `ahead = min(both)`: takes the conservative value. On a straight: `straight_read` is large and `corner_warning` is large → both high, unrestricted. On a curve: `corner_warning` drops first, pulling `ahead` down early.

**Also changed:**
- TC threshold raised: 5 → 15 above 100 km/h (old value cut throttle on every straight)
- Gear 7 added (> 175 km/h) for the 7-gear car1-ow1
- Safety margin 0.89 → 0.94 (wider sensor now trustworthy for higher margin)
- Speed ceiling 250 → 320 km/h
- Throttle band 20% → 6% (full throttle sooner on straights)
- All three hard zone caps (A/B/C) removed — dual sensor should handle those corners via lookahead

**Prediction:**
- Zone A/B/C corners handled correctly by lookahead without caps
- Top speed: rises toward 200+ km/h (margin 0.94 + wider ceiling)
- Lap time: sub-02:00 possible — no cap penalties
- Damage: 0

| Metric | Before (exp-37) | After |
|---|---|---|
| Lap time | DNF (max_steps) | **DNF — max_steps at ~88 s, distRaced 2500 m** |
| Damage | 0 | **0** ✅ |
| Top speed | 209.4 km/h | **173.3 km/h** ❌ |
| Max distRaced | 3618 m | **2500 m** ❌ |
| Recovery fired? | No | **No** ✅ |
| **Kept?** | | **No — sensor too conservative; Zone A still drifts; advanced to exp-39** |

**Observations from telemetry (run `20261011_150118Z_2b51a069`, 4044 steps, 88 s elapsed):**

- Top speed dropped from 209 → 173 km/h: `corner_warning = min(t[4], t[14])` is significantly more conservative than expected. The two ±4° sensors also clip on sweeping corners, pulling `ahead` below the level the wide-cone would have read. This over-brakes on fast sections that were previously clean.
- Zone A entry (dist ~2305): car arrives at ~57 km/h (was 198 km/h with old sensor + caps). The dual sensor is braking far earlier — correctly, but excessively.
- `trackPos` in Zone A: drifts −0.26 → −0.97 between steps 4025–4044 at 32–37 km/h. The car is still drifting wide at low speed — this is a steering/line problem at this corner independent of speed. The dual sensor alone does not prevent the drift.
- The run hit `max_steps` while crawling in the Zone A section — the car had not yet exited the Corkscrew area.
- **Root finding:** `corner_warning = min(t[4], t[14])` is too restrictive. The ±4° sensors see obstacles earlier than needed and pull the combined `ahead` well below the safe value on sections that were handled cleanly in exp-37. The dual-sensor concept is sound but the `corner_warning` floor is too low.

---

### v1-experiment-39 — Restore Zone A/B/C caps; fix sensor over-conservatism; raise maxSteps

**File:** `snakeoil3_v2.py`  
**EXP_TAG:** `exp-39-caps-restored`

**Motivation:** exp-38 confirmed that removing the hard caps entirely is not viable — the Zone A drift is a geometric property of this corner and cannot be solved by the lookahead formula alone. exp-37 confirmed that the caps DO work (0 damage, distRaced 3618 m). The only reason exp-37 never completed a lap is `maxSteps = 100,000` (~2000 s at 50 Hz) being exhausted by the cumulative zone penalties. The lap is approximately 115 s at normal pace; the caps add ~30 s → target ~145 s → needs ~7250 steps/lap → well within 100,000. The reason exp-37 hit max_steps was that the recorder's lap detection missed the finish (distRaced non-monotonic during reversal), causing the client loop to keep running past lap end.

**Root cause of max_steps exhaustion:** The `main` loop in `snakeoil3_v2.py` runs `for step in range(C.maxSteps, 0, -1)`. When the TORCS server sends `***shutdown***` after the race ends, `get_servers_input()` calls `self.shutdown()` and sets `self.so = None`, but the loop keeps iterating through the remaining 90,000+ steps calling `get_servers_input()` (which returns immediately when `self.so is None`) and `respond_to_server()` (same). The race is over but Python keeps looping. **Fix:** break the loop when `C.so is None` after `get_servers_input()`.

**Changes made:**

#### Change 1 — Restore exp-37 zone caps (revert exp-38 cap removal)
```python
# Restored Zone A, B, C caps (exp-37 values, proven clean):
if 2305.0 <= dist < 2450.0:   target_speed = min(target_speed, 40.0); in_cap = True
if 2450.0 < dist <= 2510.0:   target_speed = min(target_speed, 55.0); in_cap = True
if 3200.0 <= dist <= 3340.0:  target_speed = min(target_speed, 60.0); in_cap = True
```

#### Change 2 — Restore exp-37 wide-cone sensor (revert exp-38 dual sensor)
```python
# Restored (exp-37):
ahead = max(max(S['track'][6:15]), 0.0)
```
The dual-sensor was too conservative. Wide-cone with the zone caps is the proven-working combination.

#### Change 3 — Break main loop on server shutdown
```python
# After C.get_servers_input():
if not C.so:
    break
```
Stops Python from looping after the server has ended the race.

#### Change 4 — Revert exp-38 parameter changes back to exp-37 baseline
```python
decel_g      = 16.0          # was 16 in exp-37 (exp-38 kept it)
margin       = 0.89          # restore exp-37 value (exp-38 raised to 0.94 — too aggressive without caps)
ceiling      = 250           # restore exp-37 ceiling
throttle_band = 0.10         # restore exp-37 value (was 6% in exp-38)
# TC threshold stays at 5 always (exp-37 baseline value)
# Gear 7 KEEP — exp-37 only had 6 gears; car1-ow1 has 7, no downside to adding it
```

**Prediction:**
- Car behaviour through Zones A/B/C: identical to exp-37 (proven clean, 0 damage)
- Lap completion: when TORCS sends `***shutdown***` at race end, the loop breaks immediately → no max_steps exhaustion
- Lap time will be recorded correctly by TORCS even if the recorder misses (TORCS result screen is authority)
- Damage: 0
- Max speed: ~209 km/h (same as exp-37)

**Rollback plan:** if any zone triggers damage after cap restoration, exp-37 caps were clean → the regression is from a parameter change, not the caps themselves. Revert parameters one at a time.

| Metric | Before (exp-38) | Run 1 | Run 2 | Run 3 | Run 4 |
|---|---|---|---|---|---|
| Lap time | DNF (max_steps 88 s) | **01:54:60** ✅ | **01:55:72** ✅ | **01:54:62** ✅ | **01:54:66** ✅ |
| Damage | 0 | **0** ✅ | **0** ✅ | **0** ✅ | **0** ✅ |
| Top speed | 173.3 km/h | **205 km/h** | **202 km/h** | **206 km/h** | **204 km/h** |
| File | — | `snakeoil3_v2.py` | `snakeoil3_v1.py` | `snakeoil3_v2.py` | `snakeoil3_v2.py` |
| Loop terminated cleanly? | No (max_steps) | **Yes** ✅ | **Yes** ✅ | **Yes** ✅ | **Yes** ✅ |
| Recorder wrote to gz? | — | partial (old schema) | partial (old schema) | partial (old schema) | **Yes** ✅ |
| **Kept?** | | **Yes — promoted to v1** | **v1 baseline confirmed** | **3rd consecutive clean** | **4th consecutive clean** |

**Observations:**
- All four runs clean: 0 damage, lap completed, loop terminated on `***shutdown***` — no max_steps exhaustion.
- Lap times: 01:54:60 / 01:55:72 / 01:54:62 / 01:54:66 — range 1:12 s, mean ~01:54:90 (normal TORCS stochastic variation).
- Top speeds: 205 / 202 / 206 / 204 km/h — stable band, consistent with exp-37's 209 km/h (margin 0.89 vs 0.89, same zones).
- Run 4 confirmed the `lap_data.csv.gz` header fix — recorder wrote 5,451 rows to gz without error; file grew 3.6 → 3.9 MB.
- Recorder still logs all runs as `partial` — `distRaced` becomes non-monotonic during Zone A recovery near the finish line. TORCS race-results screen remains authoritative. This is a known limitation (see Enhancement 2 in README).
- **exp-39 is the confirmed stable baseline.** 4 consecutive clean laps across both v1 and v2.

---

### v1-experiment-40 — Raise safety margin 0.89 → 0.92 (top-speed lever)

**File:** `snakeoil3_v2.py`  
**EXP_TAG:** `exp-40-margin-092`

**Motivation:** exp-39 stabilised at ~202–206 km/h top speed across four clean laps. The only change from the exp-37 baseline that raised top speed above 209 km/h in the historical record was exp-13, which ran margin 0.92 (among three other changes) and observed 219 km/h. This experiment isolates that single variable to attribute the result cleanly. All zone caps, sensor, decel_g, and steering are unchanged from exp-39.

**Change made:**
```python
# Before (exp-39):
target_speed = clip(safe_kmh * 0.89, 10, 250)

# After (exp-40):
target_speed = clip(safe_kmh * 0.92, 10, 250)
```

**Prediction:**
- Top speed: rises from ~204 km/h toward ~215–220 km/h
- Damage: 0 (zone caps still protect A/B/C)
- Lap time: faster than exp-39 (~01:53–01:54)
- Risk: higher entry speed on fast sweepers where zone caps do not apply; if understeer appears, raise `decel_g` as next step

| Metric | Before (exp-39 avg) | Run 1 |
|---|---|---|
| Lap time | ~01:54:90 | **01:53:66** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | ~204 km/h | **210 km/h** ✅ |
| **Kept?** | | **Yes — clean lap, +6 km/h top speed, lap time −1:24 s vs exp-39 avg** |

**Observations:**
- Clean lap, 0 damage. Top speed 210 km/h — +6 km/h vs exp-39 average (204 km/h), +1 km/h vs exp-39 best (209 km/h).
- Lap time 01:53:66 — fastest recorded lap to date (exp-39 best was 01:54:60).
- Zone caps held correctly: no damage at Corkscrew (Zone A), exit chicane (Zone C), or back hairpin (Zone B).
- margin 0.92 is safe with the current cap configuration. Further top-speed headroom available via decel_g if needed.

---

### v1-experiment-41 — decel_g 16 → 17 + margin 0.92 → 0.95 (push toward 220 km/h)

**File:** `snakeoil3_v2.py`  
**EXP_TAG:** `exp-41-decelg17-margin095`

**Motivation:** exp-40 (margin 0.92, decel_g 16) delivered 210 km/h and a clean 01:53:66 lap — the fastest to date. Two remaining levers can push further: (1) `decel_g 16 → 17` fires the brake trigger later on straights, giving more time at full throttle; (2) `margin 0.92 → 0.95` lets target_speed chase closer to the sensor ceiling. Applied together because both act only on straight-line speed and the zone caps (unchanged) still guard all three dangerous corners. Historical crash risk from exp-13/14 (`decel_g=17`, `margin=0.93`, DNF) does not apply here — those runs had no zone caps; the caps are what make this envelope safe.

**Changes made:**
```python
# Before (exp-40):
decel_g      = 16.0
target_speed = clip(safe_kmh * 0.92, 10, 250)

# After (exp-41):
decel_g      = 17.0
target_speed = clip(safe_kmh * 0.95, 10, 250)
```

**Prediction:**
- Top speed: rises from 210 km/h toward 218–223 km/h
- Damage: 0 (zone caps unchanged; caps are the protection on the three problem corners)
- Lap time: faster than exp-40's 01:53:66
- Risk: if fast sweepers (where no cap applies) produce understeer, revert decel_g first

| Metric | Before (exp-40) | Run 1 |
|---|---|---|
| Lap time | 01:53:66 | **01:51:18** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 210 km/h | **216 km/h** ✅ |
| **Kept?** | | **Yes — clean lap, +6 km/h top speed, fastest lap to date** |

**Observations:**
- Clean lap, 0 damage. Top speed 216 km/h — +6 km/h vs exp-40 (210 km/h), fastest lap to date.
- Lap time 01:51:18 — 2:48 s faster than exp-40 (01:53:66), 3:24 s faster than exp-39 best (01:54:66).
- Zone caps held perfectly. decel_g=17 + margin=0.95 is safe with the current cap configuration.
- Straight-line speed envelope still has headroom; advancing to exp-42 (decel_g=18, margin=0.97).

---

### v1-experiment-42 — decel_g 17 → 18 + margin 0.95 → 0.97 (push toward 220+ km/h)

**File:** `snakeoil3_v2.py`  
**EXP_TAG:** `exp-42-decelg18-margin097`

**Motivation:** exp-41 (decel_g=17, margin=0.95) delivered 216 km/h and 01:51:18 — clean, 0 damage. Continuing the same progression: `decel_g 17 → 18` fires the brake trigger even later on straights; `margin 0.95 → 0.97` brings target_speed within 3% of the sensor ceiling. Historical risk: exp-14 crashed with decel_g=18, but that run had no zone caps and broken recovery logic. Both are fixed. Zone caps (A/B/C) unchanged.

**Changes made:**
```python
# Before (exp-41):
decel_g      = 17.0
target_speed = clip(safe_kmh * 0.95, 10, 250)

# After (exp-42):
decel_g      = 18.0
target_speed = clip(safe_kmh * 0.97, 10, 250)
```

**Prediction:**
- Top speed: rises from 216 km/h toward 220–225 km/h
- Damage: 0 (zone caps unchanged)
- Lap time: faster than exp-41's 01:51:18
- Risk: fast sweepers (no cap applied) — if understeer appears, revert decel_g to 17 first

| Metric | Before (exp-41) | Run 1 |
|---|---|---|
| Lap time | 01:51:18 | **DNF — stalled mid-lap at ~39 s** ❌ |
| Damage | 0 | **0** |
| Top speed | 216 km/h | **189 km/h** ❌ |
| **Kept?** | | **No — decel_g=18 too aggressive; advanced to exp-43 (revert decel_g→17, keep margin=0.97)** |

**Observations:**
- Car ran for ~39 s, reached 189 km/h, then stopped mid-lap with damage 0 — not a crash, a stall.
- Root cause: decel_g=18 delays the brake trigger so far that a brief low `ahead` reading (kink/apex)
  causes emergency braking from ~189 km/h to near zero. Once stopped on track with yaw > 0.3 rad,
  the yaw-recovery branch locks the car in place and it cannot restart.
- decel_g=18 is confirmed as the ceiling with the current wide-cone sensor — 17 is the safe maximum.
- margin=0.97 was not cleanly tested in isolation; exp-43 keeps it with decel_g reverted to 17.

---

### v1-experiment-43 — Revert decel_g 18 → 17; keep margin 0.97 (isolate failure cause)

**File:** `snakeoil3_v2.py`
**EXP_TAG:** `exp-43-decelg17-margin097`

**Motivation:** exp-42 stalled mid-lap: decel_g=18 brakes too hard from a brief low sensor reading, dropping speed to near zero and triggering yaw-recovery lock. Reverting decel_g to 17 (proven clean in exp-41) while keeping margin=0.97 isolates whether margin alone at this level is safe.

**Change made:**
```python
# Before (exp-42):
decel_g      = 18.0
target_speed = clip(safe_kmh * 0.97, 10, 250)

# After (exp-43):
decel_g      = 17.0   # reverted — 18 causes mid-lap stall
target_speed = clip(safe_kmh * 0.97, 10, 250)  # kept
```

**Prediction:**
- Top speed: ~216–219 km/h (decel_g=17 + margin=0.97 vs exp-41's 0.95)
- Damage: 0
- Lap time: ~01:51 or faster
- If DNF again: margin=0.97 is also too high; revert to 0.95 (exp-41 proven safe)

| Metric | Before (exp-42) | Run 1 |
|---|---|---|
| Lap time | DNF | **01:50:61** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 189 km/h (stalled) | **218 km/h** ✅ |
| **Kept?** | | **Yes — clean lap, new fastest, confirmed decel_g=18 was sole failure cause** |

**Observations:**
- Clean lap, 0 damage. Top speed 218 km/h — +2 km/h vs exp-41 (216 km/h). Lap time 01:50:61 — new fastest.
- Confirms decel_g=18 was the sole cause of exp-42's stall; margin=0.97 is safe with decel_g=17.
- margin 0.97 vs 0.95 added only +2 km/h — margin is approaching its ceiling; sensor width is the next lever.
- Advancing to exp-44: widen sensor cone t[6:15] → t[5:16] to raise safe_kmh on sweepers without touching decel_g/margin.

---

### v1-experiment-44 — Widen sensor cone t[6:15] → t[5:16] (more straight-line clearance)

**File:** `snakeoil3_v2.py`
**EXP_TAG:** `exp-44-widercone-5to16`

**Motivation:** margin and decel_g levers are near their ceilings (decel_g=18 stalls; margin=0.97 adds only +2 km/h). The upstream lever is `ahead`: widening the cone from ±4° (indices 6–14) to ±7° (indices 5–15) gives higher `ahead` readings on gentle sweepers where the road curves away from the car's centreline, raising `safe_kmh` and thus `target_speed` on those sections. On full straights all sensors read ~200 m so there's no change. Zone caps remain distance-gated and are unaffected by sensor width.

**Change made:**
```python
# Before (exp-43):
ahead = max(max(t[6:15]), 0.0)   # ±4° wide cone

# After (exp-44):
ahead = max(max(t[5:16]), 0.0)   # ±7° wider cone
```

**Prediction:**
- Top speed: rises toward 220–225 km/h (sweeper sections get higher ahead → less braking)
- Damage: 0 (zone caps still guard A/B/C; those are distance-gated, not sensor-gated)
- Lap time: faster than exp-43's 01:50:61
- Risk: if a sweeper outside the zone caps now over-reads clearance and causes understeer, revert cone to t[6:15]

| Metric | Before (exp-43) | Run 1 |
|---|---|---|
| Lap time | 01:50:61 | **01:48:59** ✅ |
| Damage | 0 | **0** ✅ |
| Top speed | 218 km/h | **228 km/h** ✅ |
| **Kept?** | | **Yes — clean lap, +10 km/h top speed, new fastest by 2 s** |

**Observations:**
- Clean lap, 0 damage. Top speed 228 km/h — +10 km/h vs exp-43 (218 km/h). Largest single-step gain recorded.
- Lap time 01:48:59 — 2:02 s faster than exp-43 (01:50:61).
- Wider cone (t[5:16]) raises `ahead` on gentle sweepers, allowing higher `target_speed` through those sections.
- Zone caps held perfectly — distance-gated, sensor width does not affect A/B/C protection.
- Cone width is a high-leverage lever; advancing to exp-45 (widen further to t[4:17], adding ±12°).

---

### v1-experiment-45 — Widen sensor cone t[5:16] → t[4:17] (±12° cone)

**File:** `snakeoil3_v2.py`  
**EXP_TAG:** `exp-45-widercone-4to17`

**Motivation:** exp-44 (t[5:16], ±7° cone) delivered +10 km/h and 01:48:59 — the largest single-step gain in the project. Cone width is now the primary lever. Widening one more step to t[4:17] adds the ±12° sensors (indices 4 and 16), raising `ahead` further on fast sweepers. Zone caps (A/B/C) are distance-gated and unaffected. decel_g=17, margin=0.97 unchanged.

**Change made:**
```python
# Before (exp-44):
ahead = max(max(t[5:16]), 0.0)   # ±7° cone

# After (exp-45):
ahead = max(max(t[4:17]), 0.0)   # ±12° cone
```

**Prediction:**
- Top speed: rises from 228 km/h toward 232–238 km/h
- Damage: 0 (zone caps unchanged; risk is tight corners *outside* the caps)
- Lap time: faster than exp-44's 01:48:59
- Risk: ±12° sensors on tight off-cap corners may over-read clearance → understeer → damage; revert to t[5:16] if so

| Metric | Before (exp-44) | Run 1 |
|---|---|---|
| Lap time | 01:48:59 | **DNF — stalled mid-lap at ~32 s** ❌ |
| Damage | 0 | **0** |
| Top speed | 228 km/h | **189 km/h** ❌ |
| **Kept?** | | **No — ±12° cone over-reads on tight off-cap sections; reverted to t[5:16]** |

**Observations:**
- Same failure mode as exp-42: car stalled mid-lap at ~32 s, damage 0, car halted in reverse on track edge.
- ±12° sensors (t[4:17]) over-read clearance on a tight section not covered by zone caps, allowing the car to
  build to 189 km/h before a short `ahead` reading triggered emergency braking to near-zero. Yaw-recovery
  locked the car.
- t[5:16] (±7°) is confirmed as the maximum safe cone width. t[4:17] (±12°) is the ceiling.
- **exp-44 (t[5:16], 228 km/h, 01:48:59) is the confirmed best stable configuration.**
- exp-44 code promoted to `snakeoil3_v1.py` as the new safe baseline.

---

### v1 baseline confirmation runs — exp-44 code in snakeoil3_v1.py

**File:** `snakeoil3_v1.py` (exp-44 code, no changes)
**Track:** Corkscrew

Ran `snakeoil3_v1.py` twice to confirm the promoted baseline is clean before further experiments in v2.

| Metric | exp-44 (v2) | v1 run 1 | v1 run 2 |
|---|---|---|---|
| Lap time | 01:48:59 | 01:50:52 ✅ | **01:48:82** ✅ |
| Damage | 0 | 0 ✅ | **0** ✅ |
| Top speed | 228 km/h | 228 km/h ✅ | **228 km/h** ✅ |
| Pit stops | 0 | 0 ✅ | **0** ✅ |

**exp-44 baseline confirmed stable in v1.** Two consecutive clean laps; run 2 (01:48:82) is within 0.23 s of the original v2 result (01:48:59) — essentially identical. Top speed locked at 228 km/h across both runs. This is the confirmed reference performance floor for all future experiments in v2.
