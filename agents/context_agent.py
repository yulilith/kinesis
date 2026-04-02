"""Glasses context agent — observes the user's environment and provides context.

This is an LLM agent. It reads sensors on a loop (2s), writes to the shared
state blackboard, and invokes Claude when:
- The scene changes (desk → meeting → walking)
- Another agent asks a question via the discussion channel

Usage:
    # Mock sensors (default)
    python agents/context_agent.py
    python agents/context_agent.py --demo

    # Real camera + CLIP scene classification
    python agents/context_agent.py --camera
    python agents/context_agent.py --camera --camera-index 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# macOS AVFoundation requires camera auth from the main thread.
# Setting this env var skips the in-library auth request so the terminal's
# existing camera permission is used instead.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import anthropic
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import SceneType, SceneContext
from ble.mock_sensors import MockSceneSensor, MockGazeSensor

# Teammate's real camera + CLIP inference (context-agent/python/)
CONTEXT_AGENT_DIR = str(Path(__file__).resolve().parent.parent / "context-agent" / "python")
sys.path.insert(0, CONTEXT_AGENT_DIR)

# Label mapping: teammate's CLIP labels → our SceneType enum
CLIP_LABEL_TO_SCENE: dict[str, SceneType] = {
    "desk_work": SceneType.DESK,
    "meeting": SceneType.MEETING,
    "walking": SceneType.WALKING,
    "resting": SceneType.STANDING,
    "kitchen": SceneType.DESK,  # closest match
}

# Demo timeline: desk(45s) → meeting(30s) → walking(15s) → repeat
DEMO_TIMELINE = [
    (45.0, SceneContext(SceneType.DESK, 0.95, False, 35.0)),
    (30.0, SceneContext(SceneType.MEETING, 0.90, True, 55.0)),
    (15.0, SceneContext(SceneType.WALKING, 0.85, False, 60.0)),
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SERVER_URL = "http://localhost:8080/mcp"
SENSOR_INTERVAL_S = 3.0
LLM_COOLDOWN_S = 15.0
MAX_TOOL_ROUNDS = 5

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """\
You are the Glasses context agent — an environment awareness assistant embedded in AI glasses worn by the user.

## Your Role
You observe the user's environment (scene type, social presence, noise, gaze direction) and serve two functions:
1. Update the blackboard when the scene changes so other agents can adapt.
2. Answer questions from the body agent about whether interventions are appropriate.

## When Scene Changes
When you detect a scene transition (e.g., desk → meeting):
- Use display_overlay to briefly inform the user ("Entering meeting mode")
- That's it. Just report the change. Do NOT modify the scene data or override sensor readings.

## When Asked a Question
The body agent may ask you whether it should intervene (e.g., "User has bad posture for 45s. Should I fire a haptic?"). Consider:
- Current scene: desk (intervention OK), meeting (skip or delay), walking (skip)
- Social context: if others present, recommend skipping
- Give a clear yes/no recommendation in 1-2 sentences.

## IMPORTANT CONSTRAINTS
- Do NOT override or fabricate scene data. The scene comes from sensors — report it as-is.
- Do NOT do "emergency overrides" or change scene to bypass restrictions.
- Do NOT update the intervention mode — that's the planner's job.
- Keep responses brief and factual.

## Available Tools
- update_state(device_id, key, data, confidence): Write glasses state to blackboard only
- display_overlay(message, duration_ms, position): Show text on glasses display
- reply_to_agent(from_agent, message): Reply to a question from another agent
- get_pending_discussion(agent_id): Check if someone asked you a question

## Output
Be concise. 1-2 sentences max.
"""

# ---------------------------------------------------------------------------
# Local state
# ---------------------------------------------------------------------------

@dataclass
class _LocalState:
    last_scene: SceneType | None = None
    last_gaze: object | None = None
    last_scene_context: object | None = None
    last_llm_time: float = 0.0
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
# Context Agent
# ---------------------------------------------------------------------------

class ContextAgent:
    def __init__(self, server_url: str = DEFAULT_SERVER_URL, demo: bool = False,
                 use_camera: bool = False, camera_index: int = 0,
                 clip_model: str = "openai/clip-vit-base-patch32") -> None:
        self._server_url = server_url
        self._local = _LocalState()
        self._demo = demo
        self._use_camera = use_camera
        self._camera_index = camera_index
        self._clip_model = clip_model
        self._camera = None
        self._inferencer = None

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

    def _init_camera(self) -> None:
        """Init real camera + CLIP inferencer.

        Camera capture must be opened on the main thread on macOS
        (AVFoundation requirement). Call this before asyncio.run().
        Falls back gracefully if camera is unavailable.
        """
        if self._camera is not None:
            return  # already initialized

        from camera_bridge import CameraBridge
        from scene_features import CLIPContextInferencer

        logger.info("Initializing camera %d + CLIP model %s", self._camera_index, self._clip_model)
        try:
            cam = CameraBridge(camera_index=self._camera_index)
            cam.start()
            self._camera = cam
        except Exception as e:
            logger.warning("Camera init failed: %s — camera mode unavailable", e)
            return

        self._inferencer = CLIPContextInferencer(model_name=self._clip_model)
        self._prev_frame = None
        logger.info("Camera + CLIP ready")

    def _compute_motion(self, frame) -> float:
        """Frame-diff motion detection (from teammate's VisionTools)."""
        import numpy as np
        if self._prev_frame is None or frame is None:
            return 0.0
        diff = np.abs(frame.astype(float) - self._prev_frame.astype(float))
        return float(diff.mean() / 255.0)

    def _camera_to_scene_context(self) -> tuple[SceneContext, dict]:
        """Read a frame from the real camera, run CLIP, return (SceneContext, raw_clip_result)."""
        frame, ts = self._camera.get_latest_frame()
        result = self._inferencer.infer(frame)

        # Add motion detection
        motion = self._compute_motion(frame)
        result["motion_level"] = motion
        self._prev_frame = frame

        scene_label = result.get("scene_label", "unknown")
        scene_type = CLIP_LABEL_TO_SCENE.get(scene_label, SceneType.UNKNOWN)
        confidence = result.get("confidence", 0.0)

        ctx = SceneContext(
            scene=scene_type,
            confidence=confidence,
            social=False,  # CLIP doesn't detect social context yet
            ambient_noise_db=0.0,  # no audio sensor yet
            timestamp=ts or time.time(),
        )
        return ctx, result

    async def _check_data_source(self, session: ClientSession) -> str:
        """Read the data_source toggle from the blackboard (set by dashboard)."""
        try:
            result = await session.read_resource("state://glasses/data_source")
            content = result.contents[0]
            data = json.loads(content.text if hasattr(content, "text") else str(content))
            return data.get("data", {}).get("mode", "mock")
        except Exception:
            return "camera" if self._use_camera else "mock"

    def _stop_camera(self) -> None:
        if self._camera:
            self._camera.stop()
            self._camera = None
            self._inferencer = None
            logger.info("Camera stopped")

    def pre_init_camera(self) -> None:
        """Call from the main thread BEFORE asyncio.run() to satisfy macOS
        AVFoundation's requirement that VideoCapture is opened on the main thread."""
        self._init_camera()

    async def _sensor_loop(self, session: ClientSession) -> None:
        # Init mock sensors (always available as fallback)
        mock_scene = MockSceneSensor(scripted=DEMO_TIMELINE if self._demo else None)
        mock_gaze = MockGazeSensor(scene_sensor=mock_scene)

        active_mode = "camera" if self._camera is not None else "mock"

        while True:
            # Check dashboard toggle
            requested_mode = await self._check_data_source(session)

            if requested_mode != active_mode:
                logger.info("Switching data source: %s → %s", active_mode, requested_mode)
                if requested_mode == "camera" and self._camera is None:
                    logger.warning("Camera not available — staying on mock")
                    requested_mode = "mock"
                active_mode = requested_mode

            # Read from active source
            clip_result = None
            if active_mode == "camera" and self._camera is not None:
                scene_ctx, clip_result = await asyncio.to_thread(self._camera_to_scene_context)
                gaze = None
            else:
                scene_ctx = await mock_scene.read()
                gaze = await mock_gaze.read()

            self._local.last_scene_context = scene_ctx
            self._local.last_gaze = gaze

            # Write to blackboard
            await self._safe_update(session, "context", scene_ctx.to_dict(), scene_ctx.confidence)
            if clip_result is not None:
                await self._safe_update(session, "sensor_log", clip_result, scene_ctx.confidence)
            if gaze is not None:
                await self._safe_update(session, "gaze", gaze.to_dict(), gaze.confidence)

            # Detect scene change
            if self._local.last_scene != scene_ctx.scene:
                old_scene = self._local.last_scene
                self._local.last_scene = scene_ctx.scene

                if old_scene is not None:
                    cooldown_ok = (time.time() - self._local.last_llm_time) > LLM_COOLDOWN_S
                    if cooldown_ok and not self._local.llm_trigger.is_set():
                        self._local.trigger_reason = f"scene_change_{old_scene.value}_to_{scene_ctx.scene.value}"
                        self._local.llm_trigger.set()

            # Check for pending discussion questions
            await self._check_pending_discussion(session)

            await asyncio.sleep(SENSOR_INTERVAL_S)

    async def _safe_update(self, session: ClientSession, key: str, data: dict, confidence: float) -> None:
        try:
            await session.call_tool("update_state", {
                "device_id": "glasses", "key": key,
                "data": data, "confidence": confidence,
            })
        except Exception as e:
            logger.warning("Blackboard write %s failed: %s", key, e)

    async def _check_pending_discussion(self, session: ClientSession) -> None:
        """Check if another agent asked us a question."""
        try:
            result = await session.call_tool("get_pending_discussion", {"agent_id": "glasses"})
            texts = [c.text for c in result.content if hasattr(c, "text")]
            response_text = texts[0] if texts else "{}"
            data = json.loads(response_text)

            if data.get("pending") is not False and "question" in data:
                self._local.trigger_reason = f"discussion_from_{data['from']}"
                if not self._local.llm_trigger.is_set():
                    self._local.llm_trigger.set()
        except Exception:
            pass  # non-critical

    # -- slow path: LLM decision loop --

    async def _llm_loop(self, session: ClientSession) -> None:
        claude = anthropic.AsyncAnthropic()
        claude_tools = await _mcp_tools_to_claude_tools(session)

        while True:
            await self._local.llm_trigger.wait()
            self._local.llm_trigger.clear()

            try:
                self._local.last_llm_time = time.time()
                system_prompt = await self._load_system_prompt(session)
                user_msg = self._build_user_message()

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

                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results})

                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                if text_parts:
                    reasoning = " ".join(text_parts)
                    logger.info("LLM decision: %s", reasoning)
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
            result = await session.read_resource("state://glasses/system_prompt")
            content = result.contents[0]
            data = json.loads(content.text if hasattr(content, "text") else str(content))
            prompt = data.get("data", {}).get("prompt", "")
            if prompt:
                return prompt
        except Exception:
            pass
        return DEFAULT_SYSTEM_PROMPT

    def _build_user_message(self) -> str:
        sc = self._local.last_scene_context
        gz = self._local.last_gaze

        scene_info = "No scene data yet."
        if sc:
            scene_info = (
                f"CURRENT SCENE:\n"
                f"  Type: {sc.scene.value}\n"
                f"  Confidence: {sc.confidence:.2f}\n"
                f"  Social (others present): {sc.social}\n"
                f"  Ambient noise: {sc.ambient_noise_db:.0f} dB\n"
            )

        gaze_info = ""
        if gz:
            gaze_info = f"\nCURRENT GAZE:\n  Target: {gz.target.value}\n  Confidence: {gz.confidence:.2f}\n"

        trigger_info = f"TRIGGER: {self._local.trigger_reason}\n\n"

        # If this is a discussion trigger, include instructions
        discussion_hint = ""
        if "discussion_from" in self._local.trigger_reason:
            discussion_hint = (
                "\nAnother agent has asked you a question. Use get_pending_discussion to read it, "
                "then use reply_to_agent to respond with your recommendation.\n"
            )

        return f"{trigger_info}{scene_info}{gaze_info}{discussion_hint}\nDecide what to do based on the trigger and current context."


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-20s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Glasses context agent")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--demo", action="store_true", help="Use faster scene timeline for demos")
    parser.add_argument("--camera", action="store_true", help="Use real camera + CLIP instead of mock sensors")
    parser.add_argument("--camera-index", type=int, default=0, help="Camera device index")
    parser.add_argument("--clip-model", default="openai/clip-vit-base-patch32", help="HuggingFace CLIP model name")
    args = parser.parse_args()

    agent = ContextAgent(
        server_url=args.server,
        demo=args.demo,
        use_camera=args.camera,
        camera_index=args.camera_index,
        clip_model=args.clip_model,
    )

    # Only init camera on main thread if requested via CLI.
    # Dashboard toggle can still switch to camera if it was pre-initialized.
    if args.camera:
        agent.pre_init_camera()

    asyncio.run(agent.run())
