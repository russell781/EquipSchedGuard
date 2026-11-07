"""管理后台接口：概览统计、知识库管理、提示词模板、对话审计。

全部路由仅管理员可访问（admin_required 接口级权限校验）。
"""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel

from . import kb_store, prompt_store, retrieval
from .database import execute, fetch_all, fetch_one, new_id, now_iso
from .errors import err_bad_file_type
from .security import admin_required

router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(admin_required)])


# ==================== 概览统计 ====================
@router.get("/stats")
async def stats():
    """后台首页统计卡与近 7 天问答量。"""
    doc = await fetch_one("SELECT COUNT(*) AS n FROM kb_documents WHERE status='active'")
    today = await fetch_one(
        "SELECT COUNT(*) AS n FROM messages WHERE role='user' AND created_at >= date('now')")
    flagged = await fetch_one("SELECT COUNT(*) AS n FROM conversations WHERE is_flagged=1")
    prompt = await prompt_store.get_active()
    week = await fetch_all(
        "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n FROM messages"
        " WHERE role='user' AND created_at >= date('now','-6 day')"
        " GROUP BY day ORDER BY day")
    return {"doc_count": doc["n"], "today_qa": today["n"],
            "flagged_count": flagged["n"], "prompt_version": prompt.get("version"),
            "week": [{"day": r["day"], "count": r["n"]} for r in week]}


# ==================== 知识库管理 ====================
@router.post("/kb/upload")
async def upload_document(file: UploadFile, user: dict = Depends(admin_required)):
    """上传制度文档：md/pdf → 存原文件 → 自动切片 → 向量化入库 → 刷新检索缓存。"""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".md", ".pdf"):
        raise err_bad_file_type()

    # 保存原文件到 data/kb_files（UUID 命名避免重名与路径注入）
    kb_store.FILES_DIR.mkdir(parents=True, exist_ok=True)
    save_path = kb_store.FILES_DIR / f"{new_id()}{suffix}"
    save_path.write_bytes(await file.read())

    # 提取文本并切片向量化
    if suffix == ".pdf":
        text = kb_store.extract_pdf(save_path)
    else:
        text = save_path.read_text(encoding="utf-8")
    doc_id, chunk_count = await kb_store.add_document(
        file.filename, suffix.lstrip("."), text, save_path, user["id"])
    await retrieval.load_documents()  # 刷新检索缓存，新制度立即生效
    await kb_store.write_audit(user["id"], "kb.upload", "kb_document", doc_id,
                               json.dumps({"doc_name": file.filename, "chunks": chunk_count},
                                          ensure_ascii=False))
    return {"doc_id": doc_id, "chunks": chunk_count}


@router.get("/kb/documents")
async def list_kb_documents():
    """制度文档列表（含切片数、上传人）。"""
    return {"items": await kb_store.list_documents()}


@router.delete("/kb/documents/{doc_id}")
async def delete_kb_document(doc_id: str, user: dict = Depends(admin_required)):
    """删除文档及其切片，检索缓存同步刷新。"""
    await kb_store.delete_document(doc_id)
    await retrieval.load_documents()
    await kb_store.write_audit(user["id"], "kb.delete", "kb_document", doc_id)
    return {"deleted": True}


@router.post("/kb/documents/{doc_id}/reindex")
async def reindex_kb_document(doc_id: str, user: dict = Depends(admin_required)):
    """重新切片 + 向量化（制度修订后使用）。"""
    n = await kb_store.reindex_document(doc_id)
    await retrieval.load_documents()
    await kb_store.write_audit(user["id"], "kb.reindex", "kb_document", doc_id)
    return {"doc_id": doc_id, "chunks": n}


# ==================== 提示词模板管理 ====================
class PromptIn(BaseModel):
    content: str  # 模板正文，支持 {{制度条文}} 占位符


@router.get("/prompts/active")
async def get_active_prompt():
    """当前生效模板。"""
    return await prompt_store.get_active()


@router.get("/prompts")
async def list_prompts():
    """历史版本列表。"""
    return {"items": await prompt_store.list_versions()}


@router.post("/prompts")
async def create_prompt(body: PromptIn, user: dict = Depends(admin_required)):
    """保存新模板并立即生效（旧版自动停用保留，可回滚）。"""
    version = await prompt_store.create_version(body.content, user["id"])
    await kb_store.write_audit(user["id"], "prompt.update", "prompt_template",
                               "", json.dumps({"version": version}))
    return {"version": version, "active": True}


@router.post("/prompts/{prompt_id}/activate")
async def activate_prompt(prompt_id: str, user: dict = Depends(admin_required)):
    """回滚到指定历史版本。"""
    await prompt_store.activate_version(prompt_id)
    await kb_store.write_audit(user["id"], "prompt.rollback", "prompt_template", prompt_id)
    return {"active": True}


# ==================== 对话审计 ====================
class FlagIn(BaseModel):
    remark: str = ""  # 标记备注


@router.get("/audit/employees")
async def audit_employees():
    """员工下拉数据源。"""
    rows = await fetch_all("SELECT id, display_name FROM users ORDER BY created_at")
    return {"items": [{"id": r["id"], "name": r["display_name"]} for r in rows]}


@router.get("/audit/conversations")
async def audit_conversations(employee_id: str = "", date_from: str = "",
                              date_to: str = "", flagged_only: bool = False,
                              page: int = 1):
    """按员工 / 时间范围 / 违规标记筛选对话记录（分页，每页 20 条）。"""
    where, params = ["1=1"], []
    if employee_id:
        where.append("c.user_id = ?")
        params.append(employee_id)
    if date_from:
        where.append("c.created_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("c.created_at <= ?")
        params.append(date_to + "T23:59:59")
    if flagged_only:
        where.append("c.is_flagged = 1")
    cond = " AND ".join(where)

    total = await fetch_one(f"SELECT COUNT(*) AS n FROM conversations c WHERE {cond}",
                            tuple(params))
    rows = await fetch_all(f"""
        SELECT c.id, c.title, c.created_at, c.updated_at, c.is_flagged, c.flag_remark,
               u.display_name AS employee,
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS msg_count
        FROM conversations c JOIN users u ON u.id = c.user_id
        WHERE {cond} ORDER BY c.updated_at DESC LIMIT 20 OFFSET ?""",
        tuple(params) + ((max(page, 1) - 1) * 20,))
    return {"total": total["n"], "page": page,
            "items": [dict(r) for r in rows]}


@router.get("/audit/conversations/{conv_id}/messages")
async def audit_messages(conv_id: str):
    """查看会话全部消息（含制度引用来源）。"""
    rows = await fetch_all(
        "SELECT role, content, kb_refs, created_at FROM messages"
        " WHERE conversation_id = ? AND role IN ('user','assistant') ORDER BY created_at ASC",
        (conv_id,))
    return {"items": [{
        "role": r["role"], "content": r["content"], "created_at": r["created_at"],
        "sources": json.loads(r["kb_refs"]) if r["kb_refs"] else [],
    } for r in rows]}


@router.post("/audit/conversations/{conv_id}/flag")
async def flag_conversation(conv_id: str, body: FlagIn,
                            user: dict = Depends(admin_required)):
    """标记疑似违规报销问答（会话级），留审计日志。"""
    await execute("UPDATE conversations SET is_flagged = 1, flag_remark = ? WHERE id = ?",
                  (body.remark, conv_id))
    await kb_store.write_audit(user["id"], "audit.flag", "conversation", conv_id, body.remark)
    return {"flagged": True}


@router.delete("/audit/conversations/{conv_id}/flag")
async def unflag_conversation(conv_id: str, user: dict = Depends(admin_required)):
    """取消违规标记，留审计日志。"""
    await execute("UPDATE conversations SET is_flagged = 0, flag_remark = NULL WHERE id = ?",
                  (conv_id,))
    await kb_store.write_audit(user["id"], "audit.unflag", "conversation", conv_id)
    return {"flagged": False}
