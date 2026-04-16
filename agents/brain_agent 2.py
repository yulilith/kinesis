"""Planner agent — the strategic planner for the Kinesis intervention system.

Runs on a 30-second loop, reads all shared state, reasons about patterns with
Claude, and writes updated intervention strategy back to the blackboard.

Usage:
    python agents/brain_agent.py
    python agents/brain_agent.py --server http://localhost:9000/mcp --interval 15
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import anthropic
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SERVER_URL = "http://localhost:8080/mcp"
DEFAULT_LOOP_INTERVAL_S = 30.0
MAX_HISTORY = 20
MAX_TOOL_ROUNDS = 5

# ---------------------------------------------------------------------------
# Planner system prompt
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are the Planner agent for a wearable posture correction system. You observe patterns across time and gently adjust the intervention strategy.

## What You Receive
Every 30 seconds you get a snapshot of ALL shared state (posture, tension, scene context, mode, attention budget) plus a history of recent snapshots.

## What You Control

1. **Intervention mode** (`state://brain/mode`):
   - "silent": no haptics (use during meetings or social situations)
   - "gentle": minimal, occasional intervention
   - "normal": standard intervention (this is the default — use it most of the time)
   Do NOT use "aggressive" or "emergency" modes. Keep things calm and conservative.

2. **Attention budget** (`state://brain/attention_budget`):
   - Default 20/day. Be conservative — do NOT spend more than 1-2 per cycle.

3. **Display overlay** via `display_overlay`:
   - Brief, encouraging messages only. "Great posture!" / "Quick stretch?"

## IMPORTANT CONSTRAINTS
- Do NOT change device agent system prompts. Leave them as they are.
- Do NOT fire haptics directly — that's the body agent's job.
- Do NOT set mode to "aggressive" or "emergency" — those don't exist.
- Keep mode on "normal" for desk work, "silent" for meetings, "gentle" for walking.
- If things look fine, just confirm and make no changes. Not every cycle needs action.

## Available Tools
- update_state(device_id, key, data, confidence): Update mode or budget only.
- display_overlay(message, duration_ms, position): Show brief encouraging message.

## Output
Briefly explain what you observe and any small adjustments made. Most of the time, no changes are needed.
"""


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
# Brain Agent
# ---------------------------------------------------------------------------

class BrainAgent:
    def __init__(self, server_url: str = DEFAULT_SERVER_URL, loop_interval: float = DEFAULT_LOOP_INTERVAL_S) -> None:
        self._server_url = server_url
        self._loop_interval = loop_interval
        self._history: list[dict] = []

    async def run(self) -> None:
        while True:
            try:
                logger.info("Connecting to %s", self._server_url)
                async with streamable_http_client(self._server_url) as (r, w, _):
                    async with ClientSession(r, w) as session:
                        await session.initialize()
                        logger.info("Connected to shared state server")
                        await self._run_loop(session)
            except Exception as e:
                logger.error("Connection lost: %s — reconnecting in 3s", e)
                await asyncio.sleep(3)

    async def _run_loop(self, session: ClientSession) -> None:
        claude = anthropic.AsyncAnthropic()
        claude_tools = await _mcp_tools_to_claude_tools(session)

        while True:
            try:
                snapshot = await self._read_all_state(session)
                self._history.append({"timestamp": time.time(), "state": snapshot})
                if len(self._history) > MAX_HISTORY:
                    self._history = self._history[-MAX_HISTORY:]

                user_msg = self._build_user_message(snapshot)
                messages: list[dict] = [{"role": "user", "content": user_msg}]

                logger.info("Planner reasoning cycle starting")

                for _ in range(MAX_TOOL_ROUNDS):
                    response = await claude.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=1024,
                        system=PLANNER_SYSTEM_PROMPT,
                        tools=claude_tools,
                        messages=messages,
                    )

                    if response.stop_reason != "tool_use":
                        break

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            logger.info("Planner tool: %s(%s)", block.name, json.dumps(block.input)[:200])
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
                    logger.info("Planner decision: %s", " ".join(text_parts))

            except anthropic.APIError as e:
                logger.error("Claude API error: %s", e)
            except Exception as e:
                logger.error("Planner loop error: %s", e)

            await asyncio.sleep(self._loop_interval)

    async def _read_all_state(self, session: ClientSession) -> dict:
        all_state: dict = {}
        for device_id in ["kinesess", "brain", "glasses"]:
            try:
                result = await session.read_resource(f"state://{device_id}")
                content = result.contents[0]
                parsed = json.loads(content.text if hasattr(content, "text") else str(content))
                all_state[device_id] = parsed
            except Exception:
                all_state[device_id] = {"status": "unavailable"}
        return all_state

    def _build_user_message(self, snapshot: dict) -> str:
        history_lines = []
        for entry in self._history[-10:]:
            ts = entry["timestamp"]
            ks = entry["state"].get("kinesess", {})
            gs = entry["state"].get("glasses", {})
            posture_data = ks.get("posture", {}).get("data", {})
            tension_data = ks.get("tension", {}).get("data", {})
            scene_data = gs.get("context", {}).get("data", {})
            history_lines.append(
                f"  t-{time.time() - ts:.0f}s: "
                f"posture={posture_data.get('classification', '?')} "
                f"deviation={posture_data.get('deviation_degrees', '?')}\u00B0 "
                f"tension={tension_data.get('level', '?')} "
                f"scene={scene_data.get('scene', '?')}"
            )

        history_text = "\n".join(history_lines) if history_lines else "  (no history yet)"

        return (
            f"CURRENT STATE SNAPSHOT:\n{json.dumps(snapshot, indent=2)}\n\n"
            f"RECENT HISTORY ({len(self._history)} observations, last 10 shown):\n"
            f"{history_text}\n\n"
            f"Analyze current state and recent patterns. "
            f"Update intervention strategy if needed, or confirm current approach is working."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-20s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Planner agent")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--interval", type=float, default=DEFAULT_LOOP_INTERVAL_S)
    args = parser.parse_args()

    asyncio.run(BrainAgent(server_url=args.server, loop_interval=args.interval).run())
