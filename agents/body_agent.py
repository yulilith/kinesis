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
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import anthropic
from mcp_client import multi_mcp_session, MultiMCPSession

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

# Scripted demo: good(15s) → slouching(35s) → good(12s) → hunched(30s) → leaning(25s) → good(15s) → repeat
# LLM triggers after BAD_POSTURE_THRESHOLD_S of sustained bad posture
DEMO_POSTURE_TIMELINE = [
    (15.0, PostureReading(PostureClass.GOOD, 0.92, 15.0, 2.5)),
    (35.0, PostureReading(PostureClass.SLOUCHING, 0.85, 35.0, 18.0)),
    (12.0, PostureReading(PostureClass.GOOD, 0.90, 12.0, 3.0)),
    (30.0, PostureReading(PostureClass.HUNCHED, 0.88, 30.0, 22.0)),
    (25.0, PostureReading(PostureClass.LEANING_LEFT, 0.80, 25.0, 14.0)),
    (15.0, PostureReading(PostureClass.GOOD, 0.93, 15.0, 2.0)),
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SERVER_URLS = {
    "state":       "http://localhost:8080/mcp",  # blackboard
    "kinesess_hw": "http://localhost:8081/mcp",  # body hardware (fire_haptic, fire_ems)
    "glasses_hw":  "http://localhost:8082/mcp",  # glasses hardware (classify_current_scene)
}

SENSOR_INTERVAL_S = 2.0
LLM_COOLDOWN_S = 20.0
BAD_POSTURE_THRESHOLD_S = 15.0
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

## IMPORTANT: Always check scene context first
Before taking ANY action, call classify_current_scene to get the current scene from the glasses hardware. This is a fast direct query — no LLM round-trip.

If you need deeper contextual judgment (ambiguous scene, unusual situation), also call ask_agent to consult the glasses LLM agent.

## Intervention Hierarchy (apply AFTER consulting context agent)

### Level 1 — Vibration (haptic)
Use for first intervention or when posture is mildly bad.
- fire_haptic with zone targeting for directional feedback:
  - lateral lean left  → zone="shoulder_r" + pattern="right_nudge"
  - lateral lean right → zone="shoulder_l" + pattern="left_nudge"
  - hunching/slouching → pattern="bilateral" (both shoulders)
  - lower back issue   → zone="lumbar_l" or "lumbar_r", pattern="lumbar_alert"

### Level 2 — EMS (escalation only)
Use ONLY when: haptic was ignored 2+ times this session AND deviation > 20° AND duration > 90s.
- fire_ems targets the muscle that needs to contract to correct the posture:
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
- classify_current_scene(): Fast direct scene query from glasses hardware. Call first.
- ask_agent(from_agent, to_agent, question, context): LLM-level consultation with glasses agent. Use for complex situations.
- fire_haptic(pattern, reason, intensity, zone): Vibration feedback (on Kinesess hardware).
- fire_ems(channel, intensity_ma, duration_ms, frequency_hz, reason): EMS (on Kinesess hardware).
- update_state(device_id, key, data, confidence): Write to shared state blackboard.
- display_overlay(message, duration_ms, position): Show text on glasses display.

## Output
1. Call classify_current_scene to check the scene.
2. If ambiguous, call ask_agent for judgment from the context agent.
3. Based on scene + coaching mode, choose Level 1 or Level 2.
4. Briefly explain your final reasoning.
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
    last_llm_time: float = 0.0
    trigger_reason: str = ""
    llm_trigger: asyncio.Event = field(default_factory=asyncio.Event)


# ---------------------------------------------------------------------------
# MCP ↔ Claude bridge
# ---------------------------------------------------------------------------

async def _execute_tool_call(mcp: MultiMCPSession, name: str, arguments: dict) -> str:
    raw = await mcp.call_tool(name, arguments)

    # Intercept ask_agent: server returns immediately with a discussion_id.
    # Poll get_reply() so the LLM receives the final reply, not the id machinery.
    if name == "ask_agent":
        data = json.loads(raw)
        if "discussion_id" in data:
            raw = await _poll_for_reply(mcp, data["discussion_id"], data.get("to", "glasses"))

    return raw


async def _poll_for_reply(
    mcp: MultiMCPSession,
    discussion_id: str,
    from_agent: str,
    interval: float = 0.3,
    timeout: float = 10.0,
) -> str:
    """Poll get_reply every `interval` seconds until a reply arrives or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(interval)
        raw = await mcp.call_tool("get_reply", {"discussion_id": discussion_id})
        data = json.loads(raw)
        if data.get("status") == "replied":
            return json.dumps({"reply": data["reply"], "from": from_agent, "status": "replied"})
    return json.dumps({"reply": "Agent did not reply in time.", "from": from_agent, "status": "timeout"})


# ---------------------------------------------------------------------------
# Body Agent
# ---------------------------------------------------------------------------

class BodyAgent:
    def __init__(self, server_urls: dict[str, str] | None = None, demo: bool = False,
                 use_esp32: bool = False, serial_port: str = "/dev/cu.usbserial-0001") -> None:
        self._server_urls = server_urls or DEFAULT_SERVER_URLS
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
                logger.info("Connecting to MCP servers: %s", list(self._server_urls.keys()))
                async with multi_mcp_session(self._server_urls) as mcp:
                    logger.info("Connected to all MCP servers")
                    await self._run_with_session(mcp)
            except Exception as e:
                logger.error("Connection lost: %s — reconnecting in 3s", e)
                await asyncio.sleep(3)

    async def _run_with_session(self, mcp: MultiMCPSession) -> None:
        sensor_task = asyncio.create_task(self._sensor_loop(mcp))
        llm_task = asyncio.create_task(self._llm_loop(mcp))
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

    async def _check_data_source(self, mcp: MultiMCPSession) -> str:
        """Read the data_source toggle from the blackboard (set by dashboard)."""
        data = await mcp.read_resource("state://kinesess/data_source")
        mode = data.get("data", {}).get("mode") if data else None
        return mode or ("esp32" if self._use_esp32 else "mock")

    # -- fast path: sensor loop --

    async def _sensor_loop(self, mcp: MultiMCPSession) -> None:
        # Mock sensors always available as fallback
        mock_posture = MockPostureSensor(scripted=DEMO_POSTURE_TIMELINE if self._demo else None)
        mock_tension = MockTensionSensor()

        active_mode = "esp32" if self._esp32 is not None else "mock"

        while True:
            # Check dashboard toggle
            requested_mode = await self._check_data_source(mcp)
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

            await self._safe_update(mcp, "posture", posture.to_dict(), posture.confidence)
            await self._safe_update(mcp, "tension", tension.to_dict(), 0.9)
            if imu_feats is not None:
                await self._safe_update(mcp, "sensor_log", imu_feats, posture.confidence)

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

            # Check if we should wake the LLM (cooldown from last LLM call OR last haptic)
            last_action = max(self._local.last_haptic_time, self._local.last_llm_time)
            cooldown_ok = (now - last_action) > LLM_COOLDOWN_S

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

    async def _safe_update(self, mcp: MultiMCPSession, key: str, data: dict, confidence: float) -> None:
        await mcp.call_tool("update_state", {
            "device_id": "kinesess", "key": key,
            "data": data, "confidence": confidence,
        })

    # -- slow path: LLM decision loop --

    async def _llm_loop(self, mcp: MultiMCPSession) -> None:
        claude = anthropic.AsyncAnthropic()
        claude_tools = await mcp.claude_tools()

        while True:
            await self._local.llm_trigger.wait()
            self._local.llm_trigger.clear()

            try:
                self._local.last_llm_time = time.time()

                system_prompt = await self._load_system_prompt(mcp)
                glasses_ctx = await self._read_glasses_context(mcp)
                planner_ctx = await self._read_planner_context(mcp)
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
                            result_text = await _execute_tool_call(mcp, block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })
                            if block.name == "fire_haptic":
                                self._local.last_haptic_time = time.time()
                                # Mirror haptic event to blackboard for dashboard visibility
                                try:
                                    fired = json.loads(result_text)
                                    await mcp.call_tool("update_state", {
                                        "device_id": "kinesess", "key": "last_haptic",
                                        "data": fired, "confidence": 1.0,
                                    })
                                except Exception:
                                    pass

                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results})

                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                if text_parts:
                    reasoning = " ".join(text_parts)
                    logger.info("LLM decision: %s", reasoning)
                    await mcp.call_tool("update_state", {
                        "device_id": "kinesess", "key": "last_decision",
                        "data": {"trigger": self._local.trigger_reason,
                                 "reasoning": reasoning, "timestamp": time.time()},
                        "confidence": 1.0,
                    })

            except anthropic.APIError as e:
                logger.error("Claude API error: %s", e)
            except Exception as e:
                logger.error("LLM loop error: %s", e)

    # -- helpers --

    async def _load_system_prompt(self, mcp: MultiMCPSession) -> str:
        data = await mcp.read_resource("state://kinesess/system_prompt")
        prompt = data.get("data", {}).get("prompt", "") if data else ""
        return prompt or DEFAULT_SYSTEM_PROMPT

    async def _read_glasses_context(self, mcp: MultiMCPSession) -> dict:
        ctx: dict = {}
        for key in ["context", "gaze"]:
            data = await mcp.read_resource(f"state://glasses/{key}")
            if data and "error" not in data:
                ctx[key] = data.get("data", data)
        return ctx

    async def _read_planner_context(self, mcp: MultiMCPSession) -> dict:
        ctx: dict = {}
        for uri_key in ["plan", "mode", "attention_budget"]:
            data = await mcp.read_resource(f"state://brain/{uri_key}")
            if data and "error" not in data:
                ctx[uri_key] = data.get("data", data)
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

        planner_info = f"\nPLANNER CONTEXT:\n{json.dumps(planner_ctx, indent=2)}\n"

        return (
            f"TRIGGER: {self._local.trigger_reason}\n\n"
            f"{posture_info}{tension_info}{glasses_info}{planner_info}\n"
            f"Decide whether to intervene. Consider the scene context. "
            f"If the situation is ambiguous, use ask_agent to consult the glasses agent. "
            f"If you decide to fire a haptic, call fire_haptic. If not, explain why briefly."
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
    parser.add_argument("--state-server",    default=DEFAULT_SERVER_URLS["state"])
    parser.add_argument("--kinesess-server", default=DEFAULT_SERVER_URLS["kinesess_hw"])
    parser.add_argument("--glasses-server",  default=DEFAULT_SERVER_URLS["glasses_hw"])
    parser.add_argument("--demo", action="store_true", help="Use scripted posture timeline for demos")
    parser.add_argument("--esp32", action="store_true", help="Use real ESP32 IMU sensor")
    parser.add_argument("--serial-port", default="/dev/cu.usbserial-0001", help="ESP32 serial port")
    args = parser.parse_args()

    agent = BodyAgent(
        server_urls={
            "state":       args.state_server,
            "kinesess_hw": args.kinesess_server,
            "glasses_hw":  args.glasses_server,
        },
        demo=args.demo,
        use_esp32=args.esp32,
        serial_port=args.serial_port,
    )

    # Only init ESP32 if requested via CLI
    if args.esp32:
        agent.pre_init_esp32()

    asyncio.run(agent.run())
