import type { ReplayEvent } from "../lib/types";

const events: ReplayEvent[] = [
  // Agents connect
  { offset_ms: 0, type: "agent_connected", payload: { agent: "brain" } },
  { offset_ms: 200, type: "agent_connected", payload: { agent: "kinesess" } },
  { offset_ms: 400, type: "agent_connected", payload: { agent: "glasses" } },

  // Initial state
  {
    offset_ms: 1000,
    type: "state_update",
    payload: { device_id: "glasses", key: "context", data: { scene: "desk_work", social: false, ambient_noise_db: 32 } },
  },
  {
    offset_ms: 1500,
    type: "state_update",
    payload: { device_id: "kinesess", key: "posture", data: { classification: "good", deviation_degrees: 3.2 } },
  },
  {
    offset_ms: 2000,
    type: "state_update",
    payload: { device_id: "brain", key: "mode", data: { mode: "normal" } },
  },
  {
    offset_ms: 2500,
    type: "state_update",
    payload: { device_id: "brain", key: "attention_budget", data: { remaining: 20 } },
  },

  // User starts slouching
  {
    offset_ms: 8000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "posture", data: { classification: "mild_slouch", deviation_degrees: 12.4 } },
  },
  {
    offset_ms: 10000,
    type: "log_entry",
    payload: { agent: "kinesess", message: "Detecting mild forward slouch. Deviation 12.4\u00B0. Monitoring..." },
  },

  // Sustained slouch — body agent considers intervention
  {
    offset_ms: 18000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "posture", data: { classification: "slouching", deviation_degrees: 18.7 } },
  },
  {
    offset_ms: 20000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "tension", data: { level: 0.4 } },
  },

  // Body agent asks context agent
  {
    offset_ms: 22000,
    type: "discussion",
    payload: {
      direction: "question",
      from: "kinesess",
      to: "glasses",
      message: "User has been slouching for 40 seconds. Deviation 18.7\u00B0. Is the user in a social setting where haptic feedback would be disruptive?",
    },
  },
  {
    offset_ms: 24000,
    type: "discussion",
    payload: {
      direction: "reply",
      from: "glasses",
      to: "kinesess",
      message: "Scene is desk_work, no social presence detected, ambient noise 32 dB. Haptic intervention is appropriate.",
    },
  },

  // Haptic fires
  {
    offset_ms: 26000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "last_haptic", data: { pattern: "gentle_pulse", intensity: 0.4, reason: "sustained slouch > 15\u00B0 for 40s" } },
  },
  {
    offset_ms: 26500,
    type: "log_entry",
    payload: { agent: "kinesess", message: "Fired haptic: gentle_pulse at intensity 0.4" },
  },
  {
    offset_ms: 27000,
    type: "state_update",
    payload: { device_id: "brain", key: "attention_budget", data: { remaining: 19 } },
  },

  // User corrects
  {
    offset_ms: 32000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "posture", data: { classification: "good", deviation_degrees: 4.1 } },
  },
  {
    offset_ms: 33000,
    type: "log_entry",
    payload: { agent: "kinesess", message: "Posture corrected. Recovery time: 6s. Good response to gentle haptic." },
  },

  // Planner notes
  {
    offset_ms: 36000,
    type: "state_update",
    payload: { device_id: "brain", key: "plan", data: { message: "User responded well to gentle haptic during desk work. Maintaining normal mode." } },
  },

  // Second slouch episode
  {
    offset_ms: 55000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "posture", data: { classification: "slouching", deviation_degrees: 22.1 } },
  },
  {
    offset_ms: 58000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "tension", data: { level: 0.6 } },
  },

  // Scene changes — colleague approaches
  {
    offset_ms: 60000,
    type: "state_update",
    payload: { device_id: "glasses", key: "context", data: { scene: "meeting", social: true, ambient_noise_db: 48 } },
  },
  {
    offset_ms: 61000,
    type: "log_entry",
    payload: { agent: "glasses", message: "Scene changed: desk_work \u2192 meeting. Social presence detected." },
  },

  // Body agent asks again — different answer this time
  {
    offset_ms: 63000,
    type: "discussion",
    payload: {
      direction: "question",
      from: "kinesess",
      to: "glasses",
      message: "User still slouching at 22.1\u00B0. Should I intervene with haptic?",
    },
  },
  {
    offset_ms: 65000,
    type: "discussion",
    payload: {
      direction: "reply",
      from: "glasses",
      to: "kinesess",
      message: "User is now in a meeting with social=true. Recommend suppressing haptic to avoid disruption. Consider speech overlay via glasses instead.",
    },
  },

  // Brain agent adjusts mode
  {
    offset_ms: 67000,
    type: "state_update",
    payload: { device_id: "brain", key: "mode", data: { mode: "gentle" } },
  },
  {
    offset_ms: 68000,
    type: "log_entry",
    payload: { agent: "brain", message: "Mode switched to gentle. Social context detected \u2014 reducing intervention aggressiveness." },
  },

  // Speech instead of haptic
  {
    offset_ms: 70000,
    type: "state_update",
    payload: { device_id: "glasses", key: "speech_command", data: { message: "You might want to sit up a bit", suppressed: false } },
  },

  // User recovers again
  {
    offset_ms: 78000,
    type: "state_update",
    payload: { device_id: "kinesess", key: "posture", data: { classification: "good", deviation_degrees: 5.8 } },
  },
  {
    offset_ms: 80000,
    type: "state_update",
    payload: { device_id: "brain", key: "attention_budget", data: { remaining: 18 } },
  },

  // Meeting ends, back to desk
  {
    offset_ms: 100000,
    type: "state_update",
    payload: { device_id: "glasses", key: "context", data: { scene: "desk_work", social: false, ambient_noise_db: 30 } },
  },
  {
    offset_ms: 102000,
    type: "state_update",
    payload: { device_id: "brain", key: "mode", data: { mode: "normal" } },
  },
  {
    offset_ms: 103000,
    type: "log_entry",
    payload: { agent: "brain", message: "Social context cleared. Restoring normal mode. Session summary: 2 interventions, 2 corrections, avg recovery 7s." },
  },
];

export default events;
