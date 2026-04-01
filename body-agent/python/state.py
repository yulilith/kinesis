# 这里定义 agent 的状态和一些可调参数。
from dataclasses import dataclass


@dataclass
class AgentConfig:
    window_ms: int = 1000
    step_interval_sec: float = 0.25
    deviation_threshold_deg: float = 10.0
    min_stillness_score: float = 0.55
    confirm_steps: int = 3
    cooldown_sec: float = 3.0
    vibration_intensity: float = 0.55
    vibration_duration_ms: int = 300


@dataclass
class AgentMemory:
    state: str = "normal"
    candidate_count: int = 0
    last_feedback_time: float = 0.0