#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>

Adafruit_MPU6050 mpu;

const int VIBRATION_PIN = 4;   // 修改成你的接线
const int SAMPLE_INTERVAL_MS = 40;  // ~25Hz

unsigned long lastSampleTime = 0;
unsigned long vibrationEndTime = 0;
bool vibrating = false;

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(VIBRATION_PIN, OUTPUT);
  digitalWrite(VIBRATION_PIN, LOW);

  Wire.begin();

  if (!mpu.begin()) {
    Serial.println("{\"type\":\"error\",\"message\":\"MPU6050 not found\"}");
    while (1) {
      delay(1000);
    }
  }

  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  Serial.println("{\"type\":\"status\",\"message\":\"esp32_ready\"}");
}

void loop() {
  unsigned long now = millis();

  handleSerialCommands();

  if (vibrating && now >= vibrationEndTime) {
    digitalWrite(VIBRATION_PIN, LOW);
    vibrating = false;
  }

  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;
    sendIMUFrame();
  }
}

void sendIMUFrame() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  StaticJsonDocument<256> doc;
  doc["type"] = "imu";
  doc["ts"] = millis();
  doc["ax"] = a.acceleration.x;
  doc["ay"] = a.acceleration.y;
  doc["az"] = a.acceleration.z;
  doc["gx"] = g.gyro.x;
  doc["gy"] = g.gyro.y;
  doc["gz"] = g.gyro.z;
  doc["temp"] = temp.temperature;

  serializeJson(doc, Serial);
  Serial.println();
}

void handleSerialCommands() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    return;
  }

  const char* cmd = doc["cmd"];
  if (!cmd) return;

  if (String(cmd) == "vibrate") {
    int duration_ms = doc["duration_ms"] | 300;
    int pwm = doc["pwm"] | 255;

    analogWrite(VIBRATION_PIN, pwm);
    vibrating = true;
    vibrationEndTime = millis() + duration_ms;

    StaticJsonDocument<128> ack;
    ack["type"] = "ack";
    ack["cmd"] = "vibrate";
    ack["duration_ms"] = duration_ms;
    serializeJson(ack, Serial);
    Serial.println();
  } else if (String(cmd) == "stop_vibration") {
    digitalWrite(VIBRATION_PIN, LOW);
    vibrating = false;

    StaticJsonDocument<128> ack;
    ack["type"] = "ack";
    ack["cmd"] = "stop_vibration";
    serializeJson(ack, Serial);
    Serial.println();
  }
}