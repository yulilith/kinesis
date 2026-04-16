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


class HapticPattern(Enum):
    GENTLE = "gentle"
    FIRM = "firm"
    PULSE = "pulse"
    LEFT_NUDGE = "left_nudge"
    RIGHT_NUDGE = "right_nudge"


class InterventionMode(Enum):
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
class PostureReading:
    classification: PostureClass
    confidence: float  # 0.0 - 1.0
    duration_s: float  # seconds in this posture
    deviation_degrees: float  # deviation from calibrated upright
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "confidence": self.confidence,
            "duration_s": self.duration_s,
            "deviation_degrees": self.deviation_degrees,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PostureReading:
        return cls(
            classification=PostureClass(d["classification"]),
            confidence=d["confidence"],
            duration_s=d["duration_s"],
            deviation_degrees=d["deviation_degrees"],
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
    intensity: float  # 0.0 - 1.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "reason": self.reason,
            "intensity": self.intensity,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HapticCommand:
        return cls(
            pattern=HapticPattern(d["pattern"]),
            reason=d["reason"],
            intensity=d["intensity"],
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
