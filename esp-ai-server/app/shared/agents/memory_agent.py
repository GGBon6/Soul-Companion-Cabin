"""
MemoryAgent：记忆智能层
- 负责从对话中提取关键情绪、事件、偏好、风险信号
- 负责写入五类记忆（工作记忆 / 情节记忆 / 语义画像 / 情绪基线 / 安全日志）
- 负责召回用户特征，辅助 LLM 给出共情化、自然的回答
- 核心贴合产品需求：青少年、树洞、情绪趋势、风险识别、家长端摘要
"""

import json
import re
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Tuple

from app.shared.agents.base_agent import BaseAgent, AgentMode, make_memory, MemoryType
from app.core import logger


class MemoryAgent(BaseAgent):
    """产品级智能记忆 Agent（继承五类记忆 BaseAgent）"""

    def __init__(self, memory_manager, llm_service):
        super().__init__(
            agent_name="MemoryAgent",
            memory_manager=memory_manager
        )
        # 通过构造函数注入LLM服务，避免在类内部获取全局单例
        self.llm = llm_service

    # -------------------------------------------------------
    # analyze：负责“理解用户 → 判断哪些记忆需要写入/召回”
    # -------------------------------------------------------
    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        快速决策层：只做轻量级判断，不进行耗时的 LLM 调用
        输入: user_message, mode, user_id
        输出:
            - should_execute: 是否需要启动 LLM 分析
            - user_message: 用户消息
            - mode: 运行模式
            - user_id: 用户ID
        """
        user_id = context["user_id"]
        msg = context.get("user_message", "")
        mode = context.get("mode", AgentMode.NORMAL)

        # 快速判断：只要有用户消息就需要执行 LLM 分析
        should_execute = bool(msg.strip())
        
        # 简单的风险关键词预筛选（不依赖 LLM）
        risk_keywords = ["不想活", "想死", "自杀", "结束生命", "撑不住", "崩溃"]
        has_risk_signal = any(keyword in msg for keyword in risk_keywords)
        
        return {
            "should_execute": should_execute,
            "user_message": msg,
            "user_id": user_id,
            "mode": mode,
            "has_risk_signal": has_risk_signal  # 预警信号，供 execute 参考
        }

    # -------------------------------------------------------
    # execute：执行记忆写入 + 召回
    # -------------------------------------------------------
    async def execute(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行层：进行 LLM 分析并使用 BaseAgent 框架的正确接口
        """
        user_id = decision["user_id"]
        msg = decision["user_message"]
        mode = decision["mode"]
        has_risk_signal = decision.get("has_risk_signal", False)

        # 1. LLM 提取情绪/事件/偏好/风险信号
        analysis = await self._llm_extract_signals(msg)
        
        # 2. 构建记忆记录列表
        memories_to_write = []
        risk_flags = analysis.get("risk_flags", [])

        # ---------（1）情绪基线写入 ----------
        if analysis.get("emotion"):
            emo = analysis["emotion"]
            mem = make_memory(
                user_id=user_id,
                type=MemoryType.AFFECT_BASELINE,
                content=f"emotion:{emo['label']} intensity:{emo['intensity']}",
                importance=5,
                meta={"raw": msg, "score": emo},
            )
            memories_to_write.append(mem)

        # ---------（2）情节记忆：明确事件 ----------
        for ev in analysis.get("events", []):
            mem = make_memory(
                user_id=user_id,
                type=MemoryType.EPISODIC_MEMORY,
                content=ev["summary"],
                importance=ev.get("importance", 6),
                related_event=ev.get("event_name"),
                event_date=ev.get("event_date"),
            )
            memories_to_write.append(mem)

        # ---------(3）偏好/性格档案 ----------
        for pref in analysis.get("preferences", []):
            mem = make_memory(
                user_id=user_id,
                type=MemoryType.SEMANTIC_PROFILE,
                content=pref["statement"],
                importance=5,
            )
            memories_to_write.append(mem)

        # ---------(4）安全风控日志 ----------
        for rf in risk_flags:
            mem = make_memory(
                user_id=user_id,
                type=MemoryType.SAFETY_LEDGER,
                content=rf["keyword"],
                importance=10,
                meta={"matched": rf},
            )
            memories_to_write.append(mem)

        # ---------(5）工作记忆（对话上下文）----------
        wk = make_memory(
            user_id=user_id,
            type=MemoryType.WORKING_MEMORY,
            content=msg,
            importance=4
        )
        memories_to_write.append(wk)

        # 3. 为需要向量检索的记忆生成 embedding
        for memory in memories_to_write:
            if memory.type in [MemoryType.EPISODIC_MEMORY, MemoryType.SEMANTIC_PROFILE]:
                try:
                    # 使用 MemoryManager 的向量操作生成 embedding
                    embedding = self.memory.vops.embed(memory.content)
                    memory.embedding = embedding
                except Exception as e:
                    logger.error(f"生成向量失败: {e}")
                    memory.embedding = []

        # 4. 使用 BaseAgent 框架的正确接口：批量写入记忆
        try:
            if memories_to_write:
                # ✅ 使用正确的 BaseAgent 接口，支持树洞模式和写入门控
                written_records = self.memory.remember(
                    user_id=user_id,
                    records=memories_to_write,
                    mode=mode  # ✅ 传递正确的 mode，支持树洞模式
                )
                logger.info(f"✅ 批量写入 {len(written_records)} 条记忆 mode={mode.value}")
        except Exception as e:
            logger.error(f"写入记忆失败: {e}")

        # 5. 使用 BaseAgent 框架的正确接口：召回记忆
        recall = {}
        try:
            # ✅ 使用正确的 BaseAgent 接口，支持 MMR、时间衰减、去重等高级功能
            recall = self.memory.recall(
                user_id=user_id,
                query_text=msg,
                mode=mode  # ✅ 传递正确的 mode
            )
            logger.info(f"✅ 召回记忆成功 mode={mode.value}")
        except Exception as e:
            logger.error(f"召回记忆失败: {e}")
            # 如果召回失败，返回空的结构
            recall = {
                "episodic_memory": [],
                "working_memory": [],
                "semantic_profile": [],
                "affect_baseline": [],
                "safety_ledger": []
            }

        return {
            "recall": recall,
            "risk_flags": risk_flags,
            "analysis": analysis  # 返回完整的分析结果
        }

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        default = {"emotion": None, "events": [], "preferences": [], "risk_flags": []}
        if isinstance(text, dict):
            return text
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            else:
                return default
        except Exception:
            pass
        s = str(text)
        s = s.strip()
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
            s = re.sub(r"```\s*$", "", s)
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start:end + 1]
        s = re.sub(r",\s*([}\]])", r"\1", s)
        s = re.sub(r"(?<!\")'([A-Za-z0-9_]+)'(?=\s*:)", r'"\1"', s)
        s = re.sub(r":\s*'([^']*)'", r': "\1"', s)
        try:
            parsed2 = json.loads(s)
            if isinstance(parsed2, dict):
                return parsed2
            else:
                return default
        except Exception:
            return default

    # -------------------------------------------------------
    # LLM 提取情绪 / 偏好 / 事件 / 风险信号（核心贴合产品需求） 
    # -------------------------------------------------------
    async def _llm_extract_signals(self, msg: str) -> Dict[str, Any]:
        """
        LLM识别：
        - 情绪（标签 + 强度）
        - 事件
        - 偏好（人物、科目、兴趣）
        - 风险信号（青少年心理关键词）
        """
        user_msg = json.dumps(msg, ensure_ascii=False)
        prompt = (
            "你是一名“青少年心理陪伴系统”的分析模块。\n\n"
            + "用户消息：" + user_msg + "\n\n"
            + "任务：从用户消息中提取结构化信息，并仅输出严格 JSON（不要任何说明、注释或代码块）。\n\n"
            + "字段要求：\n"
            + "- emotion: 对象或 null；字段 label(string)，intensity(1-10 的整数)。\n"
            + "- events: 对象数组；字段 summary(string), importance(1-10 的整数), event_name(string 可选), event_date(YYYY-MM-DD 可选)。\n"
            + "- preferences: 对象数组；字段 statement(string)。\n"
            + "- risk_flags: 对象数组；字段 keyword(string), severity(1-3 的整数)。\n"
        )
        try:
            res = await self.llm.chat_async(
                [{"role": "user", "content": prompt}],
                temperature=0.2
            )
            return self._safe_json_loads(res)
        except Exception:
            return {"emotion": None, "events": [], "preferences": [], "risk_flags": []}


from app.shared.services import get_llm_service


# 全局单例（向后兼容）
_memory_agent = None


def get_memory_agent():
    """获取记忆Agent单例（向后兼容工厂）"""
    global _memory_agent
    if _memory_agent is None:
        # ✅ 使用新的 BaseAgent 存储架构
        from app.shared.agents.stores import create_memory_manager
        
        # 创建完整的 MemoryManager
        memory_manager = create_memory_manager()

        # 仍然通过 get_llm_service() 获取单例，供旧代码使用
        llm_service = get_llm_service()
        # 直接将 MemoryManager 传入 MemoryAgent，避免依赖已删除的 MemoryService 包装层
        _memory_agent = MemoryAgent(memory_manager, llm_service)
    return _memory_agent
