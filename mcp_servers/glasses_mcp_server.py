"""Glasses Hardware MCP Server — AI glasses display and scene interface.

Exposes the AI glasses (camera, display overlay, gaze sensor) as a first-class
MCP server. This is the "Hardware MCP" pattern applied to the visual context device.

Runs on port 8082.

Agents connect here to:
- Display overlay messages on the glasses
- Query the current scene classification synchronously (no LLM round-trip)
- Update the cached scene state (called by the context agent after its LLM decides)

Usage:
    python mcp_servers/glasses_mcp_server.py
    python mcp_servers/glasses_mcp_server.py --port 8082
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Glasses Hardware")

# ---------------------------------------------------------------------------
# Device state
# ---------------------------------------------------------------------------

_scene: dict[str, Any] = {"scene": "unknown", "confidence": 0.0,
                           "social": False, "ambient_noise_db": 0.0, "timestamp": 0.0}
_gaze: dict[str, Any] = {"target": "unknown", "confidence": 0.0, "timestamp": 0.0}
_last_overlay: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# MCP Tools — display
# ---------------------------------------------------------------------------

@mcp.tool()
async def display_overlay(message: str, duration_ms: int = 3000,
                          position: str = "top") -> str:
    """Display a text overlay on the AI glasses.

    Args:
        message: Text to display (keep short — glasses display is small)
        duration_ms: How long to show it in milliseconds
        position: Where on the display — "top", "center", or "bottom"
    """
    payload: dict[str, Any] = {
        "message": message, "duration_ms": duration_ms,
        "position": position, "timestamp": time.time(),
    }
    _last_overlay.clear()
    _last_overlay.update(payload)
    logger.info("OVERLAY: [%s] %r (%dms)", position, message, duration_ms)
    return json.dumps({"sent": True, "message": message, "duration_ms": duration_ms})


# ---------------------------------------------------------------------------
# MCP Tools — scene query (direct hardware path, no LLM)
# ---------------------------------------------------------------------------

@mcp.tool()
async def classify_current_scene() -> str:
    """Return the current scene classification from the glasses camera.

    This is a DIRECT hardware query — it returns the cached latest scene without
    waking the glasses LLM agent. Use this for fast, low-latency scene checks.

    For complex contextual questions ("should I intervene right now?"), use
    ask_agent on the shared state server to consult the glasses LLM agent instead.
    """
    if not _scene["timestamp"]:
        return json.dumps({"scene": "unknown", "confidence": 0.0,
                           "note": "no scene data yet — glasses agent not running"})
    return json.dumps(_scene)


@mcp.tool()
async def update_scene(scene: str, confidence: float, social: bool,
                       ambient_noise_db: float) -> str:
    """Update the cached scene classification on this hardware server.

    Called by the context/glasses agent after its LLM interprets the latest
    camera frame. Caches the result here so other agents can query it via
    classify_current_scene() without a second LLM call.

    Args:
        scene: Scene type — "desk", "meeting", "walking", "standing", "social", "unknown"
        confidence: Classification confidence 0.0–1.0
        social: Whether another person is present
        ambient_noise_db: Ambient noise level in dB
    """
    _scene.update({
        "scene": scene, "confidence": confidence,
        "social": social, "ambient_noise_db": ambient_noise_db,
        "timestamp": time.time(),
    })
    return json.dumps({"updated": True, "scene": scene})


@mcp.tool()
async def update_gaze(target: str, confidence: float) -> str:
    """Update the cached gaze direction from the glasses eye tracker.

    Called by the context agent. Cached here for synchronous queries.

    Args:
        target: Gaze target — "screen", "person", "phone", "away", "unknown"
        confidence: Confidence 0.0–1.0
    """
    _gaze.update({"target": target, "confidence": confidence, "timestamp": time.time()})
    return json.dumps({"updated": True, "target": target})


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("device://glasses/scene")
def resource_scene() -> str:
    """Current scene classification from the glasses camera."""
    return json.dumps(_scene)


@mcp.resource("device://glasses/gaze")
def resource_gaze() -> str:
    """Current gaze direction from the glasses eye tracker."""
    return json.dumps(_gaze)


@mcp.resource("device://glasses/last_overlay")
def resource_last_overlay() -> str:
    """Most recent overlay command sent to the glasses display."""
    return json.dumps(_last_overlay or {"sent": False, "note": "no overlay yet"})


@mcp.resource("device://glasses/status")
def resource_status() -> str:
    """Hardware status summary."""
    return json.dumps({
        "device": "glasses",
        "scene": _scene,
        "gaze": _gaze,
        "last_overlay": _last_overlay or None,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Glasses Hardware MCP Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        logger.info("Glasses Hardware MCP Server on %s:%d", args.host, args.port)
        mcp.run(transport="streamable-http")
