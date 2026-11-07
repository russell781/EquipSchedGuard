"""制度知识库检索：从数据库加载切片向量，按余弦相似度返回相关片段。

数据来源为 kb_documents / kb_chunks（管理后台可上传、删除），
每次上传/删除/重建后调用 load_documents() 刷新内存缓存，立即生效。

召回策略：向量余弦相似度为主，叠加“关键词字面命中”兜底——
当问句与制度块存在连续 2 字及以上重叠（术语/专名），即便向量得分偏低
也优先召回，避免“制度里明确写了但检索不到”的漏召回。
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


def _overlap_score(question: str, content: str) -> int:
    """关键词兜底：统计问句与制度块的连续 2 字重叠次数。

    用于在向量得分偏低时兜底召回（如短问句“排产优先级”命中制度原文
    同名词组）。返回值仅用于排序与召回判定，非向量相似度。
    """
    q = "".join(question.split())
    bigrams = {q[i:i + 2] for i in range(len(q) - 1)}
    c = "".join(content.split())
    return sum(1 for bg in bigrams if bg in c)


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
            overlap = _overlap_score(question, chunk["content"])
            # 命中条件：向量相似度达标，或存在明显的字面术语重叠（兜底召回）
            if score > 0.05 or overlap >= 2:
                scored.append((score, overlap, chunk))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [{
            "doc_name": c["doc_name"],
            "snippet": c["content"][:200],  # 截断便于前端展示
            "chunk_id": c["chunk_id"],
        } for _, _, c in scored[:top_k]]
    except Exception:
        raise err_retrieve()
