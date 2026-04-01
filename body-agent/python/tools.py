# 这一层把底层 bridge 包装成 agent 可用的 tools。
import time
from typing import Dict, List

from features import compute_features


class BodyTools:
    def __init__(self, bridge):
        self.bridge = bridge
        self.baseline_tilt_deg = 0.0
        self.event_log: List[Dict] = []
        self.last_feedback_time = 0.0

    def read_imu_window(self, window_ms: int = 1000):
        return self.bridge.get_recent_frames(window_ms=window_ms)

    def get_posture_features(self, window_ms: int = 1000) -> Dict:
        frames = self.read_imu_window(window_ms=window_ms)
        return compute_features(frames, baseline_tilt_deg=self.baseline_tilt_deg)

    def trigger_vibration(self, intensity: float = 0.5, duration_ms: int = 300, pattern: str = "single_pulse") -> None:
        self.bridge.send_vibration_command(
            intensity=intensity,
            duration_ms=duration_ms,
            pattern=pattern,
        )
        self.last_feedback_time = time.time()
        self.log_event("vibration_triggered", {
            "intensity": intensity,
            "duration_ms": duration_ms,
            "pattern": pattern,
        })

    def stop_vibration(self) -> None:
        self.bridge.stop_vibration()
        self.log_event("vibration_stopped", {})

    def set_neutral_baseline(self, window_ms: int = 1500) -> Dict:
        features = self.get_posture_features(window_ms=window_ms)
        if features["ok"]:
            self.baseline_tilt_deg = features["mean_tilt_deg"]
            self.log_event("baseline_set", {"baseline_tilt_deg": self.baseline_tilt_deg})
        return {
            "baseline_tilt_deg": self.baseline_tilt_deg,
            "ok": features["ok"],
        }

    def get_feedback_history(self, window_sec: int = 30) -> List[Dict]:
        cutoff = time.time() - window_sec
        return [e for e in self.event_log if e["ts"] >= cutoff and e["type"] == "vibration_triggered"]

    def get_current_state_snapshot(self, window_ms: int = 1000) -> Dict:
        features = self.get_posture_features(window_ms=window_ms)
        return {
            "features": features,
            "baseline_tilt_deg": self.baseline_tilt_deg,
            "last_feedback_time": self.last_feedback_time,
            "feedback_count_30s": len(self.get_feedback_history(window_sec=30)),
        }

    def log_event(self, event_type: str, payload: Dict) -> None:
        self.event_log.append({
            "ts": time.time(),
            "type": event_type,
            "payload": payload,
        })
