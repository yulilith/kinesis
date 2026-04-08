"""Protocol definitions and mock implementations for all hardware sensors.

Each sensor type is a Protocol (interface). Mock and real implementations
share the same interface. Swapping mock -> real hardware means implementing
the Protocol and flipping config.use_mock_sensors.

Mocks support two modes:
- Random: realistic-ish random data for development/testing
- Scripted: follows a timeline of (duration_s, reading) pairs for demos
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import (
    EMSChannel,
    EMSCommand,
    GazeReading,
    GazeTarget,
    HapticCommand,
    HapticPattern,
    IMULocation,
    IMUReading,
    PostureClass,
    PostureReading,
    SceneContext,
    SceneType,
    TensionReading,
    VibrationZone,
)


# ---------------------------------------------------------------------------
# Protocols (the interface contracts)
# ---------------------------------------------------------------------------

@runtime_checkable
class PostureSensor(Protocol):
    async def read(self) -> PostureReading: ...


@runtime_checkable
class TensionSensor(Protocol):
    async def read(self) -> TensionReading: ...


@runtime_checkable
class SceneSensor(Protocol):
    async def read(self) -> SceneContext: ...


@runtime_checkable
class GazeSensor(Protocol):
    async def read(self) -> GazeReading: ...


@runtime_checkable
class IMUSensor(Protocol):
    async def read(self) -> IMUReading: ...


@runtime_checkable
class HapticActuator(Protocol):
    async def fire(self, pattern: HapticPattern, intensity: float,
                   zone: VibrationZone | None = None) -> None: ...


@runtime_checkable
class EMSActuator(Protocol):
    async def fire(self, cmd: EMSCommand) -> bool: ...


# ---------------------------------------------------------------------------
# Scripted timeline helper
# ---------------------------------------------------------------------------

class _ScriptedTimeline[T]:
    """Cycles through a list of (duration_s, value) pairs."""

    def __init__(self, timeline: list[tuple[float, T]]) -> None:
        self._timeline = timeline
        self._start_time = time.time()
        self._total_duration = sum(d for d, _ in timeline)

    def current(self) -> T:
        elapsed = (time.time() - self._start_time) % self._total_duration
        accumulated = 0.0
        for duration, value in self._timeline:
            accumulated += duration
            if elapsed < accumulated:
                return value
        return self._timeline[-1][1]


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class MockIMUSensor:
    """Single IMU at a fixed body location. Produces pitch/roll/yaw readings.

    Good posture:  small angles (pitch ≈ 0–5°, roll ≈ 0–3°)
    Bad posture:   larger pitch (forward lean) or roll (lateral lean)
    """

    # Typical angle ranges per posture state (pitch_mean, pitch_std, roll_std)
    _GOOD_ANGLES = (3.0, 2.0, 2.0)
    _BAD_ANGLES  = (22.0, 6.0, 5.0)

    def __init__(self, location: IMULocation) -> None:
        self._location = location
        self._is_bad = False
        self._switch_timer = time.time()

    async def read(self) -> IMUReading:
        # Randomly toggle good/bad state every ~30s
        if time.time() - self._switch_timer > random.uniform(20.0, 40.0):
            self._is_bad = not self._is_bad
            self._switch_timer = time.time()

        pitch_mean, pitch_std, roll_std = (
            self._BAD_ANGLES if self._is_bad else self._GOOD_ANGLES
        )
        # Lower back IMU shows slightly less pitch than upper back when hunching
        if self._location == IMULocation.LOWER_BACK:
            pitch_mean *= 0.6

        return IMUReading(
            location=self._location,
            pitch_deg=max(0.0, random.gauss(pitch_mean, pitch_std)),
            roll_deg=random.gauss(0.0, roll_std),
            yaw_deg=random.gauss(0.0, 1.5),
            confidence=random.uniform(0.75, 1.0),
        )


class MockPostureSensor:
    """Fuses readings from two MockIMUSensors into a PostureReading.

    Scripted mode: uses a pre-defined timeline of (duration_s, PostureReading).
    Random mode:   drives both IMUs independently and derives classification.
    """

    def __init__(
        self,
        scripted: list[tuple[float, PostureReading]] | None = None,
    ) -> None:
        self._scripted = _ScriptedTimeline(scripted) if scripted else None
        self._upper = MockIMUSensor(IMULocation.UPPER_BACK)
        self._lower = MockIMUSensor(IMULocation.LOWER_BACK)
        self._posture_start = time.time()
        self._current_class = PostureClass.GOOD

    async def read(self) -> PostureReading:
        if self._scripted:
            return self._scripted.current()

        upper = await self._upper.read()
        lower = await self._lower.read()

        # Derived spinal metrics
        flexion_deg           = upper.pitch_deg - lower.pitch_deg
        lateral_asymmetry_deg = abs(upper.roll_deg - lower.roll_deg)
        deviation_degrees     = upper.pitch_deg  # overall deviation = upper pitch

        # Classify from IMU angles
        new_class = self._classify(upper, flexion_deg, lateral_asymmetry_deg)
        if new_class != self._current_class:
            self._current_class = new_class
            self._posture_start = time.time()

        return PostureReading(
            classification=self._current_class,
            confidence=min(upper.confidence, lower.confidence),
            duration_s=time.time() - self._posture_start,
            deviation_degrees=round(deviation_degrees, 1),
            imu_upper=upper,
            imu_lower=lower,
            lateral_asymmetry_deg=round(lateral_asymmetry_deg, 1),
            flexion_deg=round(flexion_deg, 1),
        )

    @staticmethod
    def _classify(upper: IMUReading, flexion_deg: float,
                  lateral_asymmetry_deg: float) -> PostureClass:
        if upper.pitch_deg > 30 and flexion_deg > 10:
            return PostureClass.HUNCHED
        if upper.pitch_deg > 15:
            return PostureClass.SLOUCHING
        if lateral_asymmetry_deg > 8:
            return (PostureClass.LEANING_LEFT if upper.roll_deg < 0
                    else PostureClass.LEANING_RIGHT)
        if upper.pitch_deg < 8:
            return PostureClass.GOOD
        return PostureClass.UNKNOWN


class MockTensionSensor:
    """Produces tension readings that ramp up over time, reset on 'stretch'."""

    def __init__(
        self,
        scripted: list[tuple[float, TensionReading]] | None = None,
    ) -> None:
        self._scripted = _ScriptedTimeline(scripted) if scripted else None
        self._ramp_start = time.time()
        self._zones = ["shoulders", "lower_back", "neck"]

    async def read(self) -> TensionReading:
        if self._scripted:
            return self._scripted.current()

        # Ramp tension from 0.1 to 0.9 over 10 minutes, then reset
        elapsed = time.time() - self._ramp_start
        cycle = elapsed % 600.0  # 10 minute cycle
        base_level = 0.1 + (0.8 * cycle / 600.0)
        noise = random.gauss(0.0, 0.05)
        level = max(0.0, min(1.0, base_level + noise))

        return TensionReading(
            level=level,
            zone=random.choice(self._zones),
        )


class MockSceneSensor:
    """Produces scene context following a scripted day or random transitions."""

    # Default scripted day: desk(5min) -> meeting(3min) -> walking(1min) -> repeat
    DEFAULT_TIMELINE: list[tuple[float, SceneContext]] = [
        (300.0, SceneContext(SceneType.DESK, 0.95, False, 35.0)),
        (180.0, SceneContext(SceneType.MEETING, 0.90, True, 55.0)),
        (60.0, SceneContext(SceneType.WALKING, 0.85, False, 60.0)),
    ]

    def __init__(
        self,
        scripted: list[tuple[float, SceneContext]] | None = None,
    ) -> None:
        timeline = scripted or self.DEFAULT_TIMELINE
        self._scripted = _ScriptedTimeline(timeline)

    async def read(self) -> SceneContext:
        base = self._scripted.current()
        # Add slight noise to confidence
        return SceneContext(
            scene=base.scene,
            confidence=max(0.5, min(1.0, base.confidence + random.gauss(0.0, 0.03))),
            social=base.social,
            ambient_noise_db=base.ambient_noise_db + random.gauss(0.0, 3.0),
        )


class MockGazeSensor:
    """Produces gaze readings weighted by current scene context."""

    # Gaze distribution weights per scene type
    GAZE_WEIGHTS: dict[SceneType, dict[GazeTarget, float]] = {
        SceneType.DESK: {GazeTarget.SCREEN: 0.6, GazeTarget.PHONE: 0.2, GazeTarget.AWAY: 0.15, GazeTarget.PERSON: 0.05},
        SceneType.MEETING: {GazeTarget.PERSON: 0.5, GazeTarget.SCREEN: 0.2, GazeTarget.PHONE: 0.15, GazeTarget.AWAY: 0.15},
        SceneType.WALKING: {GazeTarget.AWAY: 0.5, GazeTarget.PHONE: 0.3, GazeTarget.PERSON: 0.15, GazeTarget.SCREEN: 0.05},
        SceneType.STANDING: {GazeTarget.PERSON: 0.3, GazeTarget.PHONE: 0.3, GazeTarget.AWAY: 0.3, GazeTarget.SCREEN: 0.1},
        SceneType.SOCIAL: {GazeTarget.PERSON: 0.6, GazeTarget.AWAY: 0.2, GazeTarget.PHONE: 0.15, GazeTarget.SCREEN: 0.05},
        SceneType.UNKNOWN: {GazeTarget.UNKNOWN: 1.0},
    }

    def __init__(
        self,
        scene_sensor: MockSceneSensor | None = None,
        scripted: list[tuple[float, GazeReading]] | None = None,
    ) -> None:
        self._scripted = _ScriptedTimeline(scripted) if scripted else None
        self._scene_sensor = scene_sensor

    async def read(self) -> GazeReading:
        if self._scripted:
            return self._scripted.current()

        # Determine current scene for weighted gaze
        scene = SceneType.DESK
        if self._scene_sensor:
            ctx = await self._scene_sensor.read()
            scene = ctx.scene

        weights = self.GAZE_WEIGHTS.get(scene, self.GAZE_WEIGHTS[SceneType.UNKNOWN])
        targets = list(weights.keys())
        probs = list(weights.values())
        target = random.choices(targets, weights=probs, k=1)[0]

        return GazeReading(
            target=target,
            confidence=random.uniform(0.6, 1.0),
        )


class MockHapticActuator:
    """Logs haptic commands to console instead of firing real hardware."""

    def __init__(self) -> None:
        self.history: list[HapticCommand] = []

    async def fire(self, pattern: HapticPattern, intensity: float,
                   zone: VibrationZone | None = None) -> None:
        cmd = HapticCommand(pattern=pattern, reason="mock",
                            intensity=intensity, zone=zone)
        self.history.append(cmd)
        zone_str = zone.value if zone else "all"
        print(
            f"[HAPTIC] {time.strftime('%H:%M:%S')} "
            f"pattern={pattern.value} zone={zone_str} intensity={intensity:.1f}"
        )


class MockEMSActuator:
    """Logs EMS commands to console. Enforces per-channel cooldown and intensity cap."""

    MAX_INTENSITY_MA = 15.0
    COOLDOWN_S       = 120.0

    def __init__(self) -> None:
        self.history: list[EMSCommand] = []
        self._last_fire: dict[EMSChannel, float] = {}

    async def fire(self, cmd: EMSCommand) -> bool:
        """Returns True if fired, False if blocked by cooldown or safety cap."""
        now = time.time()
        last = self._last_fire.get(cmd.channel, 0.0)
        if now - last < self.COOLDOWN_S:
            wait = self.COOLDOWN_S - (now - last)
            print(f"[EMS] {time.strftime('%H:%M:%S')} "
                  f"channel={cmd.channel.value} BLOCKED cooldown {wait:.0f}s remaining")
            return False

        safe_cmd = EMSCommand(
            channel=cmd.channel,
            intensity_ma=min(cmd.intensity_ma, self.MAX_INTENSITY_MA),
            duration_ms=min(cmd.duration_ms, 3000),
            frequency_hz=max(20.0, min(cmd.frequency_hz, 80.0)),
            reason=cmd.reason,
        )
        self._last_fire[cmd.channel] = now
        self.history.append(safe_cmd)
        print(
            f"[EMS]   {time.strftime('%H:%M:%S')} "
            f"channel={safe_cmd.channel.value} "
            f"{safe_cmd.intensity_ma:.1f}mA "
            f"{safe_cmd.duration_ms}ms "
            f"{safe_cmd.frequency_hz:.0f}Hz "
            f"reason={safe_cmd.reason}"
        )
        return True
