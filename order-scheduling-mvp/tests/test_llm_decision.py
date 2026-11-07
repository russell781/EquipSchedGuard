"""LLMDecisionEngine 单元测试：验证真实模型决策引擎的解析、白名单与回退。

测试用 mock 替换 llm.complete_json，避免真实网络调用；重点验证：
1. tool / final / confirm 三种 action 的解析；
2. 越权工具（不在 Skill 白名单内）被拒绝并回退规则引擎；
3. 模型调用失败时优雅回退规则引擎，系统不中断。
"""
import unittest
from unittest import mock

from app.agent_loop import (
    ConfirmDecision,
    FinalDecision,
    LLMDecisionEngine,
    ToolDecision,
)


class TestLLMDecisionEngine(unittest.TestCase):
    """决策引擎的解析与安全边界测试。"""

    def setUp(self) -> None:
        self.engine = LLMDecisionEngine(skill="schedule_change")

    def _ctx(self, question: str = "帮我插单，订单 SO-1001，交期 2026-11-09，数量 120 件"):
        return {"question": question, "rounds": [], "sources": [],
                "run_id": "run-test", "confirmed_draft": False}

    def _patch_model(self, return_value: dict):
        """把 complete_json 换成返回固定值的 mock。"""
        return mock.patch(
            "app.llm.complete_json",
            new=mock.AsyncMock(return_value=return_value))

    def test_parse_tool_decision(self) -> None:
        """模型返回 action=tool 时，应解析为 ToolDecision。"""
        with self._patch_model({
            "action": "tool",
            "tool": "search_policies",
            "arguments": {"query": "插单规则", "top_k": 3},
        }):
            decision = self.engine.decide(self._ctx())
        self.assertIsInstance(decision, ToolDecision)
        self.assertEqual(decision.tool_name, "search_policies")
        self.assertEqual(decision.arguments["query"], "插单规则")

    def test_parse_final_decision(self) -> None:
        """模型返回 action=final 时，应解析为 FinalDecision。"""
        with self._patch_model({
            "action": "final",
            "answer": "请补充订单号。",
        }):
            decision = self.engine.decide(self._ctx("排单标准是什么"))
        self.assertIsInstance(decision, FinalDecision)
        self.assertEqual(decision.answer, "请补充订单号。")

    def test_parse_confirm_decision(self) -> None:
        """模型返回 action=confirm 时，应解析为 ConfirmDecision（挂起人工确认）。"""
        with self._patch_model({
            "action": "confirm",
            "draft_preview": {"order_id": "SO-1001", "quantity": 120},
            "confirmation_message": "请确认草稿",
        }):
            decision = self.engine.decide(self._ctx())
        self.assertIsInstance(decision, ConfirmDecision)
        self.assertTrue(decision.requires_confirmation)
        self.assertTrue(decision.pending_token.startswith("pending-"))

    def test_forbidden_tool_rejected_and_fallback(self) -> None:
        """模型试图调用白名单外的工具（如审批）时，应回退规则引擎而非执行。"""
        with self._patch_model({
            "action": "tool",
            "tool": "approve_change_request",  # 审批工具，白名单外
            "arguments": {"change_request_id": "chg-1"},
        }):
            decision = self.engine.decide(self._ctx())
        # 回退到规则引擎：规则引擎对排产问题先检索制度
        self.assertIsInstance(decision, ToolDecision)
        self.assertEqual(decision.tool_name, "search_policies")

    def test_model_failure_falls_back(self) -> None:
        """模型调用抛异常时，应回退规则引擎，系统不中断。"""
        with mock.patch("app.llm.complete_json",
                        new=mock.AsyncMock(side_effect=Exception("network down"))):
            decision = self.engine.decide(self._ctx())
        # 回退规则引擎：先检索制度
        self.assertIsInstance(decision, ToolDecision)
        self.assertEqual(decision.tool_name, "search_policies")

    def test_unknown_action_falls_back(self) -> None:
        """模型返回未知 action 时，回退规则引擎。"""
        with self._patch_model({"action": "dance"}):
            decision = self.engine.decide(self._ctx())
        self.assertIsInstance(decision, ToolDecision)


if __name__ == "__main__":
    unittest.main()
