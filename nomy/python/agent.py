import time
from typing import Dict

from state import AgentConfig, AgentMemory


class PostureAgent:
    def __init__(self, tools, config: AgentConfig | None = None):
        self.tools = tools
        self.config = config or AgentConfig()
        self.memory = AgentMemory()

    def in_cooldown(self) -> bool:
        if self.memory.last_feedback_time <= 0:
            return False
        return (time.time() - self.memory.last_feedback_time) < self.config.cooldown_sec

    def interpret(self, snapshot: Dict) -> Dict:
        features = snapshot["features"]
        deviation = abs(features["deviation_deg"])
        still_enough = features["stillness_score"] >= self.config.min_stillness_score

        persistent_deviation_candidate = (
            features["ok"]
            and deviation >= self.config.deviation_threshold_deg
            and still_enough
        )

        return {
            "persistent_deviation_candidate": persistent_deviation_candidate,
            "deviation_deg": deviation,
            "stillness_score": features["stillness_score"],
            "mean_tilt_deg": features["mean_tilt_deg"],
            "raw": features,
        }

    def decide_and_act(self, interp: Dict) -> None:
        if self.memory.state == "normal":
            if interp["persistent_deviation_candidate"] and not self.in_cooldown():
                self.memory.state = "candidate_deviation"
                self.memory.candidate_count = 1
            return

        if self.memory.state == "candidate_deviation":
            if interp["persistent_deviation_candidate"] and not self.in_cooldown():
                self.memory.candidate_count += 1
                if self.memory.candidate_count >= self.config.confirm_steps:
                    self.memory.state = "intervening"
            else:
                self.memory.state = "normal"
                self.memory.candidate_count = 0
            return

        if self.memory.state == "intervening":
            self.tools.trigger_vibration(
                intensity=self.config.vibration_intensity,
                duration_ms=self.config.vibration_duration_ms,
                pattern="single_pulse",
            )
            self.memory.last_feedback_time = time.time()
            self.memory.state = "cooldown"
            self.memory.candidate_count = 0
            return

        if self.memory.state == "cooldown":
            if not self.in_cooldown():
                self.memory.state = "normal"
            return

    def step(self) -> None:
        snapshot = self.tools.get_current_state_snapshot(window_ms=self.config.window_ms)
        interp = self.interpret(snapshot)

        print(
            f"[Agent] state={self.memory.state:>18} | "
            f"tilt={interp['mean_tilt_deg']:+6.2f} deg | "
            f"dev={interp['deviation_deg']:5.2f} | "
            f"still={interp['stillness_score']:.2f}"
        )

        self.decide_and_act(interp)