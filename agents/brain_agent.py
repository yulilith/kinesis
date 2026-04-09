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
from mcp_client import multi_mcp_session, MultiMCPSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SERVER_URLS = {
    "state":       "http://localhost:8080/mcp",  # blackboard
    "kinesess_hw": "http://localhost:8081/mcp",  # for set_attention_budget
    "glasses_hw":  "http://localhost:8082/mcp",  # for display_overlay
    "brain_coach": "http://localhost:8083/mcp",  # drain urgent_request queue
}

DEFAULT_LOOP_INTERVAL_S = 30.0
MAX_HISTORY = 20
MAX_TOOL_ROUNDS = 5
ESCALATION_POLL_INTERVAL_S = 0.5

# Restrict which tools Claude can invoke for the brain agent.
# Brain sets strategy — it reads state, adjusts mode/budget, displays messages.
# It never fires haptics/EMS directly (that's the body agent's role).
BRAIN_ALLOWED_TOOLS = {"update_state", "display_overlay", "set_attention_budget", "get_urgent_requests"}

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
- update_state(device_id, key, data, confidence): Update mode on the blackboard.
- display_overlay(message, duration_ms, position): Show brief encouraging message on the glasses.
- set_attention_budget(remaining, daily_max): Adjust the Kinesess device's daily intervention quota.
- get_urgent_requests(mark_processed): Check for hard escalations from device agents.

## Output
Briefly explain what you observe and any small adjustments made. Most of the time, no changes are needed.
"""


# ---------------------------------------------------------------------------
# MCP ↔ Claude bridge
# ---------------------------------------------------------------------------

async def _brain_claude_tools(mcp: MultiMCPSession) -> list[dict]:
    """Return only tools the brain agent is allowed to call."""
    all_tools = await mcp.claude_tools()
    return [t for t in all_tools if t["name"] in BRAIN_ALLOWED_TOOLS]


async def _execute_tool_call(mcp: MultiMCPSession, name: str, arguments: dict) -> str:
    return await mcp.call_tool(name, arguments)


# ---------------------------------------------------------------------------
# Brain Agent
# ---------------------------------------------------------------------------

class BrainAgent:
    def __init__(self, server_urls: dict[str, str] | None = None,
                 loop_interval: float = DEFAULT_LOOP_INTERVAL_S) -> None:
        self._server_urls = server_urls or DEFAULT_SERVER_URLS
        self._loop_interval = loop_interval
        self._history: list[dict] = []
        self._escalation_event = asyncio.Event()
        self._escalation_context: dict = {}

    async def run(self) -> None:
        while True:
            try:
                logger.info("Connecting to MCP servers: %s", list(self._server_urls.keys()))
                async with multi_mcp_session(self._server_urls) as mcp:
                    logger.info("Connected to all MCP servers")
                    await self._run_loop(mcp)
            except Exception as e:
                logger.error("Connection lost: %s — reconnecting in 3s", e)
                await asyncio.sleep(3)

    async def _run_loop(self, mcp: MultiMCPSession) -> None:
        claude = anthropic.AsyncAnthropic()
        claude_tools = await _brain_claude_tools(mcp)

        escalation_watcher = asyncio.create_task(self._escalation_watcher(mcp))
        try:
            while True:
                try:
                    await asyncio.wait_for(self._escalation_event.wait(), timeout=self._loop_interval)
                    trigger = f"soft_escalation: {json.dumps(self._escalation_context)}"
                    self._escalation_event.clear()
                    self._escalation_context = {}
                except asyncio.TimeoutError:
                    trigger = "periodic_review"

                await self._reasoning_cycle(mcp, claude, claude_tools, trigger)
        finally:
            escalation_watcher.cancel()

    async def _escalation_watcher(self, mcp: MultiMCPSession) -> None:
        """Poll soft escalations (blackboard) and hard escalations (brain_mcp_server)."""
        last_versions: dict[str, int] = {"kinesess": 0, "glasses": 0}
        while True:
            # Soft escalation: device wrote to state://escalation/{device}
            for device in ("kinesess", "glasses"):
                parsed = await mcp.read_resource(f"state://escalation/{device}")
                if parsed and "error" not in parsed:
                    version = parsed.get("version", 0)
                    if version > last_versions[device]:
                        last_versions[device] = version
                        self._escalation_context = {
                            "device": device, "escalation": parsed.get("data", parsed),
                        }
                        logger.info("Soft escalation from %s — waking planner", device)
                        self._escalation_event.set()

            # Hard escalation: device called urgent_request on brain_mcp_server
            raw = await mcp.call_tool("get_urgent_requests", {"mark_processed": True})
            urgent = json.loads(raw)
            if urgent:
                self._escalation_context = {"urgent_requests": urgent}
                logger.warning("Hard escalation: %d urgent request(s)", len(urgent))
                self._escalation_event.set()

            await asyncio.sleep(ESCALATION_POLL_INTERVAL_S)

    async def _reasoning_cycle(
        self,
        mcp: MultiMCPSession,
        claude: anthropic.AsyncAnthropic,
        claude_tools: list[dict],
        trigger: str,
    ) -> None:
        """Run one LLM planning cycle, then return."""
        try:
            snapshot = await self._read_all_state(mcp)
            self._history.append({"timestamp": time.time(), "state": snapshot})
            if len(self._history) > MAX_HISTORY:
                self._history = self._history[-MAX_HISTORY:]

            user_msg = self._build_user_message(snapshot, trigger)
            messages: list[dict] = [{"role": "user", "content": user_msg}]

            logger.info("Planner reasoning cycle: %s", trigger)

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
                        result_text = await _execute_tool_call(mcp, block.name, block.input)
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

    async def _read_all_state(self, mcp: MultiMCPSession) -> dict:
        all_state: dict = {}
        for device_id in ["kinesess", "brain", "glasses"]:
            parsed = await mcp.read_resource(f"state://{device_id}")
            all_state[device_id] = parsed if (parsed and "error" not in parsed) else {"status": "unavailable"}
        return all_state

    def _build_user_message(self, snapshot: dict, trigger: str = "periodic_review") -> str:
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
            f"TRIGGER: {trigger}\n\n"
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
    parser.add_argument("--state-server",   default=DEFAULT_SERVER_URLS["state"])
    parser.add_argument("--kinesess-server", default=DEFAULT_SERVER_URLS["kinesess_hw"])
    parser.add_argument("--glasses-server",  default=DEFAULT_SERVER_URLS["glasses_hw"])
    parser.add_argument("--brain-server",    default=DEFAULT_SERVER_URLS["brain_coach"])
    parser.add_argument("--interval", type=float, default=DEFAULT_LOOP_INTERVAL_S)
    args = parser.parse_args()

    asyncio.run(BrainAgent(
        server_urls={
            "state":       args.state_server,
            "kinesess_hw": args.kinesess_server,
            "glasses_hw":  args.glasses_server,
            "brain_coach": args.brain_server,
        },
        loop_interval=args.interval,
    ).run())
