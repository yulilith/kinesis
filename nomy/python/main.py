import argparse
import time

from agent import PostureAgent
from bridge import ESP32Bridge, MockBridge
from llm_reasoner import LLMReasoner
from logger import JsonlLogger
from state import AgentConfig
from tools import BodyTools


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use mock IMU stream instead of real ESP32")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port for ESP32")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM reasoning layer")
    parser.add_argument("--model", type=str, default="gpt-5-mini", help="OpenAI model name")
    parser.add_argument("--log-dir", type=str, default="logs", help="Directory for JSONL logs")
    args = parser.parse_args()

    logger = JsonlLogger(log_dir=args.log_dir)
    logger.log_event("run_started", {
        "mock": args.mock,
        "port": args.port,
        "llm_enabled": not args.no_llm,
        "model": args.model,
    })

    if args.mock:
        bridge = MockBridge()
        print("[Main] Using MockBridge")
    else:
        bridge = ESP32Bridge(port=args.port)
        print(f"[Main] Using ESP32Bridge on {args.port}")

    bridge.start_streaming()
    tools = BodyTools(bridge)

    print("[Main] Waiting for sensor warm-up...")
    time.sleep(2.0)

    print("[Main] Calibrating neutral baseline... Please stay in neutral posture.")
    baseline = tools.set_neutral_baseline(window_ms=1500)
    print(f"[Main] Baseline set: {baseline}")
    logger.log_event("baseline_set", baseline)

    llm_reasoner = None
    if not args.no_llm:
        llm_reasoner = LLMReasoner(model=args.model, enabled=True)
        print("[Main] LLM reasoning layer enabled")
        logger.log_event("llm_enabled", {"model": args.model})
    else:
        print("[Main] LLM reasoning layer disabled")
        logger.log_event("llm_disabled", {})

    config = AgentConfig(
        window_ms=1000,
        step_interval_sec=0.25,
        deviation_threshold_deg=10.0,
        min_stillness_score=0.55,
        confirm_steps=3,
        cooldown_sec=3.0,
        vibration_intensity=0.55,
        vibration_duration_ms=300,
    )
    logger.log_event("agent_config", {
        "window_ms": config.window_ms,
        "step_interval_sec": config.step_interval_sec,
        "deviation_threshold_deg": config.deviation_threshold_deg,
        "min_stillness_score": config.min_stillness_score,
        "confirm_steps": config.confirm_steps,
        "cooldown_sec": config.cooldown_sec,
        "vibration_intensity": config.vibration_intensity,
        "vibration_duration_ms": config.vibration_duration_ms,
    })

    agent = PostureAgent(
        tools,
        config=config,
        llm_reasoner=llm_reasoner,
        logger=logger,
    )

    try:
        while True:
            agent.step()
            time.sleep(config.step_interval_sec)
    except KeyboardInterrupt:
        print("\n[Main] Stopping...")
        logger.log_event("run_stopped", {"reason": "keyboard_interrupt"})
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()