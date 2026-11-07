"""路由：登录、员工问答（SSE 流式）、执行循环、会话列表与历史消息。"""
import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from .agent_loop import AgentLoop
from .agent_orchestrator import route_skill
from .config import HISTORY_ROUNDS
from .database import execute, fetch_all, fetch_one, new_id, now_iso
from .errors import (AppError, err_forbidden, err_session_not_found, error_body)
from .llm import stream_chat
from .prompt_store import render
from .retrieval import search
from .routes_agent import get_agent_service
from .schemas import ChatIn, LoginIn
from .security import create_token, login_required, verify_password

router = APIRouter(prefix="/api/v1")


def sse_frame(event: str, data: dict) -> str:
    """组装一帧 SSE 消息（event + JSON data）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------- 登录 ----------------
@router.post("/auth/login")
async def login(body: LoginIn):
    """账号密码登录：返回 JWT 并同时写入 HttpOnly Cookie（供服务端渲染页面鉴权）。"""
    row = await fetch_one("SELECT * FROM users WHERE username = ? AND is_active = 1",
                          (body.username,))
    if row is None or not verify_password(body.password, row["password_hash"]):
        # 统一提示，不区分“用户不存在”与“密码错误”，避免账号枚举
        raise AppError(401, 40101, "用户名或密码错误")
    token = create_token(row["id"], row["role"])
    resp = JSONResponse({"token": token,
                         "user": {"display_name": row["display_name"], "role": row["role"]}})
    # Cookie 用于管理后台 SSR 页面；员工端仍用响应里的 token（localStorage + Bearer 头）
    resp.set_cookie("token", token, httponly=True, samesite="lax", max_age=720 * 60)
    return resp


@router.get("/auth/me")
async def me(user: dict = Depends(login_required)):
    """返回当前登录用户信息（前端角色判断与顶栏显示）。"""
    return {"user": user}


# ---------------- 员工问答（SSE） ----------------
@router.post("/chat")
async def chat(body: ChatIn, user: dict = Depends(login_required)):
    """问答主接口：先落库用户消息，再以 SSE 流式返回回答。"""
    question = body.question
    session_id = body.session_id

    if session_id is None:
        # 未传 session_id：自动创建新会话，标题取问题前 20 字
        session_id = new_id()
        await execute(
            "INSERT INTO conversations(id, user_id, title, created_at, updated_at)"
            " VALUES(?,?,?,?,?)",
            (session_id, user["id"], question[:20], now_iso(), now_iso()))
        history = []
    else:
        # 校验会话存在且归属当前用户
        conv = await fetch_one("SELECT * FROM conversations WHERE id = ?", (session_id,))
        if conv is None:
            raise err_session_not_found()
        if conv["user_id"] != user["id"]:
            raise err_forbidden()
        # 取最近 6 轮历史（12 条，不含本次提问），反转为时间正序
        rows = await fetch_all(
            "SELECT role, content FROM messages WHERE conversation_id = ?"
            " AND role IN ('user','assistant') ORDER BY created_at DESC LIMIT ?",
            (session_id, HISTORY_ROUNDS * 2))
        history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # 用户消息先落库（即使后续大模型失败，提问记录也保留）
    await execute(
        "INSERT INTO messages(id, conversation_id, role, content, created_at)"
        " VALUES(?,?,?,?,?)", (new_id(), session_id, "user", question, now_iso()))
    await execute("UPDATE conversations SET updated_at = ? WHERE id = ?",
                  (now_iso(), session_id))

    async def event_stream():
        """SSE 生成器：meta → status → token×N → sources → done。"""
        answer_parts: list[str] = []  # 累积完整回答，用于落库
        try:
            # 1) 元信息帧：会话与消息标识
            message_id = new_id()
            yield sse_frame("meta", {"session_id": session_id, "message_id": message_id})

            # 2) 状态帧：提示前端“正在检索制度…”
            yield sse_frame("status", {"stage": "retrieving", "text": "正在检索制度…"})

            # 3) 检索制度片段（检索失败时发送 error 帧并终止）
            sources = search(question)

            # 3.5) 智能体执行循环：先用意图路由判断是否命中排产/设备操作意图。
            #      命中则走受约束的决策循环（快照→校验→建草稿前人工确认→仿真→结果校验→提交审批）；
            #      未命中（纯制度问答）走下方原 RAG 流程，不进入循环。
            if route_skill(question) is not None:
                loop = AgentLoop(get_agent_service(), max_rounds=8)
                loop_result = await asyncio.to_thread(
                    loop.run, question, user["id"], session_id)
                answer = loop_result.get("text", "")
                if loop_result.get("status") == "AWAITING_CONFIRMATION":
                    preview = loop_result.get("draft_preview", {})
                    answer = (
                        "检测到需要创建排产草稿，请先确认以下草稿内容：\n"
                        + json.dumps(preview, ensure_ascii=False, indent=2)
                        + "\n\n确认后系统才会继续仿真、校验并提交审批；"
                        "确认令牌：" + loop_result.get("pending_token", "")
                    )
                for i in range(0, len(answer), 24):
                    chunk = answer[i:i + 24]
                    answer_parts.append(chunk)
                    yield sse_frame("token", {"text": chunk})
                await execute(
                    "INSERT INTO messages(id, conversation_id, role, content, kb_refs, created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (message_id, session_id, "assistant", "".join(answer_parts),
                     json.dumps(loop_result.get("sources", []), ensure_ascii=False), now_iso()))
                yield sse_frame("sources", {"items": loop_result.get("sources", [])})
                yield sse_frame("done", {
                    "finish_reason": "stop",
                    "agent_status": loop_result.get("status"),
                    "rounds": loop_result.get("rounds", []),
                    "pending_token": loop_result.get("pending_token"),
                })
                return

            # 4) 组装大模型消息：系统提示词从数据库当前生效模板渲染（含制度条文注入），
            #    再加最近 6 轮历史与当前问题
            messages = [{"role": "system", "content": await render(sources)}]
            messages.extend(history)
            messages.append({"role": "user", "content": question})

            # 5) 调大模型并逐段转发 token 帧
            async for chunk in stream_chat(messages):
                answer_parts.append(chunk)
                yield sse_frame("token", {"text": chunk})

            answer = "".join(answer_parts)

            # 6) 完整回答落库（含引用来源），随后发送 sources 与 done 帧
            await execute(
                "INSERT INTO messages(id, conversation_id, role, content, kb_refs, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (message_id, session_id, "assistant", answer,
                 json.dumps(sources, ensure_ascii=False), now_iso()))
            yield sse_frame("sources", {"items": sources})
            yield sse_frame("done", {"finish_reason": "stop", "token_usage": None})

        except AppError as exc:
            # 业务异常（大模型失败 / 检索失败）：以 error 帧告知前端
            yield sse_frame("error", error_body(exc.code, exc.message))
        except Exception:
            # 兜底异常：不暴露内部细节
            yield sse_frame("error", error_body(50000, "服务器内部错误，请联系管理员"))

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})  # 禁用代理缓冲，保证实时性


# ---------------- 会话列表（侧边栏） ----------------
@router.get("/sessions")
async def list_sessions(user: dict = Depends(login_required)):
    """当前用户的会话列表，按最近活跃倒序。"""
    rows = await fetch_all(
        "SELECT id, title, updated_at FROM conversations"
        " WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 50",
        (user["id"],))
    return {"items": [{"session_id": r["id"], "title": r["title"],
                       "updated_at": r["updated_at"]} for r in rows]}


# ---------------- 历史消息（刷新后恢复） ----------------
@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str, user: dict = Depends(login_required)):
    """加载指定会话的历史消息（时间正序），assistant 消息附带引用来源。"""
    conv = await fetch_one("SELECT * FROM conversations WHERE id = ?", (session_id,))
    if conv is None:
        raise err_session_not_found()
    if conv["user_id"] != user["id"]:
        raise err_forbidden()

    rows = await fetch_all(
        "SELECT role, content, kb_refs FROM messages"
        " WHERE conversation_id = ? AND role IN ('user','assistant')"
        " ORDER BY created_at ASC", (session_id,))
    items = []
    for r in rows:
        item = {"role": r["role"], "content": r["content"]}
        if r["role"] == "assistant":
            # kb_refs 以 JSON 字符串存储，这里还原为数组
            item["sources"] = json.loads(r["kb_refs"]) if r["kb_refs"] else []
        items.append(item)
    return {"items": items}
