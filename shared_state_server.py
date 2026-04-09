"""Shared State MCP Server — the blackboard for the Kinesis multi-agent system.

All agents (kinesess, glasses, brain/planner) connect here as MCP clients.
This server is NOT an agent — it's pure infrastructure: stores state, serves it
as MCP resources, and pushes subscription notifications when state changes.

Hardware tools (fire_haptic, fire_ems, display_overlay) live on the device MCP
servers (kinesess_mcp_server.py, glasses_mcp_server.py), NOT here. This server
owns shared coordination state only.

Architecture: Hardware MCP pattern
  port 8080 — shared_state_server (this file) — blackboard + subscriptions
  port 8081 — kinesess_mcp_server              — body hardware tools
  port 8082 — glasses_mcp_server               — glasses hardware tools
  port 8083 — brain_mcp_server                 — urgent escalation endpoint

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
    InterventionMode,
    PlannerStrategy,
    StateEntry,
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

_pending_discussions: dict[str, list[dict]] = defaultdict(list)  # to_agent → FIFO queue
_discussion_events: list[dict] = []  # log of all discussion messages
_discussion_replies: dict[str, str] = {}  # discussion_id → reply text (deleted after first read)

# ---------------------------------------------------------------------------
# Subscription registry
# ---------------------------------------------------------------------------

_subscriptions: dict[str, set[ServerSession]] = defaultdict(set)

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

# High-frequency keys that should only push to dashboard on value change,
# not every write.  Maps (device_id, key) → last pushed data snapshot.
_SSE_THROTTLE_KEYS = {"posture", "tension", "context", "gaze", "sensor_log"}
_sse_last_pushed: dict[tuple[str, str], dict] = {}


def _should_push_sse(device_id: str, key: str, data: dict[str, Any]) -> bool:
    """Return True if this state update should be sent to the dashboard.
    Sensor-rate keys are only pushed when the meaningful value changes."""
    if key not in _SSE_THROTTLE_KEYS:
        return True  # always push decisions, haptics, discussions, etc.

    cache_key = (device_id, key)
    prev = _sse_last_pushed.get(cache_key)

    if key == "sensor_log":
        return False  # sensor_log goes to sidebar only on explicit poll, not SSE

    if key == "posture":
        changed = prev is None or prev.get("classification") != data.get("classification")
    elif key == "context":
        changed = prev is None or prev.get("scene") != data.get("scene")
    elif key == "tension":
        # Only push if level crosses a 10% boundary
        prev_lvl = int((prev or {}).get("level", 0) * 10)
        cur_lvl = int(data.get("level", 0) * 10)
        changed = prev is None or prev_lvl != cur_lvl
    elif key == "gaze":
        changed = prev is None or prev.get("target") != data.get("target")
    else:
        changed = True

    if changed:
        _sse_last_pushed[cache_key] = dict(data)
    return changed


def _do_update(device_id: str, key: str, data: dict[str, Any], confidence: float) -> StateEntry:
    existing = _state.get((device_id, key))
    version = (existing.version + 1) if existing else 1
    entry = StateEntry(
        device_id=device_id, key=key, data=data,
        confidence=confidence, timestamp=time.time(), version=version,
    )
    _state[(device_id, key)] = entry
    if _should_push_sse(device_id, key, data):
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
    plan = PlannerStrategy(
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


# ---------------------------------------------------------------------------
# MCP Tools — inter-agent discussion
# ---------------------------------------------------------------------------

@mcp.tool()
async def ask_agent(from_agent: str, to_agent: str, question: str, context: str = "") -> str:
    """Ask another agent a question. Returns immediately with a discussion_id.

    The caller should poll get_reply(discussion_id) every ~300ms until a reply arrives.
    The body agent's Python runtime handles this polling transparently — the LLM sees
    the final reply, not the discussion_id.

    Args:
        from_agent: Your agent id ("kinesess" or "glasses")
        to_agent: Target agent id ("kinesess" or "glasses")
        question: Your question for the other agent
        context: Additional context (JSON string with relevant sensor data)
    """
    discussion_id = f"{from_agent}_{to_agent}_{int(time.time() * 1000)}"

    discussion = {
        "id": discussion_id,
        "from": from_agent,
        "to": to_agent,
        "question": question,
        "context": context,
        "timestamp": time.time(),
        "status": "pending",
    }

    # Enqueue — multiple questions can be pending for the same target (Issue 3 fix)
    _pending_discussions[to_agent].append(discussion)
    _discussion_events.append(discussion)

    # Write to blackboard — triggers subscription notification to target agent
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

    logger.info("Discussion queued: %s → %s: %s", from_agent, to_agent, question[:100])

    # Return immediately — no server blocking (Issue 1 fix)
    return json.dumps({
        "discussion_id": discussion_id,
        "status": "queued",
        "to": to_agent,
        "note": "Poll get_reply(discussion_id) to retrieve the answer",
    })


@mcp.tool()
async def reply_to_agent(from_agent: str, message: str, discussion_id: str = "") -> str:
    """Reply to a pending question from another agent.

    Call this when you've been asked a question and have formulated your response.
    Pass discussion_id (from get_pending_discussion) to target a specific question;
    omits it to reply to the oldest pending question for your agent.

    Args:
        from_agent: Your agent id ("kinesess" or "glasses")
        message: Your reply to the other agent's question
        discussion_id: Optional — the id field from get_pending_discussion output
    """
    pending = _pending_discussions.get(from_agent, [])
    if not pending:
        return json.dumps({"error": "no_pending_discussion", "from": from_agent})

    # Match by discussion_id if provided; otherwise take the oldest (FIFO)
    if discussion_id:
        discussion = next((d for d in pending if d["id"] == discussion_id), pending[0])
    else:
        discussion = pending[0]

    matched_id = discussion["id"]
    asking_agent = discussion["from"]

    # Store reply so get_reply() can return it
    _discussion_replies[matched_id] = message

    # Remove from queue
    _pending_discussions[from_agent] = [d for d in pending if d["id"] != matched_id]

    # Log the reply
    reply_event = {
        "id": matched_id,
        "from": from_agent,
        "to": asking_agent,
        "reply": message,
        "timestamp": time.time(),
        "status": "replied",
    }
    _discussion_events.append(reply_event)

    # Write to blackboard — lets brain agent / dashboard see the reply
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
    return json.dumps({"sent": True, "to": asking_agent, "discussion_id": matched_id})


@mcp.tool()
async def get_pending_discussion(agent_id: str) -> str:
    """Return the oldest pending question for this agent (FIFO).

    The returned object includes an "id" field (discussion_id) that you must pass
    to reply_to_agent so the reply is routed to the correct caller.

    Args:
        agent_id: Your agent id ("kinesess" or "glasses")
    """
    pending = _pending_discussions.get(agent_id, [])
    if pending:
        return json.dumps(pending[0])  # oldest question first
    return json.dumps({"pending": False})


@mcp.tool()
async def get_reply(discussion_id: str) -> str:
    """Check if a reply is available for a queued ask_agent call.

    The body agent's Python runtime calls this automatically after ask_agent —
    you never need to call this from a system prompt. It is exposed as a tool
    so the polling loop can use the standard MCP session.call_tool path.

    Args:
        discussion_id: The discussion_id returned by ask_agent
    """
    reply = _discussion_replies.pop(discussion_id, None)  # one-time read, then gone
    if reply is None:
        return json.dumps({"status": "pending", "discussion_id": discussion_id})
    return json.dumps({"status": "replied", "reply": reply, "discussion_id": discussion_id})


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


@mcp.custom_route("/api/sensor_log", methods=["GET"])
async def api_sensor_log(request: Request) -> Response:
    """Polled by sidebar sensor logs (not SSE — too noisy)."""
    result = {}
    for key in ["glasses/sensor_log", "kinesess/sensor_log"]:
        did, k = key.split("/", 1)
        entry = _state.get((did, k))
        if entry:
            result[key] = entry.to_dict()
    return JSONResponse(result)


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
        else:
            return JSONResponse(
                {"error": f"unknown tool: {tool_name}",
                 "note": "hardware tools (fire_haptic, fire_ems, display_overlay) "
                         "moved to device MCP servers on ports 8081/8082"},
                status_code=404,
            )
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
