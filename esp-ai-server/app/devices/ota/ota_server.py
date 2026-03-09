"""
OTA服务器
OTA Server
为ESP32设备提供固件版本检查和WebSocket配置
"""

import json
from aiohttp import web
from app.core import settings, logger


class OtaServer:
    """OTA服务器处理器"""
    
    def __init__(self):
        """初始化OTA服务器"""
        # 获取WebSocket服务器地址
        # 从环境变量或配置中获取，默认使用当前服务器
        self.websocket_host = settings.HOST
        self.websocket_port = settings.PORT
        
        # 如果HOST是0.0.0.0，需要获取实际IP
        if self.websocket_host == "0.0.0.0":
            # 尝试获取本机IP
            import socket
            try:
                # 连接到外部地址以获取本机IP
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                self.websocket_host = s.getsockname()[0]
                s.close()
            except Exception:
                # 如果获取失败，使用默认值（需要手动配置）
                self.websocket_host = "192.168.5.73"  # 从之前的ipconfig结果
                logger.warning(f"无法自动获取IP，使用默认值: {self.websocket_host}")
        
        self.websocket_url = f"ws://{self.websocket_host}:{self.websocket_port}"
        logger.info(f"📡 OTA服务器配置: WebSocket地址 = {self.websocket_url}")
    
    async def handle_ota_request(self, request: web.Request) -> web.Response:
        """处理OTA请求"""
        try:
            # 获取请求头
            device_id = request.headers.get("Device-Id", "unknown")
            client_id = request.headers.get("Client-Id", "unknown")
            user_agent = request.headers.get("User-Agent", "unknown")
            
            logger.info(f"📥 OTA请求来自设备: {device_id} (Client: {client_id})")
            
            # 读取请求体（如果有）
            body_data = {}
            if request.method == "POST":
                try:
                    body_text = await request.text()
                    if body_text:
                        body_data = json.loads(body_text)
                        logger.debug(f"请求体: {body_data}")
                except Exception as e:
                    logger.warning(f"解析请求体失败: {e}")
            
            # 构建响应
            response_data = {
                # 不返回固件升级信息（保持当前版本）
                "websocket": {
                    "url": self.websocket_url,
                    "version": 2  # 协议版本
                }
            }
            
            # 如果需要激活，可以添加activation字段
            # 如果不需要激活，可以省略activation字段，设备会自动跳过激活流程
            
            logger.info(f"📤 返回配置: WebSocket = {self.websocket_url}")
            
            return web.Response(
                text=json.dumps(response_data, ensure_ascii=False),
                content_type="application/json",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Device-Id, Client-Id, User-Agent"
                }
            )
            
        except Exception as e:
            logger.error(f"处理OTA请求失败: {e}", exc_info=True)
            return web.Response(
                text=json.dumps({"error": "Internal server error"}),
                status=500,
                content_type="application/json"
            )
    
    async def handle_options(self, request: web.Request) -> web.Response:
        """处理CORS预检请求"""
        return web.Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Device-Id, Client-Id, User-Agent"
            }
        )


# 全局OTA服务器实例
_ota_server = None

def get_ota_server() -> OtaServer:
    """获取OTA服务器单例"""
    global _ota_server
    if _ota_server is None:
        _ota_server = OtaServer()
    return _ota_server

