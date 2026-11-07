"""执行循环（AgentLoop）的红灯测试。

先定义预期行为，再据此实现。覆盖三大能力：
1. 决策循环最多 5 轮，每轮写决策日志；
2. create_draft 前强制人工确认，未确认不执行；
3. 三个典型对话轨迹（制度问答 / 插单异常 / 校验给结论）。
"""
from __future__ import annotations

import unittest
from uuid import uuid4

from app.agent_loop import (
    AgentLoop,
    ConfirmDecision,
    FinalDecision,
    RuleDecisionEngine,
    ToolDecision,
    decide_with_rules,
)
from app.agent_repository import InMemoryAgentRepository
from app.agent_service import AgentService


ACTOR = "planner-001"


def _service() -> AgentService:
    """构造一个干净的内存仓储智能体服务。"""
    return AgentService(InMemoryAgentRepository())


class DecisionModelTests(unittest.TestCase):
    """决策数据结构与规则式决策引擎的基础行为。"""

    def test_rule_decider_answers_policy_question_directly(self) -> None:
        """纯制度问题应先检索制度，最终不进入业务建草稿流程。"""
        engine = RuleDecisionEngine()
        first = engine.decide({"question": "排单标准是什么", "rounds": []})
        # 第一轮：检索制度
        self.assertIsInstance(first, ToolDecision)
        self.assertEqual("search_policies", first.tool_name)
        # 检索完成后：给最终答案，不再调用任何业务工具
        second = engine.decide({"question": "排单标准是什么",
                                "rounds": [{"tool_name": "search_policies"}], "sources": []})
        self.assertIsInstance(second, FinalDecision)
        self.assertIsNone(getattr(second, "tool_name", None))

    def test_rule_decider_asks_for_invoice_on_insert(self) -> None:
        """插单异常流程：模型应先查制度（工具1）。"""
        decision = decide_with_rules("帮我报插单导致的排单异常，订单 SO-1001")
        self.assertIsInstance(decision, ToolDecision)
        self.assertEqual("search_policies", decision.tool_name)

    def test_rule_decider_checks_invoice_before_verdict(self) -> None:
        """“插单能否加入原订单”应先校验发票相关事实，再给结论。"""
        decision = decide_with_rules("这个插单可以加入原订单吗，订单 SO-1001")
        # 该问题需要先拿事实快照才能判断是否可合并，而不是凭空给结论
        self.assertIsInstance(decision, ToolDecision)
        self.assertIn(decision.tool_name, {"get_planning_snapshot", "search_policies"})


class ConfirmDecisionTests(unittest.TestCase):
    """create_draft 前的人工确认协议。"""

    def test_confirm_decision_round_trip(self) -> None:
        """确认请求能被识别为需要员工决策。"""
        decision = ConfirmDecision(
            draft_preview={"order_id": "SO-1001", "quantity": 120},
            pending_token="tok-abc",
        )
        self.assertTrue(decision.requires_confirmation)
        self.assertEqual("tok-abc", decision.pending_token)


class AgentLoopTests(unittest.TestCase):
    """执行循环整体行为。"""

    def _loop(self) -> AgentLoop:
        return AgentLoop(_service(), max_rounds=5)

    def test_loop_stops_at_final_decision(self) -> None:
        """纯制度问答只查制度（工具1），不调用其他业务工具，然后给最终答案。"""
        loop = self._loop()
        result = loop.run("排单标准是什么", ACTOR, session_id="s1")
        self.assertEqual("FINAL", result["status"])
        tool_names = [r["tool_name"] for r in result["rounds"]]
        # 轨迹 a：只查制度，绝不出现工具 2-4（快照/校验/建草稿/仿真等）
        self.assertEqual(["search_policies"], tool_names)

    def test_loop_caps_at_max_rounds(self) -> None:
        """永不收敛的循环必须在 max_rounds 处被强制截断。"""
        class NeverConverges:
            def decide(self, context):
                return ToolDecision("search_policies", {"query": "排产"})

        loop = AgentLoop(_service(), max_rounds=3, decision_engine=NeverConverges())
        result = loop.run("反复查询", ACTOR, session_id="s1")
        self.assertEqual("MAX_ROUNDS", result["status"])
        self.assertEqual(3, len(result["rounds"]))

    def test_create_draft_requires_confirmation(self) -> None:
        """模型决定建草稿时，必须先返回确认挂起，不得直接执行。"""
        loop = self._loop()
        result = loop.run(
            "帮我报插单导致的排单异常，订单 SO-1001，请求交期 2026-11-09，数量 120 件",
            ACTOR, session_id="s1")
        self.assertEqual("AWAITING_CONFIRMATION", result["status"])
        self.assertIn("pending_token", result)
        # 未确认前不应产生任何草稿实体
        self.assertIsNone(result.get("draft"))

    def test_confirmation_resumes_and_executes(self) -> None:
        """员工确认后，循环应继续完成建草稿并停到待审批。"""
        loop = self._loop()
        pending = loop.run(
            "帮我报插单导致的排单异常，订单 SO-1001，请求交期 2026-11-09，数量 120 件",
            ACTOR, session_id="s1")
        self.assertEqual("AWAITING_CONFIRMATION", pending["status"])

        resumed = loop.confirm(pending["pending_token"], confirmed=True, actor_id=ACTOR)
        self.assertIn(resumed["status"], {"PENDING_APPROVAL", "AWAITING_CONFIRMATION"})
        # 确认后应出现 create_schedule_draft 的日志轮次
        tool_names = [r["tool_name"] for r in resumed["rounds"]]
        self.assertIn("create_schedule_draft", tool_names)

    def test_decline_aborts_draft(self) -> None:
        """员工拒绝确认时，不应建草稿，循环以 CANCELLED 结束。"""
        loop = self._loop()
        pending = loop.run(
            "帮我报插单导致的排单异常，订单 SO-1001，请求交期 2026-11-09，数量 120 件",
            ACTOR, session_id="s1")
        self.assertEqual("AWAITING_CONFIRMATION", pending["status"])

        cancelled = loop.confirm(pending["pending_token"], confirmed=False, actor_id=ACTOR)
        self.assertEqual("CANCELLED", cancelled["status"])
        tool_names = [r["tool_name"] for r in cancelled["rounds"]]
        self.assertNotIn("create_schedule_draft", tool_names)


class DecisionLogTests(unittest.TestCase):
    """决策日志落库。"""

    def test_each_round_writes_log(self) -> None:
        """每一轮决策都应写入日志表（工具、参数、耗时、结果摘要）。"""
        loop = AgentLoop(_service(), max_rounds=5)
        loop.run("帮我报插单导致的排单异常，订单 SO-1001，请求交期 2026-11-09，数量 120 件",
                 ACTOR, session_id="s1")
        logs = loop.service.list_decision_logs(actor_id=ACTOR)
        self.assertGreater(len(logs), 0)
        first = logs[0]
        for field in ("tool_name", "arguments", "duration_ms", "summary"):
            self.assertIn(field, first)


if __name__ == "__main__":
    unittest.main()
