# 这里把原始 IMU 时间窗变成 agent 容易使用的 posture features。
# 先用最简单的 trunk tilt 估计和 motion level 就够了。

import math
from typing import Dict, List


def estimate_tilt_deg(ax: float, ay: float, az: float) -> float:
    """
    一个非常简单的基于加速度重力方向的倾角估计。
    这里只是 MVP 近似，不追求严格姿态解算。
    """
    denom = math.sqrt(ay * ay + az * az) + 1e-6
    tilt_rad = math.atan2(ax, denom)
    return math.degrees(tilt_rad)


def compute_motion_level(frames: List[Dict]) -> float:
    if len(frames) < 2:
        return 0.0

    total = 0.0
    count = 0
    for frame in frames:
        gx = frame.get("gx", 0.0)
        gy = frame.get("gy", 0.0)
        gz = frame.get("gz", 0.0)
        total += abs(gx) + abs(gy) + abs(gz)
        count += 1

    return total / max(count, 1)


def compute_features(frames: List[Dict], baseline_tilt_deg: float = 0.0) -> Dict:
    if not frames:
        return {
            "ok": False,
            "tilt_deg": 0.0,
            "mean_tilt_deg": 0.0,
            "deviation_deg": 0.0,
            "motion_level": 0.0,
            "stillness_score": 0.0,
            "num_frames": 0,
        }

    tilts = [
        estimate_tilt_deg(
            frame.get("ax", 0.0),
            frame.get("ay", 0.0),
            frame.get("az", 0.0),
        )
        for frame in frames
    ]

    mean_tilt = sum(tilts) / len(tilts)
    motion_level = compute_motion_level(frames)

    # 这里简单把低运动视为更静止
    stillness_score = max(0.0, 1.0 - min(1.0, motion_level * 5.0))

    return {
        "ok": True,
        "tilt_deg": tilts[-1],
        "mean_tilt_deg": mean_tilt,
        "deviation_deg": mean_tilt - baseline_tilt_deg,
        "motion_level": motion_level,
        "stillness_score": stillness_score,
        "num_frames": len(frames),
    }