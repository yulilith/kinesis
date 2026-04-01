import json
import os
import time
from typing import Any, Dict


class JsonlLogger:
    def __init__(self, log_dir: str = "logs", run_name: str | None = None):
        os.makedirs(log_dir, exist_ok=True)

        if run_name is None:
            run_name = time.strftime("run_%Y%m%d_%H%M%S")

        self.run_name = run_name
        self.filepath = os.path.join(log_dir, f"{run_name}.jsonl")

    def log_step(
        self,
        snapshot: Dict[str, Any],
        interpretation: Dict[str, Any],
        memory: Dict[str, Any],
        action_taken: str,
        reasoning: Dict[str, Any] | None = None,
    ) -> None:
        record = {
            "ts": time.time(),
            "snapshot": snapshot,
            "interpretation": interpretation,
            "memory": memory,
            "action_taken": action_taken,
            "reasoning": reasoning or {},
        }

        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        record = {
            "ts": time.time(),
            "event_type": event_type,
            "payload": payload,
        }

        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")