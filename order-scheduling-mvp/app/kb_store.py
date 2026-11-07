"""知识库存储：文档上传解析、自动切片、离线向量化入库、删除与重建索引。

向量化说明：采用离线 n-gram（unigram + bigram 加权）哈希向量（512 维，L2 归一化），
使用 FNV-1a 稳定哈希（跨进程、跨平台结果一致，不依赖 Python 内置 hash 的随机盐），
无需外部 Embedding 服务即可演示“向量化入库 + 相似度检索”全流程；
后续若接入真实 Embedding 服务，仅需替换 embed() 并重建索引。
"""
import json
from pathlib import Path

from .config import KB_DIR
from .database import connect, execute, fetch_all, fetch_one, new_id, now_iso
from .errors import err_doc_not_found, err_pdf_parse

# 原文件保存目录（data/kb_files）
FILES_DIR = Path(__file__).resolve().parent.parent / "data" / "kb_files"
VEC_DIM = 512  # 离线向量维度

# n-gram 权重：unigram 保障短问句（如“排产优先级”）与单字术语的召回，
# bigram 提供词序信息以提升区分度。二者叠加后共同归一化。
UNIGRAM_WEIGHT = 1.0
BIGRAM_WEIGHT = 1.5


def _fnv1a(s: str) -> int:
    """FNV-1a 稳定哈希（64 位）：跨进程、跨平台确定性一致。

    替代 Python 内置 hash()（对 str 采用随机盐，进程重启后结果不同），
    确保“入库向量”与“查询向量”使用同一套哈希桶，检索结果可复现。
    """
    h = 0xCBF29CE484222325
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def embed(text: str) -> list[float]:
    """离线向量化：unigram + bigram 稳定哈希到 512 维并做 L2 归一化。"""
    text = "".join(text.split())
    vec = [0.0] * VEC_DIM
    for i in range(len(text) - 1):
        vec[_fnv1a(text[i:i + 2]) % VEC_DIM] += BIGRAM_WEIGHT
    for ch in text:
        vec[_fnv1a(ch) % VEC_DIM] += UNIGRAM_WEIGHT
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm else vec


def split_text(text: str) -> list[str]:
    """制度文档切片：按空行分块，过滤过短碎片。"""
    return [b.strip() for b in text.split("\n\n") if len(b.strip()) >= 20]


def extract_pdf(file_path: Path) -> str:
    """提取 PDF 文本（仅支持文本型 PDF，扫描件会抛中文错误）。"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if len(text.strip()) < 20:
            raise err_pdf_parse()
        return text
    except Exception as exc:
        from .errors import AppError
        if isinstance(exc, AppError):
            raise
        raise err_pdf_parse()


async def add_document(doc_name: str, doc_type: str, text: str,
                       file_path: Path, uploaded_by: str) -> tuple[str, int]:
    """新增制度文档：写元数据 → 切片 → 逐块向量化入库，返回 (文档ID, 切片数)。"""
    blocks = split_text(text)
    doc_id = new_id()
    ts = now_iso()
    db = await connect()
    try:
        await db.execute(
            "INSERT INTO kb_documents(id, doc_name, doc_type, file_path, uploaded_by, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (doc_id, doc_name, doc_type, str(file_path), uploaded_by, ts))
        for idx, block in enumerate(blocks):
            await db.execute(
                "INSERT INTO kb_chunks(id, document_id, chunk_index, content, embedding, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (new_id(), doc_id, idx, block,
                 json.dumps(embed(block)), ts))
        await db.commit()
    finally:
        await db.close()
    return doc_id, len(blocks)


async def list_documents() -> list[dict]:
    """文档列表（含切片数与上传人姓名），按上传时间倒序。"""
    rows = await fetch_all("""
        SELECT d.id, d.doc_name, d.doc_type, d.version, d.created_at,
               u.display_name AS uploader,
               (SELECT COUNT(*) FROM kb_chunks c WHERE c.document_id = d.id) AS chunk_count
        FROM kb_documents d LEFT JOIN users u ON u.id = d.uploaded_by
        WHERE d.status = 'active' ORDER BY d.created_at DESC""")
    return [dict(r) for r in rows]


async def delete_document(doc_id: str):
    """删除文档：元数据置 deleted、物理删除切片（检索立即不再命中）。"""
    doc = await fetch_one("SELECT * FROM kb_documents WHERE id = ? AND status = 'active'",
                          (doc_id,))
    if doc is None:
        raise err_doc_not_found()
    db = await connect()
    try:
        await db.execute("DELETE FROM kb_chunks WHERE document_id = ?", (doc_id,))
        await db.execute("UPDATE kb_documents SET status = 'deleted' WHERE id = ?", (doc_id,))
        await db.commit()
    finally:
        await db.close()


async def reindex_document(doc_id: str) -> int:
    """重新切片 + 向量化（制度原文修订后使用），返回新切片数。"""
    doc = await fetch_one("SELECT * FROM kb_documents WHERE id = ? AND status = 'active'",
                          (doc_id,))
    if doc is None:
        raise err_doc_not_found()
    path = Path(doc["file_path"])
    text = extract_pdf(path) if doc["doc_type"] == "pdf" else path.read_text(encoding="utf-8")
    blocks = split_text(text)
    db = await connect()
    try:
        await db.execute("DELETE FROM kb_chunks WHERE document_id = ?", (doc_id,))
        for idx, block in enumerate(blocks):
            await db.execute(
                "INSERT INTO kb_chunks(id, document_id, chunk_index, content, embedding, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (new_id(), doc_id, idx, block, json.dumps(embed(block)), now_iso()))
        await db.commit()
    finally:
        await db.close()
    return len(blocks)


async def seed_from_files(uploaded_by: str | None = None):
    """首次启动：若库中无文档，把 knowledge_base/ 目录的示例制度导入数据库。"""
    row = await fetch_one("SELECT COUNT(*) AS n FROM kb_documents")
    if row["n"] > 0 or not KB_DIR.exists():
        return
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(KB_DIR.iterdir()):
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        await add_document(path.name, "md", path.read_text(encoding="utf-8"),
                           path, uploaded_by)


async def write_audit(actor_id: str | None, action: str,
                      target_type: str = "", target_id: str = "", detail: str = ""):
    """追加一条管理操作审计日志。"""
    await execute(
        "INSERT INTO audit_logs(actor_id, action, target_type, target_id, detail, created_at)"
        " VALUES(?,?,?,?,?,?)",
        (actor_id, action, target_type, target_id, detail, now_iso()))
