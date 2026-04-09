"""Kinesis MVP — start the shared state server and all agents.

Usage:
    # Option 1: Start everything (requires 4 terminals or use this script)
    python run.py

    # Option 1b: Start everything with a stored 5-minute replay dataset
    python run.py --replay-dataset mock_data/desk_work_focus_5min.json

    # Option 2: Start each component separately
    python shared_state_server.py           # Terminal 1: blackboard + dashboard
    python agents/context_agent.py          # Terminal 2: glasses/context
    python agents/body_agent.py             # Terminal 3: body/posture
    python agents/brain_agent.py            # Terminal 4: planner

    # Dashboard: http://localhost:8080
"""

import asyncio
import argparse
import logging
import subprocess
import sys
import signal
import time
from pathlib import Path

from mock_replay import resolve_replay_dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)s %(message)s",
)
logger = logging.getLogger("run")

KINESIS_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable


def _check_runtime_dependencies() -> None:
    """Fail fast with a clear message when run.py is launched with the wrong Python."""
    probe = subprocess.run(
        [
            PYTHON,
            "-c",
            "import mcp,anthropic,dotenv,starlette; print('ok')",
        ],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        logger.error("Current interpreter is missing required packages: %s", PYTHON)
        logger.error("Start with project venv: %s", KINESIS_DIR / ".venv" / "bin" / "python")
        if probe.stderr:
            logger.error("Import error:\n%s", probe.stderr.strip())
        raise SystemExit(1)


def _resolve_replay_dataset(dataset_arg: str) -> str:
    try:
        return str(resolve_replay_dataset(dataset_arg).resolve())
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description="Start the Kinesis multi-agent system")
    parser.add_argument("--replay-dataset", help="Path to a local replay dataset JSON used by body/context agents")
    args = parser.parse_args()

    _check_runtime_dependencies()

    processes = []

    components = [
        ("Shared State Server", [PYTHON, str(KINESIS_DIR / "shared_state_server.py")]),
    ]

    # Start server first, wait for it
    logger.info("Starting shared state server...")
    server_proc = subprocess.Popen(
        components[0][1],
    )
    processes.append(("Shared State Server", server_proc))
    time.sleep(2)  # let server start

    # Start agents
    context_cmd = [PYTHON, str(KINESIS_DIR / "agents" / "context_agent.py")]
    body_cmd = [PYTHON, str(KINESIS_DIR / "agents" / "body_agent.py")]
    if args.replay_dataset:
        replay_path = _resolve_replay_dataset(args.replay_dataset)
        context_cmd.extend(["--replay-dataset", replay_path])
        body_cmd.extend(["--replay-dataset", replay_path])
    else:
        context_cmd.append("--demo")
        body_cmd.append("--demo")

    agent_commands = [
        ("Context Agent (Glasses)", context_cmd),
        ("Body Agent (Kinesess)", body_cmd),
        ("Planner Agent", [PYTHON, str(KINESIS_DIR / "agents" / "brain_agent.py")]),
    ]

    for name, cmd in agent_commands:
        logger.info("Starting %s...", name)
        proc = subprocess.Popen(
            cmd,
        )
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
        reported = set()
        while True:
            for name, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    if name not in reported:
                        reported.add(name)
                        logger.warning("%s exited with code %d", name, ret)

                    # Shared state server is foundational; stop everything if it dies.
                    if name == "Shared State Server":
                        raise RuntimeError("Shared State Server exited")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except RuntimeError as e:
        logger.error("%s", e)
        print("\nShutting down due to critical process exit...")
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
