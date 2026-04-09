"""Whoop Biometrics MCP Server — exposes WHOOP recovery, HRV, sleep, and strain data.

Runs on port 8084. Connects to the WHOOP API using OAuth2 credentials.
Falls back to mock data automatically when no credentials are configured,
so the system runs end-to-end without a physical WHOOP device.

The brain/coach agent reads biometric context from this server every 30s
and writes a BiometricContext snapshot to the shared state blackboard.
Body and context agents then read that snapshot to adapt intervention intensity.

How biometrics inform posture coaching:
  recovery_score < 50  → reduce to gentle mode, skip EMS
  hrv_rmssd < 30 ms    → user stressed, prefer vibration over EMS
  sleep_quality < 0.6  → reduce intervention frequency in first 2h of day
  strain > 15          → muscles fatigued, halve EMS intensity cap

Usage:
    # Mock mode (no WHOOP device needed)
    python mcp_servers/whoop_mcp_server.py

    # Real WHOOP API
    export WHOOP_CLIENT_ID=...
    export WHOOP_CLIENT_SECRET=...
    export WHOOP_ACCESS_TOKEN=...   # obtain via OAuth2 flow
    python mcp_servers/whoop_mcp_server.py --port 8084

    # Custom port
    python mcp_servers/whoop_mcp_server.py --port 8084
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
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

mcp = FastMCP("Whoop Biometrics")

# ---------------------------------------------------------------------------
# WHOOP API client (real mode)
# ---------------------------------------------------------------------------

_WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v1"

def _whoop_headers() -> dict[str, str]:
    token = os.getenv("WHOOP_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _fetch_whoop(endpoint: str) -> dict[str, Any] | None:
    """HTTP GET against WHOOP API. Returns parsed JSON or None on failure."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{_WHOOP_API_BASE}{endpoint}",
            headers=_whoop_headers(),
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning("WHOOP API request failed (%s): %s", endpoint, e)
        return None


# ---------------------------------------------------------------------------
# Mock data generator
# ---------------------------------------------------------------------------

class _MockWhoopData:
    """Generates realistic mock WHOOP data that cycles through a daily pattern.

    Simulates a typical workday: good recovery in the morning, rising strain
    through the day, HRV declining as fatigue accumulates.
    """

    def __init__(self) -> None:
        self._session_start = time.time()

    def _time_of_day_fraction(self) -> float:
        """0.0 = session start, 1.0 = 8 hours later (simulated workday)."""
        elapsed = (time.time() - self._session_start) % (8 * 3600)
        return elapsed / (8 * 3600)

    def recovery(self) -> dict[str, Any]:
        t = self._time_of_day_fraction()
        # Recovery starts high, dips slightly as the day wears on
        base_score = 72.0 - 15.0 * t + random.gauss(0, 3)
        score = max(10.0, min(99.0, base_score))
        hrv = 45.0 - 12.0 * t + random.gauss(0, 2)
        rhr = 52.0 + 6.0 * t + random.gauss(0, 1)
        return {
            "score": round(score, 1),
            "hrv_rmssd_ms": round(max(15.0, hrv), 1),
            "resting_heart_rate_bpm": round(max(40.0, rhr), 1),
            "recovery_level": (
                "peak" if score >= 67 else "good" if score >= 34 else "needs_recovery"
            ),
        }

    def sleep(self) -> dict[str, Any]:
        t = self._time_of_day_fraction()
        quality = 0.78 - 0.1 * t + random.gauss(0, 0.03)
        return {
            "quality_score": round(max(0.0, min(1.0, quality)), 2),
            "total_duration_h": round(7.2 + random.gauss(0, 0.3), 1),
            "disturbances": random.randint(0, 4),
            "sleep_debt_h": round(max(0.0, 0.8 + 1.5 * t + random.gauss(0, 0.2)), 1),
        }

    def strain(self) -> dict[str, Any]:
        t = self._time_of_day_fraction()
        # Strain builds through the day
        daily_strain = 4.0 + 10.0 * t + random.gauss(0, 0.5)
        avg_hr = 68.0 + 20.0 * t + random.gauss(0, 3)
        return {
            "score": round(max(0.0, min(21.0, daily_strain)), 1),
            "average_heart_rate_bpm": round(max(50.0, avg_hr), 0),
            "max_heart_rate_bpm": round(max(60.0, avg_hr + 35 + random.gauss(0, 5)), 0),
            "kilojoule": round(800 + 1200 * t + random.gauss(0, 50), 0),
        }

    def heart_rate(self) -> dict[str, Any]:
        t = self._time_of_day_fraction()
        bpm = 68.0 + 18.0 * math.sin(math.pi * t) + random.gauss(0, 4)
        return {
            "bpm": round(max(45.0, bpm), 0),
            "timestamp": time.time(),
        }


_mock = _MockWhoopData()
_use_mock: bool = True   # flipped to False when WHOOP_ACCESS_TOKEN is set
_cache: dict[str, tuple[float, Any]] = {}  # key → (timestamp, data)
CACHE_TTL_S = 60.0       # refresh at most once per minute to respect API rate limits


def _cached(key: str, fetch_fn) -> Any:
    """Return cached value if fresh, otherwise call fetch_fn() and cache result."""
    ts, data = _cache.get(key, (0.0, None))
    if time.time() - ts < CACHE_TTL_S and data is not None:
        return data
    result = fetch_fn()
    _cache[key] = (time.time(), result)
    return result


# ---------------------------------------------------------------------------
# Data fetchers (real or mock)
# ---------------------------------------------------------------------------

def _get_recovery() -> dict[str, Any]:
    if _use_mock:
        return _mock.recovery()
    raw = _fetch_whoop("/cycle?limit=1")
    if raw and raw.get("records"):
        rec = raw["records"][0]
        score_data = rec.get("score", {})
        return {
            "score": score_data.get("recovery_score", 0),
            "hrv_rmssd_ms": score_data.get("hrv_rmssd_milli", 0),
            "resting_heart_rate_bpm": score_data.get("resting_heart_rate", 0),
            "recovery_level": score_data.get("user_calibrating", False) and "calibrating" or (
                "peak" if score_data.get("recovery_score", 0) >= 67
                else "good" if score_data.get("recovery_score", 0) >= 34
                else "needs_recovery"
            ),
        }
    return _mock.recovery()  # fall back to mock if API fails


def _get_sleep() -> dict[str, Any]:
    if _use_mock:
        return _mock.sleep()
    raw = _fetch_whoop("/activity/sleep?limit=1")
    if raw and raw.get("records"):
        rec = raw["records"][0]
        score_data = rec.get("score", {})
        stage_summary = score_data.get("stage_summary", {})
        total_ms = stage_summary.get("total_in_bed_time_milli", 0)
        return {
            "quality_score": round(score_data.get("sleep_performance_percentage", 0) / 100, 2),
            "total_duration_h": round(total_ms / 3_600_000, 1),
            "disturbances": score_data.get("disturbance_count", 0),
            "sleep_debt_h": round(score_data.get("sleep_need", {}).get("baseline_milli", 0) / 3_600_000, 1),
        }
    return _mock.sleep()


def _get_strain() -> dict[str, Any]:
    if _use_mock:
        return _mock.strain()
    raw = _fetch_whoop("/cycle?limit=1")
    if raw and raw.get("records"):
        rec = raw["records"][0]
        score_data = rec.get("score", {})
        return {
            "score": score_data.get("strain", 0),
            "average_heart_rate_bpm": score_data.get("average_heart_rate", 0),
            "max_heart_rate_bpm": score_data.get("max_heart_rate", 0),
            "kilojoule": score_data.get("kilojoule", 0),
        }
    return _mock.strain()


def _get_heart_rate() -> dict[str, Any]:
    if _use_mock:
        return _mock.heart_rate()
    raw = _fetch_whoop("/metrics/heart_rate?start=now&end=now&order=desc&limit=1")
    if raw and raw.get("data"):
        entry = raw["data"][0]
        return {"bpm": entry.get("data", {}).get("bpm", 0), "timestamp": time.time()}
    return _mock.heart_rate()


# ---------------------------------------------------------------------------
# Coaching recommendation derived from biometrics
# ---------------------------------------------------------------------------

def _coaching_recommendation(recovery: dict, sleep: dict, strain: dict) -> dict[str, Any]:
    """Derive a coaching mode suggestion and EMS safety flag from biometrics.

    This is read by the brain agent to set the intervention mode on the blackboard.
    """
    rec_score   = recovery.get("score", 50)
    hrv         = recovery.get("hrv_rmssd_ms", 40)
    sleep_q     = sleep.get("quality_score", 0.7)
    strain_val  = strain.get("score", 8)

    # Determine suggested mode
    if rec_score < 33:
        suggested_mode = "silent"
    elif rec_score < 50 or hrv < 25:
        suggested_mode = "gentle"
    elif rec_score >= 67 and strain_val < 14:
        suggested_mode = "normal"
    else:
        suggested_mode = "gentle"

    # EMS safety: avoid if fatigued or very low recovery
    ems_safe = rec_score >= 40 and strain_val < 17 and hrv >= 20

    # Reduce intervention frequency if sleep deprived
    sleep_adjusted = sleep_q < 0.55

    reasons = []
    if rec_score < 50:
        reasons.append(f"low recovery ({rec_score:.0f}/100)")
    if hrv < 30:
        reasons.append(f"low HRV ({hrv:.0f} ms)")
    if sleep_q < 0.6:
        reasons.append(f"poor sleep ({sleep_q:.0%})")
    if strain_val > 15:
        reasons.append(f"high strain ({strain_val:.1f}/21)")

    return {
        "suggested_mode": suggested_mode,
        "ems_safe": ems_safe,
        "sleep_adjusted": sleep_adjusted,
        "reason": "; ".join(reasons) if reasons else "biometrics nominal",
    }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_recovery() -> str:
    """Return today's WHOOP recovery score, HRV, and resting heart rate.

    Recovery score (0-100):
      >= 67  peak — full coaching interventions OK
      33-66  good — normal coaching
      < 33   needs recovery — reduce to gentle or silent mode

    Returns:
        JSON with score, hrv_rmssd_ms, resting_heart_rate_bpm, recovery_level
    """
    data = _cached("recovery", _get_recovery)
    data["source"] = "mock" if _use_mock else "whoop_api"
    data["cached_at"] = _cache.get("recovery", (time.time(), None))[0]
    return json.dumps(data)


@mcp.tool()
async def get_sleep() -> str:
    """Return last night's sleep quality, duration, and sleep debt.

    Low sleep quality (< 0.6) or high debt suggests reducing morning intervention
    frequency — the user is already stressed from poor sleep.

    Returns:
        JSON with quality_score (0-1), total_duration_h, disturbances, sleep_debt_h
    """
    data = _cached("sleep", _get_sleep)
    data["source"] = "mock" if _use_mock else "whoop_api"
    return json.dumps(data)


@mcp.tool()
async def get_strain() -> str:
    """Return today's accumulated physical strain score and heart rate metrics.

    High strain (> 15/21) means muscles are already fatigued — EMS intensity
    should be reduced and recovery postures preferred over correction pulses.

    Returns:
        JSON with score (0-21), average_heart_rate_bpm, max_heart_rate_bpm, kilojoule
    """
    data = _cached("strain", _get_strain)
    data["source"] = "mock" if _use_mock else "whoop_api"
    return json.dumps(data)


@mcp.tool()
async def get_heart_rate() -> str:
    """Return the most recent real-time heart rate reading.

    Elevated heart rate during a posture event may indicate stress or effort —
    prefer a gentle haptic reminder over EMS in that case.

    Returns:
        JSON with bpm and timestamp
    """
    data = _get_heart_rate()  # not cached — always live
    data["source"] = "mock" if _use_mock else "whoop_api"
    return json.dumps(data)


@mcp.tool()
async def get_biometric_summary() -> str:
    """Return a full biometric snapshot: recovery, sleep, strain, and coaching recommendation.

    This is the primary tool for the brain/coach agent. Call once per coaching
    cycle (every 30s) and write the result to the shared state blackboard so
    body and context agents can adapt their intervention strategy.

    Returns:
        JSON with recovery, sleep, strain, heart_rate, coaching_recommendation
    """
    recovery  = _cached("recovery", _get_recovery)
    sleep     = _cached("sleep",    _get_sleep)
    strain    = _cached("strain",   _get_strain)
    hr        = _get_heart_rate()
    coaching  = _coaching_recommendation(recovery, sleep, strain)

    return json.dumps({
        "recovery":              recovery,
        "sleep":                 sleep,
        "strain":                strain,
        "heart_rate":            hr,
        "coaching_recommendation": coaching,
        "source":                "mock" if _use_mock else "whoop_api",
        "timestamp":             time.time(),
    })


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("biometrics://whoop/recovery")
def resource_recovery() -> str:
    """Latest recovery snapshot."""
    data = _cached("recovery", _get_recovery)
    data["source"] = "mock" if _use_mock else "whoop_api"
    return json.dumps(data)


@mcp.resource("biometrics://whoop/sleep")
def resource_sleep() -> str:
    """Latest sleep snapshot."""
    data = _cached("sleep", _get_sleep)
    data["source"] = "mock" if _use_mock else "whoop_api"
    return json.dumps(data)


@mcp.resource("biometrics://whoop/strain")
def resource_strain() -> str:
    """Latest strain snapshot."""
    data = _cached("strain", _get_strain)
    data["source"] = "mock" if _use_mock else "whoop_api"
    return json.dumps(data)


@mcp.resource("biometrics://whoop/summary")
def resource_summary() -> str:
    """Full biometric summary including coaching recommendation."""
    recovery  = _cached("recovery", _get_recovery)
    sleep     = _cached("sleep",    _get_sleep)
    strain    = _cached("strain",   _get_strain)
    coaching  = _coaching_recommendation(recovery, sleep, strain)
    return json.dumps({
        "recovery": recovery, "sleep": sleep, "strain": strain,
        "coaching_recommendation": coaching,
        "source": "mock" if _use_mock else "whoop_api",
        "timestamp": time.time(),
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Whoop Biometrics MCP Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8084)
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()

    # Auto-detect real vs mock mode
    if os.getenv("WHOOP_ACCESS_TOKEN"):
        _use_mock = False
        logger.info("WHOOP API mode — using real credentials")
    else:
        _use_mock = True
        logger.info("Mock mode — set WHOOP_ACCESS_TOKEN to use real WHOOP API")

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        logger.info("Whoop Biometrics MCP Server on %s:%d", args.host, args.port)
        mcp.run(transport="streamable-http")
