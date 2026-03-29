# Kinesess Proto

A minimal embodied posture-agent MVP using:

- ESP32
- IMU sensor
- vibration motor
- Python agent runtime

## What it does

The ESP32 streams IMU data in real time.
The Python agent reads recent windows of motion data, estimates simple posture deviation, and triggers vibration feedback when sustained bad posture is detected.

## Install

```bash
pip install pyserial
```
