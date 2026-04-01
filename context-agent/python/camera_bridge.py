import cv2
import threading
import time
from typing import Optional


class CameraBridge:
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap = None
        self.running = False
        self.thread = None
        self.latest_frame = None
        self.latest_ts = 0.0

    def start(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera {self.camera_index}")

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                self.latest_frame = frame
                self.latest_ts = time.time()
            time.sleep(0.03)

    def get_latest_frame(self):
        return self.latest_frame, self.latest_ts

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()


class MockCameraBridge:
    """
    没有真实 camera 时先跑通。
    通过时间切换不同 context label。
    """
    def __init__(self):
        self.start_time = time.time()

    def start(self):
        pass

    def get_latest_frame(self):
        return None, time.time()

    def get_mock_context(self):
        t = time.time() - self.start_time
        if t < 10:
            return "desk_work"
        if t < 20:
            return "walking"
        if t < 30:
            return "kitchen"
        return "desk_work"

    def stop(self):
        pass