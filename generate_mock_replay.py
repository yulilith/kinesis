from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any


SCENARIO_OUTPUTS = {
    "working": "mock_data/desk_work_focus_5min.json",
    "meeting": "mock_data/interview_forward_lean_5min.json",
    "walking": "mock_data/street_walk_sidebend_5min.json",
}


def _segment_at(offset_s: float, segments: list[dict[str, Any]]) -> dict[str, Any]:
    for segment in segments:
        if segment["start"] <= offset_s < segment["end"]:
            return segment
    return segments[-1]


def _piecewise_signal(offset_s: float, pattern: list[tuple[float, float, float]], base_wave_s: float = 6.0) -> float:
    for start_s, end_s, value in pattern:
        if start_s <= offset_s < end_s:
            return value + 0.8 * math.sin(offset_s / base_wave_s)
    _, _, fallback = pattern[-1]
    return fallback + 0.6 * math.sin(offset_s / base_wave_s)


def _work_tilt_deg(offset_s: float) -> float:
    return _piecewise_signal(
        offset_s,
        [
            (0.0, 42.0, 4.0),
            (42.0, 95.0, 18.5),
            (95.0, 125.0, 5.5),
            (125.0, 178.0, 23.0),
            (178.0, 212.0, 6.0),
            (212.0, 268.0, 17.8),
            (268.0, 300.0, 7.0),
        ],
        base_wave_s=7.2,
    )


def _meeting_tilt_deg(offset_s: float) -> float:
    return _piecewise_signal(
        offset_s,
        [
            (0.0, 26.0, 6.0),
            (26.0, 82.0, 20.5),
            (82.0, 102.0, 9.0),
            (102.0, 165.0, 24.5),
            (165.0, 194.0, 11.0),
            (194.0, 258.0, 22.0),
            (258.0, 300.0, 8.0),
        ],
        base_wave_s=6.3,
    )


def _walking_forward_tilt_deg(offset_s: float) -> float:
    return _piecewise_signal(
        offset_s,
        [
            (0.0, 70.0, 4.5),
            (70.0, 118.0, 8.8),
            (118.0, 180.0, 6.2),
            (180.0, 222.0, 9.8),
            (222.0, 300.0, 5.5),
        ],
        base_wave_s=5.0,
    )


def _walking_lateral_deg(offset_s: float) -> float:
    return _piecewise_signal(
        offset_s,
        [
            (0.0, 36.0, 0.0),
            (36.0, 63.0, -10.2),
            (63.0, 88.0, 0.4),
            (88.0, 118.0, 10.6),
            (118.0, 154.0, -9.4),
            (154.0, 188.0, 0.0),
            (188.0, 223.0, 10.8),
            (223.0, 255.0, -10.0),
            (255.0, 300.0, 1.0),
        ],
        base_wave_s=3.3,
    )


def _gaze_for_scene(scene_name: str, offset_s: float, rng: random.Random) -> tuple[str, float]:
    cycle = offset_s % 20.0
    if scene_name == "desk":
        if cycle < 13.0:
            return "screen", round(rng.uniform(0.82, 0.96), 3)
        if cycle < 17.0:
            return "phone", round(rng.uniform(0.65, 0.86), 3)
        return "away", round(rng.uniform(0.58, 0.78), 3)

    if scene_name in {"meeting", "social"}:
        if cycle < 10.0:
            return "person", round(rng.uniform(0.77, 0.93), 3)
        if cycle < 14.0:
            return "screen", round(rng.uniform(0.66, 0.84), 3)
        return "away", round(rng.uniform(0.56, 0.76), 3)

    if cycle < 9.0:
        return "away", round(rng.uniform(0.76, 0.94), 3)
    if cycle < 14.0:
        return "phone", round(rng.uniform(0.62, 0.86), 3)
    return "person", round(rng.uniform(0.58, 0.8), 3)


def _scores_for_scene(scene_label: str, confidence: float, rng: random.Random) -> dict[str, float]:
    ranges = {
        "desk_work": (0.02, 0.18),
        "meeting": (0.02, 0.18),
        "walking": (0.02, 0.16),
        "resting": (0.01, 0.08),
    }
    clip_scores: dict[str, float] = {}
    for label, (low, high) in ranges.items():
        if label == scene_label:
            clip_scores[label] = round(max(low, min(high, confidence)), 3)
        else:
            clip_scores[label] = round(rng.uniform(low, high), 3)

    total = sum(clip_scores.values())
    return {key: round(value / total, 3) for key, value in clip_scores.items()}


def build_dataset(scenario: str, duration_s: int = 300, imu_hz: int = 25, context_interval_s: float = 3.0) -> dict:
    seeds = {"working": 20260408, "meeting": 20260409, "walking": 20260410}
    rng = random.Random(seeds[scenario])

    if scenario == "working":
        scene_segments = [
            {"start": 0.0, "end": 132.0, "scene": "desk", "label": "desk_work", "social": False, "prompt": "a person working at a desk with a laptop", "noise": 37.0},
            {"start": 132.0, "end": 198.0, "scene": "meeting", "label": "meeting", "social": True, "prompt": "a seated interview across a table", "noise": 54.0},
            {"start": 198.0, "end": 249.0, "scene": "walking", "label": "walking", "social": False, "prompt": "a person walking through a hallway", "noise": 60.0},
            {"start": 249.0, "end": 300.0, "scene": "desk", "label": "desk_work", "social": False, "prompt": "back at desk work with laptop", "noise": 39.0},
        ]
        confidence_base = 0.9
        confidence_amp = 0.06
        forward_tilt_fn = _work_tilt_deg
        lateral_tilt_fn = lambda offset_s: 1.4 * math.sin(offset_s / 19.0)
        motion_fn = lambda tilt, offset_s: 0.014 if tilt < 10 else 0.021 if tilt < 16 else 0.028
        context_motion_fn = lambda offset_s: round(max(0.03, min(0.35, abs(math.sin(offset_s / 13.0)) * 0.22 + rng.uniform(0.0, 0.05))), 3)
        description = "Five-minute replay with desk work as the main context plus brief meeting and walking transitions to trigger scene-change reasoning."
    elif scenario == "meeting":
        scene_segments = [
            {"start": 0.0, "end": 82.0, "scene": "meeting", "label": "meeting", "social": True, "prompt": "an interview in a quiet meeting room", "noise": 53.0},
            {"start": 82.0, "end": 118.0, "scene": "desk", "label": "desk_work", "social": False, "prompt": "a short desk note-taking break", "noise": 40.0},
            {"start": 118.0, "end": 224.0, "scene": "meeting", "label": "meeting", "social": True, "prompt": "returning to an interview conversation", "noise": 55.0},
            {"start": 224.0, "end": 262.0, "scene": "social", "label": "meeting", "social": True, "prompt": "standing social conversation near others", "noise": 58.0},
            {"start": 262.0, "end": 300.0, "scene": "meeting", "label": "meeting", "social": True, "prompt": "closing meeting discussion", "noise": 52.0},
        ]
        confidence_base = 0.88
        confidence_amp = 0.05
        forward_tilt_fn = _meeting_tilt_deg
        lateral_tilt_fn = lambda offset_s: 0.9 * math.sin(offset_s / 21.0)
        motion_fn = lambda tilt, offset_s: 0.012 if tilt < 10 else 0.018 if tilt < 18 else 0.024
        context_motion_fn = lambda offset_s: round(max(0.01, min(0.16, abs(math.sin(offset_s / 17.0)) * 0.09 + rng.uniform(0.0, 0.03))), 3)
        description = "Five-minute replay centered on meeting/interview posture stress, with brief desk and social transitions for richer agent coordination."
    else:
        scene_segments = [
            {"start": 0.0, "end": 96.0, "scene": "walking", "label": "walking", "social": False, "prompt": "a person walking on a street", "noise": 64.0},
            {"start": 96.0, "end": 136.0, "scene": "social", "label": "meeting", "social": True, "prompt": "brief stop to talk with a friend", "noise": 60.0},
            {"start": 136.0, "end": 194.0, "scene": "walking", "label": "walking", "social": False, "prompt": "walking again with body sway", "noise": 66.0},
            {"start": 194.0, "end": 232.0, "scene": "meeting", "label": "meeting", "social": True, "prompt": "waiting and chatting at a crossing", "noise": 58.0},
            {"start": 232.0, "end": 300.0, "scene": "walking", "label": "walking", "social": False, "prompt": "resuming street walk", "noise": 65.0},
        ]
        confidence_base = 0.85
        confidence_amp = 0.06
        forward_tilt_fn = _walking_forward_tilt_deg
        lateral_tilt_fn = _walking_lateral_deg
        motion_fn = lambda tilt, offset_s: 0.047 + 0.02 * abs(math.sin(offset_s / 2.0))
        context_motion_fn = lambda offset_s: round(max(0.34, min(0.75, 0.5 + 0.13 * math.sin(offset_s / 2.4) + rng.uniform(-0.035, 0.035))), 3)
        description = "Five-minute replay of street walking with alternating side-bend episodes and temporary social/meeting transitions."

    context_samples = []
    sample_count = int(duration_s / context_interval_s)
    for index in range(sample_count):
        offset_s = round(index * context_interval_s, 3)
        seg = _segment_at(offset_s, scene_segments)
        scene_name = seg["scene"]
        scene_label = seg["label"]
        gaze_target, gaze_conf = _gaze_for_scene(scene_name, offset_s, rng)

        confidence = round(
            max(
                0.58,
                min(0.97, confidence_base + confidence_amp * math.sin(offset_s / 23.0) + rng.uniform(-0.03, 0.03)),
            ),
            3,
        )
        ambient_noise_db = round(seg["noise"] + 2.4 * math.sin(offset_s / 14.0) + rng.uniform(-1.5, 1.5), 2)
        clip_scores = _scores_for_scene(scene_label, confidence, rng)

        context_samples.append({
            "offset_s": offset_s,
            "scene_context": {
                "scene": scene_name,
                "confidence": confidence,
                "social": seg["social"],
                "ambient_noise_db": ambient_noise_db,
            },
            "gaze": {
                "target": gaze_target,
                "confidence": gaze_conf,
            },
            "sensor_log": {
                "scene_label": scene_label,
                "activity_hint": scene_label,
                "confidence": confidence,
                "motion_level": context_motion_fn(offset_s),
                "scores_by_label": clip_scores,
                "top_prompt": seg["prompt"],
                "model": "mock-replay-v1",
            },
        })

    imu_frames = []
    frame_count = duration_s * imu_hz
    for index in range(frame_count):
        offset_s = round(index / imu_hz, 3)
        tilt_deg = forward_tilt_fn(offset_s) + rng.uniform(-0.8, 0.8)
        roll_deg = lateral_tilt_fn(offset_s) + rng.uniform(-0.7, 0.7)
        yaw_deg = 0.8 * math.sin(offset_s / 27.0) + rng.uniform(-0.5, 0.5)
        rad_tilt = math.radians(tilt_deg)
        rad_roll = math.radians(roll_deg)

        ax = 9.81 * math.sin(rad_tilt) + rng.uniform(-0.12, 0.12)
        ay = 9.81 * math.sin(rad_roll) + rng.uniform(-0.08, 0.08)
        az = 9.81 * math.cos(rad_tilt) * math.cos(rad_roll) + rng.uniform(-0.12, 0.12)

        motion_scale = motion_fn(abs(tilt_deg), offset_s)
        imu_frames.append({
            "offset_s": offset_s,
            "type": "imu",
            "ts": int(offset_s * 1000),
            "ax": round(ax, 4),
            "ay": round(ay, 4),
            "az": round(az, 4),
            "gx": round(rng.uniform(-motion_scale, motion_scale), 4),
            "gy": round(rng.uniform(-motion_scale, motion_scale), 4),
            "gz": round(rng.uniform(-motion_scale, motion_scale), 4),
            "tilt_deg": round(tilt_deg, 3),
            "roll_deg": round(roll_deg, 3),
            "yaw_deg": round(yaw_deg, 3),
        })

    return {
        "meta": {
            "name": Path(SCENARIO_OUTPUTS[scenario]).stem,
            "scenario": scenario,
            "duration_s": duration_s,
            "imu_hz": imu_hz,
            "context_interval_s": context_interval_s,
            "loop": True,
            "description": description,
        },
        "context_samples": context_samples,
        "imu_frames": imu_frames,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a local mock replay dataset for camera + IMU")
    parser.add_argument("--scenario", choices=sorted(SCENARIO_OUTPUTS), default="working")
    parser.add_argument("--output")
    parser.add_argument("--all", action="store_true", help="Generate all built-in replay scenarios")
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--imu-hz", type=int, default=25)
    parser.add_argument("--context-interval", type=float, default=3.0)
    args = parser.parse_args()

    scenarios = sorted(SCENARIO_OUTPUTS) if args.all else [args.scenario]
    for scenario in scenarios:
        dataset = build_dataset(
            scenario=scenario,
            duration_s=args.duration,
            imu_hz=args.imu_hz,
            context_interval_s=args.context_interval,
        )

        output_value = args.output if (args.output and not args.all) else SCENARIO_OUTPUTS[scenario]
        output_path = Path(output_value)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(dataset, indent=2))
        print(f"Wrote {scenario} replay dataset to {output_path}")


if __name__ == "__main__":
    main()
