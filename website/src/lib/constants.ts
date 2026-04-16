import type { AgentId } from "./types";

export const AGENT_NAMES: Record<AgentId, string> = {
  kinesess: "Body Agent",
  glasses: "Context Agent",
  brain: "Brain Agent",
  system: "System",
};

export const AGENT_COLORS: Record<AgentId, string> = {
  kinesess: "#e06c75",
  glasses: "#56b6c2",
  brain: "#c678dd",
  system: "#5c6370",
};

export const AGENT_POWERED_BY: Record<string, string> = {
  kinesess: "Powered by Kinesis",
  glasses: "Powered by Meta AI Glasses",
  brain: "Powered by Kinesis",
};
