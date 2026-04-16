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
    GazeReading,
    GazeTarget,
    HapticCommand,
    HapticPattern,
    PostureClass,
    PostureReading,
    SceneContext,
    SceneType,
    TensionReading,
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
class HapticActuator(Protocol):
    async def fire(self, pattern: HapticPattern, intensity: float) -> None: ...


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

class MockPostureSensor:
    """Produces posture readings in random or scripted mode."""

    def __init__(
        self,
        scripted: list[tuple[float, PostureReading]] | None = None,
    ) -> None:
        self._scripted = _ScriptedTimeline(scripted) if scripted else None
        self._posture_start = time.time()
        self._current_class = PostureClass.GOOD

    async def read(self) -> PostureReading:
        if self._scripted:
            return self._scripted.current()

        # Random mode: occasionally switch postures
        if random.random() < 0.02:  # ~2% chance per read to switch
            self._current_class = random.choice(list(PostureClass))
            self._posture_start = time.time()

        duration = time.time() - self._posture_start
        deviation = (
            random.gauss(3.0, 2.0) if self._current_class == PostureClass.GOOD
            else random.gauss(20.0, 5.0)
        )
        return PostureReading(
            classification=self._current_class,
            confidence=random.uniform(0.7, 1.0),
            duration_s=duration,
            deviation_degrees=max(0.0, deviation),
        )


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

    async def fire(self, pattern: HapticPattern, intensity: float) -> None:
        cmd = HapticCommand(
            pattern=pattern,
            reason="mock",
            intensity=intensity,
        )
        self.history.append(cmd)
        print(
            f"[HAPTIC] {time.strftime('%H:%M:%S')} "
            f"pattern={pattern.value} intensity={intensity:.1f}"
        )
