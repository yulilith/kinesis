from typing import Dict
from scene_features import infer_context_from_frame


class VisionTools:
    def __init__(self, camera_bridge):
        self.camera_bridge = camera_bridge
        self.context_history = []

    def get_current_context(self) -> Dict:
        if hasattr(self.camera_bridge, "get_mock_context"):
            label = self.camera_bridge.get_mock_context()
            result = {
                "scene_label": label,
                "activity_hint": label,
                "confidence": 0.85,
                "motion_level": 0.1 if label in ["desk_work", "kitchen"] else 0.7,
            }
        else:
            frame, ts = self.camera_bridge.get_latest_frame()
            result = infer_context_from_frame(frame, fallback_label="unknown")
            result["timestamp"] = ts

        self.context_history.append(result)
        self.context_history = self.context_history[-50:]
        return result

    def get_context_window_summary(self, window_size: int = 8) -> Dict:
        history = self.context_history[-window_size:]
        if not history:
            return {
                "dominant_scene": "unknown",
                "dominant_activity": "unknown",
                "avg_confidence": 0.0,
                "avg_motion_level": 0.0,
            }

        labels = [x["scene_label"] for x in history]
        dominant_scene = max(set(labels), key=labels.count)
        avg_conf = sum(x["confidence"] for x in history) / len(history)
        avg_motion = sum(x["motion_level"] for x in history) / len(history)

        return {
            "dominant_scene": dominant_scene,
            "dominant_activity": dominant_scene,
            "avg_confidence": avg_conf,
            "avg_motion_level": avg_motion,
            "num_samples": len(history),
        }