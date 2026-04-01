**Context Agent (Embodied Context-Aware Assistant)**

## **Overview**

The Context Agent is a real-time, camera-based embodied agent that observes the user’s surrounding environment and infers high-level context (e.g., working at a desk, cooking, walking). Based on this inferred context, it decides **whether, when, and how** to deliver posture-related reminders through speech.

This agent is designed to complement a body-based posture agent (IMU + vibration). While the body agent operates at the level of physical sensing and actuation, the context agent operates at the level of **situational awareness**, enabling more intelligent and context-sensitive interventions.

Together, they form a foundation for **multi-agent embodied interaction**, where different agents perceive different aspects of the world and coordinate their actions.

---

## **What It Does**

At a high level, the context agent runs a continuous loop:

> **camera → context inference → decision → speech → observe again**

More specifically, it:

- Continuously captures frames from a webcam
- Infers a coarse-grained context label (e.g., `desk_work`, `kitchen`, `walking`)
- Aggregates short-term history to stabilize predictions
- Decides whether it is appropriate to intervene
- Delivers a short spoken reminder via TTS
- Enforces a cooldown period to avoid repeated interruptions

---

## **System Architecture**

The system follows a layered agent design:

### 1. Camera Runtime (Perception Layer)

Handles real-time frame acquisition from the webcam.

### 2. Vision Tools (MCP-like Interface)

Provides structured access to perception results:

- `get_current_context()`
- `get_context_window_summary()`

These act as **tools** that the agent can call.

### 3. Context Agent (Decision Layer)

Maintains internal state and decides:

- what the user is likely doing
- whether to intervene
- what to say

### 4. Speech Actuator (Action Layer)

Outputs voice feedback using text-to-speech.

---

## **Code Structure**

```text
python/
├── camera_bridge.py     # camera input (real + mock)
├── scene_features.py    # context inference (placeholder / pluggable)
├── vision_tools.py      # tool layer for agent
├── speech.py            # TTS output
├── context_state.py     # config + memory
├── context_agent.py     # agent logic (core)
├── main_context.py      # entry point
└── logger.py            # JSONL logging (shared with body agent)
```

---

## **How to Run**

### 1. Install dependencies

```bash
pip install opencv-python pyttsx3
```

---

### 2. Run with mock context (recommended first)

```bash
python main_context.py --mock
```

This simulates different environments over time:

- desk work
- walking
- kitchen

You should see logs like:

```text
[ContextAgent] scene= desk_work | conf=0.85 | motion=0.10 | action=speak
[VOICE] You seem to be working at your desk...
```

---

### 3. Run with real camera

```bash
python main_context.py --camera-index 0
```

Note: the default `scene_features.py` is a placeholder, so real camera mode will likely output `"unknown"` until you plug in a real vision model.

---

## **Current Context Inference (MVP)**

The current implementation uses:

- A **mock context generator** (for development)
- A placeholder inference function (`infer_context_from_frame`)

This is intentionally simple to ensure the full agent loop runs end-to-end.

---

## **Upgrading Context Recognition**

You can replace `scene_features.py` with more advanced methods:

### Option 1: Object Detection + Rules

- Detect laptop → `desk_work`
- Detect stove → `kitchen`

### Option 2: CLIP Zero-Shot Classification

Compare image embeddings with prompts like:

- “a person working at a desk”
- “a person cooking in a kitchen”

### Option 3: Vision-Language Models (VLM)

- Generate image captions
- Map captions to context labels

---

## **Agent Behavior**

The context agent is **not a simple trigger system**. It maintains:

- a short-term context history
- a confidence estimate
- a cooldown timer
- a decision policy

It only speaks when:

- the inferred context is stable and confident
- the context suggests the user is relatively stationary
- it is not in cooldown

---

## **Example Behavior**

| Scene     | Behavior                         |
| --------- | -------------------------------- |
| desk_work | give posture reminder via speech |
| kitchen   | give lighter reminder            |
| walking   | do nothing                       |
| unknown   | observe only                     |

---

## **Logging**

All agent steps are recorded as JSONL logs:

```bash
logs_context/context_agent_run.jsonl
```

Each record includes:

- context snapshot
- interpretation
- memory state
- action taken
- reasoning

This enables:

- replay
- debugging
- evaluation
- visualization

---

## **Relationship to Body Agent**

The context agent is designed to work alongside a posture (body) agent.

| Agent         | Input  | Output    | Role                  |
| ------------- | ------ | --------- | --------------------- |
| Body Agent    | IMU    | vibration | physical correction   |
| Context Agent | camera | speech    | situational awareness |

---

## **Future: Agent-to-Agent Coordination (A2A)**

In the next stage, both agents will communicate to decide:

- **when to intervene**
- **how to intervene (voice vs vibration)**
- **how strong the intervention should be**

Example:

- Body agent detects bad posture
- Context agent detects user is in a meeting-like setting
  → choose **vibration instead of speech**

---

## **Why This Is an Agent (Not Just a Program)**

Unlike a simple rule-based system, this agent:

- maintains internal state over time
- reasons over temporal context (not single frames)
- balances multiple goals (helpfulness vs interruption)
- adapts behavior based on recent history

This makes it a minimal but complete example of an **embodied context-aware agent**.

---

## **Next Steps**

- Replace mock context with real vision model
- Improve speech generation (LLM-based phrasing)
- Add personalization (user-specific habits)
- Integrate with body agent via A2A communication
