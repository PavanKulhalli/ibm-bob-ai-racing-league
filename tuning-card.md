# Tuning Card — `drive_example()` in `snakeoil3_gym.py`

All settings live inside the `drive_example()` function (lines 529–565).

| Setting | Line | Current Value | What It Controls | Raise → | Lower → | Crash Risk |
|---|---|---|---|---|---|---|
| `target_speed` | 533 | `300` (km/h) | Maximum forward speed the throttle logic tries to reach | Car chases a higher top speed; more wheel-spin, harder braking needed on corners | Car drives slower everywhere; loses time on straights but easier to keep on track | Medium |
| Steer-to-corner gain (`*15`) | 536 | `15` | Scales how aggressively `angle` (car vs. track heading) is converted to steering input | Sharper response to yaw error; corrects faster but can overshoot and oscillate | Sluggish yaw correction; car drifts wide before steering catches up | High |
| Steer-to-center gain (`*.10`) | 538 | `0.10` | Scales how hard `trackPos` (lateral offset from centre) pulls the car back to mid-track | Stronger centre-pull; car stays closer to centre line but fights corner-entry lines | Weaker centre-pull; car wanders off-centre, especially in long sweepers | Low |
| Steer-speed coupling (`*50`) | 541 | `50` | Reduces `target_speed` proportionally to current steer magnitude; slows the car in corners | More speed is shed for a given steering angle; forces hard braking every corner | Less corner slow-down; car carries more speed through bends | High |
| Throttle ramp-up step (`+= .01`) | 542 | `0.01` | How quickly `accel` climbs each tick when below target speed (~50 ticks/s) | Faster acceleration build-up; more wheel-spin at launch and corner exits | Very gradual acceleration; sluggish out of corners, slower lap times | Low |
| Throttle ramp-down step (`-= .01`) | 544 | `0.01` | How quickly `accel` decays each tick when above target speed | Faster deceleration (engine lift-off); can cause abrupt speed drops | Slower deceleration; car overshoots target speed more often | Low |
| Low-speed accel boost (`1/(speedX+.1)`) | 546 | `1 / (speedX + 0.1)` | Extra throttle injected when `speedX < 10`; prevents stalling at near-zero speed | Denominator `+.1` is fixed — to amplify, scale the numerator up; bigger boost risks wheel-spin from standstill | Smaller numerator → weaker launch boost; car may bog down from rest | Low |
| TCS rear–front wheel-spin threshold | 550 | `5` (rad/s difference) | Triggers traction-cut (`accel -= .2`) when rear wheels spin faster than fronts by this much | Higher threshold → TCS fires later; more wheel-spin allowed before cut, faster launch but more oversteer | Lower threshold → TCS cuts throttle sooner; very conservative traction, slower exits | Medium |
| TCS accel cut (`-= .2`) | 551 | `0.2` | Amount throttle is reduced each tick the TCS condition is active | Larger cut → more aggressive traction control; throttle collapses quickly | Smaller cut → TCS barely reduces power; wheel-spin persists longer | Medium |
| Gear 2 threshold | 555 | `50` km/h | `speedX` at which automatic gearbox shifts to 2nd | Shifts later; engine stays in 1st longer, higher RPM | Shifts earlier; 2nd gear at low speed, less torque | Low |
| Gear 3 threshold | 557 | `80` km/h | `speedX` at which gearbox shifts to 3rd | Later shift, higher RPM in 2nd | Earlier shift, lower RPM in 3rd | Low |
| Gear 4 threshold | 559 | `110` km/h | `speedX` at which gearbox shifts to 4th | Later shift | Earlier shift | Low |
| Gear 5 threshold | 561 | `140` km/h | `speedX` at which gearbox shifts to 5th | Later shift | Earlier shift | Low |
| Gear 6 threshold | 563 | `170` km/h | `speedX` at which gearbox shifts to 6th (top gear) | Later shift into top; more mid-range pull | Earlier shift; may lug the engine at low speeds | Low |

---

## Crash-Risk Key

| Level | Meaning |
|---|---|
| **Low** | Changing this setting is unlikely to cause an off-track incident on its own |
| **Medium** | Can cause spins or traction loss if set to an extreme value |
| **High** | Directly governs steering authority or cornering speed; extreme values will crash the car |

---

## Quick-Start Recommendations

- **Slower but stable**: lower `target_speed` to `150`, lower steer-to-corner gain to `10`.
- **Faster but riskier**: raise `target_speed` to `350`, raise steer-to-corner gain to `20`, lower TCS threshold to `3`.
- **Tighter line-keeping**: raise steer-to-center gain from `0.10` to `0.20` (watch for oscillation at high speed).
