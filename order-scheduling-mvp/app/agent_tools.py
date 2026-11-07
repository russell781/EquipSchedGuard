"""Function Calling 工具规范与 Skill 工具白名单。

这里只定义“模型可见”的工具；approve_change_request 与 activate_plan
刻意不存在于注册表中，模型无法通过提示词或参数伪造获得审批 / 生效能力。
"""
from __future__ import annotations

from typing import Any, Callable

from .agent_service import AgentService, AgentToolError


def _obj(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """生成严格 JSON Schema：默认禁止额外字段。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_planning_snapshot",
        "description": "获取订单、物料、设备、班次和当前生效计划的事实快照；只读。",
        "parameters": _obj({
            "plan_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
            "order_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "base_plan_id": {"type": ["string", "null"]},
        }, ["plan_date", "order_ids", "base_plan_id"]),
    },
    {
        "name": "search_policies",
        "description": "检索排产、审批和设备异常制度；制度依据不能替代业务校验。",
        "parameters": _obj({
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
        }, ["query"]),
    },
    {
        "name": "get_equipment_exception",
        "description": "读取真实设备异常单；不得虚构报警，也不得控制设备。",
        "parameters": _obj({
            "exception_id": {"type": ["string", "null"]},
        }, ["exception_id"]),
    },
    {
        "name": "validate_planning_request",
        "description": "对排产请求、权限、基础数据和事实版本做确定性校验，返回一次性凭证。",
        "parameters": _obj({
            "snapshot_id": {"type": "string", "description": "上一步 get_planning_snapshot 返回的 snapshot_id"},
            "request_type": {"type": "string", "enum": [
                "DAILY_PLAN", "INSERT_ORDER", "CHANGE_DELIVERY",
                "MATERIAL_SHORTAGE", "EQUIPMENT_EXCEPTION",
            ]},
            "requested_change": _obj({
                "order_id": {"type": "string", "description": "订单号，如 SO-1001"},
                "requested_delivery_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$", "description": "请求交期 YYYY-MM-DD"},
                "quantity": {"type": "integer", "minimum": 1, "description": "数量（正整数）"},
                "reason": {"type": "string", "minLength": 5, "maxLength": 500, "description": "变更原因，至少 5 个字符"},
            }, ["order_id", "requested_delivery_date", "quantity", "reason"]),
            "objective_weights": _obj({
                "due_date": {"type": "number", "minimum": 0, "maximum": 1, "description": "交期优先权重"},
                "changeover": {"type": "number", "minimum": 0, "maximum": 1, "description": "换型最少权重"},
                "utilization": {"type": "number", "minimum": 0, "maximum": 1, "description": "设备利用率权重"},
            }, ["due_date", "changeover", "utilization"]),
        }, ["snapshot_id", "request_type", "requested_change", "objective_weights"]),
    },
    {
        "name": "create_schedule_draft",
        "description": "根据已通过的输入校验创建排产草稿；草稿不会生效。",
        "parameters": _obj({
            "validation_id": {"type": "string"},
            "strategy": {"type": "string", "enum": [
                "DUE_DATE_FIRST", "MIN_CHANGEOVER", "BALANCED",
            ]},
            "reason": {"type": "string", "minLength": 5, "maxLength": 500},
            "idempotency_key": {"type": "string", "minLength": 16, "maxLength": 128},
        }, ["validation_id", "strategy", "reason", "idempotency_key"]),
    },
    {
        "name": "simulate_schedule",
        "description": "使用确定性求解器仿真草稿，计算准交率、换型和利用率。",
        "parameters": _obj({
            "draft_id": {"type": "string"},
            "solver_profile": {"type": "string", "enum": [
                "DUE_DATE_FIRST", "MIN_CHANGEOVER", "BALANCED",
            ]},
        }, ["draft_id", "solver_profile"]),
    },
    {
        "name": "validate_schedule_draft",
        "description": "校验仿真结果是否对应最新草稿，以及是否存在硬约束冲突。",
        "parameters": _obj({
            "draft_id": {"type": "string"},
            "simulation_id": {"type": "string"},
        }, ["draft_id", "simulation_id"]),
    },
    {
        "name": "assess_exception_impact",
        "description": "评估设备异常对订单与交期的影响；只分析，不停机、不改计划。",
        "parameters": _obj({
            "snapshot_id": {"type": "string"},
            "exception_id": {"type": "string"},
        }, ["snapshot_id", "exception_id"]),
    },
    {
        "name": "submit_change_request",
        "description": "将已通过结果校验的草稿提交人工审批；提交不等于生效。",
        "parameters": _obj({
            "draft_id": {"type": "string"},
            "result_validation_id": {"type": "string"},
            "explanation": {"type": "string", "minLength": 5, "maxLength": 1000},
            "idempotency_key": {"type": "string", "minLength": 16, "maxLength": 128},
        }, ["draft_id", "result_validation_id", "explanation", "idempotency_key"]),
    },
    {
        "name": "get_change_request_status",
        "description": "查询变更单审批状态；只读，不能执行审批或计划生效。",
        "parameters": _obj({
            "change_request_id": {"type": "string"},
        }, ["change_request_id"]),
    },
]

TOOL_SPEC_BY_NAME = {item["name"]: item for item in TOOL_SPECS}


SKILL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "policy_qa": {
        "name": "制度问答 Skill",
        "allowed_tools": ["search_policies"],
        "system_prompt": (
            "你是制度问答智能体。只能检索和解释制度，不得创建、提交、审批或生效任何计划；"
            "涉及业务变更时必须明确转入排产变更流程。"
        ),
    },
    "schedule_change": {
        "name": "排产变更 Skill",
        "allowed_tools": [
            "get_planning_snapshot", "search_policies", "validate_planning_request",
            "create_schedule_draft", "simulate_schedule", "validate_schedule_draft",
            "submit_change_request", "get_change_request_status",
        ],
        "system_prompt": (
            "你是订单排产智能体。你可以选择只读工具、策略和解释方式，但没有审批权、生效权和设备控制权。"
            "涉及创建或调整计划时，必须先获取最新事实快照，再调用输入校验；"
            "不得跳过 validate_planning_request 创建草稿，不得跳过仿真或结果校验提交变更；"
            "只能使用当前任务真实返回且未过期的服务端凭证。任一 FAIL、EXPIRED、STALE_FACTS "
            "或 PRECONDITION_FAILED 都必须停止写操作。不得声称已审批或已生效，"
            "不得审批自己提交的变更，不得猜测缺失订单、数量、交期或设备状态。"
        ),
    },
    "equipment_exception": {
        "name": "设备异常 Skill",
        "allowed_tools": [
            "get_planning_snapshot", "get_equipment_exception", "assess_exception_impact",
            "search_policies", "validate_planning_request", "create_schedule_draft",
            "simulate_schedule", "validate_schedule_draft", "submit_change_request",
            "get_change_request_status",
        ],
        "system_prompt": (
            "你是设备异常分析智能体。设备数据只能采集、检索和分析，不得下发启停、复位或参数修改指令。"
            "先做异常影响分析；只有用户明确要求调整排产时，才能进入快照、输入校验、草稿、仿真、"
            "结果校验和人工审批链。不得直接修改生效计划，不得跳过任何校验。"
        ),
    },
}


def _validate_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """按注册 Schema 做服务端白名单校验，并剥离任何越权字段。"""
    spec = TOOL_SPEC_BY_NAME.get(tool_name)
    if spec is None:
        raise AgentToolError("NOT_FOUND", "工具不存在或未向智能体开放", tool_name)
    schema = spec["parameters"]
    properties = schema["properties"]
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        raise AgentToolError("BAD_REQUEST", "工具参数包含未开放字段", ",".join(unknown))
    missing = [x for x in schema["required"] if x not in arguments]
    if missing:
        raise AgentToolError("BAD_REQUEST", "工具参数缺少必填字段", ",".join(missing))
    # actor_id / session_id 只允许由服务端注入；参数中出现即作为未知字段拒绝
    return {key: value for key, value in arguments.items()
            if key in properties and key not in {"actor_id", "session_id"}}


def execute_agent_tool(service: AgentService, skill: str, tool_name: str,
                       arguments: dict[str, Any], actor_id: str,
                       session_id: str | None = None) -> Any:
    """在 Skill 白名单内执行工具，所有成功 / 失败均追加审计。"""
    skill_def = SKILL_DEFINITIONS.get(skill)
    if skill_def is None:
        raise AgentToolError("NOT_FOUND", "Skill 不存在", skill)
    if tool_name not in skill_def["allowed_tools"]:
        service._audit(actor_id, tool_name, "FAILED", session_id=session_id,
                       detail={"code": "FORBIDDEN", "skill": skill})
        raise AgentToolError("FORBIDDEN", "当前 Skill 无权调用该工具", tool_name)

    call_args = _validate_arguments(tool_name, arguments)
    handler: Callable[..., Any] = getattr(service, tool_name)
    try:
        return handler(**call_args, actor_id=actor_id)
    except AgentToolError as exc:
        service._audit(actor_id, tool_name, "FAILED", session_id=session_id,
                       detail={"code": exc.code, "message": exc.message})
        raise


def public_tool_manifest() -> dict[str, Any]:
    """返回模型可见的工具清单；审批与生效接口不会出现在清单中。"""
    return {
        "tools": TOOL_SPECS,
        "skills": {
            key: {
                "name": value["name"],
                "allowed_tools": value["allowed_tools"],
                "system_prompt": value["system_prompt"],
            }
            for key, value in SKILL_DEFINITIONS.items()
        },
        "not_exposed_to_model": ["approve_change_request", "activate_plan"],
    }
