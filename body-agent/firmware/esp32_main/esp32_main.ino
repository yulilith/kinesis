#include <Wire.h>
#include <ArduinoJson.h>

const int VIBRATION_PIN = 4;
const int SAMPLE_INTERVAL_MS = 40;  // ~25Hz
const int MPU_ADDR = 0x68;

unsigned long lastSampleTime = 0;
unsigned long vibrationEndTime = 0;
bool vibrating = false;

// --- MPU6050 direct I2C helpers ---

void mpuWrite(byte reg, byte value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool mpuInit() {
  // Wake up MPU6050 (clear sleep bit)
  mpuWrite(0x6B, 0x00);
  delay(100);

  // Set accelerometer range to ±4g (register 0x1C, value 0x08)
  mpuWrite(0x1C, 0x08);
  // Set gyro range to ±500°/s (register 0x1B, value 0x08)
  mpuWrite(0x1B, 0x08);
  // Set DLPF bandwidth ~21Hz (register 0x1A, value 0x04)
  mpuWrite(0x1A, 0x04);

  // Read WHO_AM_I just for debug, don't fail on unexpected value
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x75);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 1);
  byte whoami = Wire.available() ? Wire.read() : 0xFF;
  Serial.print("{\"type\":\"debug\",\"who_am_i\":\"0x");
  Serial.print(whoami, HEX);
  Serial.println("\"}");

  return true;  // always continue regardless of WHO_AM_I
}

void mpuRead(float &ax, float &ay, float &az, float &gx, float &gy, float &gz, float &temp) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);  // starting register: ACCEL_XOUT_H
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 14);

  int16_t raw_ax = (Wire.read() << 8) | Wire.read();
  int16_t raw_ay = (Wire.read() << 8) | Wire.read();
  int16_t raw_az = (Wire.read() << 8) | Wire.read();
  int16_t raw_t  = (Wire.read() << 8) | Wire.read();
  int16_t raw_gx = (Wire.read() << 8) | Wire.read();
  int16_t raw_gy = (Wire.read() << 8) | Wire.read();
  int16_t raw_gz = (Wire.read() << 8) | Wire.read();

  // ±4g range: sensitivity = 8192 LSB/g
  ax = raw_ax / 8192.0 * 9.81;
  ay = raw_ay / 8192.0 * 9.81;
  az = raw_az / 8192.0 * 9.81;

  // ±500°/s range: sensitivity = 65.5 LSB/(°/s), convert to rad/s
  gx = raw_gx / 65.5 * (3.14159 / 180.0);
  gy = raw_gy / 65.5 * (3.14159 / 180.0);
  gz = raw_gz / 65.5 * (3.14159 / 180.0);

  temp = raw_t / 340.0 + 36.53;
}

// ----------------------------------

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(VIBRATION_PIN, OUTPUT);
  digitalWrite(VIBRATION_PIN, LOW);

  Wire.begin();
  delay(250);

  if (!mpuInit()) {
    Serial.println("{\"type\":\"error\",\"message\":\"MPU6050 not found\"}");
    while (1) { delay(1000); }
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
    sendIMUFrame();
  }
}

void sendIMUFrame() {
  float ax, ay, az, gx, gy, gz, temp;
  mpuRead(ax, ay, az, gx, gy, gz, temp);

  StaticJsonDocument<256> doc;
  doc["type"] = "imu";
  doc["ts"]   = millis();
  doc["ax"]   = ax;
  doc["ay"]   = ay;
  doc["az"]   = az;
  doc["gx"]   = gx;
  doc["gy"]   = gy;
  doc["gz"]   = gz;
  doc["temp"] = temp;

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
