#include <Wire.h>
#include <ArduinoJson.h>

// --- Pin & config ---
const int VIBRATION_PIN = 4;
const int SAMPLE_INTERVAL_MS = 40;  // ~25Hz

// Two MPU6050s on the same I2C bus:
//   upper_back: AD0 → GND  → 0x68
//   lower_back: AD0 → 3.3V → 0x69
const int NUM_IMUS = 2;
const int IMU_ADDRS[NUM_IMUS] = {0x68, 0x69};
const char* IMU_LABELS[NUM_IMUS] = {"upper_back", "lower_back"};
bool imuAlive[NUM_IMUS] = {false, false};

unsigned long lastSampleTime = 0;
unsigned long vibrationEndTime = 0;
bool vibrating = false;

// --- MPU6050 helpers ---

bool mpuInit(int addr) {
  // Check if device responds
  Wire.beginTransmission(addr);
  if (Wire.endTransmission() != 0) return false;

  // Wake up
  Wire.beginTransmission(addr);
  Wire.write(0x6B);
  Wire.write(0);
  Wire.endTransmission();
  delay(100);

  // ±4g accel range
  Wire.beginTransmission(addr);
  Wire.write(0x1C);
  Wire.write(0x08);
  Wire.endTransmission();

  // ±500°/s gyro range
  Wire.beginTransmission(addr);
  Wire.write(0x1B);
  Wire.write(0x08);
  Wire.endTransmission();

  // 21Hz low-pass filter
  Wire.beginTransmission(addr);
  Wire.write(0x1A);
  Wire.write(0x04);
  Wire.endTransmission();

  return true;
}

bool mpuRead(int addr, float &ax, float &ay, float &az,
             float &gx, float &gy, float &gz, float &temp) {
  Wire.beginTransmission(addr);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  int n = Wire.requestFrom(addr, 14);
  if (n < 14) return false;

  int16_t raw_ax = (Wire.read() << 8) | Wire.read();
  int16_t raw_ay = (Wire.read() << 8) | Wire.read();
  int16_t raw_az = (Wire.read() << 8) | Wire.read();
  int16_t raw_t  = (Wire.read() << 8) | Wire.read();
  int16_t raw_gx = (Wire.read() << 8) | Wire.read();
  int16_t raw_gy = (Wire.read() << 8) | Wire.read();
  int16_t raw_gz = (Wire.read() << 8) | Wire.read();

  ax = raw_ax / 8192.0 * 9.81;
  ay = raw_ay / 8192.0 * 9.81;
  az = raw_az / 8192.0 * 9.81;
  gx = raw_gx / 65.5 * 0.01745;
  gy = raw_gy / 65.5 * 0.01745;
  gz = raw_gz / 65.5 * 0.01745;
  temp = raw_t / 340.0 + 36.53;
  return true;
}

// ----------------------------------

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(VIBRATION_PIN, OUTPUT);
  digitalWrite(VIBRATION_PIN, LOW);

  Wire.begin();
  delay(250);

  for (int i = 0; i < NUM_IMUS; i++) {
    imuAlive[i] = mpuInit(IMU_ADDRS[i]);
    StaticJsonDocument<128> doc;
    doc["type"]   = "debug";
    doc["sensor"] = IMU_LABELS[i];
    doc["addr"]   = String("0x") + String(IMU_ADDRS[i], HEX);
    doc["status"] = imuAlive[i] ? "ok" : "not found";
    serializeJson(doc, Serial);
    Serial.println();
  }

  Serial.println("{\"type\":\"status\",\"message\":\"esp32_ready\"}");
}

void loop() {
  unsigned long now = millis();

  handleSerialCommands();

  if (vibrating && now >= vibrationEndTime) {
    analogWrite(VIBRATION_PIN, 0);
    vibrating = false;
  }

  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;
    sendAllIMUFrames();
  }
}

void sendAllIMUFrames() {
  unsigned long ts = millis();

  for (int i = 0; i < NUM_IMUS; i++) {
    if (!imuAlive[i]) continue;

    float ax, ay, az, gx, gy, gz, temp;
    if (!mpuRead(IMU_ADDRS[i], ax, ay, az, gx, gy, gz, temp)) continue;

    StaticJsonDocument<320> doc;
    doc["type"]   = "imu";
    doc["sensor"] = IMU_LABELS[i];
    doc["ts"]     = ts;
    doc["ax"]     = ax;
    doc["ay"]     = ay;
    doc["az"]     = az;
    doc["gx"]     = gx;
    doc["gy"]     = gy;
    doc["gz"]     = gz;
    doc["temp"]   = temp;

    serializeJson(doc, Serial);
    Serial.println();
  }
}

void handleSerialCommands() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) return;

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
    ack["cmd"]  = "vibrate";
    ack["duration_ms"] = duration_ms;
    serializeJson(ack, Serial);
    Serial.println();

  } else if (String(cmd) == "stop_vibration") {
    analogWrite(VIBRATION_PIN, 0);
    vibrating = false;

    StaticJsonDocument<128> ack;
    ack["type"] = "ack";
    ack["cmd"]  = "stop_vibration";
    serializeJson(ack, Serial);
    Serial.println();
  }
}
