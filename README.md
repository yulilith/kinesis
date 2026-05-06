# Kinesis

**An agentic solution for personalized posture correction**

context-aware | adaptive | closed-loop

Team: Chloe Ni, Lilith Yu, Nomy Yu — MAS.664 AI Studio

---

## The Problem

Posture isn't a sensing problem. It's a **decision problem**.

| # | Dimension | Why it matters |
|---|-----------|----------------|
| 01 | **Body State** | Muscle fatigue and tension shift what "good posture" means hour to hour |
| 02 | **Activity** | Typing, lifting, walking — each demands a different baseline |
| 03 | **Context** | A buzz mid-meeting is noise; the same buzz at the desk is a useful nudge |
| 04 | **History** | What worked yesterday can adapt away. Habits drift; feedback must drift with them |

## Our Solution

Kinesis is a multi-agent wearable that turns posture correction into a closed loop — embodied, contextual, and personalized.

- **Embodied sensing** — IMU + EMG, head to back
- **Context awareness** — activity and surroundings, in real time
- **Adaptive decisions** — three agents, one orchestrated strategy
- **Closed-loop intervention** — haptic + audio feedback, calibrated per moment

## System Architecture

```
                    CONTEXT AGENT
                    (AI Glasses)
                 Activity, surroundings,
                   interruptibility
                         │
                      context
                         │
COACH AGENT ◄────────── USER ──────────► EXTERNAL MCPs
(Orchestrator)         human              Whoop, Oura, etc.
Long memory,        embodied I/O         Recovery, strain,
strategy across                           readiness [optional]
hours/days/weeks
        ▲
        │
  BODY AGENT
  (Kinesis Wearable)
  IMU x2 (spinal deviation)
  EMG x3 (muscle response)
  Vibration x4 | ESP32
```

The Coach Agent orchestrates personal agents and external data sources, using each one's signal where it's strongest. Hardware stays close to the body; reasoning stays close to the context.

## Agents

| Agent | Role | Signal |
|-------|------|--------|
| **Body Agent** | Reads spinal alignment from IMUs and muscle response from EMG. Knows the difference between bad posture and a fatigued one. | What is the body doing right now? Did the last intervention actually engage muscle? |
| **Context Agent** | Classifies activity and surroundings — focused work, meeting, walking — so intervention fits the social and physical moment. | Is this an interruptible moment? What's the user actually trying to do? |
| **Coach Agent** | Orchestrates body + context with history and external biometrics. Decides strategy across hours, days, and weeks. | Is this strategy still working? What pattern is forming over time? |

## The Closed Loop

Each cycle teaches the next one.

```
SENSE → INTERPRET → DECIDE → INTERVENE → MEASURE → ADAPT
  │          │          │          │          │         │
IMU+EMG   Body Agent  Coach     Haptic cue  EMG      Strategy
capture   reads dev-  weighs    tuned to    verifies  updates
posture   iation and  context,  the moment. muscle    for the
& muscle  fatigue     history,              responded. cycle.
signal              biometrics
```

## Hardware

- **ESP32** — microcontroller streaming IMU + EMG data
- **IMU x2** — spinal deviation (upper + lower back)
- **EMG x3** — muscle response sensing
- **Vibration motors x4** — haptic feedback zones

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/chloewantsleep/kinesis.git
cd kinesis
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your Anthropic API key
echo "ANTHROPIC_API_KEY=sk-..." > .env

# 3. Run with mock sensors (no hardware needed)
python run.py

# 4. Open dashboard
open http://localhost:8080
```

## Mock Replay

Run the system against pre-recorded 5-minute sessions without any hardware:

```bash
# Desk work session
python run.py --replay-dataset mock_data/desk_work_focus_5min.json

# Interview forward lean
python run.py --replay-dataset mock_data/interview_forward_lean_5min.json

# Street walk with side bend
python run.py --replay-dataset mock_data/street_walk_sidebend_5min.json
```

Generate new mock datasets:

```bash
python generate_mock_replay.py
```

## Run Components Separately

```bash
python shared_state_server.py    # Terminal 1 — blackboard + dashboard
python agents/context_agent.py   # Terminal 2 — glasses/scene
python agents/body_agent.py      # Terminal 3 — posture/EMG
python agents/coach_agent.py     # Terminal 4 — strategy/long memory
```

## Project Structure

```
kinesis/
├── agents/
│   ├── body_agent.py        # Posture + EMG agent
│   ├── context_agent.py     # Scene/glasses agent
│   └── coach_agent.py       # Orchestrator/planner agent
├── body-agent/
│   ├── firmware/            # ESP32 Arduino code
│   └── python/              # IMU + EMG feature extraction
├── context-agent/           # Camera + CLIP scene classifier
├── esp32_agent/             # ESP32 firmware (esp32_agent.ino)
├── ble/                     # BLE + mock sensor layer
├── mock_data/               # Pre-recorded 5-min replay datasets
├── shared_state_server.py   # MCP blackboard + dashboard server
├── schemas.py               # Shared data contracts
├── mock_replay.py           # Replay dataset runner
├── generate_mock_replay.py  # Mock data generator
├── dashboard.html           # Web dashboard (served at :8080)
├── run.py                   # Start everything
└── requirements.txt
```

## Requirements

- Python 3.11+
- Anthropic API key
- For real hardware: ESP32 with IMU + EMG + vibration hardware
- For camera mode: webcam + `torch`, `transformers`, `opencv-python`
- For biometrics: Whoop or Oura API credentials (optional)
