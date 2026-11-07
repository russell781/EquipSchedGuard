import unittest
from uuid import uuid4

from app.agent_orchestrator import AgentOrchestrator
from app.agent_service import AgentService, AgentToolError
from app.agent_tools import execute_agent_tool, public_tool_manifest


ACTOR = "planner-001"


class AgentToolRegistryTests(unittest.TestCase):
    def test_manifest_does_not_expose_approval_or_activation(self) -> None:
        manifest = public_tool_manifest()
        tool_names = {item["name"] for item in manifest["tools"]}

        self.assertNotIn("approve_change_request", tool_names)
        self.assertNotIn("activate_plan", tool_names)
        self.assertEqual(
            ["approve_change_request", "activate_plan"],
            manifest["not_exposed_to_model"],
        )

    def test_policy_skill_cannot_call_write_tool(self) -> None:
        service = AgentService()

        with self.assertRaises(AgentToolError) as context:
            execute_agent_tool(
                service,
                "policy_qa",
                "create_schedule_draft",
                {
                    "validation_id": str(uuid4()),
                    "strategy": "BALANCED",
                    "reason": "制度问答 Skill 不应拥有写权限",
                    "idempotency_key": f"draft-{uuid4()}",
                },
                ACTOR,
            )

        self.assertEqual("FORBIDDEN", context.exception.code)

    def test_orchestrator_asks_for_missing_business_fields(self) -> None:
        service = AgentService()
        result = AgentOrchestrator(service).maybe_run(
            "请帮我发起插单调整，比较着急", ACTOR, "session-1")

        self.assertIsNotNone(result)
        self.assertEqual("NEED_INPUT", result["status"])
        self.assertIn("订单号", result["missing_fields"])
        self.assertIn("数量", result["missing_fields"])

    def test_orchestrator_full_chain_stops_at_pending_approval(self) -> None:
        service = AgentService()
        result = AgentOrchestrator(service).maybe_run(
            "请帮我发起插单调整，订单 SO-1001，请求交期 2026-11-09，数量 120 件",
            ACTOR,
            "session-2",
        )

        self.assertIsNotNone(result)
        self.assertEqual("PENDING_APPROVAL", result["status"])
        self.assertEqual("PENDING_APPROVAL", result["change_request"]["status"])
        self.assertFalse(result["change_request"]["activated"])
        self.assertEqual(
            ["get_planning_snapshot", "validate_planning_request",
             "create_schedule_draft", "simulate_schedule", "validate_schedule_draft",
             "submit_change_request"],
            [item["tool"] for item in result["tool_trace"]],
        )


if __name__ == "__main__":
    unittest.main()
