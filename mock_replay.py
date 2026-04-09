from __future__ import annotations

import json
import time
from bisect import bisect_right
from pathlib import Path
from typing import Any

from schemas import GazeReading, SceneContext


REPLAY_DATASET_DIR = Path(__file__).resolve().parent / "mock_data"
REPLAY_PROFILE_PATHS = {
    "working": REPLAY_DATASET_DIR / "desk_work_focus_5min.json",
    "meeting": REPLAY_DATASET_DIR / "interview_forward_lean_5min.json",
    "walking": REPLAY_DATASET_DIR / "street_walk_sidebend_5min.json",
}


def resolve_replay_dataset(dataset_ref: str) -> Path:
    candidate = Path(dataset_ref)
    if candidate.is_absolute() and candidate.exists():
        return candidate

    if dataset_ref in REPLAY_PROFILE_PATHS:
        return REPLAY_PROFILE_PATHS[dataset_ref]

    search_paths = [
        Path(__file__).resolve().parent / candidate,
        REPLAY_DATASET_DIR / candidate,
    ]
    for path in search_paths:
        if path.exists():
            return path

    available = ", ".join(sorted(REPLAY_PROFILE_PATHS))
    raise FileNotFoundError(f"Replay dataset not found: {dataset_ref}. Available profiles: {available}")


class ReplayDataset:
    def __init__(self, dataset_path: str) -> None:
        self.path = resolve_replay_dataset(dataset_path)
        payload = json.loads(self.path.read_text())

        self.meta = payload.get("meta", {})
        self.duration_s = float(self.meta.get("duration_s", 0.0))
        self.context_samples: list[dict[str, Any]] = payload.get("context_samples", [])
        self.imu_frames: list[dict[str, Any]] = payload.get("imu_frames", [])

        if self.duration_s <= 0.0:
            raise ValueError(f"Invalid replay duration in {self.path}")
        if not self.context_samples:
            raise ValueError(f"Replay dataset {self.path} has no context_samples")
        if not self.imu_frames:
            raise ValueError(f"Replay dataset {self.path} has no imu_frames")

        self.context_samples.sort(key=lambda item: float(item["offset_s"]))
        self.imu_frames.sort(key=lambda item: float(item["offset_s"]))
        self._context_offsets = [float(item["offset_s"]) for item in self.context_samples]
        self._imu_offsets = [float(item["offset_s"]) for item in self.imu_frames]
        self._start_time = time.time()

    def reset(self) -> None:
        self._start_time = time.time()

    def _current_offset(self) -> float:
        return (time.time() - self._start_time) % self.duration_s

    def _sample_at_offset(self, samples: list[dict[str, Any]], offsets: list[float], offset_s: float) -> dict[str, Any]:
        idx = bisect_right(offsets, offset_s) - 1
        if idx < 0:
            idx = len(samples) - 1
        return samples[idx]

    def get_current_context_sample(self) -> dict[str, Any]:
        return self._sample_at_offset(self.context_samples, self._context_offsets, self._current_offset())

    def get_window_frames(self, window_ms: int = 1000) -> list[dict[str, Any]]:
        current_offset = self._current_offset()
        window_s = window_ms / 1000.0
        start_offset = current_offset - window_s

        selected: list[dict[str, Any]] = []
        for frame in self.imu_frames:
            frame_offset = float(frame["offset_s"])
            if start_offset >= 0.0:
                in_window = start_offset <= frame_offset <= current_offset
            else:
                in_window = frame_offset >= (self.duration_s + start_offset) or frame_offset <= current_offset

            if in_window:
                frame_copy = dict(frame)
                frame_copy["host_time"] = time.time() - (current_offset - frame_offset)
                selected.append(frame_copy)

        return selected


class ReplayContextSource:
    def __init__(self, dataset_path: str) -> None:
        self._dataset = ReplayDataset(dataset_path)
        self.dataset_ref = dataset_path

    def reset(self) -> None:
        self._dataset.reset()

    def set_dataset(self, dataset_ref: str) -> bool:
        resolved = resolve_replay_dataset(dataset_ref)
        if resolved == self._dataset.path:
            self.reset()
            self.dataset_ref = dataset_ref
            return False
        self._dataset = ReplayDataset(str(resolved))
        self.dataset_ref = dataset_ref
        return True

    def read(self) -> tuple[SceneContext, GazeReading | None, dict[str, Any]]:
        sample = self._dataset.get_current_context_sample()
        now = time.time()

        scene_payload = dict(sample["scene_context"])
        scene_payload["timestamp"] = now
        scene = SceneContext.from_dict(scene_payload)

        gaze = None
        if sample.get("gaze"):
            gaze_payload = dict(sample["gaze"])
            gaze_payload["timestamp"] = now
            gaze = GazeReading.from_dict(gaze_payload)

        sensor_log = dict(sample.get("sensor_log", {}))
        sensor_log["timestamp"] = now
        sensor_log["replay_source"] = str(self._dataset.path)
        return scene, gaze, sensor_log


class ReplayIMUBridge:
    def __init__(self, dataset_path: str) -> None:
        self._dataset = ReplayDataset(dataset_path)
        self.dataset_ref = dataset_path
        self._running = False

    def start_streaming(self, reset: bool = True) -> None:
        if reset:
            self._dataset.reset()
        self._running = True

    def stop(self) -> None:
        self._running = False

    def set_dataset(self, dataset_ref: str, reset: bool = True) -> bool:
        resolved = resolve_replay_dataset(dataset_ref)
        if resolved == self._dataset.path:
            if reset:
                self._dataset.reset()
            self.dataset_ref = dataset_ref
            return False
        self._dataset = ReplayDataset(str(resolved))
        self.dataset_ref = dataset_ref
        self._running = True
        if reset:
            self._dataset.reset()
        return True

    def get_recent_frames(self, window_ms: int = 1000) -> list[dict[str, Any]]:
        if not self._running:
            self.start_streaming(reset=False)
        return self._dataset.get_window_frames(window_ms=window_ms)

    def send_vibration_command(self, intensity: float = 0.5, duration_ms: int = 300, pattern: str = "single_pulse") -> None:
        print(f"[REPLAY VIBRATION] intensity={intensity:.2f}, duration={duration_ms}ms, pattern={pattern}")

    def stop_vibration(self) -> None:
        print("[REPLAY VIBRATION] stop")
