# Vibration Logic

Complete pipeline from IMU sensor to haptic feedback.

---

## Pipeline

```
ESP32 (IMU, 25Hz) → bridge.py → features.py → agent.py → tools.py → vibration
                                                    │
                                              llm_reasoner.py (logging only)
```

---

## 1. Sensing — ESP32 @ 25Hz

Every 40ms, the ESP32 reads the MPU6050 and sends a JSON frame over Serial:

```json
{"type":"imu", "ts":1234, "ax":0.1, "ay":0.0, "az":9.8, "gx":0.01, "gy":0.0, "gz":0.0}
```

---

## 2. Feature Extraction — `features.py`

Each agent step takes the last `1000ms` of IMU frames and computes:

| Feature | How |
|---|---|
| `mean_tilt_deg` | `atan2(ax, sqrt(ay²+az²))` averaged over window |
| `deviation_deg` | `mean_tilt_deg − baseline_tilt_deg` |
| `stillness_score` | `1 − (avg gyro magnitude × 5)`, clamped 0–1 |

---

## 3. Trigger Conditions — `agent.py`

All three must be true simultaneously:

```
deviation_deg  > 10.0°
stillness_score ≥ 0.55      (person must be still, not mid-movement)
not in cooldown
```

Confirmed across **3 consecutive steps** (0.75 seconds) before acting.

---

## 4. State Machine

```
normal
  └─(conditions met)──────────→ candidate_deviation
        └─(3× confirmed)───────→ intervening ──→ send vibration command
              │                                         ↓
              └─(conditions lost)──→ normal      cooldown (3 sec)
                                                        ↓
                                                   normal (loop)
```

---

## 5. Vibration Command — `bridge.py` → ESP32

Python sends over Serial:

```json
{"cmd": "vibrate", "duration_ms": 300, "pwm": 140}
```

ESP32 runs the motor for exactly 300ms, then stops automatically.

---

## 6. Tunable Parameters — `main.py` → `AgentConfig`

| Parameter | Default | Meaning |
|---|---|---|
| `deviation_threshold_deg` | 10.0° | How much tilt counts as bad posture |
| `min_stillness_score` | 0.55 | Minimum stillness required to trigger |
| `confirm_steps` | 3 | Consecutive confirmations before acting |
| `step_interval_sec` | 0.25s | How often the agent runs |
| `cooldown_sec` | 3.0s | Wait time after each vibration |
| `vibration_intensity` | 0.55 | Motor strength (→ PWM 140/255) |
| `vibration_duration_ms` | 300ms | How long each vibration lasts |
| `window_ms` | 1000ms | IMU history window per step |

---

## 7. LLM Layer (optional)

The LLM **does not control vibration**. It only explains each step after the fact:

- What is the current body state?
- Why did the agent intervene (or not)?
- What should it watch next?

Output is logged to `logs/run_YYYYMMDD_HHMMSS.jsonl` only.
