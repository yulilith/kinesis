# 这个 agent 先独立完成：看环境、解释用户在干什么、在适当时机说一句提醒。
# 为了让它之后容易接 body agent，我特意把决策拆成 interpretation 和 action。

import time
from typing import Dict

from context_state import ContextAgentConfig, ContextAgentMemory


class ContextAgent:
    def __init__(self, tools, speech_actuator, config: ContextAgentConfig | None = None, logger=None):
        self.tools = tools
        self.speech = speech_actuator
        self.config = config or ContextAgentConfig()
        self.memory = ContextAgentMemory()
        self.logger = logger

    def in_cooldown(self) -> bool:
        if self.memory.last_speech_time <= 0:
            return False
        return (time.time() - self.memory.last_speech_time) < self.config.cooldown_sec

    def interpret(self) -> Dict:
        current = self.tools.get_current_context()
        summary = self.tools.get_context_window_summary(window_size=6)

        scene = summary["dominant_scene"]
        conf = summary["avg_confidence"]
        motion = summary["avg_motion_level"]

        likely_static_context = scene in ["desk_work", "kitchen"]
        likely_dynamic_context = scene in ["walking", "exercise"]

        return {
            "current_context": current,
            "summary": summary,
            "scene": scene,
            "confidence": conf,
            "motion_level": motion,
            "likely_static_context": likely_static_context,
            "likely_dynamic_context": likely_dynamic_context,
        }

    def choose_prompt(self, interp: Dict) -> str | None:
        scene = interp["scene"]

        if scene == "desk_work":
            return "You seem to be working at your desk. Relax your shoulders and keep your back supported."
        if scene == "kitchen":
            return "You look busy in the kitchen. Try not to round your back for too long."
        if scene == "walking":
            return None
        return None

    def step(self):
        interp = self.interpret()
        action_taken = "none"
        speech_text = None

        if (
            interp["confidence"] >= self.config.min_confidence
            and interp["likely_static_context"]
            and not self.in_cooldown()
        ):
            speech_text = self.choose_prompt(interp)
            if speech_text and self.config.speech_enabled:
                self.speech.speak(speech_text)
                self.memory.last_speech_time = time.time()
                action_taken = "speak"

        self.memory.last_context = interp["scene"]

        print(
            f"[ContextAgent] scene={interp['scene']:>10} | "
            f"conf={interp['confidence']:.2f} | "
            f"motion={interp['motion_level']:.2f} | "
            f"action={action_taken}"
        )

        if self.logger is not None:
            self.logger.log_step(
                snapshot={"context": interp["current_context"], "summary": interp["summary"]},
                interpretation=interp,
                memory={
                    "state": self.memory.state,
                    "last_context": self.memory.last_context,
                    "last_speech_time": self.memory.last_speech_time,
                    "in_cooldown": self.in_cooldown(),
                },
                action_taken=action_taken,
                reasoning={
                    "summary": f"Context agent inferred {interp['scene']} and decided whether speech reminder was appropriate.",
                    "prompt_text": speech_text,
                },
            )