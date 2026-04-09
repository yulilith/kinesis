"""Kinesis MVP — start all MCP servers and agents.

Architecture: Hardware MCP pattern (5 servers + 3 agents)
  Port 8080 — shared_state_server   (blackboard + dashboard)
  Port 8081 — kinesess_mcp_server   (body hardware: haptic, EMS, budget)
  Port 8082 — glasses_mcp_server    (glasses hardware: overlay, scene cache)
  Port 8083 — brain_mcp_server      (coach endpoint: urgent escalation)
  Port 8084 — whoop_mcp_server      (biometrics: recovery, HRV, sleep, strain)
                                     mock mode by default — set WHOOP_ACCESS_TOKEN
                                     env var to use real WHOOP API

Usage:
    # Option 1: Start everything (this script)
    python run.py

    # Option 2: Start each component separately (order matters — servers before agents)
    python shared_state_server.py                    # Terminal 1
    python mcp_servers/kinesess_mcp_server.py        # Terminal 2
    python mcp_servers/glasses_mcp_server.py         # Terminal 3
    python mcp_servers/brain_mcp_server.py           # Terminal 4
    python mcp_servers/whoop_mcp_server.py           # Terminal 5
    python agents/context_agent.py                   # Terminal 6
    python agents/body_agent.py                      # Terminal 7
    python agents/brain_agent.py                     # Terminal 8

    # Dashboard: http://localhost:8080
"""

import asyncio
import logging
import subprocess
import sys
import signal
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)s %(message)s",
)
logger = logging.getLogger("run")

KINESIS_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable


def _start(name: str, cmd: list, processes: list, delay: float = 1.0) -> None:
    logger.info("Starting %s...", name)
    proc = subprocess.Popen(cmd)
    processes.append((name, proc))
    time.sleep(delay)


def main():
    processes = []

    # ------------------------------------------------------------------ servers
    # Start servers in order — agents will fail to connect if servers aren't up.
    _start("Shared State Server (8080)",
           [PYTHON, str(KINESIS_DIR / "shared_state_server.py")], processes, delay=2.0)

    _start("Kinesess Hardware MCP (8081)",
           [PYTHON, str(KINESIS_DIR / "mcp_servers" / "kinesess_mcp_server.py")], processes)

    _start("Glasses Hardware MCP (8082)",
           [PYTHON, str(KINESIS_DIR / "mcp_servers" / "glasses_mcp_server.py")], processes)

    _start("Brain Coach MCP (8083)",
           [PYTHON, str(KINESIS_DIR / "mcp_servers" / "brain_mcp_server.py")], processes)

    _start("Whoop Biometrics MCP (8084)",
           [PYTHON, str(KINESIS_DIR / "mcp_servers" / "whoop_mcp_server.py")], processes)

    # ------------------------------------------------------------------ agents
    _start("Context Agent (Glasses)",
           [PYTHON, str(KINESIS_DIR / "agents" / "context_agent.py"), "--demo"], processes)

    _start("Body Agent (Kinesess)",
           [PYTHON, str(KINESIS_DIR / "agents" / "body_agent.py"), "--demo"], processes)

    # _start("Planner Agent",
    #        [PYTHON, str(KINESIS_DIR / "agents" / "brain_agent.py")], processes)

    print()
    print("=" * 60)
    print("  Kinesis — Hardware MCP Architecture")
    print("  Blackboard + Dashboard: http://localhost:8080")
    print("  Kinesess Hardware MCP:  http://localhost:8081")
    print("  Glasses Hardware MCP:   http://localhost:8082")
    print("  Brain Coach MCP:        http://localhost:8083")
    print("  Press Ctrl+C to stop all components")
    print("=" * 60)
    print()

    try:
        # Wait for any process to exit
        while True:
            for name, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    logger.warning("%s exited with code %d", name, ret)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        for name, proc in reversed(processes):
            logger.info("Stopping %s...", name)
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("All components stopped.")


if __name__ == "__main__":
    main()
