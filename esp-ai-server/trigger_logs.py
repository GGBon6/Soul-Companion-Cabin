#!/usr/bin/env python3
"""
触发ESP32语音处理日志的测试脚本
"""

import asyncio
import websockets
import json
import struct
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def trigger_speech_processing():
    try:
        uri = "ws://localhost:8767"
        logger.info(f"🔌 连接ESP32服务器: {uri}")
        
        async with websockets.connect(uri) as websocket:
            # 1. Hello握手
            hello = {
                "type": "hello",
                "version": 2,
                "features": {"mcp": True},
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 40
                }
            }
            
            await websocket.send(json.dumps(hello))
            response = await websocket.recv()
            logger.info("✅ Hello握手完成")
            
            # 2. 发送文本消息（这会触发意图处理和TTS）
            text_message = {
                "type": "text",
                "content": "你好，请说一句简短的问候语"
            }
            
            logger.info("📤 发送文本消息，触发AI回复...")
            await websocket.send(json.dumps(text_message))
            
            # 3. 等待响应
            logger.info("⏳ 等待AI处理和TTS音频...")
            
            timeout_count = 0
            while timeout_count < 15:  # 等待15秒
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    
                    if isinstance(response, str):
                        data = json.loads(response)
                        logger.info(f"📨 收到JSON: {data.get('type', 'unknown')}")
                        if data.get('type') == 'assistant_message':
                            logger.info(f"🤖 AI回复: {data.get('content', '')[:50]}...")
                    else:
                        logger.info(f"📨 收到TTS音频: {len(response)}字节")
                        # 解析音频包
                        if len(response) >= 12:
                            version, msg_type, timestamp, payload_size = struct.unpack('>HHII', response[:12])
                            logger.info(f"   音频包: 版本={version}, 类型={msg_type}, 负载={payload_size}字节")
                    
                except asyncio.TimeoutError:
                    timeout_count += 1
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break
            
            logger.info("🏁 测试完成")
            
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_speech_processing())
