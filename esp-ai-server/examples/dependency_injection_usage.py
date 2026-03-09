"""
依赖注入使用示例 - 无全局单例
Dependency Injection Usage Examples - No Global Singletons
"""
import asyncio
from app.core.application import create_app, ApplicationConfig


# ==================== 示例1: WebSocket处理器（推荐方式）====================

class WebSocketHandler:
    """WebSocket处理器 - 通过构造函数注入应用实例"""
    
    def __init__(self, app):
        """
        构造函数注入
        
        Args:
            app: 应用实例
        """
        self.app = app
    
    async def handle_esp32_message(self, message: str, user_id: str):
        """处理ESP32设备消息"""
        # 从注入的应用实例获取服务
        llm_service = await self.app.get_llm_service('esp32')
        
        response = await llm_service.chat_async(
            messages=[{"role": "user", "content": message}],
            user_id=user_id
        )
        
        return response
    
    async def handle_web_message(self, message: str, user_id: str):
        """处理Web端消息"""
        # 从注入的应用实例获取服务
        llm_service = await self.app.get_llm_service('web')
        
        response = await llm_service.chat_async(
            messages=[{"role": "user", "content": message}],
            user_id=user_id
        )
        
        return response


# ==================== 示例2: ChatAgent（推荐方式）====================

class ChatAgent:
    """聊天Agent - 通过构造函数注入应用实例"""
    
    def __init__(self, app, user_id: str):
        """
        构造函数注入
        
        Args:
            app: 应用实例
            user_id: 用户ID
        """
        self.app = app
        self.user_id = user_id
    
    async def process_chat(self, message: str, client_type: str = 'web'):
        """处理对话"""
        # 根据客户端类型获取对应的LLM服务
        llm_service = await self.app.get_llm_service(client_type)
        
        response = await llm_service.chat_async(
            messages=[{"role": "user", "content": message}],
            user_id=self.user_id
        )
        
        return response


# ==================== 示例3: 服务层（推荐方式）====================

class DiaryService:
    """日记服务 - 通过构造函数注入应用实例"""
    
    def __init__(self, app):
        self.app = app
    
    async def generate_diary(self, user_id: str, mood_data: dict):
        """生成日记"""
        # 使用system类型的LLM服务
        llm_service = await self.app.get_llm_service('system')
        
        prompt = f"根据用户的心情数据生成日记：{mood_data}"
        
        response = await llm_service.chat_async(
            messages=[{"role": "user", "content": prompt}],
            user_id=user_id
        )
        
        return response


# ==================== 示例4: 主程序（完整流程）====================

async def main():
    """主程序 - 展示完整的依赖注入流程"""
    
    # 1. 创建应用实例（不是单例！）
    app = create_app(ApplicationConfig(
        name="心理对话AI",
        dashscope_api_key="your_api_key_here"
    ))
    
    # 2. 初始化应用
    await app.initialize()
    
    try:
        # 3. 创建处理器，注入应用实例
        ws_handler = WebSocketHandler(app)
        
        # 4. 处理ESP32请求
        print("\n📱 处理ESP32请求...")
        esp32_response = await ws_handler.handle_esp32_message(
            message="你好，我是ESP32设备",
            user_id="esp32_001"
        )
        print(f"ESP32响应: {esp32_response[:100]}...")
        
        # 5. 处理Web请求
        print("\n🌐 处理Web请求...")
        web_response = await ws_handler.handle_web_message(
            message="你好，我是Web用户",
            user_id="web_001"
        )
        print(f"Web响应: {web_response[:100]}...")
        
        # 6. 创建ChatAgent，注入应用实例
        print("\n💬 使用ChatAgent...")
        agent = ChatAgent(app, user_id="user_123")
        agent_response = await agent.process_chat(
            message="今天心情不太好",
            client_type='web'
        )
        print(f"Agent响应: {agent_response[:100]}...")
        
        # 7. 创建服务，注入应用实例
        print("\n📝 使用DiaryService...")
        diary_service = DiaryService(app)
        diary = await diary_service.generate_diary(
            user_id="user_123",
            mood_data={"mood": "sad", "intensity": 7}
        )
        print(f"日记: {diary[:100]}...")
        
    finally:
        # 8. 关闭应用
        await app.shutdown()


# ==================== 示例5: 测试（多实例）====================

async def test_multiple_instances():
    """测试多个应用实例（证明不是单例）"""
    
    print("\n" + "="*60)
    print("测试: 创建多个应用实例")
    print("="*60)
    
    # 创建第一个应用实例
    app1 = create_app(ApplicationConfig(
        name="应用实例1",
        dashscope_api_key="key1"
    ))
    await app1.initialize()
    
    # 创建第二个应用实例
    app2 = create_app(ApplicationConfig(
        name="应用实例2",
        dashscope_api_key="key2"
    ))
    await app2.initialize()
    
    # 验证是不同的实例
    assert app1 is not app2, "应该是不同的实例"
    print("✅ 成功创建两个独立的应用实例")
    
    # 每个实例有自己的服务
    llm1 = await app1.get_llm_service('web')
    llm2 = await app2.get_llm_service('web')
    
    assert llm1 is not llm2, "应该是不同的LLM服务实例"
    print("✅ 每个应用实例有自己的服务")
    
    # 清理
    await app1.shutdown()
    await app2.shutdown()
    
    print("✅ 多实例测试通过！")


# ==================== 示例6: 函数式风格（推荐）====================

async def handle_request(app, request_data: dict):
    """
    函数式风格 - 将应用实例作为参数传递
    
    Args:
        app: 应用实例（依赖注入）
        request_data: 请求数据
    """
    client_type = request_data.get('client_type', 'web')
    message = request_data.get('message', '')
    user_id = request_data.get('user_id', '')
    
    # 从参数获取应用实例
    llm_service = await app.get_llm_service(client_type)
    
    response = await llm_service.chat_async(
        messages=[{"role": "user", "content": message}],
        user_id=user_id
    )
    
    return response


async def functional_style_example():
    """函数式风格示例"""
    app = create_app()
    await app.initialize()
    
    try:
        # 将应用实例作为参数传递
        response = await handle_request(app, {
            'client_type': 'esp32',
            'message': '你好',
            'user_id': 'user_001'
        })
        
        print(f"响应: {response}")
        
    finally:
        await app.shutdown()


# ==================== 运行示例 ====================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎯 依赖注入使用示例")
    print("="*60)
    
    # 运行主示例
    # asyncio.run(main())
    
    # 运行多实例测试
    asyncio.run(test_multiple_instances())
    
    # 运行函数式风格示例
    # asyncio.run(functional_style_example())
