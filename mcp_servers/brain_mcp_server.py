"""Brain/Coach MCP Server — urgent escalation endpoint.

Exposes the coach/planner as an MCP server so device agents can hard-escalate
critical events directly. This is the "hard escalation" channel from CLAUDE.md:
device agent → brain_mcp_server.urgent_request() — bypasses the blackboard entirely.

Runs on port 8083.

The brain agent connects here as a CLIENT to drain the urgent request queue.
Device agents connect here to fire urgent requests.

Use this channel ONLY for:
- Injury risk (EMG spike above safety threshold)
- User distress signals
- Critical sensor failure

For non-emergency escalation, write to state://escalation/{device} on the
shared state server instead.

Usage:
    python mcp_servers/brain_mcp_server.py
    python mcp_servers/brain_mcp_server.py --port 8083
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Brain Coach")

# ---------------------------------------------------------------------------
# Urgent request queue
# ---------------------------------------------------------------------------

_urgent_queue: deque[dict[str, Any]] = deque(maxlen=50)

# ---------------------------------------------------------------------------
# MCP Tools — escalation intake (device agents call these)
# ---------------------------------------------------------------------------

@mcp.tool()
async def urgent_request(from_agent: str, reason: str, context: str = "",
                         severity: str = "high") -> str:
    """Hard-escalate a critical event directly to the coach/planner agent.

    Use ONLY for: injury risk (EMG spike), user distress, critical failure.
    For anything less urgent, use the soft escalation channel (blackboard).

    The coach will process this on its next loop iteration (target: <500ms).

    Args:
        from_agent: Source agent id — "kinesess" or "glasses"
        reason: What happened — short description
        context: JSON string with relevant sensor readings / evidence
        severity: "high" (default) or "critical" (immediate danger)
    """
    request: dict[str, Any] = {
        "id": f"{from_agent}_{int(time.time() * 1000)}",
        "from": from_agent,
        "reason": reason,
        "context": context,
        "severity": severity,
        "timestamp": time.time(),
        "processed": False,
    }
    _urgent_queue.append(request)
    logger.warning("URGENT REQUEST from %s [%s]: %s", from_agent, severity, reason)
    return json.dumps({"received": True, "id": request["id"],
                       "note": "Coach will process this within one reasoning cycle"})


# ---------------------------------------------------------------------------
# MCP Tools — queue drain (brain agent calls these)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_urgent_requests(mark_processed: bool = True) -> str:
    """Return all unprocessed urgent requests. Called by the brain agent.

    Args:
        mark_processed: If True (default), marks returned requests as processed
                        so they won't be returned again.
    """
    pending = [r for r in _urgent_queue if not r["processed"]]
    if mark_processed:
        for r in pending:
            r["processed"] = True
    return json.dumps(pending)


@mcp.tool()
async def get_urgent_queue_depth() -> str:
    """Return count of unprocessed urgent requests (lightweight status check)."""
    pending_count = sum(1 for r in _urgent_queue if not r["processed"])
    return json.dumps({"pending": pending_count, "total": len(_urgent_queue)})


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("coach://urgent_queue")
def resource_urgent_queue() -> str:
    """All urgent requests (processed and pending)."""
    return json.dumps(list(_urgent_queue))


@mcp.resource("coach://status")
def resource_status() -> str:
    """Coach escalation endpoint status."""
    pending = sum(1 for r in _urgent_queue if not r["processed"])
    return json.dumps({
        "server": "brain_mcp_server",
        "pending_urgent_requests": pending,
        "total_received": len(_urgent_queue),
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Brain Coach MCP Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8083)
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        logger.info("Brain Coach MCP Server on %s:%d", args.host, args.port)
        mcp.run(transport="streamable-http")
