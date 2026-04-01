#!/bin/bash
echo "🦞 Claw的姿态监控系统 - 依赖安装脚本"

# 更新系统
echo "更新系统包..."
sudo apt update

# 安装Python依赖
echo "安装Python依赖..."
pip3 install websockets numpy

# 安装Arduino IDE (如果还没有)
if ! command -v arduino &> /dev/null; then
    echo "安装Arduino IDE..."
    sudo apt install -y arduino
fi

# 创建用户组权限
echo "配置USB权限..."
sudo usermod -a -G dialout $USER

echo "✅ 依赖安装完成！"
echo ""
echo "📋 后续步骤："
echo "1. 重启终端或注销重新登录以应用权限更改"
echo "2. 在Arduino IDE中安装以下库："
echo "   - WebSockets by Markus Sattler"
echo "   - ArduinoJson by Benoit Blanchon"  
echo "   - MPU6050 by Electronic Cats"
echo "3. 修改esp32_agent.ino中的WiFi设置"
echo "4. 上传代码到ESP32"
echo "5. 运行AI服务器: python3 ai_posture_server.py"