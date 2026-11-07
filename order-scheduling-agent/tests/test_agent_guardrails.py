import unittest
from uuid import uuid4

from app.agent_service import AgentService, AgentToolError


ACTOR = "planner-001"


def make_service() -> AgentService:
    return AgentService()


def make_snapshot(service: AgentService) -> dict:
    return service.get_planning_snapshot(
        plan_date="2026-11-07",
        order_ids=["SO-1001", "SO-1002"],
        base_plan_id="PLAN-20261106-A",
        actor_id=ACTOR,
    )


def make_change() -> dict:
    return {
        "order_id": "SO-1001",
        "requested_delivery_date": "2026-11-09",
        "quantity": 120,
        "reason": "客户插单，需要评估对现有日计划的影响",
    }


def validate_snapshot(service: AgentService, snapshot: dict) -> dict:
    return service.validate_planning_request(
        snapshot_id=snapshot["snapshot_id"],
        request_type="INSERT_ORDER",
        requested_change=make_change(),
        objective_weights={"due_date": 0.6, "changeover": 0.25, "utilization": 0.15},
        actor_id=ACTOR,
    )


def create_valid_draft(service: AgentService) -> dict:
    snapshot = make_snapshot(service)
    validation = validate_snapshot(service, snapshot)
    return service.create_schedule_draft(
        validation_id=validation["validation_id"],
        strategy="DUE_DATE_FIRST",
        reason="优先保障准交率，同时评估换型损失",
        idempotency_key=f"draft-{uuid4()}",
        actor_id=ACTOR,
    )


class AgentGuardrailTests(unittest.TestCase):
    def assert_tool_error(self, expected_code: str, action, *args, **kwargs) -> None:
        with self.assertRaises(AgentToolError) as context:
            action(*args, **kwargs)
        self.assertEqual(expected_code, context.exception.code)

    def test_create_draft_rejects_missing_input_validation(self) -> None:
        service = make_service()

        self.assert_tool_error(
            "PRECONDITION_FAILED",
            service.create_schedule_draft,
            validation_id=str(uuid4()),
            strategy="DUE_DATE_FIRST",
            reason="试图绕过输入校验创建草稿",
            idempotency_key=f"draft-{uuid4()}",
            actor_id=ACTOR,
        )

    def test_stale_snapshot_cannot_be_used_for_validation(self) -> None:
        service = make_service()
        snapshot = make_snapshot(service)
        service.mark_snapshot_stale(snapshot["snapshot_id"], reason="设备状态已变化")

        self.assert_tool_error("STALE_FACTS", validate_snapshot, service, snapshot)

    def test_input_validation_is_single_use(self) -> None:
        service = make_service()
        snapshot = make_snapshot(service)
        validation = validate_snapshot(service, snapshot)

        first = service.create_schedule_draft(
            validation_id=validation["validation_id"],
            strategy="DUE_DATE_FIRST",
            reason="第一次创建草稿",
            idempotency_key=f"draft-{uuid4()}",
            actor_id=ACTOR,
        )
        self.assertEqual("DRAFTED", first["state"])

        self.assert_tool_error(
            "PRECONDITION_FAILED",
            service.create_schedule_draft,
            validation_id=validation["validation_id"],
            strategy="MIN_CHANGEOVER",
            reason="试图重复使用同一校验凭证",
            idempotency_key=f"draft-{uuid4()}",
            actor_id=ACTOR,
        )

    def test_draft_validation_rejects_mismatched_simulation(self) -> None:
        service = make_service()
        first_draft = create_valid_draft(service)
        second_draft = create_valid_draft(service)
        simulation = service.simulate_schedule(
            draft_id=first_draft["draft_id"],
            solver_profile="BALANCED",
            actor_id=ACTOR,
        )

        self.assert_tool_error(
            "PRECONDITION_FAILED",
            service.validate_schedule_draft,
            draft_id=second_draft["draft_id"],
            simulation_id=simulation["simulation_id"],
            actor_id=ACTOR,
        )

    def test_full_chain_stops_at_pending_approval(self) -> None:
        service = make_service()
        draft = create_valid_draft(service)
        simulation = service.simulate_schedule(
            draft_id=draft["draft_id"],
            solver_profile="BALANCED",
            actor_id=ACTOR,
        )
        result_validation = service.validate_schedule_draft(
            draft_id=draft["draft_id"],
            simulation_id=simulation["simulation_id"],
            actor_id=ACTOR,
        )

        change_request = service.submit_change_request(
            draft_id=draft["draft_id"],
            result_validation_id=result_validation["result_validation_id"],
            explanation="预计准交率提升，且没有设备硬冲突，请审批。",
            idempotency_key=f"submit-{uuid4()}",
            actor_id=ACTOR,
        )

        self.assertEqual("PENDING_APPROVAL", change_request["status"])
        self.assertTrue(change_request["approval_required"])
        self.assertFalse(change_request["activated"])
        status = service.get_change_request_status(
            change_request["change_request_id"], actor_id=ACTOR
        )
        self.assertEqual("PENDING_APPROVAL", status["status"])


if __name__ == "__main__":
    unittest.main()
