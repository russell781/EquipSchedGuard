"""智能体工具服务：事实快照、校验凭证、草稿、仿真与审批提交。

核心原则：模型可以选择工具和策略，但所有“通过 / 提交 / 生效”判断都由
本服务的确定性状态机完成；本服务不提供审批与计划生效方法。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .agent_repository import InMemoryAgentRepository


class AgentToolError(Exception):
    """智能体工具前置条件或状态机错误，code 为稳定字符串。"""

    def __init__(self, code: str, message: str, detail: str | None = None) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


def _canonical_hash(value: Any) -> str:
    """对业务输入做规范化 JSON 哈希，用于发现参数漂移。"""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> datetime:
    """统一使用 UTC 时间。"""
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    """时间转 ISO 字符串。"""
    return value.isoformat()


def _parse_iso(value: str) -> datetime:
    """解析 ISO 时间，兼容无 timezone 的历史值。"""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class AgentService:
    """智能体工具门面：所有方法同步、确定性，并追加工具审计。"""

    REQUEST_TYPES = {
        "DAILY_PLAN", "INSERT_ORDER", "CHANGE_DELIVERY",
        "MATERIAL_SHORTAGE", "EQUIPMENT_EXCEPTION",
    }
    STRATEGIES = {"DUE_DATE_FIRST", "MIN_CHANGEOVER", "BALANCED"}
    VALIDATION_TTL_MINUTES = 10
    SNAPSHOT_TTL_MINUTES = 30

    def __init__(self, repository: Any | None = None) -> None:
        self.repository = repository or InMemoryAgentRepository()
        self.repository.initialize()
        self._lock = threading.RLock()

    # ---------- 通用工具 ----------
    def _audit(self, actor_id: str, tool_name: str, status: str,
               target_id: str | None = None, detail: dict | None = None,
               session_id: str | None = None) -> None:
        """记录工具调用结果；审计只能追加，不能修改。"""
        self.repository.append_audit({
            "actor_id": actor_id,
            "session_id": session_id,
            "tool_name": tool_name,
            "status": status,
            "target_id": target_id,
            "detail": detail or {},
            "created_at": _iso(_now()),
        })

    def _get(self, kind: str, entity_id: str, actor_id: str) -> dict[str, Any]:
        """读取实体并校验归属，禁止跨用户使用凭证。"""
        entity = self.repository.get_object(kind, entity_id)
        if entity is None:
            raise AgentToolError("NOT_FOUND", "目标记录不存在", entity_id)
        if entity.get("actor_id") != actor_id:
            raise AgentToolError("FORBIDDEN", "不能使用其他用户生成的工具凭证")
        return entity

    def _require_fresh_snapshot(self, snapshot: dict[str, Any]) -> None:
        """检查快照未过期且未被事实变更标记失效。"""
        if snapshot.get("state") == "FACTS_STALE" or not snapshot.get("fresh", False):
            raise AgentToolError("STALE_FACTS", "事实快照已失效，请重新获取订单与设备数据",
                                 snapshot.get("stale_reason"))
        if _parse_iso(snapshot["expires_at"]) <= _now():
            raise AgentToolError("EXPIRED", "事实快照已过期，请重新获取")

    def _idempotent_result(self, key: str, actor_id: str) -> dict[str, Any] | None:
        """如果幂等键已成功使用，直接返回原实体。"""
        found = self.repository.find_idempotency(key)
        if not found:
            return None
        if found["actor_id"] != actor_id:
            raise AgentToolError("FORBIDDEN", "幂等键属于其他用户")
        return self.repository.get_object(found["kind"], found["id"])

    # ---------- 只读取数工具 ----------
    def get_planning_snapshot(self, plan_date: str, order_ids: list[str],
                              base_plan_id: str | None, actor_id: str) -> dict[str, Any]:
        """创建计划事实快照；当前未接 ERP/MES 时使用确定性演示事实。"""
        try:
            datetime.strptime(plan_date, "%Y-%m-%d")
        except ValueError:
            raise AgentToolError("BAD_REQUEST", "plan_date 必须是 YYYY-MM-DD")
        if not order_ids:
            raise AgentToolError("BAD_REQUEST", "至少需要一个订单号")

        created = _now()
        orders = []
        for index, order_id in enumerate(order_ids):
            orders.append({
                "order_id": order_id,
                "quantity": 100 + index * 20,
                "promised_delivery_date": plan_date,
                "material_ready": True,
                "priority": "HIGH" if index == 0 else "NORMAL",
            })
        snapshot_id = f"snap-{uuid4()}"
        payload = {
            "id": snapshot_id,
            "snapshot_id": snapshot_id,
            "actor_id": actor_id,
            "plan_date": plan_date,
            "order_ids": order_ids,
            "base_plan_id": base_plan_id or "PLAN-CURRENT",
            "state": "SNAPSHOT_READY",
            "fresh": True,
            "facts_version": _canonical_hash({
                "plan_date": plan_date, "order_ids": order_ids,
                "base_plan_id": base_plan_id or "PLAN-CURRENT",
            })[:16],
            "facts": {
                "orders": orders,
                "equipment": [
                    {"equipment_id": "CNC-01", "status": "RUNNING", "capacity_minutes": 480},
                    {"equipment_id": "ASM-01", "status": "RUNNING", "capacity_minutes": 480},
                ],
                "shifts": [{"shift_id": "DAY", "start": "08:00", "end": "16:00"}],
                "current_plan": {"plan_id": base_plan_id or "PLAN-CURRENT", "version": "V1"},
                "data_complete": True,
            },
            "created_at": _iso(created),
            "updated_at": _iso(created),
            "expires_at": _iso(created + timedelta(minutes=self.SNAPSHOT_TTL_MINUTES)),
        }
        self.repository.put_object("snapshot", payload)
        self._audit(actor_id, "get_planning_snapshot", "SUCCESS", payload["snapshot_id"],
                    {"order_count": len(order_ids)})
        return payload

    def mark_snapshot_stale(self, snapshot_id: str, reason: str,
                            actor_id: str = "system") -> dict[str, Any]:
        """供外部事实变更回调使用；该接口不注册给模型。"""
        with self._lock:
            snapshot = self.repository.get_object("snapshot", snapshot_id)
            if snapshot is None:
                raise AgentToolError("NOT_FOUND", "事实快照不存在", snapshot_id)
            snapshot["state"] = "FACTS_STALE"
            snapshot["fresh"] = False
            snapshot["stale_reason"] = reason
            snapshot["updated_at"] = _iso(_now())
            self.repository.put_object("snapshot", snapshot)
            self._audit(actor_id, "mark_snapshot_stale", "SUCCESS", snapshot_id,
                        {"reason": reason})
            return snapshot

    def search_policies(self, query: str, top_k: int = 3,
                        actor_id: str = "system") -> list[dict[str, Any]]:
        """制度 RAG 检索；只读，不产生任何业务凭证。"""
        from .retrieval import search

        result = search(query, top_k=top_k)
        self._audit(actor_id, "search_policies", "SUCCESS", detail={"hits": len(result)})
        return result

    def get_equipment_exception(self, exception_id: str | None = None,
                                actor_id: str = "system") -> dict[str, Any]:
        """读取设备异常；当前为 MES 接入前的确定性演示数据。"""
        events = {
            "EQ-EX-001": {
                "exception_id": "EQ-EX-001", "equipment_id": "CNC-01",
                "alarm_code": "SPINDLE_OVERHEAT", "severity": "HIGH",
                "started_at": "2026-11-06T08:20:00+08:00",
                "estimated_downtime_minutes": 120, "status": "OPEN",
            },
            "EQ-EX-002": {
                "exception_id": "EQ-EX-002", "equipment_id": "ASM-01",
                "alarm_code": "FEEDER_JAM", "severity": "MEDIUM",
                "started_at": "2026-11-06T09:10:00+08:00",
                "estimated_downtime_minutes": 45, "status": "OPEN",
            },
        }
        if exception_id:
            event = events.get(exception_id)
            if event is None:
                self._audit(actor_id, "get_equipment_exception", "FAILED", exception_id,
                            {"code": "NOT_FOUND"})
                raise AgentToolError("NOT_FOUND", "设备异常单不存在", exception_id)
            self._audit(actor_id, "get_equipment_exception", "SUCCESS", exception_id)
            return dict(event)
        self._audit(actor_id, "get_equipment_exception", "SUCCESS",
                    detail={"count": len(events)})
        return {"items": list(events.values())}

    # ---------- 校验与草稿 ----------
    def validate_planning_request(self, snapshot_id: str, request_type: str,
                                  requested_change: dict[str, Any],
                                  objective_weights: dict[str, float],
                                  actor_id: str) -> dict[str, Any]:
        """校验请求，返回一次性、短期有效的服务端凭证。"""
        snapshot = self._get("snapshot", snapshot_id, actor_id)
        self._require_fresh_snapshot(snapshot)
        if request_type not in self.REQUEST_TYPES:
            raise AgentToolError("BAD_REQUEST", "不支持的排产变更类型", request_type)

        failures: list[str] = []
        quantity = requested_change.get("quantity", 1)
        if not isinstance(quantity, int) or quantity <= 0:
            failures.append("数量必须为正整数")
        if len(str(requested_change.get("reason", "")).strip()) < 5:
            failures.append("变更原因至少 5 个字符")
        requested_date = requested_change.get("requested_delivery_date")
        try:
            datetime.strptime(str(requested_date), "%Y-%m-%d")
        except ValueError:
            failures.append("请求交期必须是 YYYY-MM-DD")
        weight_sum = sum(float(v) for v in objective_weights.values())
        if not 0.99 <= weight_sum <= 1.01:
            failures.append("目标权重之和必须等于 1")
        if not snapshot["facts"].get("data_complete"):
            failures.append("基础数据不完整")

        request_hash = _canonical_hash({
            "snapshot_id": snapshot_id,
            "facts_version": snapshot["facts_version"],
            "request_type": request_type,
            "requested_change": requested_change,
            "objective_weights": objective_weights,
        })
        status = "PASS" if not failures else "FAIL"
        created = _now()
        validation_id = f"val-{uuid4()}"
        validation = {
            "id": validation_id,
            "validation_id": validation_id,
            "actor_id": actor_id,
            "snapshot_id": snapshot_id,
            "facts_version": snapshot["facts_version"],
            "request_type": request_type,
            "requested_change": requested_change,
            "objective_weights": objective_weights,
            "request_hash": request_hash,
            "status": status,
            "state": "INPUT_VALIDATED" if status == "PASS" else "VALIDATION_FAILED",
            "failures": failures,
            "single_use": True,
            "used_at": None,
            "created_at": _iso(created),
            "updated_at": _iso(created),
            "expires_at": _iso(created + timedelta(minutes=self.VALIDATION_TTL_MINUTES)),
        }
        self.repository.put_object("input_validation", validation)
        self._audit(actor_id, "validate_planning_request", status, validation["validation_id"],
                    {"failures": failures})
        return validation

    def create_schedule_draft(self, validation_id: str, strategy: str, reason: str,
                              idempotency_key: str, actor_id: str) -> dict[str, Any]:
        """凭 PASS 输入校验创建草稿；凭证一次性使用。"""
        existing = self._idempotent_result(idempotency_key, actor_id)
        if existing:
            return existing
        if strategy not in self.STRATEGIES:
            raise AgentToolError("BAD_REQUEST", "不支持的排产策略", strategy)

        with self._lock:
            validation = self.repository.get_object("input_validation", validation_id)
            if validation is None or validation.get("actor_id") != actor_id:
                raise AgentToolError("PRECONDITION_FAILED",
                                     "缺少有效的输入校验凭证，不能创建草稿")
            snapshot = self._get("snapshot", validation["snapshot_id"], actor_id)
            self._require_fresh_snapshot(snapshot)
            if validation.get("status") != "PASS" or validation.get("used_at"):
                raise AgentToolError("PRECONDITION_FAILED",
                                     "输入校验未通过或凭证已使用，不能创建草稿")
            if _parse_iso(validation["expires_at"]) <= _now():
                raise AgentToolError("EXPIRED", "输入校验凭证已过期，请重新校验")

            change = validation["requested_change"]
            created = _now()
            plan_items = [{
                "order_id": change.get("order_id"),
                "equipment_id": "CNC-01",
                "start_at": f"{snapshot['plan_date']}T08:00:00+08:00",
                "end_at": f"{snapshot['plan_date']}T11:00:00+08:00",
                "quantity": change.get("quantity"),
                "strategy": strategy,
            }]
            draft_hash = _canonical_hash({
                "request_hash": validation["request_hash"],
                "strategy": strategy,
                "reason": reason,
                "plan_items": plan_items,
            })
            draft_id = f"draft-{uuid4()}"
            draft = {
                "id": draft_id,
                "draft_id": draft_id,
                "actor_id": actor_id,
                "validation_id": validation_id,
                "snapshot_id": validation["snapshot_id"],
                "facts_version": validation["facts_version"],
                "request_hash": validation["request_hash"],
                "strategy": strategy,
                "reason": reason,
                "plan_items": plan_items,
                "draft_hash": draft_hash,
                "state": "DRAFTED",
                "created_at": _iso(created),
                "updated_at": _iso(created),
            }
            validation["used_at"] = _iso(created)
            validation["updated_at"] = _iso(created)
            self.repository.put_object("input_validation", validation)
            self.repository.put_object("schedule_draft", draft)
            self.repository.put_idempotency(idempotency_key, "schedule_draft",
                                            draft["draft_id"], actor_id)
            self._audit(actor_id, "create_schedule_draft", "SUCCESS", draft["draft_id"],
                        {"validation_id": validation_id})
            return draft

    # ---------- 仿真与结果校验 ----------
    def simulate_schedule(self, draft_id: str, solver_profile: str,
                          actor_id: str) -> dict[str, Any]:
        """调用确定性求解器的演示实现，只处理 DRAFTED 状态草稿。"""
        if solver_profile not in self.STRATEGIES:
            raise AgentToolError("BAD_REQUEST", "不支持的求解配置", solver_profile)
        with self._lock:
            draft = self._get("schedule_draft", draft_id, actor_id)
            if draft.get("state") != "DRAFTED":
                raise AgentToolError("STATE_CONFLICT", "草稿当前状态不允许重复仿真",
                                     draft.get("state"))
            snapshot = self._get("snapshot", draft["snapshot_id"], actor_id)
            self._require_fresh_snapshot(snapshot)

            kpis = {
                "on_time_rate": 0.94,
                "changeover_count": 3 if solver_profile != "MIN_CHANGEOVER" else 2,
                "equipment_utilization": 0.82,
            }
            created = _now()
            simulation_id = f"sim-{uuid4()}"
            simulation = {
                "id": simulation_id,
                "simulation_id": simulation_id,
                "actor_id": actor_id,
                "draft_id": draft_id,
                "draft_hash": draft["draft_hash"],
                "solver_profile": solver_profile,
                "solver_version": "deterministic-demo-1.0",
                "status": "SUCCESS",
                "state": "SIMULATED",
                "kpis": kpis,
                "conflicts": [],
                "created_at": _iso(created),
                "updated_at": _iso(created),
            }
            draft["state"] = "SIMULATED"
            draft["updated_at"] = _iso(created)
            self.repository.put_object("simulation", simulation)
            self.repository.put_object("schedule_draft", draft)
            self._audit(actor_id, "simulate_schedule", "SUCCESS", simulation["simulation_id"],
                        {"draft_id": draft_id})
            return simulation

    def validate_schedule_draft(self, draft_id: str, simulation_id: str,
                                actor_id: str) -> dict[str, Any]:
        """校验仿真结果必须对应最新草稿，且没有硬冲突。"""
        with self._lock:
            draft = self._get("schedule_draft", draft_id, actor_id)
            simulation = self._get("simulation", simulation_id, actor_id)
            if simulation.get("draft_id") != draft_id:
                raise AgentToolError("PRECONDITION_FAILED", "仿真结果不属于该草稿")
            if simulation.get("draft_hash") != draft.get("draft_hash"):
                raise AgentToolError("PRECONDITION_FAILED", "草稿已变化，仿真结果不能复用")
            if draft.get("state") != "SIMULATED":
                raise AgentToolError("STATE_CONFLICT", "草稿尚未完成确定性仿真",
                                     draft.get("state"))
            snapshot = self._get("snapshot", draft["snapshot_id"], actor_id)
            self._require_fresh_snapshot(snapshot)
            if simulation.get("status") != "SUCCESS":
                raise AgentToolError("VALIDATION_FAILED", "仿真未成功，不能提交审批")

            failures = ["存在设备或班次硬冲突"] if simulation.get("conflicts") else []
            status = "PASS" if not failures else "FAIL"
            created = _now()
            result_validation_id = f"rval-{uuid4()}"
            result = {
                "id": result_validation_id,
                "result_validation_id": result_validation_id,
                "actor_id": actor_id,
                "draft_id": draft_id,
                "simulation_id": simulation_id,
                "draft_hash": draft["draft_hash"],
                "status": status,
                "state": "OUTPUT_VALIDATED" if status == "PASS" else "VALIDATION_FAILED",
                "checks": {
                    "hard_constraints": "PASS" if not failures else "FAIL",
                    "kpi_complete": "PASS",
                    "facts_fresh": "PASS",
                },
                "failures": failures,
                "single_use": True,
                "used_at": None,
                "created_at": _iso(created),
                "updated_at": _iso(created),
                "expires_at": _iso(created + timedelta(minutes=self.VALIDATION_TTL_MINUTES)),
            }
            if status == "PASS":
                draft["state"] = "OUTPUT_VALIDATED"
                draft["updated_at"] = _iso(created)
                self.repository.put_object("schedule_draft", draft)
            self.repository.put_object("result_validation", result)
            self._audit(actor_id, "validate_schedule_draft", status,
                        result["result_validation_id"], {"draft_id": draft_id})
            return result

    # ---------- 提交与查询 ----------
    def submit_change_request(self, draft_id: str, result_validation_id: str,
                              explanation: str, idempotency_key: str,
                              actor_id: str) -> dict[str, Any]:
        """提交人工审批；只进入 PENDING_APPROVAL，绝不直接生效。"""
        existing = self._idempotent_result(idempotency_key, actor_id)
        if existing:
            return existing
        if len(explanation.strip()) < 5:
            raise AgentToolError("BAD_REQUEST", "提交说明至少 5 个字符")

        with self._lock:
            draft = self._get("schedule_draft", draft_id, actor_id)
            validation = self._get("result_validation", result_validation_id, actor_id)
            snapshot = self._get("snapshot", draft["snapshot_id"], actor_id)
            self._require_fresh_snapshot(snapshot)
            if validation.get("draft_id") != draft_id:
                raise AgentToolError("PRECONDITION_FAILED", "结果校验不属于该草稿")
            if validation.get("status") != "PASS" or validation.get("used_at"):
                raise AgentToolError("PRECONDITION_FAILED",
                                     "结果校验未通过或凭证已使用，不能提交审批")
            if validation.get("draft_hash") != draft.get("draft_hash"):
                raise AgentToolError("PRECONDITION_FAILED", "草稿已变化，请重新仿真与校验")
            if draft.get("state") != "OUTPUT_VALIDATED":
                raise AgentToolError("STATE_CONFLICT", "草稿尚未通过结果校验",
                                     draft.get("state"))
            if _parse_iso(validation["expires_at"]) <= _now():
                raise AgentToolError("EXPIRED", "结果校验凭证已过期，请重新校验")

            created = _now()
            change_request_id = f"chg-{uuid4()}"
            request = {
                "id": change_request_id,
                "change_request_id": change_request_id,
                "actor_id": actor_id,
                "draft_id": draft_id,
                "result_validation_id": result_validation_id,
                "explanation": explanation,
                "status": "PENDING_APPROVAL",
                "state": "PENDING_APPROVAL",
                "approval_required": True,
                "activated": False,
                "approver_roles": ["生产计划负责人", "交付负责人"],
                "created_at": _iso(created),
                "updated_at": _iso(created),
            }
            validation["used_at"] = _iso(created)
            validation["updated_at"] = _iso(created)
            draft["state"] = "PENDING_APPROVAL"
            draft["updated_at"] = _iso(created)
            self.repository.put_object("result_validation", validation)
            self.repository.put_object("schedule_draft", draft)
            self.repository.put_object("change_request", request)
            self.repository.put_idempotency(idempotency_key, "change_request",
                                            request["change_request_id"], actor_id)
            self._audit(actor_id, "submit_change_request", "SUCCESS",
                        request["change_request_id"], {"draft_id": draft_id})
            return request

    # ---------- 审批与生效（仅管理员/系统，不注册给模型） ----------
    def list_change_requests(self, actor_id: str = "system",
                             status: str | None = None) -> list[dict[str, Any]]:
        """列出变更单（默认全部），供管理后台审批面板使用。"""
        items = self.repository.list_objects("change_request")
        if status:
            items = [x for x in items if x.get("status") == status]
        self._audit(actor_id, "list_change_requests", "SUCCESS",
                    detail={"count": len(items)})
        return items

    def approve_change_request(self, change_request_id: str, comment: str,
                               approver_id: str) -> dict[str, Any]:
        """管理员审批同意：变更单 APPROVED → 草稿 APPROVED → 生成当日计划（生效）。

        这是确定性写操作，包在单进程锁内完成；审批只追加，不修改原草稿内容。
        """
        if len(comment.strip()) < 2:
            raise AgentToolError("BAD_REQUEST", "审批意见至少 2 个字符")
        with self._lock:
            request = self.repository.get_object("change_request", change_request_id)
            if request is None:
                raise AgentToolError("NOT_FOUND", "变更单不存在", change_request_id)
            if request.get("status") != "PENDING_APPROVAL":
                raise AgentToolError("STATE_CONFLICT", "变更单不在待审批状态",
                                     request.get("status"))
            draft = self.repository.get_object("schedule_draft", request["draft_id"])
            if draft is None:
                raise AgentToolError("NOT_FOUND", "草稿不存在", request["draft_id"])

            now = _now()
            # 1) 变更单置为已批准
            request["status"] = "APPROVED"
            request["state"] = "APPROVED"
            request["activated"] = True
            request["approver_id"] = approver_id
            request["approval_comment"] = comment.strip()
            request["approved_at"] = _iso(now)
            request["updated_at"] = _iso(now)
            self.repository.put_object("change_request", request)

            # 2) 草稿置为已批准
            draft["state"] = "APPROVED"
            draft["updated_at"] = _iso(now)
            self.repository.put_object("schedule_draft", draft)

            # 3) 生成当日计划生效记录（daily_plan）
            plan_date = draft.get("plan_items", [{}])[0].get("start_at", _iso(now))[:10] \
                if draft.get("plan_items") else _iso(now)[:10]
            plan_id = f"plan-{uuid4()}"
            plan = {
                "id": plan_id,
                "plan_id": plan_id,
                "plan_date": plan_date,
                "version": "V1",
                "source_draft_id": draft["draft_id"],
                "change_request_id": change_request_id,
                "plan_items": draft.get("plan_items", []),
                "strategy": draft.get("strategy"),
                "status": "active",
                "state": "ACTIVE",
                "published_by": approver_id,
                "created_at": _iso(now),
                "updated_at": _iso(now),
            }
            self.repository.put_object("daily_plan", plan)
            self._audit(approver_id, "approve_change_request", "SUCCESS",
                        change_request_id, {"plan_id": plan_id})
            return plan

    def reject_change_request(self, change_request_id: str, comment: str,
                              approver_id: str) -> dict[str, Any]:
        """管理员审批拒绝：变更单 REJECTED → 草稿 REJECTED，不生成生效计划。"""
        if len(comment.strip()) < 2:
            raise AgentToolError("BAD_REQUEST", "审批意见至少 2 个字符")
        with self._lock:
            request = self.repository.get_object("change_request", change_request_id)
            if request is None:
                raise AgentToolError("NOT_FOUND", "变更单不存在", change_request_id)
            if request.get("status") != "PENDING_APPROVAL":
                raise AgentToolError("STATE_CONFLICT", "变更单不在待审批状态",
                                     request.get("status"))
            draft = self.repository.get_object("schedule_draft", request["draft_id"])
            now = _now()
            request["status"] = "REJECTED"
            request["state"] = "REJECTED"
            request["activated"] = False
            request["approver_id"] = approver_id
            request["approval_comment"] = comment.strip()
            request["rejected_at"] = _iso(now)
            request["updated_at"] = _iso(now)
            self.repository.put_object("change_request", request)
            if draft is not None:
                draft["state"] = "REJECTED"
                draft["updated_at"] = _iso(now)
                self.repository.put_object("schedule_draft", draft)
            self._audit(approver_id, "reject_change_request", "SUCCESS",
                        change_request_id)
            return request

    def list_daily_plans(self, actor_id: str = "system") -> list[dict[str, Any]]:
        """列出已生效的当日计划（管理后台展示）。"""
        items = self.repository.list_objects("daily_plan")
        self._audit(actor_id, "list_daily_plans", "SUCCESS",
                    detail={"count": len(items)})
        return items

    def get_change_request_status(self, change_request_id: str,
                                  actor_id: str) -> dict[str, Any]:
        """查询变更单状态；模型不能通过该接口执行审批或生效。"""
        request = self._get("change_request", change_request_id, actor_id)
        self._audit(actor_id, "get_change_request_status", "SUCCESS", change_request_id)
        return {
            "change_request_id": request["change_request_id"],
            "status": request["status"],
            "approval_required": request["approval_required"],
            "activated": request["activated"],
            "updated_at": request["updated_at"],
        }

    # ---------- 设备异常影响分析 ----------
    def assess_exception_impact(self, snapshot_id: str, exception_id: str,
                                actor_id: str) -> dict[str, Any]:
        """基于真实异常单与事实快照评估影响，不控制设备、不改计划。"""
        snapshot = self._get("snapshot", snapshot_id, actor_id)
        self._require_fresh_snapshot(snapshot)
        event = self.get_equipment_exception(exception_id, actor_id)
        affected = [item for item in snapshot["facts"]["orders"]
                    if item.get("material_ready")]
        impact_minutes = int(event["estimated_downtime_minutes"])
        assessment = {
            "exception_id": exception_id,
            "equipment_id": event["equipment_id"],
            "severity": event["severity"],
            "affected_order_ids": [x["order_id"] for x in affected],
            "estimated_delay_minutes": impact_minutes,
            "requires_schedule_review": impact_minutes >= 30,
            "allowed_actions": ["生成影响说明", "重新校验并创建排产草稿"],
            "forbidden_actions": ["直接停机", "直接修改生效计划", "跳过审批"],
        }
        self._audit(actor_id, "assess_exception_impact", "SUCCESS", exception_id,
                    {"affected_count": len(affected)})
        return assessment

    def list_tool_audits(self, actor_id: str | None = None,
                         limit: int = 100) -> list[dict[str, Any]]:
        """读取工具调用审计，供后台排查与演示。"""
        return self.repository.list_audits(actor_id, limit)

    # ---------- 执行循环决策日志 ----------
    def append_decision_log(self, record: dict[str, Any]) -> None:
        """追加执行循环的决策日志（每轮一条），供阶段 5 分析。"""
        self.repository.append_decision_log(record)

    def list_decision_logs(self, actor_id: str | None = None,
                           limit: int = 100) -> list[dict[str, Any]]:
        """读取决策日志（时间倒序）。"""
        return self.repository.list_decision_logs(actor_id, limit)
