#!/usr/bin/env python3
"""
Agent 功能测试
Test Agent Functionality
验证大模型Agent的所有功能是否正常工作
"""

import sys
import os
import asyncio
import tempfile
import shutil
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))


def test_agent_imports():
    """测试 Agent 模块导入"""
    print("🧪 测试 Agent 模块导入...")
    
    try:
        # 测试基础 Agent
        from app.shared.agents.base_agent import BaseAgent, AgentMode, MemoryManager
        print("  ✅ BaseAgent 导入成功")
        
        # 测试聊天 Agent
        from app.shared.agents.chat_agent import PureChatAgent
        print("  ✅ PureChatAgent 导入成功")
        
        # 测试记忆 Agent
        from app.shared.agents.memory_agent import MemoryAgent
        print("  ✅ MemoryAgent 导入成功")
        
        # 测试记忆存储
        from app.shared.agents.stores import create_memory_manager
        print("  ✅ create_memory_manager 导入成功")
        
        # 测试 Agent 工厂函数
        from app.shared.agents import get_memory_agent
        print("  ✅ get_memory_agent 工厂函数导入成功")
        
        return True
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_mode():
    """测试 AgentMode 枚举值"""
    print("\n🧪 测试 AgentMode 枚举值...")
    
    try:
        from app.shared.agents.base_agent import AgentMode
        
        # 测试所有模式
        modes = [
            AgentMode.NORMAL,
            AgentMode.TREE_HOLE,
            AgentMode.PARENT_VIEW,
            AgentMode.SCHOOL_VIEW
        ]
        
        for mode in modes:
            print(f"  ✅ AgentMode.{mode.name} = '{mode.value}'")
        
        return True
    except Exception as e:
        print(f"  ❌ AgentMode 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_manager_creation():
    """测试记忆管理器创建"""
    print("\n🧪 测试记忆管理器创建...")
    
    try:
        from app.shared.agents.stores import create_memory_manager
        
        # 创建临时目录用于测试
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 创建记忆管理器
            memory_manager = create_memory_manager(data_dir=Path(temp_dir))
            print("  ✅ 记忆管理器创建成功")
            
            # 检查记忆管理器组件
            if memory_manager.vops:
                print("  ✅ 向量操作组件初始化成功")
            else:
                print("  ❌ 向量操作组件初始化失败")
                return False
            
            if memory_manager.ep_store:
                print("  ✅ 情节记忆存储组件初始化成功")
            else:
                print("  ❌ 情节记忆存储组件初始化失败")
                return False
            
            if memory_manager.pr_store:
                print("  ✅ 用户档案存储组件初始化成功")
            else:
                print("  ❌ 用户档案存储组件初始化失败")
                return False
            
            if memory_manager.af_store:
                print("  ✅ 情绪状态存储组件初始化成功")
            else:
                print("  ❌ 情绪状态存储组件初始化失败")
                return False
            
            if memory_manager.sa_store:
                print("  ✅ 安全合规存储组件初始化成功")
            else:
                print("  ❌ 安全合规存储组件初始化失败")
                return False
            
            if memory_manager.wk_cache:
                print("  ✅ 工作缓存组件初始化成功")
            else:
                print("  ❌ 工作缓存组件初始化失败")
                return False
            
            return True
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        print(f"  ❌ 记忆管理器创建测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pure_chat_agent():
    """测试 PureChatAgent 功能"""
    print("\n🧪 测试 PureChatAgent 功能...")
    
    try:
        from app.shared.agents.chat_agent import PureChatAgent, ChatRequest, AgentMode, ConversationStrategy
        
        # 初始化聊天代理
        chat_agent = PureChatAgent()
        print("  ✅ PureChatAgent 初始化成功")
        
        # 测试对话策略
        strategies = [
            ConversationStrategy.EMPATHY,
            ConversationStrategy.GUIDANCE,
            ConversationStrategy.KNOWLEDGE,
            ConversationStrategy.CASUAL,
            ConversationStrategy.CRISIS
        ]
        
        for strategy in strategies:
            if strategy in chat_agent.strategy_prompts:
                print(f"  ✅ 对话策略存在: {strategy.value}")
            else:
                print(f"  ❌ 对话策略不存在: {strategy.value}")
                return False
        
        # 测试意图分析
        test_message = "我今天感到很难过，因为考试没考好"
        intent = chat_agent._analyze_intent(test_message)
        if intent and isinstance(intent, dict):
            print(f"  ✅ 意图分析成功: {intent}")
        else:
            print("  ❌ 意图分析失败")
            return False
        
        # 测试风险分析
        risk = chat_agent._analyze_risk(test_message)
        if risk and isinstance(risk, dict) and "level" in risk:
            print(f"  ✅ 风险分析成功: level={risk['level']}")
        else:
            print("  ❌ 风险分析失败")
            return False
        
        # 测试策略确定
        strategy = chat_agent._determine_strategy(intent, risk)
        if strategy and isinstance(strategy, ConversationStrategy):
            print(f"  ✅ 策略确定成功: {strategy.value}")
        else:
            print("  ❌ 策略确定失败")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ PureChatAgent 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_agent():
    """测试 MemoryAgent 功能"""
    print("\n🧪 测试 MemoryAgent 功能...")
    
    try:
        from app.shared.agents.memory_agent import MemoryAgent
        from app.shared.agents.stores import create_memory_manager
        
        # 创建临时目录用于测试
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 创建记忆管理器
            memory_manager = create_memory_manager(data_dir=Path(temp_dir))
            
            # 初始化记忆代理
            memory_agent = MemoryAgent(memory_manager)
            print("  ✅ MemoryAgent 初始化成功")
            
            # 测试安全JSON加载
            test_json = '{"emotion": {"label": "happy", "intensity": 8}}'
            parsed = memory_agent._safe_json_loads(test_json)
            if parsed and parsed.get("emotion") and parsed["emotion"].get("label") == "happy":
                print("  ✅ 安全JSON加载成功")
            else:
                print("  ❌ 安全JSON加载失败")
                return False
            
            # 测试记忆管理器组件
            if memory_agent.memory:
                print("  ✅ 记忆管理器引用成功")
            else:
                print("  ❌ 记忆管理器引用失败")
                return False
            
            # 测试记忆管理器的存储组件
            if memory_agent.memory.vops:
                print("  ✅ 向量操作组件引用成功")
            else:
                print("  ❌ 向量操作组件引用失败")
                return False
            
            return True
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        print(f"  ❌ MemoryAgent 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_agent_with_llm():
    """测试 Agent 与 LLM 的集成"""
    print("\n🧪 测试 Agent 与 LLM 的集成...")
    
    try:
        from app.shared.agents import get_memory_agent
        from app.shared.services import get_llm_service
        
        # 检查 API Key 是否配置
        from app.core.config import settings
        if not settings.DASHSCOPE_API_KEY:
            print("  ⚠️ DASHSCOPE_API_KEY 未配置，跳过 LLM 集成测试")
            return True
        
        # 初始化记忆代理
        memory_agent = get_memory_agent()
        print("  ✅ MemoryAgent 初始化成功")
        
        # 初始化 LLM 服务
        llm_service = get_llm_service()
        print("  ✅ LLM 服务初始化成功")
        
        # 测试简单对话
        test_messages = [
            {"role": "system", "content": "你是一个友好的助手"},
            {"role": "user", "content": "你好"}
        ]
        
        response = llm_service.chat(test_messages)
        if response and len(response) > 0:
            print(f"  ✅ LLM 调用成功，回复长度: {len(response)} 字符")
        else:
            print("  ❌ LLM 调用失败")
            return False
        
        # 测试 MemoryAgent 信号提取
        signals = await memory_agent._llm_extract_signals("我今天感到非常开心！")
        if signals and isinstance(signals, dict):
            print(f"  ✅ 信号提取成功: {signals}")
        else:
            print("  ❌ 信号提取失败")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Agent 与 LLM 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_stores():
    """测试记忆存储功能"""
    print("\n🧪 测试记忆存储功能...")
    
    try:
        from app.shared.agents.stores import (
            SimpleVectorOps,
            FileEpisodicStore,
            FileProfileStore,
            FileAffectStore,
            FileSafetyStore,
            MemoryWorkingCache
        )
        
        # 创建临时目录用于测试
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 测试向量操作
            vector_ops = SimpleVectorOps()
            test_text = "这是一个测试文本"
            embedding = vector_ops.embed(test_text)
            if embedding and len(embedding) > 0:
                print(f"  ✅ 向量嵌入成功，维度: {len(embedding)}")
            else:
                print("  ❌ 向量嵌入失败")
                return False
            
            # 测试相似度计算
            similarity = vector_ops.similarity(embedding, embedding)
            if similarity > 0.99:  # 相同文本应该有极高的相似度
                print(f"  ✅ 相似度计算成功: {similarity}")
            else:
                print(f"  ❌ 相似度计算失败: {similarity}")
                return False
            
            # 测试存储组件初始化
            episodic_store = FileEpisodicStore(Path(temp_dir))
            profile_store = FileProfileStore(Path(temp_dir))
            affect_store = FileAffectStore(Path(temp_dir))
            safety_store = FileSafetyStore(Path(temp_dir))
            working_cache = MemoryWorkingCache()
            
            print("  ✅ 所有存储组件初始化成功")
            
            return True
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        print(f"  ❌ 记忆存储测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 Agent 功能测试")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("导入测试", test_agent_imports()))
    results.append(("AgentMode 测试", test_agent_mode()))
    results.append(("记忆管理器创建测试", test_memory_manager_creation()))
    results.append(("PureChatAgent 测试", test_pure_chat_agent()))
    results.append(("MemoryAgent 测试", test_memory_agent()))
    results.append(("记忆存储测试", test_memory_stores()))
    results.append(("Agent 与 LLM 集成测试", await test_agent_with_llm()))
    
    # 打印总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    print(f"\n总体: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有 Agent 测试通过！Agent 功能正常工作。")
        return 0
    else:
        print("\n⚠️ 部分 Agent 测试失败，请检查上述错误。")
        return 1


if __name__ == "__main__":
    # 设置环境变量
    os.environ.setdefault("PYTHONPATH", str(project_root))
    
    # 运行异步主函数
    sys.exit(asyncio.run(main()))