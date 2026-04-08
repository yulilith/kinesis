"""Kinesess body sensor agent — interprets posture/tension and decides interventions.

This is an LLM agent. It reads mock sensors on a fast loop (500ms), writes to
the shared state blackboard, and invokes Claude when a threshold is crossed
(bad posture > 30s, high tension). Before deciding, it reads the glasses agent's
scene context and can ask the glasses agent questions via the discussion channel.

Usage:
    python agents/body_agent.py
    python agents/body_agent.py --server http://localhost:9000/mcp
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
You are the Kinesess body sensor agent — a posture coaching assistant embedded in a wearable exoskeleton.

## Hardware
- 2 IMU sensors: upper_back (T3-T6) and lower_back (L2-L4)
- 4 vibration motors: shoulder_l, shoulder_r, lumbar_l, lumbar_r
- 4 EMS channels: rhomboid_l, rhomboid_r, lumbar_erector_l, lumbar_erector_r

## Your Role
You interpret dual-IMU posture data (classification, per-sensor angles, spinal metrics) and decide when and how to intervene. You are called ONLY when a threshold has been crossed (bad posture > 30s, or high muscle tension).

## IMPORTANT: Always consult the Context Agent first
Before taking ANY action, call ask_agent to consult the glasses/context agent. Describe what you're seeing and ask whether now is a good time to intervene.

Example: ask_agent(from_agent="kinesess", to_agent="glasses", question="User has been slouching for 45s, upper_back pitch=22°, flexion=12°. Should I intervene? Vibration or EMS?", context="posture=slouching, deviation=22deg, tension=0.3")

## Intervention Hierarchy (apply AFTER consulting context agent)

### Level 1 — Vibration (haptic)
Use for first intervention or when posture is mildly bad.
- send_haptic with zone targeting for directional feedback:
  - lateral lean left  → zone="shoulder_r" + pattern="right_nudge"
  - lateral lean right → zone="shoulder_l" + pattern="left_nudge"
  - hunching/slouching → pattern="bilateral" (both shoulders)
  - lower back issue   → zone="lumbar_l" or "lumbar_r", pattern="lumbar_alert"

### Level 2 — EMS (escalation only)
Use ONLY when: haptic was ignored 2+ times this session AND deviation > 20° AND duration > 90s.
- send_ems targets the muscle that needs to contract to correct the posture:
  - slouching/hunching  → rhomboid_l + rhomboid_r (retract scapulae)
  - lateral lean left   → rhomboid_r (pull right side back)
  - lateral lean right  → rhomboid_l (pull left side back)
  - lower back issue    → lumbar_erector_l + lumbar_erector_r
- EMS costs 3x attention budget. Use sparingly.
- NEVER fire EMS if: social=True, scene=walking or meeting, budget < 3.

## Coaching Mode (from brain agent)
- "silent":     No interventions. Log only.
- "gentle":     Vibration only, low intensity. Skip borderline cases.
- "normal":     Standard escalation hierarchy.
- "aggressive": Escalate to EMS sooner (after 1 ignored haptic).

## Available Tools
- ask_agent(from_agent, to_agent, question, context): ALWAYS call first.
- send_haptic(pattern, reason, intensity, zone): Vibration feedback.
- send_ems(channel, intensity_ma, duration_ms, frequency_hz, reason): EMS.
- update_state(device_id, key, data, confidence): Write to blackboard.
- display_overlay(message, duration_ms, position): Show text on glasses.

## Output
1. Call ask_agent to consult the context agent.
2. Based on their reply + coaching mode, choose Level 1 or Level 2.
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
    def __init__(self, server_url: str = DEFAULT_SERVER_URL, demo: bool = False) -> None:
        self._server_url = server_url
        self._local = _LocalState()
        self._demo = demo

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

    # -- fast path: sensor loop --

    async def _sensor_loop(self, session: ClientSession) -> None:
        posture_sensor = MockPostureSensor(scripted=DEMO_POSTURE_TIMELINE if self._demo else None)
        tension_sensor = MockTensionSensor()

        while True:
            posture = await posture_sensor.read()
            tension = await tension_sensor.read()

            self._local.last_posture = posture
            self._local.last_tension = tension

            await self._safe_update(session, "posture", posture.to_dict(), posture.confidence)
            await self._safe_update(session, "tension", tension.to_dict(), 0.9)

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
                coaching_ctx = await self._read_coaching_context(session)
                user_msg = self._build_user_message(glasses_ctx, coaching_ctx)

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

    async def _read_coaching_context(self, session: ClientSession) -> dict:
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

    def _build_user_message(self, glasses_ctx: dict, coaching_ctx: dict) -> str:
        p = self._local.last_posture
        t = self._local.last_tension

        posture_info = "No posture data."
        if p:
            posture_info = (
                f"CURRENT POSTURE:\n"
                f"  Classification: {p.classification.value}\n"
                f"  Confidence: {p.confidence:.2f}\n"
                f"  Duration in this posture: {p.duration_s:.0f}s\n"
                f"  Overall deviation: {p.deviation_degrees:.1f}\u00B0\n"
                f"  Flexion (upper-lower pitch diff): {p.flexion_deg:.1f}\u00B0\n"
                f"  Lateral asymmetry: {p.lateral_asymmetry_deg:.1f}\u00B0\n"
            )
            if p.imu_upper:
                u = p.imu_upper
                posture_info += (
                    f"  IMU upper_back — pitch={u.pitch_deg:.1f}\u00B0 "
                    f"roll={u.roll_deg:.1f}\u00B0 yaw={u.yaw_deg:.1f}\u00B0\n"
                )
            if p.imu_lower:
                l = p.imu_lower
                posture_info += (
                    f"  IMU lower_back — pitch={l.pitch_deg:.1f}\u00B0 "
                    f"roll={l.roll_deg:.1f}\u00B0 yaw={l.yaw_deg:.1f}\u00B0\n"
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

        coaching_info = f"\nCOACHING CONTEXT:\n{json.dumps(coaching_ctx, indent=2)}\n"

        return (
            f"TRIGGER: {self._local.trigger_reason}\n\n"
            f"{posture_info}{tension_info}{glasses_info}{coaching_info}\n"
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
    args = parser.parse_args()

    asyncio.run(BodyAgent(server_url=args.server, demo=args.demo).run())
