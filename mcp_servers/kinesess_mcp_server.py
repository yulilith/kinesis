"""Kinesess Hardware MCP Server — body sensor actuator interface.

Exposes the Kinesess wearable device (IMU sensors, vibration motors, EMS channels)
as a first-class MCP server. This is the "Hardware MCP" pattern: physical device
capabilities are tools in the MCP protocol stack, not wrappers on a shared blackboard.

Runs on port 8081 (shared_state_server runs on 8080).

Agents connect here to:
- Fire haptic/EMS interventions directly on the device
- Read/set the attention budget
- Query device hardware status

Usage:
    python mcp_servers/kinesess_mcp_server.py
    python mcp_servers/kinesess_mcp_server.py --port 8081
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

from schemas import EMSChannel, HapticPattern, VibrationZone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Kinesess Hardware")

# ---------------------------------------------------------------------------
# Device state
# ---------------------------------------------------------------------------

_attention_budget: dict[str, Any] = {"remaining": 20, "daily_max": 20}
_ems_last_fire: dict[str, float] = {}
_last_haptic: dict[str, Any] = {}
_last_ems: dict[str, Any] = {}

EMS_MAX_INTENSITY_MA = 15.0
EMS_MAX_DURATION_MS  = 3000
EMS_COOLDOWN_S       = 120.0

# ---------------------------------------------------------------------------
# MCP Tools — actuators
# ---------------------------------------------------------------------------

@mcp.tool()
async def fire_haptic(pattern: str, reason: str, intensity: float = 0.5,
                      zone: str = "") -> str:
    """Fire a haptic (vibration) pattern on the Kinesess body sensor device.

    Deducts 1 from the attention budget. Returns immediately if budget is exhausted.

    Args:
        pattern: Vibration pattern — "gentle", "firm", "pulse", "left_nudge",
                 "right_nudge", "lumbar_alert", "bilateral"
        reason: Why this haptic is being fired (logged)
        intensity: Strength 0.0–1.0
        zone: Target motor zone — "shoulder_l", "shoulder_r", "lumbar_l", "lumbar_r".
              Leave empty to fire all zones.
    """
    HapticPattern(pattern)
    if zone:
        VibrationZone(zone)

    remaining = _attention_budget["remaining"]
    if remaining <= 0:
        return json.dumps({"fired": False, "reason": "attention_budget_exhausted",
                           "budget_remaining": 0})

    payload: dict[str, Any] = {
        "pattern": pattern, "reason": reason, "intensity": intensity,
        "timestamp": time.time(),
    }
    if zone:
        payload["zone"] = zone

    _last_haptic.clear()
    _last_haptic.update(payload)
    _attention_budget["remaining"] = remaining - 1

    logger.info("HAPTIC fired: pattern=%s zone=%s intensity=%.1f reason=%s",
                pattern, zone or "all", intensity, reason)

    return json.dumps({
        "fired": True, "pattern": pattern, "zone": zone or "all",
        "intensity": intensity, "budget_remaining": _attention_budget["remaining"],
    })


@mcp.tool()
async def fire_ems(channel: str, intensity_ma: float, duration_ms: int,
                   frequency_hz: float, reason: str) -> str:
    """Fire an EMS (electrical muscle stimulation) pulse on a specific muscle channel.

    Safety limits are enforced in hardware and cannot be overridden.
    Costs 3 attention budget points (use sparingly).

    Args:
        channel: "rhomboid_l", "rhomboid_r", "lumbar_erector_l", "lumbar_erector_r"
        intensity_ma: Current in milliamps. Hard cap: 15.0 mA.
        duration_ms: Pulse duration. Hard cap: 3000 ms.
        frequency_hz: Stimulation frequency. Range: 20–80 Hz.
        reason: Why this EMS is being fired (logged)
    """
    EMSChannel(channel)

    # Hard safety caps
    intensity_ma = min(intensity_ma, EMS_MAX_INTENSITY_MA)
    duration_ms  = min(duration_ms,  EMS_MAX_DURATION_MS)
    frequency_hz = max(20.0, min(frequency_hz, 80.0))

    # Cooldown check per channel
    elapsed = time.time() - _ems_last_fire.get(channel, 0.0)
    if elapsed < EMS_COOLDOWN_S:
        return json.dumps({"fired": False, "reason": "cooldown",
                           "channel": channel, "wait_s": round(EMS_COOLDOWN_S - elapsed, 1)})

    remaining = _attention_budget["remaining"]
    if remaining < 3:
        return json.dumps({"fired": False, "reason": "attention_budget_exhausted",
                           "budget_remaining": remaining})

    _ems_last_fire[channel] = time.time()
    _attention_budget["remaining"] = remaining - 3

    payload: dict[str, Any] = {
        "channel": channel, "intensity_ma": intensity_ma,
        "duration_ms": duration_ms, "frequency_hz": frequency_hz,
        "reason": reason, "timestamp": time.time(),
    }
    _last_ems.clear()
    _last_ems.update(payload)

    logger.info("EMS fired: channel=%s %.1fmA %dms %.0fHz reason=%s",
                channel, intensity_ma, duration_ms, frequency_hz, reason)

    return json.dumps({
        "fired": True, "channel": channel, "intensity_ma": intensity_ma,
        "duration_ms": duration_ms, "frequency_hz": frequency_hz,
        "budget_remaining": _attention_budget["remaining"],
    })


# ---------------------------------------------------------------------------
# MCP Tools — budget management (for brain/planner agent)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_attention_budget() -> str:
    """Return the current attention budget for this device.

    Budget limits total daily actuator use to prevent habituation.
    Haptic costs 1 point; EMS costs 3 points.
    """
    return json.dumps(_attention_budget)


@mcp.tool()
async def set_attention_budget(remaining: int, daily_max: int = 20) -> str:
    """Set the attention budget. Called by the brain/planner agent to adjust strategy.

    Args:
        remaining: New remaining budget for today
        daily_max: Total daily cap (default 20)
    """
    _attention_budget["remaining"] = max(0, min(remaining, daily_max))
    _attention_budget["daily_max"] = daily_max
    logger.info("Attention budget set: %d/%d", _attention_budget["remaining"], daily_max)
    return json.dumps(_attention_budget)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("device://kinesess/last_haptic")
def resource_last_haptic() -> str:
    """Most recent haptic command fired on this device."""
    return json.dumps(_last_haptic or {"fired": False, "note": "no haptic yet"})


@mcp.resource("device://kinesess/last_ems")
def resource_last_ems() -> str:
    """Most recent EMS pulse fired on this device."""
    return json.dumps(_last_ems or {"fired": False, "note": "no EMS yet"})


@mcp.resource("device://kinesess/attention_budget")
def resource_attention_budget() -> str:
    """Current attention budget state."""
    return json.dumps(_attention_budget)


@mcp.resource("device://kinesess/status")
def resource_status() -> str:
    """Hardware status summary."""
    now = time.time()
    ems_cooldowns = {
        ch: max(0.0, round(EMS_COOLDOWN_S - (now - ts), 1))
        for ch, ts in _ems_last_fire.items()
    }
    return json.dumps({
        "device": "kinesess",
        "attention_budget": _attention_budget,
        "ems_cooldowns_remaining_s": ems_cooldowns,
        "last_haptic": _last_haptic or None,
        "last_ems": _last_ems or None,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Kinesess Hardware MCP Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        logger.info("Kinesess Hardware MCP Server on %s:%d", args.host, args.port)
        mcp.run(transport="streamable-http")
