"""Kinesis MVP — start the shared state server and all agents.

Usage:
    # Option 1: Start everything (requires 4 terminals or use this script)
    python run.py

    # Option 2: Start each component separately
    python shared_state_server.py           # Terminal 1: blackboard + dashboard
    python agents/context_agent.py          # Terminal 2: glasses/context
    python agents/body_agent.py             # Terminal 3: body/posture
    python agents/brain_agent.py            # Terminal 4: planner

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


def main():
    processes = []

    components = [
        ("Shared State Server", [PYTHON, str(KINESIS_DIR / "shared_state_server.py")]),
    ]

    # Start server first, wait for it
    logger.info("Starting shared state server...")
    server_proc = subprocess.Popen(
        components[0][1],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(("Shared State Server", server_proc))
    time.sleep(2)  # let server start

    # Start agents
    agent_commands = [
        ("Context Agent (Glasses)", [PYTHON, str(KINESIS_DIR / "agents" / "context_agent.py"), "--demo"]),
        ("Body Agent (Kinesess)", [PYTHON, str(KINESIS_DIR / "agents" / "body_agent.py"), "--demo"]),
        # ("Planner Agent", [PYTHON, str(KINESIS_DIR / "agents" / "brain_agent.py")]),  # disabled for now
    ]

    for name, cmd in agent_commands:
        logger.info("Starting %s...", name)
        proc = subprocess.Popen(cmd)
        processes.append((name, proc))
        time.sleep(1)

    print()
    print("=" * 60)
    print("  Kinesis Multi-Agent System")
    print("  Dashboard: http://localhost:8080")
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
