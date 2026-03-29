#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <MPU6050.h>
#include <Wire.h>

// WiFi设置 - 请修改为你的网络
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";

// AI服务器设置 - 请修改为树莓派IP
const char* ai_server_ip = "192.168.1.100";
const int ai_server_port = 8080;

// 硬件引脚定义
#define LED_PIN 2
#define VIBRATION_PIN 4
#define EMS_PIN 5
#define BUTTON_PIN 0

// 传感器对象
MPU6050 imu;
WebSocketsClient webSocket;

// 数据缓冲区
struct PostureData {
    float accelX, accelY, accelZ;
    float gyroX, gyroY, gyroZ;
    float roll, pitch, yaw;
    unsigned long timestamp;
};

void setup() {
    Serial.begin(115200);
    Serial.println("🦞 Claw's ESP32 Agent Starting...");
    
    // 初始化引脚
    pinMode(LED_PIN, OUTPUT);
    pinMode(VIBRATION_PIN, OUTPUT);
    pinMode(EMS_PIN, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    
    // 初始化IMU
    Wire.begin();
    imu.initialize();
    if (imu.testConnection()) {
        Serial.println("✅ IMU连接成功");
    } else {
        Serial.println("❌ IMU连接失败");
    }
    
    // 连接WiFi
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(1000);
        Serial.println("正在连接WiFi...");
        digitalWrite(LED_PIN, !digitalRead(LED_PIN)); // LED闪烁表示连接中
    }
    digitalWrite(LED_PIN, HIGH); // 连接成功，LED常亮
    Serial.println("✅ WiFi连接成功: " + WiFi.localIP().toString());
    
    // 连接AI服务器
    webSocket.begin(ai_server_ip, ai_server_port, "/");
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
    
    Serial.println("🧠 我的大脑已就位，手脚开始工作！");
}

void loop() {
    webSocket.loop();
    
    // 读取姿态数据
    PostureData data;
    readPostureData(&data);
    
    // 发送给AI大脑
    sendPostureDataToAI(data);
    
    // 检查按钮输入
    if (digitalRead(BUTTON_PIN) == LOW) {
        Serial.println("用户按钮按下");
        webSocket.sendTXT("{\"event\":\"button_press\",\"timestamp\":" + String(millis()) + "}");
        delay(500); // 防抖
    }
    
    delay(100); // 10Hz采样率
}

void readPostureData(PostureData* data) {
    int16_t ax, ay, az, gx, gy, gz;
    imu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    
    // 转换为实际单位
    data->accelX = ax / 16384.0;  // ±2g范围
    data->accelY = ay / 16384.0;
    data->accelZ = az / 16384.0;
    data->gyroX = gx / 131.0;     // ±250°/s范围
    data->gyroY = gy / 131.0;
    data->gyroZ = gz / 131.0;
    
    // 计算欧拉角
    data->roll = atan2(data->accelY, data->accelZ) * 180.0 / PI;
    data->pitch = atan2(-data->accelX, sqrt(data->accelY * data->accelY + data->accelZ * data->accelZ)) * 180.0 / PI;
    data->yaw = 0; // 需要磁力计才能准确计算
    
    data->timestamp = millis();
}

void sendPostureDataToAI(PostureData data) {
    // 创建JSON数据
    DynamicJsonDocument doc(1024);
    doc["event"] = "posture_data";
    doc["timestamp"] = data.timestamp;
    doc["accel"]["x"] = data.accelX;
    doc["accel"]["y"] = data.accelY;
    doc["accel"]["z"] = data.accelZ;
    doc["gyro"]["x"] = data.gyroX;
    doc["gyro"]["y"] = data.gyroY;
    doc["gyro"]["z"] = data.gyroZ;
    doc["euler"]["roll"] = data.roll;
    doc["euler"]["pitch"] = data.pitch;
    doc["euler"]["yaw"] = data.yaw;
    
    String jsonString;
    serializeJson(doc, jsonString);
    webSocket.sendTXT(jsonString);
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            Serial.println("💔 与AI大脑断开连接");
            digitalWrite(LED_PIN, LOW);
            break;
            
        case WStype_CONNECTED:
            Serial.printf("❤️ 连接到AI大脑: %s\n", payload);
            digitalWrite(LED_PIN, HIGH);
            webSocket.sendTXT("{\"event\":\"agent_connected\",\"device\":\"esp32_posture_monitor\"}");
            break;
            
        case WStype_TEXT:
            Serial.printf("🧠 AI指令: %s\n", payload);
            processAICommand((char*)payload);
            break;
            
        case WStype_ERROR:
            Serial.printf("❌ WebSocket错误: %s\n", payload);
            break;
            
        default:
            break;
    }
}

void processAICommand(const char* command) {
    DynamicJsonDocument doc(512);
    deserializeJson(doc, command);
    
    String action = doc["action"];
    
    if (action == "vibrate") {
        int intensity = doc["intensity"] | 50;  // 默认50%强度
        int duration = doc["duration"] | 500;   // 默认500ms
        triggerVibration(intensity, duration);
        Serial.println("🔔 触发振动反馈");
        
    } else if (action == "ems") {
        int intensity = doc["intensity"] | 30;  // 默认30%强度
        int duration = doc["duration"] | 200;   // 默认200ms
        triggerEMS(intensity, duration);
        Serial.println("⚡ 触发EMS刺激");
        
    } else if (action == "led") {
        bool state = doc["state"] | false;
        digitalWrite(LED_PIN, state ? HIGH : LOW);
        Serial.println("💡 LED状态: " + String(state ? "开" : "关"));
        
    } else if (action == "alert") {
        String message = doc["message"];
        Serial.println("🚨 AI警告: " + message);
        alertPattern();
    }
}

void triggerVibration(int intensity, int duration) {
    int pwm_value = map(intensity, 0, 100, 0, 255);
    analogWrite(VIBRATION_PIN, pwm_value);
    delay(duration);
    analogWrite(VIBRATION_PIN, 0);
}

void triggerEMS(int intensity, int duration) {
    // ⚠️ 注意：EMS设备需要特殊电路和安全措施
    // 这里只是示例，实际使用需要专业医疗级EMS设备
    int pwm_value = map(intensity, 0, 100, 0, 128); // 限制最大强度
    analogWrite(EMS_PIN, pwm_value);
    delay(duration);
    analogWrite(EMS_PIN, 0);
    Serial.println("⚠️ 警告：请确保EMS设备安全性");
}

void alertPattern() {
    // LED闪烁 + 振动提醒
    for (int i = 0; i < 3; i++) {
        digitalWrite(LED_PIN, HIGH);
        analogWrite(VIBRATION_PIN, 100);
        delay(200);
        digitalWrite(LED_PIN, LOW);
        analogWrite(VIBRATION_PIN, 0);
        delay(200);
    }
    digitalWrite(LED_PIN, HIGH); // 恢复常亮状态
}