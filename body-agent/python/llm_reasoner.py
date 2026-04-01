import json
import os
from typing import Dict, Optional

from prompts import SYSTEM_PROMPT, build_user_prompt

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class LLMReasoner:
    def __init__(self, model: str = "gpt-5-mini", enabled: bool = True):
        self.enabled = enabled
        self.model = model
        self.client = None

        api_key = os.getenv("OPENAI_API_KEY")
        if enabled and api_key and OpenAI is not None:
            self.client = OpenAI(api_key=api_key)

    def explain(self, snapshot: Dict, interp: Dict, memory: Dict, action_taken: str) -> Dict:
        if not self.enabled:
            return self._fallback_reasoning(snapshot, interp, memory, action_taken)

        if self.client is None:
            return self._fallback_reasoning(snapshot, interp, memory, action_taken)

        try:
            prompt = build_user_prompt(snapshot, interp, memory, action_taken)

            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                text={"format": {"type": "text"}},
            )

            text = response.output_text.strip()
            return self._safe_parse_json(text) or self._fallback_reasoning(
                snapshot, interp, memory, action_taken
            )

        except Exception as e:
            print(f"[LLMReasoner] API error: {e}")
            return self._fallback_reasoning(snapshot, interp, memory, action_taken)

    def _safe_parse_json(self, text: str) -> Optional[Dict]:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _fallback_reasoning(self, snapshot: Dict, interp: Dict, memory: Dict, action_taken: str) -> Dict:
        features = snapshot.get("features", {})
        deviation = interp.get("deviation_deg", 0.0)
        stillness = interp.get("stillness_score", 0.0)
        state = memory.get("state", "unknown")

        if deviation < 5:
            body_state = "near-neutral posture"
        elif stillness > 0.6 and deviation >= 10:
            body_state = "sustained posture deviation"
        else:
            body_state = "possibly transitional movement"

        if action_taken == "trigger_vibration":
            rationale = "deviation appeared persistent and still enough to justify embodied feedback"
        elif state == "cooldown":
            rationale = "feedback was recently given, so the agent is observing recovery before acting again"
        elif state == "candidate_deviation":
            rationale = "deviation was detected but the agent is waiting for confirmation before intervening"
        else:
            rationale = "current evidence is insufficient for intervention"

        if state == "cooldown":
            next_focus = "watch whether posture returns toward baseline after the last reminder"
        elif state == "candidate_deviation":
            next_focus = "check whether the deviation persists across the next few windows"
        else:
            next_focus = "monitor posture trend and stillness"

        summary = (
            f"The agent interprets the current body state as {body_state}. "
            f"Mean deviation is {deviation:.2f} degrees with stillness score {stillness:.2f}. "
            f"It {('did' if action_taken == 'trigger_vibration' else 'did not')} intervene because {rationale}."
        )

        confidence = 0.55
        if features.get("ok"):
            confidence += 0.15
        if stillness > 0.7:
            confidence += 0.1
        if deviation > 12:
            confidence += 0.1

        return {
            "summary": summary,
            "body_state": body_state,
            "decision_rationale": rationale,
            "next_focus": next_focus,
            "confidence": min(confidence, 0.95),
        }