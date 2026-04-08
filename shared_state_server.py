"""Shared State MCP Server — the blackboard for the Kinesis multi-agent system.

All agents (kinesess, glasses, brain/coach) connect here. This server is NOT
an agent — it's infrastructure. It stores state, serves it as MCP resources,
and pushes subscription notifications when state changes.

Additions over kinesis-software version:
- ask_agent / reply_to_agent tools for inter-agent discussion
- Discussion state tracking for dashboard visibility

Usage:
    python shared_state_server.py              # streamable-http on 0.0.0.0:8080
    python shared_state_server.py --stdio      # stdio transport (single-agent testing)
    python shared_state_server.py --port 9000  # custom port
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.lowlevel.server import Server as LowLevelServer
from mcp.server.session import ServerSession
from mcp import types
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse, Response

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from schemas import (
    CoachingPlan,
    EMSChannel,
    HapticPattern,
    InterventionMode,
    StateEntry,
    VibrationZone,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Kinesis Shared State")

# ---------------------------------------------------------------------------
# State store
# ---------------------------------------------------------------------------

_state: dict[tuple[str, str], StateEntry] = {}

# ---------------------------------------------------------------------------
# Discussion state — for inter-agent Q&A
# ---------------------------------------------------------------------------

_pending_discussions: dict[str, dict] = {}  # keyed by to_agent
_discussion_events: list[dict] = []  # log of all discussion messages
_discussion_reply_events: dict[str, asyncio.Event] = {}  # signal when reply arrives
_discussion_replies: dict[str, str] = {}  # reply content keyed by discussion_id

# ---------------------------------------------------------------------------
# Subscription registry
# ---------------------------------------------------------------------------

_subscriptions: dict[str, set[ServerSession]] = defaultdict(set)

# EMS cooldown tracking — keyed by channel value, stores last fire timestamp
_ems_last_fire: dict[str, float] = {}
EMS_MAX_INTENSITY_MA = 15.0
EMS_MAX_DURATION_MS  = 3000
EMS_COOLDOWN_S       = 120.0


async def _notify_subscribers(uri: str) -> None:
    dead: list[ServerSession] = []
    for session in _subscriptions.get(uri, set()):
        try:
            await session.send_resource_updated(uri=uri)
        except Exception:
            dead.append(session)
    for s in dead:
        _subscriptions[uri].discard(s)


_ll: LowLevelServer = mcp._mcp_server  # type: ignore[attr-defined]


@_ll.subscribe_resource()
async def _handle_subscribe(uri: Any) -> None:
    ctx = _ll.request_context
    _subscriptions[str(uri)].add(ctx.session)
    logger.info("SUBSCRIBE %s", uri)


@_ll.unsubscribe_resource()
async def _handle_unsubscribe(uri: Any) -> None:
    ctx = _ll.request_context
    _subscriptions[str(uri)].discard(ctx.session)
    logger.info("UNSUBSCRIBE %s", uri)


_orig_get_caps = _ll.get_capabilities


def _patched_get_capabilities(
    notification_options: Any, experimental_capabilities: Any
) -> types.ServerCapabilities:
    caps = _orig_get_caps(notification_options, experimental_capabilities)
    if caps.resources:
        caps.resources.subscribe = True
    return caps


_ll.get_capabilities = _patched_get_capabilities  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Dashboard SSE
# ---------------------------------------------------------------------------

_sse_queues: list[asyncio.Queue[dict]] = []
_connected_agents: dict[str, float] = {}


def _push_sse_event(entry: StateEntry) -> None:
    data = entry.to_dict()
    dead = []
    for q in _sse_queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_queues.remove(q)


def _push_sse_raw(data: dict) -> None:
    dead = []
    for q in _sse_queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_queues.remove(q)


def _track_agent(device_id: str) -> None:
    now = time.time()
    is_new = device_id not in _connected_agents
    _connected_agents[device_id] = now
    if is_new:
        _push_sse_raw({"type": "agent_connected", "agent": device_id, "timestamp": now})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _do_update(device_id: str, key: str, data: dict[str, Any], confidence: float) -> StateEntry:
    existing = _state.get((device_id, key))
    version = (existing.version + 1) if existing else 1
    entry = StateEntry(
        device_id=device_id, key=key, data=data,
        confidence=confidence, timestamp=time.time(), version=version,
    )
    _state[(device_id, key)] = entry
    _push_sse_event(entry)
    return entry


async def _update_and_notify(device_id: str, key: str, data: dict[str, Any], confidence: float) -> StateEntry:
    entry = _do_update(device_id, key, data, confidence)
    _track_agent(device_id)
    await _notify_subscribers(f"state://{device_id}/{key}")
    await _notify_subscribers(f"state://{device_id}")
    return entry


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------

def _init_defaults() -> None:
    plan = CoachingPlan(
        mode=InterventionMode.NORMAL,
        attention_budget_remaining=20,
        active_chain=None, chain_step=0,
        message="Session starting.",
    )
    defaults: list[tuple[str, str, dict[str, Any], float]] = [
        ("kinesess", "system_prompt", {"prompt": ""}, 1.0),
        ("glasses", "system_prompt", {"prompt": ""}, 1.0),
        ("brain", "plan", plan.to_dict(), 1.0),
        ("brain", "mode", {"mode": InterventionMode.NORMAL.value}, 1.0),
        ("brain", "attention_budget", {"remaining": 20, "daily_max": 20}, 1.0),
        ("brain", "active_chain", {"chain": None, "step": 0}, 1.0),
    ]
    for device_id, key, data, confidence in defaults:
        _do_update(device_id, key, data, confidence)


_init_defaults()


# ---------------------------------------------------------------------------
# MCP Tools — state operations
# ---------------------------------------------------------------------------

@mcp.tool()
async def update_state(device_id: str, key: str, data: dict[str, Any], confidence: float) -> str:
    """Write or update a shared state entry. Notifies all subscribers.

    Args:
        device_id: Device identifier — "kinesess", "glasses", or "brain"
        key: State key — e.g. "posture", "context", "plan"
        data: The state payload as a JSON object
        confidence: Data reliability score, 0.0 to 1.0
    """
    entry = await _update_and_notify(device_id, key, data, confidence)
    return json.dumps(entry.to_dict())


@mcp.tool()
async def send_haptic(pattern: str, reason: str, intensity: float = 0.5,
                      zone: str = "") -> str:
    """Fire a haptic pattern on the Kinesess device. Deducts from attention budget.

    Args:
        pattern: One of "gentle", "firm", "pulse", "left_nudge", "right_nudge",
                 "lumbar_alert", "bilateral"
        reason: Why this haptic is being fired
        intensity: Strength 0.0 to 1.0
        zone: Target vibration zone — "shoulder_l", "shoulder_r", "lumbar_l",
              "lumbar_r". Leave empty to fire all zones.
    """
    HapticPattern(pattern)
    if zone:
        VibrationZone(zone)  # validate zone value

    budget_entry = _state.get(("brain", "attention_budget"))
    remaining = budget_entry.data["remaining"] if budget_entry else 0
    if remaining <= 0:
        return json.dumps({"fired": False, "reason": "attention_budget_exhausted"})

    payload = {"pattern": pattern, "reason": reason, "intensity": intensity}
    if zone:
        payload["zone"] = zone

    await _update_and_notify("kinesess", "last_haptic", payload, 1.0)
    new_remaining = remaining - 1
    await _update_and_notify(
        "brain", "attention_budget",
        {"remaining": new_remaining, "daily_max": budget_entry.data["daily_max"]}, 1.0,
    )
    return json.dumps({"fired": True, "pattern": pattern, "zone": zone or "all",
                       "budget_remaining": new_remaining})


@mcp.tool()
async def send_ems(channel: str, intensity_ma: float, duration_ms: int,
                   frequency_hz: float, reason: str) -> str:
    """Fire an EMS pulse on a specific muscle channel.

    Safety limits are enforced server-side and cannot be overridden.

    Args:
        channel: "rhomboid_l", "rhomboid_r", "lumbar_erector_l", "lumbar_erector_r"
        intensity_ma: Current in milliamps. Hard cap: 15.0 mA.
        duration_ms: Pulse duration in milliseconds. Hard cap: 3000 ms.
        frequency_hz: Stimulation frequency in Hz. Typical range: 20.0–80.0.
        reason: Why this EMS pulse is being fired
    """
    EMSChannel(channel)  # validate channel value

    # Hard safety caps — never bypassed
    intensity_ma = min(intensity_ma, EMS_MAX_INTENSITY_MA)
    duration_ms  = min(duration_ms,  EMS_MAX_DURATION_MS)
    frequency_hz = max(20.0, min(frequency_hz, 80.0))

    # Cooldown check per channel
    last = _ems_last_fire.get(channel, 0.0)
    elapsed = time.time() - last
    if elapsed < EMS_COOLDOWN_S:
        wait = EMS_COOLDOWN_S - elapsed
        return json.dumps({"fired": False, "reason": "cooldown",
                           "channel": channel, "wait_s": round(wait, 1)})

    # Budget check — EMS costs 3x a haptic
    budget_entry = _state.get(("brain", "attention_budget"))
    remaining = budget_entry.data["remaining"] if budget_entry else 0
    if remaining < 3:
        return json.dumps({"fired": False, "reason": "attention_budget_exhausted",
                           "budget_remaining": remaining})

    _ems_last_fire[channel] = time.time()

    await _update_and_notify(
        "kinesess", "last_ems",
        {"channel": channel, "intensity_ma": intensity_ma,
         "duration_ms": duration_ms, "frequency_hz": frequency_hz,
         "reason": reason}, 1.0,
    )
    new_remaining = remaining - 3
    await _update_and_notify(
        "brain", "attention_budget",
        {"remaining": new_remaining, "daily_max": budget_entry.data["daily_max"]}, 1.0,
    )
    return json.dumps({"fired": True, "channel": channel,
                       "intensity_ma": intensity_ma, "duration_ms": duration_ms,
                       "frequency_hz": frequency_hz, "budget_remaining": new_remaining})


@mcp.tool()
async def display_overlay(message: str, duration_ms: int = 3000, position: str = "top") -> str:
    """Display a text overlay on the AI glasses.

    Args:
        message: Text to display
        duration_ms: How long to show it (milliseconds)
        position: Where on the display — "top", "center", or "bottom"
    """
    await _update_and_notify(
        "glasses", "overlay_command",
        {"message": message, "duration_ms": duration_ms, "position": position}, 1.0,
    )
    return json.dumps({"sent": True, "message": message})


# ---------------------------------------------------------------------------
# MCP Tools — inter-agent discussion
# ---------------------------------------------------------------------------

@mcp.tool()
async def ask_agent(from_agent: str, to_agent: str, question: str, context: str = "") -> str:
    """Ask another agent a question and wait for their reply.

    Use this when you need the other agent's perspective before making a decision.
    The target agent will be notified, reason about your question, and reply.

    Args:
        from_agent: Your agent id ("kinesess" or "glasses")
        to_agent: Target agent id ("kinesess" or "glasses")
        question: Your question for the other agent
        context: Additional context (JSON string with relevant sensor data)
    """
    discussion_id = f"{from_agent}_{to_agent}_{time.time()}"

    discussion = {
        "id": discussion_id,
        "from": from_agent,
        "to": to_agent,
        "question": question,
        "context": context,
        "timestamp": time.time(),
        "status": "pending",
    }

    _pending_discussions[to_agent] = discussion
    _discussion_events.append(discussion)
    _discussion_reply_events[discussion_id] = asyncio.Event()

    # Write to blackboard so target agent sees it via subscription
    await _update_and_notify(
        "discussion", f"pending_{to_agent}",
        discussion, 1.0,
    )

    # Push to dashboard
    _push_sse_raw({
        "type": "discussion_message",
        "direction": "question",
        "from": from_agent,
        "to": to_agent,
        "message": question,
        "context": context,
        "timestamp": time.time(),
    })

    logger.info("Discussion: %s → %s: %s", from_agent, to_agent, question[:100])

    # Wait for reply (timeout 30s)
    try:
        await asyncio.wait_for(_discussion_reply_events[discussion_id].wait(), timeout=30.0)
        reply = _discussion_replies.pop(discussion_id, "No reply received.")
        return json.dumps({"reply": reply, "from": to_agent, "status": "replied"})
    except asyncio.TimeoutError:
        return json.dumps({"reply": "Agent did not reply in time.", "from": to_agent, "status": "timeout"})
    finally:
        _discussion_reply_events.pop(discussion_id, None)
        _pending_discussions.pop(to_agent, None)


@mcp.tool()
async def reply_to_agent(from_agent: str, message: str) -> str:
    """Reply to a pending question from another agent.

    Call this when you've been asked a question and have formulated your response.

    Args:
        from_agent: Your agent id ("kinesess" or "glasses")
        message: Your reply to the other agent's question
    """
    # Find the pending discussion targeting this agent
    discussion = _pending_discussions.get(from_agent)
    if not discussion:
        return json.dumps({"error": "no_pending_discussion", "from": from_agent})

    discussion_id = discussion["id"]
    asking_agent = discussion["from"]

    # Store reply and signal
    _discussion_replies[discussion_id] = message
    if discussion_id in _discussion_reply_events:
        _discussion_reply_events[discussion_id].set()

    # Log the reply
    reply_event = {
        "id": discussion_id,
        "from": from_agent,
        "to": asking_agent,
        "reply": message,
        "timestamp": time.time(),
        "status": "replied",
    }
    _discussion_events.append(reply_event)

    # Write to blackboard
    await _update_and_notify(
        "discussion", f"reply_{asking_agent}",
        reply_event, 1.0,
    )

    # Push to dashboard
    _push_sse_raw({
        "type": "discussion_message",
        "direction": "reply",
        "from": from_agent,
        "to": asking_agent,
        "message": message,
        "timestamp": time.time(),
    })

    logger.info("Discussion reply: %s → %s: %s", from_agent, asking_agent, message[:100])
    return json.dumps({"sent": True, "to": asking_agent})


@mcp.tool()
async def get_pending_discussion(agent_id: str) -> str:
    """Check if there's a pending question for this agent.

    Args:
        agent_id: Your agent id ("kinesess" or "glasses")
    """
    discussion = _pending_discussions.get(agent_id)
    if discussion:
        return json.dumps(discussion)
    return json.dumps({"pending": False})


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("state://{device_id}/{key}")
def read_state(device_id: str, key: str) -> str:
    """Read a single shared state entry."""
    entry = _state.get((device_id, key))
    if entry is None:
        return json.dumps({"error": "not_found", "device_id": device_id, "key": key})
    return json.dumps(entry.to_dict())


@mcp.resource("state://{device_id}")
def read_device_state(device_id: str) -> str:
    """Read all shared state entries for a device."""
    entries = {
        k: entry.to_dict()
        for (did, k), entry in _state.items()
        if did == device_id
    }
    if not entries:
        return json.dumps({"error": "no_state", "device_id": device_id})
    return json.dumps(entries)


# ---------------------------------------------------------------------------
# Dashboard HTTP routes
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text()


@mcp.custom_route("/", methods=["GET"])
async def dashboard_page(request: Request) -> Response:
    return HTMLResponse(_DASHBOARD_HTML)


@mcp.custom_route("/api/state", methods=["GET"])
async def api_get_state(request: Request) -> Response:
    all_state = {
        f"{did}/{k}": entry.to_dict()
        for (did, k), entry in _state.items()
    }
    return JSONResponse(all_state)


@mcp.custom_route("/api/agents", methods=["GET"])
async def api_get_agents(request: Request) -> Response:
    now = time.time()
    agents = {
        name: {"last_seen": ts, "active": (now - ts) < 5.0}
        for name, ts in _connected_agents.items()
    }
    return JSONResponse(agents)


@mcp.custom_route("/api/discussions", methods=["GET"])
async def api_get_discussions(request: Request) -> Response:
    return JSONResponse(_discussion_events[-50:])


@mcp.custom_route("/api/events", methods=["GET"])
async def api_events(request: Request) -> Response:
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=500)
    _sse_queues.append(queue)

    async def event_generator():
        try:
            all_state = {
                f"{did}/{k}": entry.to_dict()
                for (did, k), entry in _state.items()
            }
            yield f"event: full_state\ndata: {json.dumps(all_state)}\n\n"

            now = time.time()
            agents = {
                name: {"last_seen": ts, "active": (now - ts) < 5.0}
                for name, ts in _connected_agents.items()
            }
            yield f"event: agents_status\ndata: {json.dumps(agents)}\n\n"

            while True:
                data = await queue.get()
                event_type = data.get("type", "state_update")
                if event_type == "agent_connected":
                    yield f"event: agent_connected\ndata: {json.dumps(data)}\n\n"
                elif event_type == "discussion_message":
                    yield f"event: discussion\ndata: {json.dumps(data)}\n\n"
                else:
                    yield f"event: state_update\ndata: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _sse_queues:
                _sse_queues.remove(queue)

    from starlette.responses import StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@mcp.custom_route("/api/tool/{tool_name}", methods=["POST"])
async def api_call_tool(request: Request) -> Response:
    tool_name = request.path_params["tool_name"]
    body = await request.json()
    try:
        if tool_name == "update_state":
            result = await _update_and_notify(
                body["device_id"], body["key"], body["data"], body.get("confidence", 1.0),
            )
            return JSONResponse(result.to_dict())
        elif tool_name == "send_haptic":
            result_json = await send_haptic(
                body["pattern"], body.get("reason", "dashboard"), body.get("intensity", 0.5),
            )
            return JSONResponse(json.loads(result_json))
        elif tool_name == "display_overlay":
            result_json = await display_overlay(
                body["message"], body.get("duration_ms", 3000), body.get("position", "top"),
            )
            return JSONResponse(json.loads(result_json))
        else:
            return JSONResponse({"error": f"unknown tool: {tool_name}"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Kinesis Shared State MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (testing)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        logger.info("Starting on streamable-http at %s:%d", args.host, args.port)
        mcp.run(transport="streamable-http")
