"""Shared data contracts for the Kinesis multi-agent system.

This is the single source of truth for all data shapes that cross component
boundaries. Every agent and the shared state server import from here.
When the hardware team changes a sensor format, update this file first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import time


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PostureClass(Enum):
    GOOD = "good"
    SLOUCHING = "slouching"
    LEANING_LEFT = "leaning_left"
    LEANING_RIGHT = "leaning_right"
    HUNCHED = "hunched"
    UNKNOWN = "unknown"


class SceneType(Enum):
    DESK = "desk"
    MEETING = "meeting"
    WALKING = "walking"
    STANDING = "standing"
    SOCIAL = "social"
    UNKNOWN = "unknown"


class GazeTarget(Enum):
    SCREEN = "screen"
    PERSON = "person"
    PHONE = "phone"
    AWAY = "away"
    UNKNOWN = "unknown"


class IMULocation(str, Enum):
    UPPER_BACK = "upper_back"   # T3-T6, between shoulder blades
    LOWER_BACK = "lower_back"   # L2-L4, lumbar region


class VibrationZone(str, Enum):
    SHOULDER_L = "shoulder_l"   # left scapular region
    SHOULDER_R = "shoulder_r"   # right scapular region
    LUMBAR_L   = "lumbar_l"     # lower back left
    LUMBAR_R   = "lumbar_r"     # lower back right


class EMGChannel(str, Enum):
    UPPER_BACK = "upper_back"  # rhomboid/trapezius area — detects active scapular retraction


class EMSChannel(str, Enum):
    RHOMBOID_L     = "rhomboid_l"      # left rhomboid → retract left scapula
    RHOMBOID_R     = "rhomboid_r"      # right rhomboid → retract right scapula
    LUMBAR_ERECTOR = "lumbar_erector"  # center lumbar erector → extend lower back


class HapticPattern(str, Enum):
    GENTLE       = "gentle"
    FIRM         = "firm"
    PULSE        = "pulse"
    LEFT_NUDGE   = "left_nudge"
    RIGHT_NUDGE  = "right_nudge"
    LUMBAR_ALERT = "lumbar_alert"   # lower back vibration only
    BILATERAL    = "bilateral"      # both shoulders simultaneously


class InterventionMode(str, Enum):
    SILENT = "silent"
    GENTLE = "gentle"
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"


class EscalationType(Enum):
    HABIT_CHAIN_PASSED = "habit_chain_passed"
    HAPTIC_IGNORED = "haptic_ignored"
    AMBIGUOUS_SCENE = "ambiguous_scene"
    HIGH_TENSION = "high_tension"
    USER_FEEDBACK = "user_feedback"


# ---------------------------------------------------------------------------
# Sensor readings
# ---------------------------------------------------------------------------

@dataclass
class IMUReading:
    """Raw reading from a single IMU sensor at a fixed body location."""
    location: IMULocation
    pitch_deg: float        # forward/backward tilt (positive = forward lean)
    roll_deg: float         # left/right lean (positive = right lean)
    yaw_deg: float          # axial rotation
    confidence: float       # 0.0 - 1.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location.value,
            "pitch_deg": self.pitch_deg,
            "roll_deg": self.roll_deg,
            "yaw_deg": self.yaw_deg,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IMUReading:
        return cls(
            location=IMULocation(d["location"]),
            pitch_deg=d["pitch_deg"],
            roll_deg=d["roll_deg"],
            yaw_deg=d["yaw_deg"],
            confidence=d["confidence"],
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class PostureReading:
    # High-level classification derived from both IMUs
    classification: PostureClass
    confidence: float       # 0.0 - 1.0
    duration_s: float       # seconds in this posture
    deviation_degrees: float  # overall deviation scalar from upright

    # Per-IMU raw data
    imu_upper: Optional[IMUReading] = None  # upper_back IMU
    imu_lower: Optional[IMUReading] = None  # lower_back IMU

    # Derived spinal metrics
    lateral_asymmetry_deg: float = 0.0  # |upper.roll - lower.roll|, detects lateral lean
    flexion_deg: float = 0.0            # upper.pitch - lower.pitch, detects hunching

    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "confidence": self.confidence,
            "duration_s": self.duration_s,
            "deviation_degrees": self.deviation_degrees,
            "imu_upper": self.imu_upper.to_dict() if self.imu_upper else None,
            "imu_lower": self.imu_lower.to_dict() if self.imu_lower else None,
            "lateral_asymmetry_deg": self.lateral_asymmetry_deg,
            "flexion_deg": self.flexion_deg,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PostureReading:
        return cls(
            classification=PostureClass(d["classification"]),
            confidence=d["confidence"],
            duration_s=d["duration_s"],
            deviation_degrees=d["deviation_degrees"],
            imu_upper=IMUReading.from_dict(d["imu_upper"]) if d.get("imu_upper") else None,
            imu_lower=IMUReading.from_dict(d["imu_lower"]) if d.get("imu_lower") else None,
            lateral_asymmetry_deg=d.get("lateral_asymmetry_deg", 0.0),
            flexion_deg=d.get("flexion_deg", 0.0),
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class TensionReading:
    level: float  # 0.0 - 1.0 normalized
    zone: str  # "shoulders", "lower_back", "neck"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "zone": self.zone,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TensionReading:
        return cls(
            level=d["level"],
            zone=d["zone"],
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class SceneContext:
    scene: SceneType
    confidence: float  # 0.0 - 1.0
    social: bool  # is someone else present/talking
    ambient_noise_db: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene.value,
            "confidence": self.confidence,
            "social": self.social,
            "ambient_noise_db": self.ambient_noise_db,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SceneContext:
        return cls(
            scene=SceneType(d["scene"]),
            confidence=d["confidence"],
            social=d["social"],
            ambient_noise_db=d["ambient_noise_db"],
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class GazeReading:
    target: GazeTarget
    confidence: float  # 0.0 - 1.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GazeReading:
        return cls(
            target=GazeTarget(d["target"]),
            confidence=d["confidence"],
            timestamp=d.get("timestamp", time.time()),
        )


# ---------------------------------------------------------------------------
# Planner outputs
# ---------------------------------------------------------------------------

@dataclass
class PlannerStrategy:
    mode: InterventionMode
    attention_budget_remaining: int  # interventions left today
    active_chain: Optional[str]  # habit chain name or None
    chain_step: int  # 0 if no chain active
    message: str  # latest planner text for user
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "attention_budget_remaining": self.attention_budget_remaining,
            "active_chain": self.active_chain,
            "chain_step": self.chain_step,
            "message": self.message,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlannerStrategy:
        return cls(
            mode=InterventionMode(d["mode"]),
            attention_budget_remaining=d["attention_budget_remaining"],
            active_chain=d.get("active_chain"),
            chain_step=d.get("chain_step", 0),
            message=d.get("message", ""),
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class HapticCommand:
    pattern: HapticPattern
    reason: str
    intensity: float        # 0.0 - 1.0
    zone: Optional[VibrationZone] = None  # None = all zones
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "reason": self.reason,
            "intensity": self.intensity,
            "zone": self.zone.value if self.zone else None,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HapticCommand:
        return cls(
            pattern=HapticPattern(d["pattern"]),
            reason=d["reason"],
            intensity=d["intensity"],
            zone=VibrationZone(d["zone"]) if d.get("zone") else None,
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class EMGReading:
    """Raw EMG reading from the muscle sensor module."""
    channel: EMGChannel
    signal_mv: float        # millivolts, rectified amplitude
    is_active: bool         # True when signal exceeds contraction threshold
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value,
            "signal_mv": self.signal_mv,
            "is_active": self.is_active,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EMGReading:
        return cls(
            channel=EMGChannel(d["channel"]),
            signal_mv=d["signal_mv"],
            is_active=d["is_active"],
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class EMSCommand:
    """Command to fire an EMS pulse on a specific muscle channel."""
    channel: EMSChannel
    intensity_ma: float     # milliamps — server hard cap: 15.0 mA
    duration_ms: int        # milliseconds — server hard cap: 3000 ms
    frequency_hz: float     # stimulation frequency, 20.0–80.0 Hz typical
    reason: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value,
            "intensity_ma": self.intensity_ma,
            "duration_ms": self.duration_ms,
            "frequency_hz": self.frequency_hz,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EMSCommand:
        return cls(
            channel=EMSChannel(d["channel"]),
            intensity_ma=d["intensity_ma"],
            duration_ms=d["duration_ms"],
            frequency_hz=d["frequency_hz"],
            reason=d["reason"],
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class Escalation:
    type: EscalationType
    source_device: str  # "kinesess" or "glasses"
    details: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "source_device": self.source_device,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Escalation:
        return cls(
            type=EscalationType(d["type"]),
            source_device=d["source_device"],
            details=d["details"],
            timestamp=d.get("timestamp", time.time()),
        )


# ---------------------------------------------------------------------------
# State wrapper (used by shared state server)
# ---------------------------------------------------------------------------

@dataclass
class StateEntry:
    """Wraps any state value stored in the shared state server."""
    device_id: str
    key: str
    data: dict[str, Any]
    confidence: float  # 0.0 - 1.0
    timestamp: float = field(default_factory=time.time)
    version: int = 0

    @property
    def stale(self) -> bool:
        """State is stale if older than 30 seconds."""
        return (time.time() - self.timestamp) > 30.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "key": self.key,
            "data": self.data,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "version": self.version,
            "stale": self.stale,
        }
