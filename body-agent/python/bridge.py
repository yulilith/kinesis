# 这个文件负责串口通信、缓存最近的 IMU 数据，以及发送 vibration 命令。
# 它也内置了一个 MockBridge，这样即使你还没接硬件，也可以先跑通 agent。
import json
import math
import random
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional

try:
    import serial
except ImportError:
    serial = None


class ESP32Bridge:
    def __init__(self, port: str, baudrate: int = 115200, max_buffer_size: int = 5000):
        if serial is None:
            raise ImportError("pyserial is required. Install with: pip install pyserial")

        self.port = port
        self.baudrate = baudrate
        self.ser = serial.Serial(port, baudrate, timeout=0.1)
        self.buffer: Deque[Dict] = deque(maxlen=max_buffer_size)
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start_streaming(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()

    def _reader_loop(self) -> None:
        while self.running:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                msg = json.loads(line)

                if msg.get("type") == "imu":
                    msg["host_time"] = time.time()
                    self.buffer.append(msg)
                else:
                    print(f"[ESP32] {msg}")
            except Exception as e:
                print(f"[Bridge read error] {e}")
                time.sleep(0.05)

    def get_recent_frames(self, window_ms: int = 1000) -> List[Dict]:
        cutoff = time.time() - (window_ms / 1000.0)
        return [frame for frame in self.buffer if frame.get("host_time", 0) >= cutoff]

    def send_vibration_command(self, intensity: float = 0.5, duration_ms: int = 300, pattern: str = "single_pulse") -> None:
        pwm = max(0, min(255, int(intensity * 255)))
        cmd = {
            "cmd": "vibrate",
            "duration_ms": duration_ms,
            "pwm": pwm,
            "pattern": pattern,
        }
        self._send_json(cmd)

    def stop_vibration(self) -> None:
        self._send_json({"cmd": "stop_vibration"})

    def _send_json(self, payload: Dict) -> None:
        try:
            line = json.dumps(payload) + "\n"
            self.ser.write(line.encode("utf-8"))
        except Exception as e:
            print(f"[Bridge write error] {e}")


class MockBridge:
    """
    没有硬件时用这个先跑通。
    默认模拟：前几秒正常，之后逐渐前倾，触发 agent。
    """

    def __init__(self, max_buffer_size: int = 5000):
        self.buffer: Deque[Dict] = deque(maxlen=max_buffer_size)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = time.time()

    def start_streaming(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._simulate_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _simulate_loop(self) -> None:
        while self.running:
            now = time.time()
            t = now - self.start_time

            # 简单模拟：6秒后开始“持续驼背”
            tilt_deg = 2.0 if t < 6 else min(20.0, 2.0 + (t - 6) * 2.5)

            # 反推一个简化加速度方向（只做 demo）
            rad = math.radians(tilt_deg)
            ax = 9.81 * math.sin(rad) + random.uniform(-0.1, 0.1)
            ay = random.uniform(-0.15, 0.15)
            az = 9.81 * math.cos(rad) + random.uniform(-0.1, 0.1)

            gx = random.uniform(-0.03, 0.03)
            gy = random.uniform(-0.03, 0.03)
            gz = random.uniform(-0.03, 0.03)

            frame = {
                "type": "imu",
                "ts": int(t * 1000),
                "ax": ax,
                "ay": ay,
                "az": az,
                "gx": gx,
                "gy": gy,
                "gz": gz,
                "host_time": now,
            }
            self.buffer.append(frame)
            time.sleep(0.04)  # ~25Hz

    def get_recent_frames(self, window_ms: int = 1000) -> List[Dict]:
        cutoff = time.time() - (window_ms / 1000.0)
        return [frame for frame in self.buffer if frame.get("host_time", 0) >= cutoff]

    def send_vibration_command(self, intensity: float = 0.5, duration_ms: int = 300, pattern: str = "single_pulse") -> None:
        print(f"[MOCK VIBRATION] intensity={intensity:.2f}, duration={duration_ms}ms, pattern={pattern}")

    def stop_vibration(self) -> None:
        print("[MOCK VIBRATION] stop")