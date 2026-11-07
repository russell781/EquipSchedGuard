"""受约束的 Agent 执行循环（ReAct 内核）。

背景
----
本系统已经从“固定流程问答”升级为“会自主决策的智能体”。但智能体的
“自主”必须被约束在确定性状态机之内：LLM 只能决定“下一步调用哪个工具、
传什么参数”，而“校验是否通过、草稿能否创建、计划能否生效”全部由服务端
硬编码判断。这个模块就是那层“模型决策 → 执行工具 → 结果回填 → 再决策”
的执行循环。

框架选择说明
------------
用户推荐 Harness，但 Harness 不是通用的 LLM Agent 编排库（业界常见的是
LangChain/LangGraph、Semantic Kernel、AutoGen）。本项目的核心理念要求
“工具边界与状态机是服务端硬约束，不能依赖第三方框架的提示词注入”，因此
这里实现一个轻量自研循环 AgentLoop，等价于一个最小 ReAct 内核：

    while 未结束 and 轮数 < max_rounds:
        decision = engine.decide(context)      # 模型决策：下一步做什么
        if decision 是最终答案: 结束
        if decision 是确认请求: 挂起等待员工确认
        执行工具 → 结果回填 context → 记决策日志 → 下一轮

决策引擎（DecisionEngine）被抽象成接口：默认用规则式决策器（本地演示、
无需大模型），后续可替换为真实 LLM 的 function calling，循环骨架不变。

人工确认协议
------------
当决策引擎准备调用 create_schedule_draft 时，循环不会立即执行，而是先把
草稿预览作为确认请求返回并挂起（状态 AWAITING_CONFIRMATION），由员工
通过 confirm() 明确同意后才真正建草稿；拒绝则整个流程取消（CANCELLED）。
这是“create_draft 调用前强制中断”的硬约束，不依赖提示词，而是靠控制流。
"""
from __future__ import annotations

import json
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable
from uuid import uuid4

from .agent_service import AgentService, AgentToolError
from .agent_tools import SKILL_DEFINITIONS, execute_agent_tool


# ======================================================================
# 决策数据结构
# ======================================================================

class Decision:
    """一次决策的基类。"""


@dataclass
class ToolDecision(Decision):
    """决定调用一个工具。"""

    tool_name: str
    arguments: dict[str, Any]


@dataclass
class FinalDecision(Decision):
    """决定直接给出最终答案，不再调用工具。"""

    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ConfirmDecision(Decision):
    """在调用 create_schedule_draft 之前，请求员工确认草稿内容。

    这不是“调用工具”，而是一次控制流中断：循环必须挂起，等待员工
    通过 confirm() 明确同意或拒绝。pending_token 是本次确认的会话令牌，
    用于在员工回传确认时定位被挂起的循环状态。
    """

    draft_preview: dict[str, Any]      # 草稿内容预览（发流式给员工看）
    pending_token: str                  # 确认令牌
    confirmation_message: str = "请确认是否按以下草稿创建排产草稿："

    @property
    def requires_confirmation(self) -> bool:
        """标记这是一个需要人工确认的决策。"""
        return True


class LoopExceeded(Exception):
    """超过最大决策轮数仍未收敛时抛出。"""


class ConfirmPending(Exception):
    """内部信号：循环需要挂起等待确认。由 AgentLoop 捕获并转换为返回值。"""

    def __init__(self, decision: ConfirmDecision) -> None:
        self.decision = decision


# ======================================================================
# 决策引擎抽象
# ======================================================================

class DecisionEngine(ABC):
    """决策引擎接口：根据当前上下文决定下一步动作。

    替换点：默认的规则式引擎 RuleDecisionEngine 用于本地演示；接入真实
    大模型时，实现一个 LLMDecisionEngine 即可，循环骨架无需改动。
    """

    @abstractmethod
    def decide(self, context: dict[str, Any]) -> Decision:
        """根据上下文（用户问题、已执行工具的结果、技能白名单）返回决策。"""


# ======================================================================
# 规则式决策引擎（本地演示，无需大模型）
# ======================================================================

# 制度问答关键词：命中则直接走 RAG 检索并给最终答案
_POLICY_QUESTION_RE = re.compile(r"(标准|制度|规定|规则|要求|流程|怎么|如何|是什么|怎么处理|是什么样)")

# 需要“建草稿”的动作意图：明确出现“帮我/要/发起/调整”等执行动词 + 排产对象
# 注意：“插单”只作为对象词出现，不作为动作词，避免“插单时原来订单怎么处理”
# 这类纯制度提问被误判为排产动作。
_SCHEDULE_ACTION_RE = re.compile(r"(帮我|我要|需要|请|发起|调整|重排|插入|安排|创建|报|上报).{0,24}(插单|排产|排单|计划|订单|异常)")
_ORDER_RE = re.compile(r"\b[A-Z]{1,6}-\d{3,}\b")
_DATE_RE = re.compile(r"20\d{2}-\d{1,2}-\d{1,2}")
_QTY_RE = re.compile(r"(\d{1,6})\s*(?:件|个|台)")

# “插单能否加入原订单”这类需要先校验事实再给结论
_MERGE_QUESTION_RE = re.compile(r"(加入|并入|合并|能否|可以吗|可以加入)")


def _has_schedule_context(question: str) -> bool:
    """判断问题是否携带了足以发起排产变更的业务字段。"""
    return bool(_ORDER_RE.search(question) and _DATE_RE.search(question)
                and _QTY_RE.search(question))


class RuleDecisionEngine(DecisionEngine):
    """基于正则 + 上下文的确定性决策器。

    它只负责“下一步该做什么”的启发式判断，绝不代替服务端校验。所有
    校验结论仍由 AgentService 的状态机给出。
    """

    def decide(self, context: dict[str, Any]) -> Decision:
        question = context["question"]
        done_tools = {r["tool_name"] for r in context["rounds"]}

        # —— 纯制度问题：只查制度，直接给最终答案（不调用任何业务工具）——
        # 判断标准：命中“标准/规定/怎么处理”等提问词，且没有“帮我/发起/调整”
        # 等执行动词。注意“排单标准是什么”里的“排单”不能算执行动作。
        if _POLICY_QUESTION_RE.search(question) and not _SCHEDULE_ACTION_RE.search(question):
            # 若尚未检索，先检索一次制度，然后下一轮给最终答案
            if "search_policies" not in done_tools:
                return ToolDecision("search_policies", {"query": question, "top_k": 3})
            return FinalDecision(
                "已根据制度检索到相关条款，详见下方引用来源。",
                context.get("sources", []))

        # —— 以下为排产变更类意图 ——

        # 1. 尚未检索制度：先查制度（工具 1）
        if "search_policies" not in done_tools:
            return ToolDecision("search_policies", {"query": "插单 变更 审批 生效计划", "top_k": 3})

        # 2. 尚未获取事实快照：先取数（用于校验与合并判断）
        if "get_planning_snapshot" not in done_tools:
            order_ids = _ORDER_RE.findall(question)
            if not order_ids:
                return FinalDecision("请补充订单号，我才能继续分析。", [])
            return ToolDecision("get_planning_snapshot", {
                "plan_date": (date.today() + timedelta(days=1)).isoformat(),
                "order_ids": order_ids,
                "base_plan_id": "PLAN-CURRENT",
            })

        # 3. “插单能否加入原订单”：校验事实后给结论（不再建草稿）
        if _MERGE_QUESTION_RE.search(question):
            return FinalDecision(
                "根据当前事实快照，该插单与现有订单的交期、物料齐套情况可以纳入原订单"
                "评估范围；如需正式合并，请走排产变更流程发起审批。",
                context.get("sources", []))

        # 4. 完整的插单异常流程：查制度→取数→(要发票)→校验→建草稿→确认
        if not _has_schedule_context(question):
            return FinalDecision("请补充订单号、请求交期和数量，我才能发起排产变更。", [])

        # 4a. 尚未做输入校验：先校验（拿到一次性凭证）
        if "validate_planning_request" not in done_tools:
            snapshot = context["latest_snapshot"]
            order_id = _ORDER_RE.findall(question)[0]
            date_str = _normalize_date(_DATE_RE.findall(question)[-1])
            qty = int(_QTY_RE.search(question).group(1))
            return ToolDecision("validate_planning_request", {
                "snapshot_id": snapshot["snapshot_id"],
                "request_type": "INSERT_ORDER" if "插单" in question else "CHANGE_DELIVERY",
                "requested_change": {
                    "order_id": order_id,
                    "requested_delivery_date": date_str,
                    "quantity": qty,
                    "reason": question[:500],
                },
                "objective_weights": {"due_date": 0.6, "changeover": 0.25, "utilization": 0.15},
            })

        # 4b. 尚未建草稿——必须先经过人工确认
        if "create_schedule_draft" not in done_tools:
            # 已经确认过（confirm() 恢复流程）→ 直接返回建草稿的工具决策
            if context.get("confirmed_draft"):
                validation = context.get("latest_validation") or {}
                return ToolDecision("create_schedule_draft", {
                    "validation_id": validation.get("validation_id"),
                    "strategy": "MIN_CHANGEOVER" if "换型" in question else "DUE_DATE_FIRST",
                    "reason": question[:500],
                    "idempotency_key": _idem("draft", context["run_id"]),
                })
            # 尚未确认 → 触发人工确认挂起
            validation = context.get("latest_validation") or {}
            preview = {
                "order_id": _ORDER_RE.findall(question)[0],
                "requested_delivery_date": _normalize_date(_DATE_RE.findall(question)[-1]),
                "quantity": int(_QTY_RE.search(question).group(1)),
                "strategy": "MIN_CHANGEOVER" if "换型" in question else "DUE_DATE_FIRST",
                "validation_id": validation.get("validation_id"),
            }
            return ConfirmDecision(
                draft_preview=preview,
                pending_token=f"pending-{uuid4()}",
            )

        # 4c. 已确认并建草稿，剩余流程：仿真 → 结果校验 → 提交审批
        if "simulate_schedule" not in done_tools:
            return ToolDecision("simulate_schedule", {
                "draft_id": context["latest_draft"]["draft_id"],
                "solver_profile": "MIN_CHANGEOVER" if "换型" in question else "DUE_DATE_FIRST",
            })
        if "validate_schedule_draft" not in done_tools:
            return ToolDecision("validate_schedule_draft", {
                "draft_id": context["latest_draft"]["draft_id"],
                "simulation_id": context["latest_simulation"]["simulation_id"],
            })
        if "submit_change_request" not in done_tools:
            return ToolDecision("submit_change_request", {
                "draft_id": context["latest_draft"]["draft_id"],
                "result_validation_id": context["latest_result_validation"]["result_validation_id"],
                "explanation": "由智能体完成快照、校验、草稿、仿真与结果校验后提交审批。",
                "idempotency_key": _idem("submit", context["run_id"]),
            })

        # 全部完成后给最终答案
        change = context.get("latest_change_request") or {}
        return FinalDecision(
            f"已提交人工审批：{change.get('change_request_id', '')}，当前状态待审批，尚未生效。",
            context.get("sources", []))


def _normalize_date(raw: str) -> str:
    """把 2026-11-9 规范为 YYYY-MM-DD。"""
    year, month, day = raw.split("-")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


# ======================================================================
# 真实大模型决策引擎（Function Calling 式，工具白名单 + 状态机兜底）
# ======================================================================

class LLMDecisionEngine(DecisionEngine):
    """基于真实大模型的决策引擎：让模型决定“下一步调哪个工具、传什么参数”。

    与 RuleDecisionEngine 的区别：
    - 规则引擎靠正则启发式判断，无法理解口语化/复杂表述；
    - 本引擎把「当前上下文 + 可选工具白名单」交给大模型，让模型用结构化
      JSON 输出一个决策（tool / final / confirm），再由循环执行。

    安全边界（与规则引擎一致，甚至更严格）：
    1. 模型只能从当前 Skill 的 allowed_tools 里选工具；审批、生效、设备控制
       根本不在白名单里，模型不可能“说”出它们。
    2. 模型的每个工具参数仍要过 execute_agent_tool → _validate_arguments 的
       Schema 校验，越权字段会被剥离或报错。
    3. 所有校验结论（validate_planning_request 是否 PASS、草稿能否创建、
       计划能否生效）仍由 AgentService 状态机硬判定，模型无法伪造凭证。
    4. create_schedule_draft 前的人工确认是控制流硬约束，模型只能“请求确认”，
       不能跳过。

    容错：模型调用失败、返回非法 JSON 或非法工具时，回退到 RuleDecisionEngine，
    保证系统在无 Key / 网络异常 / 模型幻觉时仍可用。
    """

    def __init__(self, skill: str = "schedule_change",
                 fallback: DecisionEngine | None = None) -> None:
        self.skill = skill
        # 默认回退到规则引擎，保证可用性
        self._fallback = fallback or RuleDecisionEngine()

    # ---------- 决策接口 ----------
    def decide(self, context: dict[str, Any]) -> Decision:
        """用真实大模型做一次决策；失败则回退规则引擎。"""
        try:
            raw = self._call_model(context)
            return self._parse(raw, context)
        except Exception:
            # 模型不可用 / 解析失败 / 非法工具 → 回退规则引擎（绝不因模型故障中断业务）
            return self._fallback.decide(context)

    # ---------- 模型调用 ----------
    def _call_model(self, context: dict[str, Any]) -> dict[str, Any]:
        """组装提示词并调用大模型，返回结构化 JSON。"""
        from .llm import complete_json  # 延迟导入避免循环依赖

        skill_def = SKILL_DEFINITIONS.get(self.skill, {})
        allowed = skill_def.get("allowed_tools", [])
        system_prompt = skill_def.get("system_prompt", "")

        # 把当前 Skill 允许的工具列成 JSON Schema 片段，供模型理解可调用范围
        from .agent_tools import TOOL_SPEC_BY_NAME
        tools_desc = json.dumps(
            [TOOL_SPEC_BY_NAME[name] for name in allowed if name in TOOL_SPEC_BY_NAME],
            ensure_ascii=False)

        system = (
            f"{system_prompt}\n\n"
            "你是受约束的排产智能体，只能通过“调用工具”来推进任务，不能凭空编造结果。\n"
            "你每一步必须输出一个 JSON 对象，格式如下（三选一）：\n"
            '1. 调用工具：{"action":"tool","tool":"工具名","arguments":{...}}\n'
            '2. 给出最终答案：{"action":"final","answer":"给用户的中文回答"}\n'
            '3. 需要建草稿前先请求员工确认：{"action":"confirm","draft_preview":{...},"confirmation_message":"..."}\n'
            f"\n当前 Skill 允许调用的工具（含参数 schema）如下：\n{tools_desc}\n\n"
            "必须遵守的硬性规则：\n"
            "- 只能从上述工具中选择，不得调用未列出的工具；\n"
            "- 创建草稿 create_schedule_draft 之前，必须先调用过 validate_planning_request "
            "并拿到服务端返回的 validation_id；不得跳过校验；\n"
            "- 提交 submit_change_request 之前，必须先完成 simulate_schedule 和 "
            "validate_schedule_draft；\n"
            "- 不得声称“已审批”“已生效”“已写回系统”；\n"
            "- 信息不足（缺订单号/交期/数量等）时，用 action=final 向用户追问，不要编造；\n"
            "- arguments 里的字段必须严格使用工具 schema 中定义的字段名；\n"
            "- validate_planning_request 的 requested_change 必须包含 reason（变更原因，≥5 字）；\n"
            "- objective_weights 必须使用 due_date / changeover / utilization 三个键，且三者之和为 1。"
        )

        # 用户消息：原始问题 + 已完成的工具执行摘要 + 真实凭证 ID，让模型“接续”而非重来。
        # 关键：必须把上一步工具真实返回的凭证（snapshot_id / validation_id / draft_id /
        # simulation_id / result_validation_id）原样回传给模型，否则模型会自己编造 ID，
        # 导致状态机校验时 NOT_FOUND。这些凭证是服务端生成的，模型只能引用、不能编造。
        rounds = context.get("rounds", [])
        done_desc = "\n".join(
            f"- 已调用 {r['tool_name']}：{r.get('summary', '')}"
            for r in rounds) or "（尚无）"

        # 把上下文里已回填的真实结果字段打包，供模型引用真实凭证
        real_fields = {
            "snapshot_id": (context.get("latest_snapshot") or {}).get("snapshot_id"),
            "validation_id": (context.get("latest_validation") or {}).get("validation_id"),
            "draft_id": (context.get("latest_draft") or {}).get("draft_id"),
            "simulation_id": (context.get("latest_simulation") or {}).get("simulation_id"),
            "result_validation_id": (context.get("latest_result_validation") or {}).get("result_validation_id"),
            "change_request_id": (context.get("latest_change_request") or {}).get("change_request_id"),
        }
        real_fields = {k: v for k, v in real_fields.items() if v}  # 去掉空值
        real_desc = json.dumps(real_fields, ensure_ascii=False) if real_fields else "（尚无）"

        user = (
            f"用户问题：{context['question']}\n\n"
            f"已完成步骤：\n{done_desc}\n\n"
            f"上一步工具返回的真实凭证（只能引用这些值，禁止编造新的 ID）：\n{real_desc}\n\n"
            "请根据当前进展，给出下一步动作的 JSON。"
        )

        # 模型已确认建草稿（confirm() 恢复后），提示它直接建草稿
        if context.get("confirmed_draft"):
            user += "\n\n注意：员工已经确认了草稿内容，请直接调用 create_schedule_draft。"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # 同步桥接：AgentLoop 本身在 to_thread 里运行，这里 asyncio.run 不会阻塞事件循环
        import asyncio
        return asyncio.run(complete_json(messages))

    # ---------- 解析模型输出 ----------
    def _parse(self, raw: dict[str, Any], context: dict[str, Any]) -> Decision:
        """把模型返回的 JSON 解析为 Decision；校验工具合法性。"""
        action = raw.get("action")

        if action == "tool":
            return self._parse_tool(raw, context)

        if action == "final":
            answer = raw.get("answer") or "已完成处理。"
            return FinalDecision(answer, context.get("sources", []))

        if action == "confirm":
            draft_preview = raw.get("draft_preview") or {}
            message = raw.get("confirmation_message") or "请确认是否按以下草稿创建排产草稿："
            return ConfirmDecision(
                draft_preview=draft_preview,
                pending_token=f"pending-{uuid4()}",
                confirmation_message=message,
            )

        # 无法识别的 action → 抛异常，交由 decide() 回退规则引擎
        raise ValueError(f"未知决策类型：{action}")

    def _parse_tool(self, raw: dict[str, Any], context: dict[str, Any]) -> Decision:
        """校验并构造工具决策：工具必须在当前 Skill 白名单内。"""
        tool_name = raw.get("tool")
        arguments = raw.get("arguments") or {}

        skill_def = SKILL_DEFINITIONS.get(self.skill, {})
        allowed = skill_def.get("allowed_tools", [])
        if tool_name not in allowed:
            # 模型试图调用越权工具（如审批/生效）→ 拒绝并抛异常，触发回退
            raise ValueError(f"模型请求了越权工具：{tool_name}")

        if not isinstance(arguments, dict):
            raise ValueError("工具参数必须是对象")

        return ToolDecision(tool_name, arguments)


def _make_decision_engine(skill: str = "schedule_change") -> DecisionEngine:
    """按配置构造决策引擎：开启真实模型则用 LLMDecisionEngine，否则用规则引擎。

    这是 AgentLoop 默认决策引擎的工厂函数，集中控制开关。
    """
    from .config import LLM_DECIDE
    from .llm import has_real_llm

    if LLM_DECIDE == "true" or (LLM_DECIDE == "auto" and has_real_llm()):
        return LLMDecisionEngine(skill=skill)
    return RuleDecisionEngine()


def _idem(prefix: str, run_id: str) -> str:
    """基于 run_id 生成幂等键，避免历史已仿真草稿被误判为可重复仿真。"""
    import hashlib
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:24]}"


# 默认决策引擎（本地演示）
def decide_with_rules(question: str) -> Decision:
    """便捷入口：用规则引擎对单个问题做一次决策（供测试与演示）。"""
    return RuleDecisionEngine().decide({"question": question, "rounds": []})


# ======================================================================
# 执行循环
# ======================================================================

class AgentLoop:
    """受约束的 ReAct 执行循环。

    职责：
    - 驱动“决策 → 执行 → 回填 → 再决策”，最多 max_rounds 轮；
    - 每轮写一条决策日志（工具名、参数、耗时、结果摘要）；
    - 遇到 ConfirmDecision 时挂起，等待员工 confirm()；
    - 所有工具执行都经过 Skill 白名单 + 服务端状态机校验。
    """

    def __init__(self, service: AgentService, max_rounds: int = 5,
                 decision_engine: DecisionEngine | None = None,
                 skill: str = "schedule_change") -> None:
        self.service = service
        self.max_rounds = max_rounds
        # 默认按配置选择：开启真实模型用 LLMDecisionEngine，否则回退规则引擎
        self.engine = decision_engine or _make_decision_engine(skill)
        self.skill = skill
        # 挂起的确认：token -> 被挂起的上下文（进程内字典，演示用）
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    # ---------- 对外入口 ----------
    def run(self, question: str, actor_id: str,
            session_id: str | None = None) -> dict[str, Any]:
        """发起一次执行循环。

        返回字典，status 可能为：
        - FINAL：给出最终答案
        - AWAITING_CONFIRMATION：挂起等待员工确认建草稿
        - PENDING_APPROVAL：已完成提交审批
        - MAX_ROUNDS：超过最大轮数
        - FAILED：工具护栏错误
        """
        context = self._new_context(question, actor_id, session_id)
        return self._drive(context)

    def confirm(self, pending_token: str, confirmed: bool,
                actor_id: str) -> dict[str, Any]:
        """员工对挂起的建草稿请求做出确认。

        confirmed=True  → 继续执行剩余流程（建草稿→仿真→校验→提交）
        confirmed=False → 取消，不建草稿，返回 CANCELLED
        """
        with self._lock:
            ctx = self._pending.pop(pending_token, None)
        if ctx is None:
            return {"status": "EXPIRED", "text": "确认请求已失效或已处理"}
        if ctx.get("actor_id") != actor_id:
            return {"status": "FORBIDDEN", "text": "无权确认他人的草稿请求"}
        if not confirmed:
            self._log(ctx, "confirm_draft", {"confirmed": False}, 0,
                      "CANCELLED", "员工拒绝确认，草稿未创建")
            return {"status": "CANCELLED", "text": "已取消，未创建草稿",
                    "rounds": ctx["rounds"]}
        # 确认后：把待执行的 create_draft 决策重新放回引擎
        ctx["confirmed_draft"] = True
        return self._drive(ctx)

    # ---------- 内部实现 ----------
    def _new_context(self, question: str, actor_id: str,
                     session_id: str | None) -> dict[str, Any]:
        """初始化一次循环的上下文。"""
        return {
            "run_id": str(uuid4()),
            "question": question,
            "actor_id": actor_id,
            "session_id": session_id,
            "rounds": [],           # 已完成的轮次（用于决策日志与引擎记忆）
            "sources": [],          # 制度检索来源
            "latest_snapshot": None,
            "latest_validation": None,
            "latest_draft": None,
            "latest_simulation": None,
            "latest_result_validation": None,
            "latest_change_request": None,
            "confirmed_draft": False,
        }

    def _drive(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """驱动循环直到收敛、挂起、超限或失败。"""
        for _ in range(self.max_rounds):
            decision = self.engine.decide(ctx)

            # 最终答案：结束
            if isinstance(decision, FinalDecision):
                return self._finalize(ctx, decision)

            # 确认请求：挂起等待员工（除非已经在确认恢复流程中）
            if isinstance(decision, ConfirmDecision):
                return self._suspend_for_confirmation(ctx, decision)

            # 工具决策：执行并回填
            if isinstance(decision, ToolDecision):
                # —— 硬约束：create_schedule_draft 之前必须经过人工确认 ——
                # 无论决策引擎（规则式或 LLM 式）返回什么，只要即将创建草稿且尚未
                # 确认过，就在循环层强制挂起，绝不依赖模型“自觉”返回 confirm。
                # 这是控制流安全，不依赖提示词。
                if (decision.tool_name == "create_schedule_draft"
                        and not ctx.get("confirmed_draft")):
                    return self._suspend_for_confirmation(
                        ctx, self._build_confirm_decision(ctx))

                try:
                    self._execute_tool(ctx, decision)
                except AgentToolError as exc:
                    # 工具护栏错误（校验失败 / 凭证无效 / 越权等）：优雅降级为
                    # FAILED，而不是让异常冒泡成 500。真实模型决策偶尔会传错参数，
                    # 这里给出可读错误并终止本次流程，绝不继续或崩溃。
                    return {
                        "status": "FAILED",
                        "text": f"操作未完成：{exc.message}",
                        "code": exc.code,
                        "rounds": ctx["rounds"],
                    }
                continue

            # 未知决策类型：视为最终答案兜底
            return self._finalize(ctx, FinalDecision("无法理解下一步动作，已停止。"))

        return {"status": "MAX_ROUNDS", "text": "决策轮数超限，已停止",
                "rounds": ctx["rounds"]}

    def _build_confirm_decision(self, ctx: dict[str, Any]) -> ConfirmDecision:
        """根据当前上下文构造建草稿前的人工确认请求。

        用于在循环层强制拦截 create_schedule_draft：从已校验的结果中提取草稿预览，
        供员工确认。若上下文缺少关键字段则给空预览，员工仍可确认/拒绝。
        """
        validation = ctx.get("latest_validation") or {}
        snapshot = ctx.get("latest_snapshot") or {}
        preview = {
            "order_id": (validation.get("requested_change") or {}).get("order_id")
                        or (snapshot.get("order_ids") or [""])[0],
            "requested_delivery_date": (validation.get("requested_change") or {}).get("requested_delivery_date"),
            "quantity": (validation.get("requested_change") or {}).get("quantity"),
            "strategy": "DUE_DATE_FIRST",
            "validation_id": validation.get("validation_id"),
        }
        return ConfirmDecision(
            draft_preview=preview,
            pending_token=f"pending-{uuid4()}",
        )

    def _execute_tool(self, ctx: dict[str, Any], decision: ToolDecision) -> None:
        """执行一个工具，记录耗时与结果摘要，回填上下文。

        工具执行失败（AgentToolError）时抛给 _drive 上层转为 FAILED；
        这里不吞错误，因为护栏错误必须终止流程，不能继续。
        """
        start = time.perf_counter()
        result = execute_agent_tool(
            self.service, self.skill, decision.tool_name, decision.arguments,
            ctx["actor_id"], ctx["session_id"])
        duration_ms = int((time.perf_counter() - start) * 1000)
        summary = self._summarize(decision.tool_name, result)

        # 回填上下文，供下一轮决策使用
        self._backfill(ctx, decision.tool_name, result)
        ctx["rounds"].append({
            "tool_name": decision.tool_name,
            "arguments": decision.arguments,
            "duration_ms": duration_ms,
            "summary": summary,
        })
        self._log(ctx, decision.tool_name, decision.arguments, duration_ms,
                  "SUCCESS", summary)

    def _backfill(self, ctx: dict[str, Any], tool_name: str, result: Any) -> None:
        """把工具结果写入上下文，供决策引擎下一轮参考。"""
        if tool_name == "search_policies":
            ctx["sources"] = result if isinstance(result, list) else []
        elif tool_name == "get_planning_snapshot":
            ctx["latest_snapshot"] = result
        elif tool_name == "validate_planning_request":
            ctx["latest_validation"] = result
        elif tool_name == "create_schedule_draft":
            ctx["latest_draft"] = result
        elif tool_name == "simulate_schedule":
            ctx["latest_simulation"] = result
        elif tool_name == "validate_schedule_draft":
            ctx["latest_result_validation"] = result
        elif tool_name == "submit_change_request":
            ctx["latest_change_request"] = result

    def _suspend_for_confirmation(self, ctx: dict[str, Any],
                                  decision: ConfirmDecision) -> dict[str, Any]:
        """把循环挂起，返回待确认状态；保存上下文供 confirm() 恢复。"""
        with self._lock:
            self._pending[decision.pending_token] = ctx
        self._log(ctx, "confirm_draft", {"pending": True}, 0,
                  "AWAITING_CONFIRMATION", "等待员工确认草稿内容")
        return {
            "status": "AWAITING_CONFIRMATION",
            "pending_token": decision.pending_token,
            "confirmation_message": decision.confirmation_message,
            "draft_preview": decision.draft_preview,
            "rounds": ctx["rounds"],
        }

    def _finalize(self, ctx: dict[str, Any], decision: FinalDecision) -> dict[str, Any]:
        """组装最终返回。"""
        # 如果已提交审批，状态用 PENDING_APPROVAL
        if ctx.get("latest_change_request"):
            status = "PENDING_APPROVAL"
            change = ctx["latest_change_request"]
        else:
            status = "FINAL"
            change = None
        return {
            "status": status,
            "text": decision.answer,
            "rounds": ctx["rounds"],
            "sources": decision.sources or ctx["sources"],
            "change_request": change,
        }

    @staticmethod
    def _summarize(tool_name: str, result: Any) -> str:
        """生成结果摘要（阶段 5 分析用，保留关键字段而非全文）。"""
        if tool_name == "search_policies":
            return f"命中 {len(result) if isinstance(result, list) else 0} 条制度"
        if tool_name == "get_planning_snapshot":
            return f"快照 {result.get('snapshot_id', '')[:13]}…，{len(result.get('order_ids', []))} 订单"
        if tool_name == "validate_planning_request":
            return f"校验 {result.get('status', '')}"
        if tool_name == "create_schedule_draft":
            return f"草稿 {result.get('draft_id', '')[:13]}…"
        if tool_name == "simulate_schedule":
            kpi = result.get("kpis", {})
            return f"准交率 {kpi.get('on_time_rate', 0):.0%}"
        if tool_name == "validate_schedule_draft":
            return f"结果校验 {result.get('status', '')}"
        if tool_name == "submit_change_request":
            return f"变更单 {result.get('change_request_id', '')[:13]}…"
        if tool_name == "get_equipment_exception":
            return f"异常 {result.get('exception_id', '')}"
        if tool_name == "assess_exception_impact":
            return f"影响 {result.get('estimated_delay_minutes', 0)} 分钟"
        if tool_name == "get_change_request_status":
            return f"状态 {result.get('status', '')}"
        return "OK"

    def _log(self, ctx: dict[str, Any], tool_name: str, arguments: dict[str, Any],
             duration_ms: int, status: str, summary: str) -> None:
        """写一条决策日志（落库，供阶段 5 分析）。"""
        from .agent_service import _iso, _now  # 复用时间工具

        self.service.append_decision_log({
            "run_id": ctx["run_id"],
            "actor_id": ctx["actor_id"],
            "session_id": ctx["session_id"],
            "round_no": len(ctx["rounds"]) + 1,
            "tool_name": tool_name,
            "arguments": arguments,
            "duration_ms": duration_ms,
            "status": status,
            "summary": summary,
            "created_at": _iso(_now()),
        })
