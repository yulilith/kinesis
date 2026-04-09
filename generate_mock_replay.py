from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


SCENARIO_OUTPUTS = {
    "working": "mock_data/desk_work_focus_5min.json",
    "meeting": "mock_data/interview_forward_lean_5min.json",
    "walking": "mock_data/street_walk_sidebend_5min.json",
}


def _work_tilt_deg(offset_s: float) -> float:
    if offset_s < 45.0:
        return 3.0 + 1.0 * math.sin(offset_s / 9.0)
    if offset_s < 105.0:
        return 9.0 + 3.0 * math.sin(offset_s / 12.0)
    if offset_s < 140.0:
        return 4.0 + 1.5 * math.sin(offset_s / 8.0)
    if offset_s < 220.0:
        return 13.0 + 4.0 * math.sin(offset_s / 10.0)
    if offset_s < 270.0:
        return 18.0 + 3.0 * math.sin(offset_s / 7.0)
    return 5.0 + 1.5 * math.sin(offset_s / 11.0)


def _meeting_tilt_deg(offset_s: float) -> float:
    cycle = offset_s % 95.0
    if cycle < 18.0:
        return 4.0 + 0.8 * math.sin(cycle / 5.0)
    if cycle < 52.0:
        return 16.0 + 2.8 * math.sin(cycle / 6.0)
    if cycle < 76.0:
        return 21.0 + 2.0 * math.sin(cycle / 5.5)
    return 7.0 + 1.2 * math.sin(cycle / 4.0)


def _walking_forward_tilt_deg(offset_s: float) -> float:
    cycle = offset_s % 70.0
    if cycle < 20.0:
        return 2.0 + 0.7 * math.sin(cycle / 4.0)
    if cycle < 45.0:
        return 6.0 + 1.3 * math.sin(cycle / 3.3)
    return 3.5 + 0.9 * math.sin(cycle / 4.7)


def _walking_lateral_deg(offset_s: float) -> float:
    cycle = offset_s % 80.0
    if cycle < 16.0:
        return 0.0
    if cycle < 36.0:
        return -8.5 + 1.4 * math.sin(cycle / 2.8)
    if cycle < 52.0:
        return 0.0 + 0.8 * math.sin(cycle / 2.5)
    if cycle < 72.0:
        return 9.0 + 1.6 * math.sin(cycle / 3.0)
    return 0.0


def _gaze_for_offset(offset_s: float, rng: random.Random) -> tuple[str, float]:
    cycle = offset_s % 30.0
    if cycle < 20.0:
        return "screen", round(rng.uniform(0.82, 0.97), 3)
    if cycle < 24.0:
        return "phone", round(rng.uniform(0.68, 0.88), 3)
    if cycle < 28.0:
        return "away", round(rng.uniform(0.60, 0.82), 3)
    return "screen", round(rng.uniform(0.78, 0.95), 3)


def _meeting_gaze_for_offset(offset_s: float, rng: random.Random) -> tuple[str, float]:
    cycle = offset_s % 24.0
    if cycle < 11.0:
        return "person", round(rng.uniform(0.78, 0.93), 3)
    if cycle < 18.0:
        return "screen", round(rng.uniform(0.70, 0.88), 3)
    if cycle < 21.0:
        return "away", round(rng.uniform(0.58, 0.78), 3)
    return "person", round(rng.uniform(0.76, 0.91), 3)


def _walking_gaze_for_offset(offset_s: float, rng: random.Random) -> tuple[str, float]:
    cycle = offset_s % 18.0
    if cycle < 10.0:
        return "away", round(rng.uniform(0.76, 0.95), 3)
    if cycle < 14.0:
        return "phone", round(rng.uniform(0.62, 0.86), 3)
    return "person", round(rng.uniform(0.55, 0.78), 3)


def build_dataset(scenario: str, duration_s: int = 300, imu_hz: int = 25, context_interval_s: float = 3.0) -> dict:
    seeds = {"working": 20260408, "meeting": 20260409, "walking": 20260410}
    rng = random.Random(seeds[scenario])

    if scenario == "working":
        scene_name = "desk"
        scene_label = "desk_work"
        top_prompt = "a person working at a desk with a laptop"
        gaze_fn = _gaze_for_offset
        social_fn = lambda offset_s: False
        noise_fn = lambda offset_s: round(37.0 + 2.5 * math.sin(offset_s / 17.0) + rng.uniform(-1.2, 1.2), 2)
        confidence_fn = lambda offset_s: round(0.89 + 0.05 * math.sin(offset_s / 30.0) + rng.uniform(-0.02, 0.02), 3)
        forward_tilt_fn = _work_tilt_deg
        lateral_tilt_fn = lambda offset_s: 1.4 * math.sin(offset_s / 19.0)
        motion_fn = lambda tilt, offset_s: 0.012 if tilt < 8 else 0.02 if tilt < 14 else 0.03
        context_motion_fn = lambda offset_s: round(max(0.02, min(0.25, abs(math.sin(offset_s / 14.0)) * 0.18 + rng.uniform(0.0, 0.04))), 3)
        score_ranges = {"desk_work": (0.72, 0.95), "meeting": (0.02, 0.09), "walking": (0.01, 0.05), "resting": (0.01, 0.04)}
        description = "Five-minute replay of desk work with repeated slouch / recovery cycles for posture interventions."
    elif scenario == "meeting":
        scene_name = "meeting"
        scene_label = "meeting"
        top_prompt = "someone attending an interview or meeting across a table"
        gaze_fn = _meeting_gaze_for_offset
        social_fn = lambda offset_s: True
        noise_fn = lambda offset_s: round(54.0 + 3.0 * math.sin(offset_s / 20.0) + rng.uniform(-1.5, 1.5), 2)
        confidence_fn = lambda offset_s: round(0.87 + 0.04 * math.sin(offset_s / 28.0) + rng.uniform(-0.02, 0.02), 3)
        forward_tilt_fn = _meeting_tilt_deg
        lateral_tilt_fn = lambda offset_s: 0.9 * math.sin(offset_s / 21.0)
        motion_fn = lambda tilt, offset_s: 0.01 if tilt < 10 else 0.015 if tilt < 18 else 0.02
        context_motion_fn = lambda offset_s: round(max(0.01, min(0.12, abs(math.sin(offset_s / 18.0)) * 0.07 + rng.uniform(0.0, 0.02))), 3)
        score_ranges = {"desk_work": (0.08, 0.18), "meeting": (0.70, 0.9), "walking": (0.01, 0.04), "resting": (0.02, 0.05)}
        description = "Five-minute replay of an interview / meeting with sustained forward lean and social context to trigger skip decisions."
    else:
        scene_name = "walking"
        scene_label = "walking"
        top_prompt = "a person walking along a street with body sway"
        gaze_fn = _walking_gaze_for_offset
        social_fn = lambda offset_s: (offset_s % 42.0) > 30.0
        noise_fn = lambda offset_s: round(63.0 + 5.5 * math.sin(offset_s / 11.0) + rng.uniform(-2.0, 2.0), 2)
        confidence_fn = lambda offset_s: round(0.84 + 0.05 * math.sin(offset_s / 22.0) + rng.uniform(-0.03, 0.03), 3)
        forward_tilt_fn = _walking_forward_tilt_deg
        lateral_tilt_fn = _walking_lateral_deg
        motion_fn = lambda tilt, offset_s: 0.05 + 0.015 * abs(math.sin(offset_s / 2.2))
        context_motion_fn = lambda offset_s: round(max(0.32, min(0.68, 0.46 + 0.12 * math.sin(offset_s / 2.6) + rng.uniform(-0.03, 0.03))), 3)
        score_ranges = {"desk_work": (0.02, 0.07), "meeting": (0.02, 0.06), "walking": (0.72, 0.9), "resting": (0.01, 0.04)}
        description = "Five-minute replay of street walking with mild alternating side-bend episodes and high motion."

    context_samples = []
    sample_count = int(duration_s / context_interval_s)
    for index in range(sample_count):
        offset_s = round(index * context_interval_s, 3)
        gaze_target, gaze_conf = gaze_fn(offset_s, rng)
        confidence = confidence_fn(offset_s)
        ambient_noise_db = noise_fn(offset_s)
        clip_scores = {}
        for label, (low, high) in score_ranges.items():
            if label == scene_label:
                clip_scores[label] = round(max(low, min(high, confidence)), 3)
            else:
                clip_scores[label] = round(rng.uniform(low, high), 3)
        total = sum(clip_scores.values())
        clip_scores = {key: round(value / total, 3) for key, value in clip_scores.items()}

        context_samples.append({
            "offset_s": offset_s,
            "scene_context": {
                "scene": scene_name,
                "confidence": confidence,
                "social": social_fn(offset_s),
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
                "top_prompt": top_prompt,
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
