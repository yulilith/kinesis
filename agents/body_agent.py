"""Kinesess body sensor agent — interprets posture/tension and decides interventions.

This is an LLM agent. It reads sensors on a fast loop (500ms), writes to the
shared state blackboard, and invokes Claude when a threshold is crossed
(bad posture > 30s, high tension). Before deciding, it reads the glasses agent's
scene context and can ask the glasses agent questions via the discussion channel.

Usage:
    # Mock sensors (default)
    python agents/body_agent.py
    python agents/body_agent.py --demo

    # Real ESP32 IMU sensor
    python agents/body_agent.py --esp32 --serial-port /dev/cu.usbserial-0001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import anthropic
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import PostureClass, PostureReading, TensionReading
from ble.mock_sensors import MockPostureSensor, MockTensionSensor

# Teammate's ESP32 bridge + feature extraction (body-agent/python/)
BODY_AGENT_DIR = str(Path(__file__).resolve().parent.parent / "body-agent" / "python")
sys.path.insert(0, BODY_AGENT_DIR)

# Deviation → PostureClass mapping
def _deviation_to_posture(dev_deg: float) -> PostureClass:
    abs_dev = abs(dev_deg)
    if abs_dev < 8:
        return PostureClass.GOOD
    elif abs_dev < 15:
        return PostureClass.SLOUCHING
    elif dev_deg > 0:
        return PostureClass.HUNCHED
    else:
        return PostureClass.LEANING_LEFT if abs_dev < 20 else PostureClass.LEANING_RIGHT

# Scripted demo: good(20s) → slouching(40s) → good(15s) → hunched(35s) → repeat
DEMO_POSTURE_TIMELINE = [
    (20.0, PostureReading(PostureClass.GOOD, 0.9, 20.0, 3.0)),
    (40.0, PostureReading(PostureClass.SLOUCHING, 0.85, 40.0, 18.0)),
    (15.0, PostureReading(PostureClass.GOOD, 0.9, 15.0, 2.5)),
    (35.0, PostureReading(PostureClass.HUNCHED, 0.88, 35.0, 22.0)),
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SERVER_URL = "http://localhost:8080/mcp"
SENSOR_INTERVAL_S = 0.5
LLM_COOLDOWN_S = 30.0
BAD_POSTURE_THRESHOLD_S = 30.0
HIGH_TENSION_THRESHOLD = 0.8
HIGH_TENSION_DURATION_S = 10.0
MAX_TOOL_ROUNDS = 5

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """\
You are the Kinesess body sensor agent — a posture correction assistant embedded in a wearable device.

## Your Role
You interpret body sensor data (posture classification, muscle tension) and decide when to fire haptic interventions. You are called ONLY when a threshold has been crossed (bad posture sustained 30+ seconds, or high muscle tension).

## IMPORTANT: Always consult the Context Agent first
Before taking ANY action, you MUST ask the glasses/context agent for their recommendation using ask_agent. Describe what you're seeing and ask whether now is a good time to intervene and what approach they recommend. Use from_agent="kinesess" and to_agent="glasses".

Example: ask_agent(from_agent="kinesess", to_agent="glasses", question="User has been slouching for 45 seconds with 18 degree deviation. Should I intervene? What pattern and intensity do you recommend?", context="posture=slouching, deviation=18deg, tension=0.3")

After receiving their reply, incorporate their advice into your decision. Then act.

## Decision Framework (apply AFTER consulting context agent)

1. COACHING MODE (from brain agent):
   - "silent": Do NOT fire haptics. Log only.
   - "gentle": Sparse, gentle haptics. Skip borderline cases.
   - "normal": Fire when posture is clearly bad for sustained period.
   - "aggressive": Fire more readily, use firm patterns.

2. POSTURE SEVERITY: 5° deviation is minor. 25°+ for 2+ minutes is serious.

3. TENSION CONTEXT: High tension + bad posture likely means stress → gentle pulse.

4. ATTENTION BUDGET: If budget low, only intervene for serious issues.

## Available Tools
- ask_agent(from_agent, to_agent, question, context): ALWAYS call this first to consult the glasses agent.
- send_haptic(pattern, reason, intensity): Fire haptic. Patterns: "gentle", "firm", "pulse", "left_nudge", "right_nudge". Intensity 0.0-1.0.
- update_state(device_id, key, data, confidence): Write state to blackboard.
- display_overlay(message, duration_ms, position): Show text on glasses.

## Output
1. First call ask_agent to consult the context agent.
2. Based on their reply, decide whether to call send_haptic or skip.
3. Briefly explain your final reasoning.
"""


# ---------------------------------------------------------------------------
# Local state
# ---------------------------------------------------------------------------

@dataclass
class _LocalState:
    last_posture: object | None = None
    last_tension: object | None = None
    bad_posture_since: float | None = None
    high_tension_since: float | None = None
    last_haptic_time: float = 0.0
    trigger_reason: str = ""
    llm_trigger: asyncio.Event = field(default_factory=asyncio.Event)


# ---------------------------------------------------------------------------
# MCP ↔ Claude bridge
# ---------------------------------------------------------------------------

async def _mcp_tools_to_claude_tools(session: ClientSession) -> list[dict]:
    result = await session.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema,
        }
        for tool in result.tools
    ]


async def _execute_tool_call(session: ClientSession, name: str, arguments: dict) -> str:
    try:
        result = await session.call_tool(name, arguments)
        texts = [c.text for c in result.content if hasattr(c, "text")]
        return "\n".join(texts) if texts else "{}"
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Body Agent
# ---------------------------------------------------------------------------

class BodyAgent:
    def __init__(self, server_url: str = DEFAULT_SERVER_URL, demo: bool = False,
                 use_esp32: bool = False, serial_port: str = "/dev/cu.usbserial-0001") -> None:
        self._server_url = server_url
        self._local = _LocalState()
        self._demo = demo
        self._use_esp32 = use_esp32
        self._serial_port = serial_port
        self._esp32 = None
        self._baseline_tilt: float = 0.0
        self._baseline_calibrated: bool = False

    async def run(self) -> None:
        while True:
            try:
                logger.info("Connecting to %s", self._server_url)
                async with streamable_http_client(self._server_url) as (r, w, _):
                    async with ClientSession(r, w) as session:
                        await session.initialize()
                        logger.info("Connected to shared state server")
                        await self._run_with_session(session)
            except Exception as e:
                logger.error("Connection lost: %s — reconnecting in 3s", e)
                await asyncio.sleep(3)

    async def _run_with_session(self, session: ClientSession) -> None:
        sensor_task = asyncio.create_task(self._sensor_loop(session))
        llm_task = asyncio.create_task(self._llm_loop(session))
        try:
            await asyncio.gather(sensor_task, llm_task)
        finally:
            sensor_task.cancel()
            llm_task.cancel()

    # -- ESP32 bridge --

    def pre_init_esp32(self) -> None:
        """Init ESP32 bridge on main thread. Falls back gracefully."""
        if self._esp32 is not None:
            return
        try:
            from bridge import ESP32Bridge
            logger.info("Initializing ESP32 on %s", self._serial_port)
            self._esp32 = ESP32Bridge(port=self._serial_port)
            self._esp32.start_streaming()
            logger.info("ESP32 bridge ready")
        except Exception as e:
            logger.warning("ESP32 init failed: %s — ESP32 mode unavailable", e)
            self._esp32 = None

    def _esp32_to_readings(self) -> tuple[PostureReading, TensionReading, dict]:
        """Read IMU frames from ESP32, compute features, return (posture, tension, raw)."""
        from features import compute_features

        frames = self._esp32.get_recent_frames(window_ms=1000)
        feats = compute_features(frames, baseline_tilt_deg=self._baseline_tilt)

        if not feats["ok"]:
            return (
                PostureReading(PostureClass.UNKNOWN, 0.0, 0.0, 0.0),
                TensionReading(level=0.0, zone="unknown"),
                feats,
            )

        # Calibrate baseline from first good window
        if not self._baseline_calibrated and feats["num_frames"] > 5:
            self._baseline_tilt = feats["mean_tilt_deg"]
            self._baseline_calibrated = True
            feats["deviation_deg"] = 0.0
            logger.info("Baseline calibrated: %.1f°", self._baseline_tilt)

        dev = feats["deviation_deg"]
        posture_cls = _deviation_to_posture(dev)
        confidence = min(1.0, feats["num_frames"] / 20.0)

        posture = PostureReading(
            classification=posture_cls,
            confidence=confidence,
            duration_s=0.0,  # tracked by the sensor loop
            deviation_degrees=abs(dev),
        )

        # Stillness inversely maps to tension (moving = less tense)
        tension_level = max(0.0, 1.0 - feats["stillness_score"])
        tension = TensionReading(level=tension_level, zone="upper_back")

        return posture, tension, feats

    async def _check_data_source(self, session: ClientSession) -> str:
        """Read the data_source toggle from the blackboard (set by dashboard)."""
        try:
            result = await session.read_resource("state://kinesess/data_source")
            content = result.contents[0]
            data = json.loads(content.text if hasattr(content, "text") else str(content))
            return data.get("data", {}).get("mode", "mock")
        except Exception:
            return "esp32" if self._use_esp32 else "mock"

    # -- fast path: sensor loop --

    async def _sensor_loop(self, session: ClientSession) -> None:
        # Mock sensors always available as fallback
        mock_posture = MockPostureSensor(scripted=DEMO_POSTURE_TIMELINE if self._demo else None)
        mock_tension = MockTensionSensor()

        active_mode = "esp32" if self._esp32 is not None else "mock"

        while True:
            # Check dashboard toggle
            requested_mode = await self._check_data_source(session)
            if requested_mode != active_mode:
                if requested_mode == "esp32" and self._esp32 is None:
                    logger.warning("ESP32 not available — staying on mock")
                    requested_mode = "mock"
                else:
                    logger.info("Switching body data source: %s → %s", active_mode, requested_mode)
                active_mode = requested_mode

            # Read from active source
            imu_feats = None
            if active_mode == "esp32" and self._esp32 is not None:
                posture, tension, imu_feats = await asyncio.to_thread(self._esp32_to_readings)
            else:
                posture = await mock_posture.read()
                tension = await mock_tension.read()

            self._local.last_posture = posture
            self._local.last_tension = tension

            await self._safe_update(session, "posture", posture.to_dict(), posture.confidence)
            await self._safe_update(session, "tension", tension.to_dict(), 0.9)
            if imu_feats is not None:
                await self._safe_update(session, "sensor_log", imu_feats, posture.confidence)

            # Track bad posture duration
            is_bad = posture.classification not in (PostureClass.GOOD, PostureClass.UNKNOWN)
            now = time.time()

            if is_bad and self._local.bad_posture_since is None:
                self._local.bad_posture_since = now
            elif not is_bad:
                self._local.bad_posture_since = None

            # Track high tension
            if tension.level > HIGH_TENSION_THRESHOLD and self._local.high_tension_since is None:
                self._local.high_tension_since = now
            elif tension.level <= HIGH_TENSION_THRESHOLD:
                self._local.high_tension_since = None

            # Check if we should wake the LLM
            cooldown_ok = (now - self._local.last_haptic_time) > LLM_COOLDOWN_S

            if cooldown_ok and not self._local.llm_trigger.is_set():
                bad_dur = (now - self._local.bad_posture_since) if self._local.bad_posture_since else 0
                tension_dur = (now - self._local.high_tension_since) if self._local.high_tension_since else 0

                if bad_dur > BAD_POSTURE_THRESHOLD_S:
                    self._local.trigger_reason = (
                        f"bad_posture_{posture.classification.value}_for_{bad_dur:.0f}s"
                    )
                    self._local.llm_trigger.set()
                elif tension_dur > HIGH_TENSION_DURATION_S:
                    self._local.trigger_reason = (
                        f"high_tension_{tension.level:.2f}_in_{tension.zone}"
                    )
                    self._local.llm_trigger.set()

            await asyncio.sleep(SENSOR_INTERVAL_S)

    async def _safe_update(self, session: ClientSession, key: str, data: dict, confidence: float) -> None:
        try:
            await session.call_tool("update_state", {
                "device_id": "kinesess", "key": key,
                "data": data, "confidence": confidence,
            })
        except Exception as e:
            logger.warning("Blackboard write %s failed: %s", key, e)

    # -- slow path: LLM decision loop --

    async def _llm_loop(self, session: ClientSession) -> None:
        claude = anthropic.AsyncAnthropic()
        claude_tools = await _mcp_tools_to_claude_tools(session)

        while True:
            await self._local.llm_trigger.wait()
            self._local.llm_trigger.clear()

            try:
                system_prompt = await self._load_system_prompt(session)
                glasses_ctx = await self._read_glasses_context(session)
                planner_ctx = await self._read_planner_context(session)
                user_msg = self._build_user_message(glasses_ctx, planner_ctx)

                logger.info("LLM triggered: %s", self._local.trigger_reason)

                messages: list[dict] = [{"role": "user", "content": user_msg}]

                for _ in range(MAX_TOOL_ROUNDS):
                    response = await claude.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=512,
                        system=system_prompt,
                        tools=claude_tools,
                        messages=messages,
                    )

                    if response.stop_reason != "tool_use":
                        break

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            result_text = await _execute_tool_call(session, block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })
                            if block.name == "send_haptic":
                                self._local.last_haptic_time = time.time()

                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results})

                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                if text_parts:
                    reasoning = " ".join(text_parts)
                    logger.info("LLM decision: %s", reasoning)
                    # Post reasoning to blackboard so dashboard can show it
                    await self._safe_update(session, "last_decision", {
                        "trigger": self._local.trigger_reason,
                        "reasoning": reasoning,
                        "timestamp": time.time(),
                    }, 1.0)

            except anthropic.APIError as e:
                logger.error("Claude API error: %s", e)
            except Exception as e:
                logger.error("LLM loop error: %s", e)

    # -- helpers --

    async def _load_system_prompt(self, session: ClientSession) -> str:
        try:
            result = await session.read_resource("state://kinesess/system_prompt")
            content = result.contents[0]
            data = json.loads(content.text if hasattr(content, "text") else str(content))
            prompt = data.get("data", {}).get("prompt", "")
            if prompt:
                return prompt
        except Exception:
            pass
        return DEFAULT_SYSTEM_PROMPT

    async def _read_glasses_context(self, session: ClientSession) -> dict:
        ctx: dict = {}
        for key in ["context", "gaze"]:
            try:
                result = await session.read_resource(f"state://glasses/{key}")
                content = result.contents[0]
                parsed = json.loads(content.text if hasattr(content, "text") else str(content))
                ctx[key] = parsed.get("data", parsed)
            except Exception:
                pass
        return ctx

    async def _read_planner_context(self, session: ClientSession) -> dict:
        ctx: dict = {}
        for uri_key in ["plan", "mode", "attention_budget"]:
            try:
                result = await session.read_resource(f"state://brain/{uri_key}")
                content = result.contents[0]
                parsed = json.loads(content.text if hasattr(content, "text") else str(content))
                ctx[uri_key] = parsed.get("data", parsed)
            except Exception:
                pass
        return ctx

    def _build_user_message(self, glasses_ctx: dict, planner_ctx: dict) -> str:
        p = self._local.last_posture
        t = self._local.last_tension

        posture_info = "No posture data."
        if p:
            posture_info = (
                f"CURRENT POSTURE:\n"
                f"  Classification: {p.classification.value}\n"
                f"  Confidence: {p.confidence:.2f}\n"
                f"  Duration in this posture: {p.duration_s:.0f}s\n"
                f"  Deviation from upright: {p.deviation_degrees:.1f}\u00B0\n"
            )

        tension_info = ""
        if t:
            tension_info = (
                f"\nCURRENT TENSION:\n"
                f"  Level: {t.level:.2f} (0=relaxed, 1=very tense)\n"
                f"  Zone: {t.zone}\n"
            )

        glasses_info = "\nGLASSES CONTEXT (from context agent):\n"
        if glasses_ctx.get("context"):
            gc = glasses_ctx["context"]
            glasses_info += (
                f"  Scene: {gc.get('scene', 'unknown')}\n"
                f"  Social (others present): {gc.get('social', False)}\n"
                f"  Ambient noise: {gc.get('ambient_noise_db', 0):.0f} dB\n"
                f"  Confidence: {gc.get('confidence', 0):.2f}\n"
            )
        else:
            glasses_info += "  (not available yet)\n"

        if glasses_ctx.get("gaze"):
            glasses_info += f"  Gaze target: {glasses_ctx['gaze'].get('target', 'unknown')}\n"

        planner_info = f"\nPLANNER CONTEXT:\n{json.dumps(planner_ctx, indent=2)}\n"

        return (
            f"TRIGGER: {self._local.trigger_reason}\n\n"
            f"{posture_info}{tension_info}{glasses_info}{planner_info}\n"
            f"Decide whether to intervene. Consider the scene context. "
            f"If the situation is ambiguous, use ask_agent to consult the glasses agent. "
            f"If you decide to fire a haptic, call send_haptic. If not, explain why briefly."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-20s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Kinesess body sensor agent")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--demo", action="store_true", help="Use scripted posture timeline for demos")
    parser.add_argument("--esp32", action="store_true", help="Use real ESP32 IMU sensor")
    parser.add_argument("--serial-port", default="/dev/cu.usbserial-0001", help="ESP32 serial port")
    args = parser.parse_args()

    agent = BodyAgent(
        server_url=args.server,
        demo=args.demo,
        use_esp32=args.esp32,
        serial_port=args.serial_port,
    )

    # Always try to init ESP32 on main thread so dashboard toggle works
    agent.pre_init_esp32()

    asyncio.run(agent.run())
