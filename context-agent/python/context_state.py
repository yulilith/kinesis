from dataclasses import dataclass


@dataclass
class ContextAgentConfig:
    step_interval_sec: float = 2.0
    cooldown_sec: float = 12.0
    min_confidence: float = 0.55
    speech_enabled: bool = True


@dataclass
class ContextAgentMemory:
    state: str = "observing"
    last_context: str = "unknown"
    last_speech_time: float = 0.0
    recent_reason: str = ""