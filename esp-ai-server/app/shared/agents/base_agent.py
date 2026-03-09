"""
- Working Context（短期工作记忆，缓存）
- Episodic Memory（情节记忆，事件型，可向量检索）
- Semantic Profile（语义档案，稳定特征/偏好）
- Affect Baseline / Timeseries（情绪基线与趋势）
- Safety Ledger（安全与合规打点）
支持：写入门控、保留/删除策略、模式隔离（tree_hole等）、统一召回接口
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Iterable, Protocol
from datetime import datetime, timedelta
import asyncio
import uuid
import time
import math
import hashlib
# AgentMode 和 RetentionPolicy 在本文件中定义
from app.core import logger

# -------------------- 记忆类型 --------------------
class MemoryType(str, Enum):
    WORKING_MEMORY = "working_memory"   #短期工作记忆，缓存
    EPISODIC_MEMORY = "episodic_memory"  #情节记忆，事件型，可向量检索
    SEMANTIC_PROFILE = "semantic_profile" #语义档案，稳定特征/偏好
    AFFECT_BASELINE = "affect_baseline" #情绪基线与趋势
    SAFETY_LEDGER = "safety_ledger"     #安全与合规打点


# -------------------- 运行模式（影响写入/召回） --------------------
class AgentMode(str, Enum):
    NORMAL = "normal"
    TREE_HOLE = "tree_hole"             # 树洞：禁止任何长期写入与检索
    PARENT_VIEW = "parent_view"         # 家长端视角：只看聚合，不看原文（一般只读）
    SCHOOL_VIEW = "school_view"         # 学校/机构视角：需匿名化聚合（一般只读））

# -------------------- 记忆记录格式 --------------------
@dataclass
class MemoryRecord:
    id: str
    user_id: str
    type: MemoryType
    content: str
    timestamp: str
    importance: int = 5                 # 1-10
    related_event: Optional[str] = None
    event_date: Optional[str] = None    # YYYY-MM-DD
    embedding: Optional[List[float]] = None
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RetentionPolicy:
    # 保留策略
    ttl_hours: Optional[int] = None                 # 超期删除（None 表示长期）
    time_decay_half_life_days: Optional[float] = 30 # 检索加权的时间半衰期
    redact_on_export: bool = False                  # 对外导出是否脱敏（AFFECT/SAFETY常用）

@dataclass
class WriteGatePolicy:
    # 写入门控：是否允许、稳定性阈值、敏感度等
    allow_persist: bool = True
    min_importance: int = 4
    # profile（档案）类需要≥2次证据才写入
    require_multi_evidence_for_profile: bool = True
    evidence_window_days: int = 7

@dataclass
class RecallPolicy:
    # 召回策略
    min_similarity: float = 0.3  # 降低阈值，提高召回率
    top_k: int = 5
    max_return: int = 3
    mmr_lambda: float = 0.7
    avoid_repeat_hours: int = 2

@dataclass
class MemoryPolicies:
    working: RetentionPolicy = field(default_factory=lambda: RetentionPolicy(ttl_hours=2))     # 会话缓存
    episodic: RetentionPolicy = field(default_factory=lambda: RetentionPolicy(ttl_hours=None, time_decay_half_life_days=45))
    profile: RetentionPolicy = field(default_factory=lambda: RetentionPolicy(ttl_hours=None))
    affect: RetentionPolicy = field(default_factory=lambda: RetentionPolicy(ttl_hours=None, redact_on_export=True))
    safety: RetentionPolicy = field(default_factory=lambda: RetentionPolicy(ttl_hours=None, redact_on_export=True))

    write_gate: WriteGatePolicy = field(default_factory=WriteGatePolicy)
    recall: RecallPolicy = field(default_factory=RecallPolicy)

# -------------------- 存储与计算接口（由具体实现注入） --------------------
class VectorOps(Protocol):
    """向量操作：文本嵌入和相似度计算"""
    def embed(self, text: str) -> List[float]: ...  # 文本转向量嵌入
    def similarity(self, a: List[float], b: List[float]) -> float: ...  # 计算向量相似度

class EpisodicStore(Protocol):
    """情节记忆存储：事件型记忆的向量检索"""
    def upsert(self, records: List[MemoryRecord]) -> None: ...  # 插入或更新记忆记录
    def search(self, user_id: str, query_vec: List[float], top_k: int) -> List[Tuple[MemoryRecord, float]]: ...  # 向量相似度搜索记忆
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int: ...  # 删除过期记忆

class ProfileStore(Protocol):
    """用户档案存储：稳定特征和偏好，支持多证据验证"""
    def upsert(self, records: List[MemoryRecord]) -> None: ...  # 插入或更新档案记录
    def get_recent_support(self, user_id: str, normalized_key: str, window_days: int) -> int: ...  # 获取特征支持证据数量
    def add_support_signal(self, user_id: str, normalized_key: str, content: str) -> None: ...  # 添加特征支持信号
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int: ...  # 删除过期档案

class AffectStore(Protocol):
    """情绪状态存储：情绪基线和时序数据"""
    def append_points(self, user_id: str, points: List[Dict[str, Any]]) -> None: ...  # 追加情绪数据点
    def get_series(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]: ...  # 获取情绪时序数据
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int: ...  # 删除过期情绪记录

class SafetyStore(Protocol):
    """安全合规存储：风险监控和审计记录"""
    def append(self, user_id: str, rows: List[Dict[str, Any]]) -> None: ...  # 追加安全记录
    def get_recent(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]: ...  # 获取最近安全记录
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int: ...  # 删除过期安全记录

class WorkingCache(Protocol):
    """工作缓存：短期记忆和会话缓存，支持TTL"""
    def add(self, user_id: str, items: List[MemoryRecord], ttl_hours: int) -> None: ...  # 添加缓存项
    def get(self, user_id: str) -> List[MemoryRecord]: ...  # 获取用户缓存
    def trim(self, user_id: str, max_items: int = 100) -> None: ...  # 修剪缓存数量
    def wipe(self, user_id: str) -> None: ...  # 清空用户缓存

# -------------------- 记忆管理器（BaseAgent 内部持有） --------------------
class MemoryManager:
    def __init__(
        self,
        vector_ops: VectorOps,
        episodic_store: EpisodicStore,
        profile_store: ProfileStore,
        affect_store: AffectStore,
        safety_store: SafetyStore,
        working_cache: WorkingCache,
        policies: Optional[MemoryPolicies] = None,
    ):
        self.vops = vector_ops
        self.ep_store = episodic_store
        self.pr_store = profile_store
        self.af_store = affect_store
        self.sa_store = safety_store
        self.wk_cache = working_cache
        self.policies = policies or MemoryPolicies()
        # 近用去重
        self._recent_used_ids: Dict[str, List[Tuple[str, datetime]]] = {}

    # ---------- 写入（带门控） ----------
    """
    根据记忆记录的类型、重要性及运行模式，将记忆分发到不同的存储介质中
    （如工作缓存、场景记忆库、用户画像库等）
    """
    def remember(
        self,
        user_id: str,
        records: List[MemoryRecord],
        mode: AgentMode = AgentMode.NORMAL,
    ) -> List[MemoryRecord]:
        """
        统一入口：根据 type 分发到不同介质与策略；树洞模式全面阻断长期写入。
        """
        if not records:
            return []

        gate = self.policies.write_gate
        now = datetime.now()

        # 树洞：仅允许 Working（且只缓存），其它全部丢弃
        if mode == AgentMode.TREE_HOLE:
            working_to_add = [r for r in records if r.type == MemoryType.WORKING_MEMORY]
            if working_to_add:
                self.wk_cache.add(user_id, working_to_add, ttl_hours=self.policies.working.ttl_hours or 2)
            return working_to_add

        to_epi, to_profile, to_working, to_affect, to_safety = [], [], [], [], []

        for r in records:
            # 门控：重要性阈值
            if r.importance < gate.min_importance and r.type not in (MemoryType.WORKING_MEMORY, MemoryType.AFFECT_BASELINE, MemoryType.SAFETY_LEDGER):
                continue

            # 计算 embedding（仅 EPISODIC 需要）
            if r.type == MemoryType.EPISODIC_MEMORY and r.embedding is None:
                r.embedding = self.vops.embed(r.content)

            # profile 需要多证据
            if r.type == MemoryType.SEMANTIC_PROFILE and gate.require_multi_evidence_for_profile:
                key = self._normalize_profile_key(r)
                support = self.pr_store.get_recent_support(user_id, key, gate.evidence_window_days)
                if support < 1:
                    # 先记录证据，下次再真正 upsert 档案
                    self.pr_store.add_support_signal(user_id, key, r.content)
                    continue

            # 分发
            if r.type == MemoryType.EPISODIC_MEMORY:
                to_epi.append(r)
            elif r.type == MemoryType.SEMANTIC_PROFILE:
                to_profile.append(r)
            elif r.type == MemoryType.WORKING_MEMORY:
                to_working.append(r)
            elif r.type == MemoryType.AFFECT_BASELINE:
                to_affect.append(r)
            elif r.type == MemoryType.SAFETY_LEDGER:
                to_safety.append(r)

        # 执行写入
        if to_working:
            self.wk_cache.add(user_id, to_working, ttl_hours=self.policies.working.ttl_hours or 2)
            self.wk_cache.trim(user_id)

        if gate.allow_persist:
            if to_epi:
                self.ep_store.upsert(to_epi)
            if to_profile:
                self.pr_store.upsert(to_profile)
            if to_affect:
                # affect 是时序点，通常不是 MemoryRecord，这里把 meta 里的点转给时序存储
                pts = [dict(ts=r.timestamp, **(r.meta or {})) for r in to_affect]
                if pts:
                    self.af_store.append_points(user_id, pts)
            if to_safety:
                rows = [dict(ts=r.timestamp, content=r.content, **(r.meta or {})) for r in to_safety]
                if rows:
                    self.sa_store.append(user_id, rows)

        return records

    # ---------- 召回 ----------
    def recall(
        self,
        user_id: str,
        query_text: str,
        mode: AgentMode = AgentMode.NORMAL
    ) -> Dict[MemoryType, List[Tuple[MemoryRecord, float]]]:
        """
        统一召回：按策略返回
        - TREE_HOLE：仅返回 Working
        - NORMAL：Working + Episodic 向量召回 + Profile 命中
        - AFFECT/SAFETY 一般不“注入对话”，但可用于系统提示或边界
        """
        out: Dict[MemoryType, List[Tuple[MemoryRecord, float]]] = {
            MemoryType.WORKING_MEMORY: [],
            MemoryType.EPISODIC_MEMORY: [],
            MemoryType.SEMANTIC_PROFILE: [],
            MemoryType.AFFECT_BASELINE: [],
            MemoryType.SAFETY_LEDGER: [],
        }

        # 先拿 Working
        working = self.wk_cache.get(user_id) or []
        out[MemoryType.WORKING_MEMORY] = [(w, 1.0) for w in working]

        if mode == AgentMode.TREE_HOLE:
            return out

        # Episodic 检索
        qvec = self.vops.embed(query_text)
        epi_pairs = self.ep_store.search(
            user_id=user_id,
            query_vec=qvec,
            top_k=self.policies.recall.top_k
        )

        # 时间 & 重要性加权 + MMR
        epi_pairs = self._rerank_with_signals_and_mmr(epi_pairs, self.policies.episodic, self.policies.recall)

        # 限制返回数量 + 去近期重复
        epi_pairs = self._filter_recent_used(user_id, epi_pairs, self.policies.recall)
        out[MemoryType.EPISODIC_MEMORY] = epi_pairs[: self.policies.recall.max_return]

        # Profile 常用做直接提示（这里示例：不做检索，交由上层决定是否注入）
        # 你可以在 ProfileStore 里提供 query 接口，这里保留占位
        return out

    # ---------- 清理 ----------
    def gc(self, now: Optional[datetime] = None) -> Dict[str, int]:
        """
        垃圾回收：按 TTL 删除过期数据；返回各类删除条数（由存储实现）
        """
        now = now or datetime.now()
        removed = {
            "episodic": self.ep_store.delete_expired(now, self.policies.episodic),
            "profile": self.pr_store.delete_expired(now, self.policies.profile),
            "affect": self.af_store.delete_expired(now, self.policies.affect),
            "safety": self.sa_store.delete_expired(now, self.policies.safety),
        }
        return removed

    # ---------- 工具 ----------
    def _normalize_profile_key(self, r: MemoryRecord) -> str:
        text = r.content.strip().lower()
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _time_decay(self, ts_iso: str, policy: RetentionPolicy) -> float:
        if not policy.time_decay_half_life_days:
            return 1.0
        try:
            ts = datetime.fromisoformat(ts_iso)
        except Exception:
            return 1.0
        age_days = max((datetime.now() - ts).days, 0)
        hl = policy.time_decay_half_life_days
        return 2 ** (-age_days / hl)

    def _rerank_with_signals_and_mmr(
        self,
        pairs: List[Tuple[MemoryRecord, float]],
        ret_pol: RetentionPolicy,
        rc_pol: RecallPolicy
    ) -> List[Tuple[MemoryRecord, float]]:
        if not pairs:
            return []
        # 基础分：相似度 * 时间衰减 * 重要性
        scored = []
        for m, sim in pairs:
            if sim < rc_pol.min_similarity:
                continue
            decay = self._time_decay(m.timestamp, ret_pol)
            imp = 1.0 + (m.importance - 5) * 0.05
            scored.append((m, sim, sim * decay * imp))

        if not scored:
            return []

        # MMR 去冗余
        selected: List[Tuple[MemoryRecord, float]] = []
        remaining = scored[:]
        lam = rc_pol.mmr_lambda

        def cos(a: List[float], b: List[float]) -> float:
            if not a or not b:
                return 0.0
            return VectorSimilarity._cos(a, b)

        while remaining and len(selected) < rc_pol.top_k:
            if not selected:
                best = max(remaining, key=lambda x: x[2])
                selected.append((best[0], best[1]))
                remaining.remove(best)
                continue

            best_item, best_val = None, -1e9
            for item in remaining:
                mi, simi, scorei = item
                redundancy = 0.0
                for (mj, _) in selected:
                    redundancy = max(redundancy, cos(mi.embedding or [], mj.embedding or []))
                mmr = lam * scorei - (1 - lam) * redundancy
                if mmr > best_val:
                    best_item, best_val = item, mmr
            selected.append((best_item[0], best_item[1]))
            remaining.remove(best_item)

        return selected

    def _filter_recent_used(
        self,
        user_id: str,
        pairs: List[Tuple[MemoryRecord, float]],
        rc: RecallPolicy
    ) -> List[Tuple[MemoryRecord, float]]:
        window = timedelta(hours=rc.avoid_repeat_hours)
        now = datetime.now()
        recent = self._recent_used_ids.get(user_id, [])
        recent = [(mid, ts) for (mid, ts) in recent if now - ts < window]
        self._recent_used_ids[user_id] = recent
        used_ids = {mid for mid, _ in recent}

        filtered = []
        for m, s in pairs:
            mid = m.id or hashlib.sha256((m.type + "::" + m.content).encode("utf-8")).hexdigest()
            if mid in used_ids:
                continue
            filtered.append((m, s))
            # 标记使用（只在召回阶段先记上）
            self._recent_used_ids[user_id].append((mid, now))
        return filtered

class VectorSimilarity:
    """向量相似度计算工具"""

    # 缓存向量的模长（key: 向量的哈希值，value: 模长）
    _norm_cache: Dict[int, float] = {}
    
    @staticmethod
    def _get_norm(vec: List[float]) -> float:
        """计算并缓存向量的模长"""
        vec_id = hash(tuple(vec))  # 用元组哈希作为唯一标识（仅适合小规模向量）
        if vec_id not in VectorSimilarity._norm_cache:
            norm_sq = sum(x * x for x in vec)
            VectorSimilarity._norm_cache[vec_id] = math.sqrt(norm_sq) if norm_sq > 1e-12 else 0.0
        return VectorSimilarity._norm_cache[vec_id]

    @staticmethod
    def _cos(a: List[float], b: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

# -------------------- 基类 Agent（带 run + 五类记忆） --------------------
class AgentDisabledError(RuntimeError): ...
class AgentExecutionError(RuntimeError): ...

class BaseAgent(ABC):
    """带五类记忆与模板方法的增强版 BaseAgent"""

    def __init__(
        self,
        agent_name: str = "BaseAgent",
        default_timeout_s: float = 15.0,
        max_concurrency: int = 1,
        memory_manager: Optional[MemoryManager] = None
    ):
        self.agent_name = agent_name
        self.enabled = True
        self.default_timeout_s = default_timeout_s
        self._sema = asyncio.Semaphore(max(1, max_concurrency))
        self.memory: MemoryManager = memory_manager  # 外部注入，或子类在 __init__ 里构造
        logger.info(f"✅ {self.agent_name} 初始化完成（五类记忆版）")

    # ---- 生命周期钩子（可覆写） ----
    async def before_analyze(self, context: Dict[str, Any]) -> None: ...
    async def after_analyze(self, context: Dict[str, Any], decision: Dict[str, Any]) -> None: ...
    async def before_execute(self, decision: Dict[str, Any]) -> None: ...
    async def after_execute(self, decision: Dict[str, Any], result: Any) -> None: ...

    # ---- 抽象方法 ----
    @abstractmethod
    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """分析上下文并返回决策（可以调用 self.memory.remember/recall）"""
        ...

    @abstractmethod
    async def execute(self, decision: Dict[str, Any]) -> Any:
        """执行决策"""
        ...

    # ---- 统一入口 ----
    async def run(
        self,
        context: Dict[str, Any],
        timeout_s: Optional[float] = None,
        allow_skip_execute: bool = False
    ) -> Dict[str, Any]:
        if not self.enabled:
            raise AgentDisabledError(f"{self.agent_name} 已禁用")

        trace_id = context.get("trace_id") or str(uuid.uuid4())
        context = {**context, "trace_id": trace_id}
        timeout = timeout_s or self.default_timeout_s
        t0 = time.perf_counter()

        async with self._guard_concurrency(trace_id):
            try:
                await self.before_analyze(context)
                decision = await asyncio.wait_for(self._safe_analyze(context), timeout=timeout)
                await self.after_analyze(context, decision)

                result = None
                if (not allow_skip_execute) or decision.get("should_execute", True):
                    await self.before_execute(decision)
                    result = await asyncio.wait_for(self._safe_execute(decision), timeout=timeout)
                    await self.after_execute(decision, result)

                dur = int((time.perf_counter() - t0) * 1000)
                logger.info(f"🧩 {self.agent_name} run ok trace={trace_id} dur={dur}ms")
                return {"trace_id": trace_id, "decision": decision, "result": result, "duration_ms": dur}
            except asyncio.TimeoutError:
                logger.error(f"⏱️ {self.agent_name} run timeout trace={trace_id}")
                raise AgentExecutionError(f"{self.agent_name} 执行超时")
            except Exception as e:
                logger.exception(f"💥 {self.agent_name} run failed trace={trace_id}: {e}")
                raise

    # ---- 内部工具 ----
    async def _safe_analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_context(context)
        decision = await self.analyze(context) or {}
        if not isinstance(decision, dict):
            decision = {"raw": decision}
        decision.setdefault("should_execute", True)
        decision.setdefault("mode", context.get("mode", AgentMode.NORMAL))
        return decision

    async def _safe_execute(self, decision: Dict[str, Any]) -> Any:
        return await self.execute(decision)

    def _validate_context(self, context: Dict[str, Any]) -> None:
        if "user_id" not in context:
            logger.warning(f"{self.agent_name} context 缺少 user_id")
        if "user_message" not in context and "payload" not in context:
            logger.warning(f"{self.agent_name} context 缺少 user_message/payload")

    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def _guard_concurrency(self, trace_id: str):
        await self._sema.acquire()
        try:
            yield
        finally:
            self._sema.release()

    # ---- 启停 ----
    def enable(self):
        self.enabled = True
        logger.info(f"✅ {self.agent_name} 已启用")

    def disable(self):
        self.enabled = False
        logger.info(f"⏸️ {self.agent_name} 已禁用")

    def is_enabled(self) -> bool:
        return self.enabled

# -------------------- 帮助函数：快速构造 MemoryRecord --------------------
def make_memory(
    user_id: str,
    type: MemoryType,
    content: str,
    importance: int = 5,
    related_event: Optional[str] = None,
    event_date: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    embedding: Optional[List[float]] = None,
) -> MemoryRecord:
    rid = hashlib.sha256((f"{type}::{content}").encode("utf-8")).hexdigest()
    return MemoryRecord(
        id=rid,
        user_id=user_id,
        type=type,
        content=content,
        importance=importance,
        related_event=related_event,
        event_date=event_date,
        embedding=embedding,
        timestamp=datetime.now().isoformat(),
        meta=meta or {}
    )
