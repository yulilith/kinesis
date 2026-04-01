#!/usr/bin/env python3
"""
🦞 Claw的AI姿态监控服务器
接收ESP32数据，分析姿态，发送反馈指令
"""

import asyncio
import websockets
import json
import numpy as np
from datetime import datetime
import logging
from typing import Dict, List, Optional

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - 🦞 - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PostureAnalyzer:
    """AI姿态分析器"""
    
    def __init__(self):
        self.posture_history: List[Dict] = []
        self.alert_thresholds = {
            'slouch_angle': 30,      # 驼背角度阈值
            'tilt_angle': 15,        # 侧倾角度阈值
            'sitting_time': 1800,    # 久坐时间阈值(秒)
            'movement_threshold': 2   # 运动检测阈值
        }
        self.current_state = {
            'is_sitting': False,
            'sitting_start': None,
            'last_movement': datetime.now(),
            'posture_score': 100
        }
        
    def analyze_posture(self, data: Dict) -> Dict:
        """分析姿态数据，返回判断结果"""
        try:
            # 提取传感器数据
            accel = data['accel']
            gyro = data['gyro']
            euler = data['euler']
            
            # 检测当前姿态
            analysis = {
                'timestamp': data['timestamp'],
                'alerts': [],
                'score': 100,
                'recommendations': []
            }
            
            # 1. 检测驼背
            if abs(euler['pitch']) > self.alert_thresholds['slouch_angle']:
                analysis['alerts'].append({
                    'type': 'slouching',
                    'severity': 'high' if abs(euler['pitch']) > 45 else 'medium',
                    'message': f"检测到驼背！前倾角度: {euler['pitch']:.1f}°"
                })
                analysis['score'] -= 20
                analysis['recommendations'].append("请坐直，肩膀向后")
                
            # 2. 检测侧倾
            if abs(euler['roll']) > self.alert_thresholds['tilt_angle']:
                analysis['alerts'].append({
                    'type': 'tilting',
                    'severity': 'medium',
                    'message': f"身体侧倾！角度: {euler['roll']:.1f}°"
                })
                analysis['score'] -= 10
                analysis['recommendations'].append("调整身体位置，保持平衡")
                
            # 3. 检测久坐
            self._update_sitting_status(accel, gyro)
            if self.current_state['is_sitting'] and self.current_state['sitting_start']:
                sitting_duration = (datetime.now() - self.current_state['sitting_start']).seconds
                if sitting_duration > self.alert_thresholds['sitting_time']:
                    analysis['alerts'].append({
                        'type': 'prolonged_sitting',
                        'severity': 'high',
                        'message': f"久坐警告！已坐 {sitting_duration//60} 分钟"
                    })
                    analysis['score'] -= 15
                    analysis['recommendations'].append("起来活动一下吧！")
                    
            # 4. 检测缺乏运动
            movement_intensity = np.sqrt(gyro['x']**2 + gyro['y']**2 + gyro['z']**2)
            if movement_intensity < self.alert_thresholds['movement_threshold']:
                time_since_movement = (datetime.now() - self.current_state['last_movement']).seconds
                if time_since_movement > 600:  # 10分钟无运动
                    analysis['alerts'].append({
                        'type': 'low_activity',
                        'severity': 'low',
                        'message': "长时间无活动检测"
                    })
            else:
                self.current_state['last_movement'] = datetime.now()
                
            # 更新历史记录
            self.posture_history.append(analysis)
            if len(self.posture_history) > 1000:  # 保留最近1000条记录
                self.posture_history = self.posture_history[-1000:]
                
            self.current_state['posture_score'] = analysis['score']
            
            logger.info(f"姿态分析完成 - 评分: {analysis['score']}, 警告数: {len(analysis['alerts'])}")
            return analysis
            
        except Exception as e:
            logger.error(f"姿态分析错误: {e}")
            return {'error': str(e)}
    
    def _update_sitting_status(self, accel: Dict, gyro: Dict):
        """更新坐姿状态"""
        # 简单的坐姿检测逻辑：垂直加速度接近1g且运动幅度小
        vertical_accel = abs(accel['z'])
        movement_intensity = np.sqrt(gyro['x']**2 + gyro['y']**2 + gyro['z']**2)
        
        is_sitting_now = (0.8 < vertical_accel < 1.2) and (movement_intensity < 5)
        
        if is_sitting_now and not self.current_state['is_sitting']:
            # 开始坐下
            self.current_state['is_sitting'] = True
            self.current_state['sitting_start'] = datetime.now()
            logger.info("检测到开始坐姿")
        elif not is_sitting_now and self.current_state['is_sitting']:
            # 站起来了
            self.current_state['is_sitting'] = False
            sitting_duration = (datetime.now() - self.current_state['sitting_start']).seconds
            logger.info(f"检测到结束坐姿，持续了 {sitting_duration} 秒")
            self.current_state['sitting_start'] = None
    
    def generate_feedback(self, analysis: Dict) -> Dict:
        """根据分析结果生成反馈指令"""
        feedback = {'actions': []}
        
        for alert in analysis.get('alerts', []):
            if alert['type'] == 'slouching':
                if alert['severity'] == 'high':
                    # 强烈振动提醒
                    feedback['actions'].append({
                        'action': 'vibrate',
                        'intensity': 80,
                        'duration': 1000
                    })
                else:
                    # 轻柔振动提醒
                    feedback['actions'].append({
                        'action': 'vibrate',
                        'intensity': 50,
                        'duration': 500
                    })
                    
            elif alert['type'] == 'tilting':
                # LED警告
                feedback['actions'].append({
                    'action': 'led',
                    'state': True
                })
                
            elif alert['type'] == 'prolonged_sitting':
                # 组合提醒：EMS + 振动
                feedback['actions'].append({
                    'action': 'ems',
                    'intensity': 25,
                    'duration': 300
                })
                feedback['actions'].append({
                    'action': 'alert',
                    'message': '该起来活动了！'
                })
                
        return feedback

class ClawPostureServer:
    """Claw的WebSocket服务器"""
    
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.analyzer = PostureAnalyzer()
        self.connected_clients = set()
        
    async def register_client(self, websocket):
        """注册新客户端"""
        self.connected_clients.add(websocket)
        logger.info(f"新的ESP32代理连接: {websocket.remote_address}")
        
    async def unregister_client(self, websocket):
        """注销客户端"""
        self.connected_clients.discard(websocket)
        logger.info(f"ESP32代理断开连接: {websocket.remote_address}")
        
    async def handle_client(self, websocket, path):
        """处理客户端连接"""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                await self.process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("客户端连接关闭")
        finally:
            await self.unregister_client(websocket)
            
    async def process_message(self, websocket, message):
        """处理收到的消息"""
        try:
            data = json.loads(message)
            event_type = data.get('event', 'unknown')
            
            if event_type == 'posture_data':
                # 处理姿态数据
                analysis = self.analyzer.analyze_posture(data)
                
                if 'error' not in analysis:
                    # 生成反馈
                    feedback = self.analyzer.generate_feedback(analysis)
                    
                    # 发送反馈给ESP32
                    for action in feedback.get('actions', []):
                        await websocket.send(json.dumps(action))
                        
                    # 如果有重要警告，记录日志
                    high_severity_alerts = [a for a in analysis.get('alerts', []) if a.get('severity') == 'high']
                    if high_severity_alerts:
                        logger.warning(f"高严重性姿态警告: {[a['message'] for a in high_severity_alerts]}")
                        
            elif event_type == 'button_press':
                logger.info("用户按钮交互")
                # 可以添加按钮交互逻辑
                
            elif event_type == 'agent_connected':
                logger.info(f"AI代理已连接: {data.get('device', 'unknown')}")
                # 发送欢迎消息
                await websocket.send(json.dumps({
                    'action': 'alert',
                    'message': '🦞 Claw的AI大脑已连接！'
                }))
                
        except json.JSONDecodeError:
            logger.error(f"无效的JSON消息: {message}")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def start_server(self):
        """启动服务器"""
        logger.info(f"🦞 Claw的AI姿态监控服务器启动中...")
        logger.info(f"监听地址: {self.host}:{self.port}")
        
        server = await websockets.serve(self.handle_client, self.host, self.port)
        logger.info("✅ 服务器启动成功！等待ESP32代理连接...")
        
        try:
            await server.wait_closed()
        except KeyboardInterrupt:
            logger.info("服务器关闭中...")
            server.close()
            await server.wait_closed()
            logger.info("🦞 再见！")

def main():
    """主函数"""
    print("🦞" * 20)
    print("   Claw的AI姿态监控系统")  
    print("🦞" * 20)
    
    server = ClawPostureServer()
    
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\n👋 拜拜！")

if __name__ == "__main__":
    main()