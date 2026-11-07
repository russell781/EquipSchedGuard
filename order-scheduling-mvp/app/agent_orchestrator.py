"""聊天入口的智能体编排器。

当前大模型客户端尚未启用原生 function calling，因此第一阶段采用
“确定性意图路由 + 服务端工具链”的编排：模型负责表达，工具链负责决策边界。
后续接入支持 tools 的模型时，可直接复用 agent_tools.py 中的同一份规范。
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from .agent_service import AgentService, AgentToolError
from .agent_tools import execute_agent_tool


SCHEDULE_ACTION_RE = re.compile(
    r"(帮我|请|需要|立即|我要|发起|上报|报|创建|生成|调整|重排|安排).{0,24}(插单|排产|排单|计划|订单|异常)")
EQUIPMENT_ACTION_RE = re.compile(
    r"(设备|机台|机床).{0,24}(异常|故障|停机)")
EQUIPMENT_IMPACT_RE = re.compile(r"(评估|分析|处理|影响)")
MERGE_QUESTION_RE = re.compile(r"(加入|并入|合并|能否|可以吗|可以加入)")
ORDER_RE = re.compile(r"\b[A-Z]{1,6}-\d{3,}\b")
DATE_RE = re.compile(r"20\d{2}-\d{1,2}-\d{1,2}")
QTY_RE = re.compile(r"(?:数量|工单量|件数)?\s*(\d{1,6})\s*(?:件|个|台)")
EXCEPTION_RE = re.compile(r"\bEQ-EX-\d{3,}\b")


def route_skill(question: str) -> str | None:
    """识别需要进入智能体工具链的意图；普通制度问答返回 None。"""
    if EQUIPMENT_ACTION_RE.search(question) and EQUIPMENT_IMPACT_RE.search(question):
        return "equipment_exception"
    # 插单能否合并/加入原订单：需要校验事实后给结论，也算业务意图
    if MERGE_QUESTION_RE.search(question) and ORDER_RE.search(question):
        return "schedule_change"
    if SCHEDULE_ACTION_RE.search(question):
        return "schedule_change"
    return None


def _normalize_date(raw: str) -> str:
    """把 2026-11-7 这类日期规范为 YYYY-MM-DD。"""
    year, month, day = raw.split("-")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _idem(prefix: str, run_id: str) -> str:
    """基于本次编排运行的唯一标识生成幂等键。

    每次智能体编排（maybe_run）都会生成一个 run_id，同一 run_id 内的重试
    会被去重；不同 run_id（即用户再次发起）则生成全新草稿，避免把历史已
    仿真 / 已提交的草稿误当成“可重复仿真”的新草稿。
    """
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:24]}"


def _need_input(skill: str, missing: list[str], text: str) -> dict[str, Any]:
    """信息不足时不猜测，返回需要补充的字段。"""
    return {
        "skill": skill,
        "status": "NEED_INPUT",
        "missing_fields": missing,
        "text": text,
        "tool_trace": [],
        "sources": [],
    }


def _failure(skill: str, exc: AgentToolError,
             trace: list[dict[str, Any]]) -> dict[str, Any]:
    """把工具护栏错误转成对用户友好的中断说明。"""
    return {
        "skill": skill,
        "status": "FAILED",
        "error_code": exc.code,
        "text": f"已停止本次操作：{exc.message}。请修正后重新发起，系统不会跳过校验继续执行。",
        "tool_trace": trace,
        "sources": [],
    }


class AgentOrchestrator:
    """按 Skill 白名单执行工具链，保证聊天入口也受同一状态机约束。"""

    def __init__(self, service: AgentService) -> None:
        self.service = service

    def maybe_run(self, question: str, actor_id: str,
                  session_id: str | None = None) -> dict[str, Any] | None:
        """如果是业务操作意图则执行；普通问答返回 None，交给原 RAG 流程。"""
        skill = route_skill(question)
        if skill is None:
            return None
        if skill == "equipment_exception":
            return self._run_equipment(question, actor_id, session_id)
        return self._run_schedule(question, actor_id, session_id)

    def _run_schedule(self, question: str, actor_id: str,
                      session_id: str | None) -> dict[str, Any]:
        """执行排产变更完整链路，直到提交人工审批。"""
        run_id = str(uuid4())
        orders = ORDER_RE.findall(question)
        dates = [_normalize_date(x) for x in DATE_RE.findall(question)]
        qty_match = QTY_RE.search(question)
        missing = []
        if not orders:
            missing.append("订单号")
        if not dates:
            missing.append("请求交期（YYYY-MM-DD）")
        if not qty_match:
            missing.append("数量")
        if missing:
            return _need_input(
                "schedule_change", missing,
                "我可以继续创建排产变更草稿，但不会猜测关键业务字段。请补充："
                + "、".join(missing) + "。")

        trace: list[dict[str, Any]] = []
        try:
            plan_date = (date.today() + timedelta(days=1)).isoformat()
            snapshot = execute_agent_tool(
                self.service, "schedule_change", "get_planning_snapshot", {
                    "plan_date": plan_date,
                    "order_ids": orders,
                    "base_plan_id": "PLAN-CURRENT",
                }, actor_id, session_id)
            trace.append({"tool": "get_planning_snapshot", "id": snapshot["snapshot_id"]})

            strategy = "MIN_CHANGEOVER" if "换型" in question else "DUE_DATE_FIRST"
            weights = {"due_date": 0.6, "changeover": 0.25, "utilization": 0.15}
            if strategy == "MIN_CHANGEOVER":
                weights = {"due_date": 0.45, "changeover": 0.4, "utilization": 0.15}
            validation = execute_agent_tool(
                self.service, "schedule_change", "validate_planning_request", {
                    "snapshot_id": snapshot["snapshot_id"],
                    "request_type": "INSERT_ORDER" if "插单" in question else "CHANGE_DELIVERY",
                    "requested_change": {
                        "order_id": orders[0],
                        "requested_delivery_date": dates[-1],
                        "quantity": int(qty_match.group(1)),
                        "reason": question[:500],
                    },
                    "objective_weights": weights,
                }, actor_id, session_id)
            trace.append({"tool": "validate_planning_request", "id": validation["validation_id"],
                          "status": validation["status"]})
            if validation["status"] != "PASS":
                return {
                    "skill": "schedule_change",
                    "status": "VALIDATION_FAILED",
                    "text": "输入校验未通过：" + "；".join(validation["failures"]),
                    "tool_trace": trace,
                    "sources": [],
                }

            draft = execute_agent_tool(
                self.service, "schedule_change", "create_schedule_draft", {
                    "validation_id": validation["validation_id"],
                    "strategy": strategy,
                    "reason": question[:500],
                    "idempotency_key": _idem("draft", run_id),
                }, actor_id, session_id)
            trace.append({"tool": "create_schedule_draft", "id": draft["draft_id"]})

            simulation = execute_agent_tool(
                self.service, "schedule_change", "simulate_schedule", {
                    "draft_id": draft["draft_id"],
                    "solver_profile": strategy,
                }, actor_id, session_id)
            trace.append({"tool": "simulate_schedule", "id": simulation["simulation_id"]})

            result_validation = execute_agent_tool(
                self.service, "schedule_change", "validate_schedule_draft", {
                    "draft_id": draft["draft_id"],
                    "simulation_id": simulation["simulation_id"],
                }, actor_id, session_id)
            trace.append({"tool": "validate_schedule_draft",
                          "id": result_validation["result_validation_id"],
                          "status": result_validation["status"]})
            if result_validation["status"] != "PASS":
                return {
                    "skill": "schedule_change",
                    "status": "VALIDATION_FAILED",
                    "text": "结果校验未通过：" + "；".join(result_validation["failures"]),
                    "tool_trace": trace,
                    "sources": [],
                }

            change = execute_agent_tool(
                self.service, "schedule_change", "submit_change_request", {
                    "draft_id": draft["draft_id"],
                    "result_validation_id": result_validation["result_validation_id"],
                    "explanation": "由智能体完成快照、校验、草稿、仿真与结果校验后提交审批。",
                    "idempotency_key": _idem("submit", run_id),
                }, actor_id, session_id)
            trace.append({"tool": "submit_change_request",
                          "id": change["change_request_id"], "status": change["status"]})
            policies = execute_agent_tool(
                self.service, "schedule_change", "search_policies", {
                    "query": "插单 变更 审批 生效计划", "top_k": 3,
                }, actor_id, session_id)

            kpi = simulation["kpis"]
            text = (
                "已完成受约束的排产变更流程：\n"
                f"1. 事实快照：{snapshot['snapshot_id']}（版本 {snapshot['facts_version']}）\n"
                f"2. 排产草稿：{draft['draft_id']}，策略 {strategy}\n"
                f"3. 仿真结果：准交率 {kpi['on_time_rate']:.0%}，"
                f"换型 {kpi['changeover_count']} 次，利用率 {kpi['equipment_utilization']:.0%}\n"
                f"4. 已提交审批：{change['change_request_id']}\n\n"
                "当前状态是“待人工审批”，尚未生效，也不会直接写回 MES。"
                "只有审批人电子签核后，系统后端才会执行版本冻结与生效。"
            )
            return {
                "skill": "schedule_change",
                "status": "PENDING_APPROVAL",
                "text": text,
                "tool_trace": trace,
                "change_request": change,
                "sources": policies,
            }
        except AgentToolError as exc:
            return _failure("schedule_change", exc, trace)

    def _run_equipment(self, question: str, actor_id: str,
                       session_id: str | None) -> dict[str, Any]:
        """设备异常只做真实异常单读取与影响分析，不控制设备。"""
        run_id = str(uuid4())
        exception_match = EXCEPTION_RE.search(question)
        orders = ORDER_RE.findall(question)
        missing = []
        if not exception_match:
            missing.append("设备异常单号（如 EQ-EX-001）")
        if not orders:
            missing.append("受影响订单号")
        if missing:
            return _need_input(
                "equipment_exception", missing,
                "我可以分析设备异常影响，但不会虚构报警或订单。请补充："
                + "、".join(missing) + "。")

        trace: list[dict[str, Any]] = []
        try:
            exception = execute_agent_tool(
                self.service, "equipment_exception", "get_equipment_exception", {
                    "exception_id": exception_match.group(0),
                }, actor_id, session_id)
            trace.append({"tool": "get_equipment_exception",
                          "id": exception["exception_id"]})
            snapshot = execute_agent_tool(
                self.service, "equipment_exception", "get_planning_snapshot", {
                    "plan_date": (date.today() + timedelta(days=1)).isoformat(),
                    "order_ids": orders,
                    "base_plan_id": "PLAN-CURRENT",
                }, actor_id, session_id)
            trace.append({"tool": "get_planning_snapshot", "id": snapshot["snapshot_id"]})
            assessment = execute_agent_tool(
                self.service, "equipment_exception", "assess_exception_impact", {
                    "snapshot_id": snapshot["snapshot_id"],
                    "exception_id": exception["exception_id"],
                }, actor_id, session_id)
            trace.append({"tool": "assess_exception_impact", "id": exception["exception_id"]})
            policies = execute_agent_tool(
                self.service, "equipment_exception", "search_policies", {
                    "query": "设备异常 停机 排产 变更 审批", "top_k": 3,
                }, actor_id, session_id)

            text = (
                "设备异常影响分析已完成：\n"
                f"- 异常单：{assessment['exception_id']}，设备：{assessment['equipment_id']}\n"
                f"- 预计影响：{assessment['estimated_delay_minutes']} 分钟，"
                f"受影响订单 {len(assessment['affected_order_ids'])} 个\n"
                f"- 是否建议重排：{'是' if assessment['requires_schedule_review'] else '否'}\n\n"
                "本次仅完成分析，没有停机、没有修改生效计划。若需要调整排产，"
                "请继续提供调整目标，系统将重新走校验、仿真和人工审批流程。"
            )
            return {
                "skill": "equipment_exception",
                "status": "ANALYZED",
                "text": text,
                "tool_trace": trace,
                "assessment": assessment,
                "sources": policies,
            }
        except AgentToolError as exc:
            return _failure("equipment_exception", exc, trace)
