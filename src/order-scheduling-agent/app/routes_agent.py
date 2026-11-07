"""智能体受控工具 API：工具清单、Skill 执行、执行循环、工具审计与决策日志。"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .agent_loop import AgentLoop
from .agent_orchestrator import AgentOrchestrator
from .agent_repository import SQLiteAgentRepository
from .agent_service import AgentService, AgentToolError
from .agent_tools import execute_agent_tool, public_tool_manifest
from .errors import AppError
from .security import admin_required, login_required

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

_AGENT_SERVICE: AgentService | None = None
# 应用级执行循环：保存挂起的人工确认上下文，使 run/confirm 跨请求可衔接
_AGENT_LOOP: AgentLoop | None = None


def get_agent_service() -> AgentService:
    """应用级智能体服务（SQLite 持久化），避免每次请求重建连接池。"""
    global _AGENT_SERVICE
    if _AGENT_SERVICE is None:
        _AGENT_SERVICE = AgentService(SQLiteAgentRepository())
    return _AGENT_SERVICE


def get_agent_loop() -> AgentLoop:
    """应用级执行循环；与智能体服务共享同一仓储，保证状态一致。"""
    global _AGENT_LOOP
    if _AGENT_LOOP is None:
        _AGENT_LOOP = AgentLoop(get_agent_service(), max_rounds=8)
    return _AGENT_LOOP


def _app_error(exc: AgentToolError) -> AppError:
    """把状态机字符串错误码转换为统一 {code,message,detail} 响应。"""
    mapping = {
        "BAD_REQUEST": (400, 40020),
        "FORBIDDEN": (403, 40320),
        "NOT_FOUND": (404, 40420),
        "VALIDATION_FAILED": (422, 42220),
        "PRECONDITION_FAILED": (409, 40920),
        "STATE_CONFLICT": (409, 40921),
        "STALE_FACTS": (409, 40922),
        "EXPIRED": (409, 40923),
    }
    http_status, code = mapping.get(exc.code, (500, 50020))
    return AppError(http_status, code, exc.message, exc.detail)


class AgentToolCallIn(BaseModel):
    """单个 Function Calling 工具执行请求。"""

    skill: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentRunIn(BaseModel):
    """自然语言编排请求；返回是否命中智能体工具链。"""

    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class StaleIn(BaseModel):
    """事实变化通知；只用于模拟 ERP/MES/Webhook 使快照失效。"""

    reason: str = Field(min_length=2, max_length=500)


class LoopRunIn(BaseModel):
    """执行循环发起请求。"""

    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    skill: str = Field(default="schedule_change", max_length=64)


class LoopConfirmIn(BaseModel):
    """员工对挂起的建草稿请求做出确认。"""

    pending_token: str = Field(min_length=1, max_length=128)
    confirmed: bool = False


class ApprovalIn(BaseModel):
    """管理员审批操作。"""

    comment: str = Field(default="", max_length=500)


@router.get("/manifest")
async def agent_manifest(user: dict = Depends(login_required)):
    """查看模型可见工具、Skill 白名单与系统提示词约束。"""
    return public_tool_manifest()


@router.post("/tools/{tool_name}/execute")
async def call_agent_tool(tool_name: str, body: AgentToolCallIn,
                          user: dict = Depends(login_required)):
    """执行一个受 Skill 白名单约束的工具；身份由登录态注入，参数不能伪造。"""
    try:
        result = await asyncio.to_thread(
            execute_agent_tool, get_agent_service(), body.skill, tool_name,
            body.arguments, user["id"])
        return {"status": "SUCCESS", "result": result}
    except AgentToolError as exc:
        raise _app_error(exc)


@router.post("/run")
async def run_agent(body: AgentRunIn, user: dict = Depends(login_required)):
    """自然语言智能体入口：命中操作意图则自动执行受约束工具链。"""
    orchestrator = AgentOrchestrator(get_agent_service())
    result = await asyncio.to_thread(
        orchestrator.maybe_run, body.question, user["id"], body.session_id)
    if result is None:
        return {"handled": False, "message": "普通制度问答，未进入写工具链"}
    return {"handled": True, "result": result}


@router.get("/audits")
async def list_agent_audits(limit: int = 100, user: dict = Depends(admin_required)):
    """管理员查看智能体工具调用审计（追加式记录，不能修改）。"""
    limit = min(max(limit, 1), 500)
    return {"items": get_agent_service().list_tool_audits(limit=limit)}


@router.post("/loop/run")
async def loop_run(body: LoopRunIn, user: dict = Depends(login_required)):
    """发起一次受约束的执行循环（决策→执行→回填→再决策，最多 5 轮）。

    返回 status：
    - FINAL / PENDING_APPROVAL：已给出结果或已提交审批
    - AWAITING_CONFIRMATION：停在建草稿前，等待员工确认
    - MAX_ROUNDS / FAILED：超限或护栏错误
    """
    result = await asyncio.to_thread(
        get_agent_loop().run, body.question, user["id"], body.session_id)
    return {"handled": True, "result": result}


@router.post("/loop/confirm")
async def loop_confirm(body: LoopConfirmIn, user: dict = Depends(login_required)):
    """员工确认或拒绝建草稿。

    confirmed=True  → 继续执行建草稿→仿真→校验→提交审批
    confirmed=False → 取消，不建草稿
    """
    result = await asyncio.to_thread(
        get_agent_loop().confirm, body.pending_token, body.confirmed, user["id"])
    return {"result": result}


@router.get("/decisions")
async def list_decision_logs(limit: int = 100, user: dict = Depends(admin_required)):
    """管理员查看执行循环的决策日志（每轮：工具名、参数、耗时、结果摘要）。"""
    limit = min(max(limit, 1), 500)
    return {"items": get_agent_service().list_decision_logs(limit=limit)}


@router.post("/snapshots/{snapshot_id}/stale")
async def mark_snapshot_stale(snapshot_id: str, body: StaleIn,
                              user: dict = Depends(admin_required)):
    """模拟外部事实变化使快照失效；这是管理 / Webhook 接口，不开放给模型。"""
    try:
        result = await asyncio.to_thread(
            get_agent_service().mark_snapshot_stale, snapshot_id, body.reason, user["id"])
        return {"stale": True, "snapshot": result}
    except AgentToolError as exc:
        raise _app_error(exc)


# ---------------- 审批与当日计划（仅管理员，不注册给模型） ----------------
@router.get("/change-requests")
async def list_change_requests(status: str | None = None,
                               user: dict = Depends(admin_required)):
    """管理员查看待审批/全部变更单。"""
    items = await asyncio.to_thread(
        get_agent_service().list_change_requests, user["id"], status)
    return {"items": items}


@router.post("/change-requests/{change_request_id}/approve")
async def approve_change_request(change_request_id: str, body: ApprovalIn,
                                 user: dict = Depends(admin_required)):
    """管理员审批同意：生成当日计划生效记录。"""
    try:
        plan = await asyncio.to_thread(
            get_agent_service().approve_change_request,
            change_request_id, body.comment, user["id"])
        return {"approved": True, "plan": plan}
    except AgentToolError as exc:
        raise _app_error(exc)


@router.post("/change-requests/{change_request_id}/reject")
async def reject_change_request(change_request_id: str, body: ApprovalIn,
                                user: dict = Depends(admin_required)):
    """管理员审批拒绝：草稿置为已驳回，不生效。"""
    try:
        result = await asyncio.to_thread(
            get_agent_service().reject_change_request,
            change_request_id, body.comment, user["id"])
        return {"rejected": True, "change_request": result}
    except AgentToolError as exc:
        raise _app_error(exc)


@router.get("/daily-plans")
async def list_daily_plans(user: dict = Depends(admin_required)):
    """管理员查看已生效的当日计划。"""
    items = await asyncio.to_thread(get_agent_service().list_daily_plans, user["id"])
    return {"items": items}
