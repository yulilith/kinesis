#!/usr/bin/env python3
"""
🦞 Claw姿态监控系统测试脚本
用于验证AI服务器和通信功能
"""

import asyncio
import websockets
import json
import random
import time
from datetime import datetime

async def simulate_esp32_client():
    """模拟ESP32客户端发送测试数据"""
    uri = "ws://localhost:8080"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("🦞 测试客户端已连接到AI服务器")
            
            # 发送连接确认
            await websocket.send(json.dumps({
                "event": "agent_connected",
                "device": "test_esp32_simulator"
            }))
            
            # 接收欢迎消息
            response = await websocket.recv()
            print(f"📨 收到AI回应: {response}")
            
            # 模拟不同的姿态数据场景
            test_scenarios = [
                {"name": "正常坐姿", "pitch": 5, "roll": 2, "movement": 1.5},
                {"name": "轻微驼背", "pitch": 25, "roll": 3, "movement": 0.8},
                {"name": "严重驼背", "pitch": 45, "roll": 5, "movement": 0.5},
                {"name": "身体左倾", "pitch": 8, "roll": 20, "movement": 1.2},
                {"name": "身体右倾", "pitch": 6, "roll": -18, "movement": 1.0},
                {"name": "活动状态", "pitch": 15, "roll": 8, "movement": 8.5},
            ]
            
            for scenario in test_scenarios:
                print(f"\n🎭 测试场景: {scenario['name']}")
                
                # 发送模拟数据
                test_data = generate_test_data(scenario)
                await websocket.send(json.dumps(test_data))
                
                # 等待AI分析和反馈
                try:
                    feedback = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    feedback_data = json.loads(feedback)
                    print(f"🤖 AI反馈: {feedback_data}")
                    
                    # 模拟执行反馈动作
                    action = feedback_data.get('action', 'none')
                    if action == 'vibrate':
                        print(f"📳 模拟振动: 强度{feedback_data.get('intensity', 50)}%, 持续{feedback_data.get('duration', 500)}ms")
                    elif action == 'ems':
                        print(f"⚡ 模拟EMS刺激: 强度{feedback_data.get('intensity', 30)}%, 持续{feedback_data.get('duration', 200)}ms")
                    elif action == 'led':
                        print(f"💡 模拟LED: {'开启' if feedback_data.get('state') else '关闭'}")
                    elif action == 'alert':
                        print(f"🚨 模拟警告: {feedback_data.get('message', '无消息')}")
                        
                except asyncio.TimeoutError:
                    print("⏰ 无AI反馈 (可能姿态正常)")
                
                await asyncio.sleep(1)  # 间隔1秒
            
            print(f"\n✅ 测试完成！共测试了{len(test_scenarios)}个场景")
            
            # 测试按钮交互
            print("\n🔘 测试按钮交互...")
            await websocket.send(json.dumps({
                "event": "button_press",
                "timestamp": int(time.time() * 1000)
            }))
            
            try:
                button_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"🔘 按钮反馈: {button_response}")
            except asyncio.TimeoutError:
                print("🔘 按钮无特殊反馈")
                
    except ConnectionRefusedError:
        print("❌ 无法连接到AI服务器")
        print("请确保已启动 ai_posture_server.py")
    except Exception as e:
        print(f"❌ 测试出错: {e}")

def generate_test_data(scenario):
    """生成测试用的传感器数据"""
    # 基础传感器数据
    base_data = {
        "event": "posture_data",
        "timestamp": int(time.time() * 1000),
        "accel": {
            "x": random.uniform(-0.2, 0.2),
            "y": random.uniform(-0.2, 0.2), 
            "z": random.uniform(0.8, 1.2)  # 模拟重力
        },
        "gyro": {
            "x": random.uniform(-scenario['movement'], scenario['movement']),
            "y": random.uniform(-scenario['movement'], scenario['movement']),
            "z": random.uniform(-scenario['movement'], scenario['movement'])
        },
        "euler": {
            "roll": scenario['roll'] + random.uniform(-2, 2),
            "pitch": scenario['pitch'] + random.uniform(-2, 2),
            "yaw": random.uniform(-5, 5)
        }
    }
    return base_data

def print_welcome():
    """打印欢迎信息"""
    print("🦞" * 30)
    print("  Claw姿态监控系统 - 测试工具")
    print("🦞" * 30)
    print()
    print("这个测试工具会：")
    print("📊 模拟ESP32发送各种姿态数据")
    print("🤖 验证AI分析和反馈功能")  
    print("🔍 检查系统各组件是否正常工作")
    print()
    print("⚠️  请确保AI服务器已启动 (python3 ai_posture_server.py)")
    print()

async def main():
    """主测试函数"""
    print_welcome()
    
    print("🚀 开始系统测试...")
    await simulate_esp32_client()
    print("\n👋 测试结束，感谢使用Claw系统！")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 测试中断，再见！")