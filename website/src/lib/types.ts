export type AgentId = "kinesess" | "glasses" | "brain" | "system";

export type EventType =
  | "question"
  | "reply"
  | "haptic"
  | "speech"
  | "muted"
  | "decision"
  | "scene"
  | "trigger";

export interface DashboardEvent {
  id: string;
  agent: AgentId;
  from?: AgentId;
  to?: AgentId;
  type: EventType;
  message: string;
  detail?: string;
  timestamp: number;
}

export interface ReplayEvent {
  offset_ms: number;
  type: "state_update" | "agent_connected" | "discussion" | "log_entry";
  payload: Record<string, unknown>;
}

export interface ContextBarState {
  posture: string;
  deviation: string;
  scene: string;
  social: boolean;
  tension: string;
  mode: string;
  budget: number;
}
