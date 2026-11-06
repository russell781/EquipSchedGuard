"""制度知识库检索：从数据库加载切片向量，按余弦相似度返回相关片段。

数据来源为 kb_documents / kb_chunks（管理后台可上传、删除），
每次上传/删除/重建后调用 load_documents() 刷新内存缓存，立即生效。
"""
import json
import math

from .database import fetch_all
from .errors import err_retrieve
from .kb_store import embed

# 内存切片缓存：[{chunk_id, doc_name, content, embedding}]
_CHUNKS: list[dict] = []


async def load_documents():
    """从数据库加载全部生效文档的切片与向量。"""
    rows = await fetch_all("""
        SELECT c.id, c.content, c.embedding, d.doc_name
        FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
        WHERE d.status = 'active'""")
    _CHUNKS.clear()
    for r in rows:
        _CHUNKS.append({
            "chunk_id": r["id"],
            "doc_name": r["doc_name"],
            "content": r["content"],
            "embedding": json.loads(r["embedding"]) if r["embedding"] else None,
        })


def _cosine(a: list[float], b: list[float]) -> float:
    """两个已归一化向量的点积即余弦相似度。"""
    return math.fsum(x * y for x, y in zip(a, b))


def search(question: str, top_k: int = 3) -> list[dict]:
    """检索与问题最相关的制度片段，按相关度降序，最多 top_k 条。

    检索不到时返回空列表（不视为错误）；异常统一转为 50002。
    """
    try:
        if not _CHUNKS:
            return []
        q_vec = embed(question)
        scored = []
        for chunk in _CHUNKS:
            if not chunk["embedding"]:
                continue
            score = _cosine(q_vec, chunk["embedding"])
            if score > 0.05:  # 过滤弱相关片段
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{
            "doc_name": c["doc_name"],
            "snippet": c["content"][:200],  # 截断便于前端展示
            "chunk_id": c["chunk_id"],
        } for _, c in scored[:top_k]]
    except Exception:
        raise err_retrieve()
