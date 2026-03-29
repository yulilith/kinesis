# 程序入口。先校准 baseline，然后开始 agent loop。
# 你可以用硬件串口，也可以先用 mock 跑通。

import argparse
import time

from agent import PostureAgent
from bridge import ESP32Bridge, MockBridge
from state import AgentConfig
from tools import BodyTools


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use mock IMU stream instead of real ESP32")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port for ESP32")
    args = parser.parse_args()

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
    agent = PostureAgent(tools, config=config)

    try:
        while True:
            agent.step()
            time.sleep(config.step_interval_sec)
    except KeyboardInterrupt:
        print("\n[Main] Stopping...")
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()