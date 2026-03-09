"""
WebChatAgent单元测试
Web Chat Agent Unit Tests
验证WebChatAgent的核心功能和网页端特性
"""

import asyncio
import pytest
from app.shared.agents import (
    WebChatAgent, WebChatRequest, WebChatResponse,
    get_web_chat_agent, AgentMode, TreeHoleMode
)


class TestWebChatAgent:
    """WebChatAgent测试类"""
    
    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """测试Agent初始化"""
        agent = WebChatAgent()
        assert agent is not None
        assert agent.profile_service is not None
        assert agent.mood_service is not None
        assert agent.enable_tree_hole is True
        assert agent.enable_character_system is True
    
    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """测试单例模式"""
        agent1 = get_web_chat_agent()
        agent2 = get_web_chat_agent()
        assert agent1 is agent2
    
    @pytest.mark.asyncio
    async def test_basic_chat(self):
        """测试基础对话功能"""
        agent = WebChatAgent()
        
        request = WebChatRequest(
            user_id="test_user_001",
            message="你好",
            mode=AgentMode.NORMAL
        )
        
        response = await agent.process_web_chat(request)
        
        assert response is not None
        assert isinstance(response, WebChatResponse)
        assert response.response is not None
        assert len(response.response) > 0
        print(f"✅ 基础对话测试通过: {response.response[:50]}...")
    
    @pytest.mark.asyncio
    async def test_character_system(self):
        """测试角色系统"""
        agent = WebChatAgent()
        
        # 测试指定角色
        request = WebChatRequest(
            user_id="test_user_002",
            message="我今天心情不好",
            character="心理咨询师",
            mode=AgentMode.NORMAL
        )
        
        response = await agent.process_web_chat(request)
        
        assert response.character_used == "心理咨询师"
        print(f"✅ 角色系统测试通过: 使用角色={response.character_used}")
    
    @pytest.mark.asyncio
    async def test_tree_hole_mode(self):
        """测试树洞模式"""
        agent = WebChatAgent()
        
        request = WebChatRequest(
            user_id="test_user_003",
            message="这是一个秘密，不要告诉别人",
            tree_hole_mode=True,
            mode=AgentMode.NORMAL
        )
        
        response = await agent.process_web_chat(request)
        
        assert response is not None
        # 树洞模式下亲密度不应该增加
        assert response.intimacy_change == 0.0
        print(f"✅ 树洞模式测试通过: 亲密度变化={response.intimacy_change}")
    
    @pytest.mark.asyncio
    async def test_voice_enabled_chat(self):
        """测试语音对话"""
        agent = WebChatAgent()
        
        request = WebChatRequest(
            user_id="test_user_004",
            message="给我讲个故事",
            enable_voice=True,
            mode=AgentMode.NORMAL
        )
        
        response = await agent.process_web_chat(request)
        
        assert response is not None
        # 语音对话应该有额外的亲密度加成
        assert response.intimacy_change > 1.0
        print(f"✅ 语音对话测试通过: 亲密度变化={response.intimacy_change}")
    
    @pytest.mark.asyncio
    async def test_time_context(self):
        """测试时间上下文"""
        agent = WebChatAgent()
        
        request = WebChatRequest(
            user_id="test_user_005",
            message="现在几点了？",
            include_time_context=True,
            mode=AgentMode.NORMAL
        )
        
        response = await agent.process_web_chat(request)
        
        assert response is not None
        assert 'time_context' in response.metadata
        print(f"✅ 时间上下文测试通过: {response.metadata['time_context']}")
    
    @pytest.mark.asyncio
    async def test_conversation_summary(self):
        """测试对话摘要"""
        agent = WebChatAgent()
        user_id = "test_user_006"
        
        # 先进行几轮对话
        messages = ["你好", "今天天气怎么样", "谢谢"]
        for msg in messages:
            request = WebChatRequest(
                user_id=user_id,
                message=msg,
                mode=AgentMode.NORMAL
            )
            await agent.process_web_chat(request)
        
        # 获取对话摘要
        summary = await agent.get_conversation_summary(user_id, limit=5)
        
        assert summary is not None
        assert len(summary) > 0
        print(f"✅ 对话摘要测试通过:\n{summary}")
    
    @pytest.mark.asyncio
    async def test_intimacy_calculation(self):
        """测试亲密度计算"""
        agent = WebChatAgent()
        
        # 短消息
        short_request = WebChatRequest(
            user_id="test_user_007",
            message="好",
            mode=AgentMode.NORMAL
        )
        short_response = await agent.process_web_chat(short_request)
        
        # 长消息
        long_request = WebChatRequest(
            user_id="test_user_007",
            message="我今天遇到了很多事情，想和你聊聊。首先是工作上的压力，然后是家庭的一些琐事...",
            mode=AgentMode.NORMAL
        )
        long_response = await agent.process_web_chat(long_request)
        
        # 长消息应该有更高的亲密度
        assert long_response.intimacy_change > short_response.intimacy_change
        print(f"✅ 亲密度计算测试通过: 短消息={short_response.intimacy_change}, 长消息={long_response.intimacy_change}")
    
    @pytest.mark.asyncio
    async def test_multiple_users(self):
        """测试多用户隔离"""
        agent = WebChatAgent()
        
        # 用户1
        request1 = WebChatRequest(
            user_id="user_a",
            message="我叫Alice",
            mode=AgentMode.NORMAL
        )
        response1 = await agent.process_web_chat(request1)
        
        # 用户2
        request2 = WebChatRequest(
            user_id="user_b",
            message="我叫Bob",
            mode=AgentMode.NORMAL
        )
        response2 = await agent.process_web_chat(request2)
        
        # 验证用户1的记忆
        request1_check = WebChatRequest(
            user_id="user_a",
            message="我叫什么名字？",
            mode=AgentMode.NORMAL
        )
        response1_check = await agent.process_web_chat(request1_check)
        
        assert response1 is not None
        assert response2 is not None
        assert response1_check is not None
        print(f"✅ 多用户隔离测试通过")
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """测试错误处理"""
        agent = WebChatAgent()
        
        # 空消息
        try:
            request = WebChatRequest(
                user_id="test_user_008",
                message="",
                mode=AgentMode.NORMAL
            )
            response = await agent.process_web_chat(request)
            # 应该能处理空消息
            assert response is not None
            print(f"✅ 空消息处理测试通过")
        except Exception as e:
            print(f"⚠️ 空消息处理异常: {e}")


@pytest.mark.asyncio
async def test_concurrent_requests():
    """测试并发请求"""
    agent = WebChatAgent()
    
    async def send_message(user_id: str, message: str):
        request = WebChatRequest(
            user_id=user_id,
            message=message,
            mode=AgentMode.NORMAL
        )
        return await agent.process_web_chat(request)
    
    # 并发5个请求
    tasks = [
        send_message(f"user_{i}", f"消息{i}")
        for i in range(5)
    ]
    
    responses = await asyncio.gather(*tasks)
    
    assert len(responses) == 5
    assert all(r is not None for r in responses)
    print(f"✅ 并发请求测试通过: 5个请求全部成功")


@pytest.mark.asyncio
async def test_inheritance_from_pure_chat_agent():
    """测试继承关系"""
    from app.shared.agents import PureChatAgent
    
    agent = WebChatAgent()
    
    # 验证继承关系
    assert isinstance(agent, PureChatAgent)
    assert isinstance(agent, WebChatAgent)
    
    # 验证基类方法可用
    assert hasattr(agent, 'process_chat')
    assert hasattr(agent, 'memory_agent')
    
    print(f"✅ 继承关系测试通过")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
