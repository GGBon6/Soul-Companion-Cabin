"""
向量操作实现
支持 DashScope 和简单文本相似度的回退机制
"""

import hashlib
import math
from typing import List
from app.core import settings, logger

# 尝试导入向量化库
try:
    import dashscope
    from http import HTTPStatus
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False


class SimpleVectorOps:
    """向量操作实现，支持 DashScope 和简单回退"""
    
    def __init__(self):
        self.use_dashscope = False
        
        if DASHSCOPE_AVAILABLE and settings.DASHSCOPE_API_KEY:
            try:
                dashscope.api_key = settings.DASHSCOPE_API_KEY
                self.use_dashscope = True
                logger.info("✅ VectorOps: 使用 DashScope 向量化")
            except Exception as e:
                logger.warning(f"DashScope 初始化失败: {e}")
        
        if not self.use_dashscope:
            logger.info("⚠️ VectorOps: 使用简单文本相似度（无向量化）")
    
    def embed(self, text: str) -> List[float]:
        """文本转向量嵌入"""
        if not text or not text.strip():
            return []
            
        if self.use_dashscope:
            try:
                response = dashscope.TextEmbedding.call(
                    model=dashscope.TextEmbedding.Models.text_embedding_v2,
                    input=text.strip()
                )
                if response.status_code == HTTPStatus.OK:
                    return response.output['embeddings'][0]['embedding']
                else:
                    logger.error(f"DashScope 向量化失败: {response.message}")
            except Exception as e:
                logger.error(f"DashScope 向量化异常: {e}")
        
        # 回退到简单的文本哈希向量
        return self._text_to_hash_vector(text)
    
    def similarity(self, a: List[float], b: List[float]) -> float:
        """计算向量相似度（余弦相似度）"""
        if not a or not b or len(a) != len(b):
            return 0.0
        
        try:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            return dot / (norm_a * norm_b)
        except Exception as e:
            logger.error(f"计算向量相似度失败: {e}")
            return 0.0
    
    def _text_to_hash_vector(self, text: str, dim: int = 128) -> List[float]:
        """将文本转换为基于哈希的向量表示"""
        # 使用 MD5 哈希生成固定维度向量
        hash_obj = hashlib.md5(text.encode('utf-8'))
        hash_bytes = hash_obj.digest()
        
        # 将哈希字节转换为归一化的浮点向量
        vector = []
        for i in range(dim):
            byte_idx = i % len(hash_bytes)
            # 将字节值 [0,255] 映射到 [-1,1]
            normalized_val = (hash_bytes[byte_idx] - 127.5) / 127.5
            vector.append(normalized_val)
        
        return vector
