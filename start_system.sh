#!/bin/bash
echo "🦞 启动 Claw 姿态监控系统"
echo ""

# 检查Python依赖
echo "检查系统依赖..."
python3 -c "import websockets, numpy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ 缺少Python依赖，请运行 ./install_dependencies.sh"
    exit 1
fi

# 检查AI服务器文件
if [ ! -f "ai_posture_server.py" ]; then
    echo "❌ 找不到 ai_posture_server.py 文件"
    exit 1
fi

echo "✅ 依赖检查完成"
echo ""

# 显示网络信息
echo "📡 网络信息："
hostname -I | awk '{print "   IP地址: " $1}'
echo "   端口: 8080"
echo ""

echo "🚀 启动AI姿态监控服务器..."
echo "   (按 Ctrl+C 停止服务器)"
echo ""
echo "📋 后续步骤："
echo "1. 确保ESP32已连接并配置正确的IP地址"
echo "2. 上传 esp32_agent.ino 到ESP32"
echo "3. 或运行测试: python3 test_system.py"
echo ""
echo "🦞" | figlet 2>/dev/null || echo "🦞 Claw AI System Starting..."

python3 ai_posture_server.py