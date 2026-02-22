import unittest

import service.graph.rag.agents.equity_agent as equity_agent_module
from service.graph.rag.agents.equity_agent import run_equity_agent_stub


class _Request:
    question = "애플 주가 어때"


class TestPhaseDEquityAgent(unittest.TestCase):
    def test_equity_agent_sql_branch_uses_focus_symbols_and_companion(self):
        original_execute_live_tool = equity_agent_module.execute_live_tool
        original_detect_companion_branch = equity_agent_module.detect_companion_branch
        equity_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "sql",
                "status": "ok",
                "template_id": "equity.ohlcv.latest.v1",
                "row_count": 5,
            }
        )
        equity_agent_module.detect_companion_branch = lambda branch, tool_probe: "graph"
        try:
            result = run_equity_agent_stub(
                branch="sql",
                request=_Request(),
                route_decision={
                    "matched_symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"],
                },
                context_meta={},
            )
        finally:
            equity_agent_module.execute_live_tool = original_execute_live_tool
            equity_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("agent"), "equity_analyst_agent")
        self.assertEqual(result.get("status"), "executed")
        self.assertEqual(result.get("primary_store"), "rdb")
        self.assertEqual(result.get("focus_symbols"), ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"])
        self.assertTrue(result.get("needs_companion_branch"))
        self.assertEqual(result.get("companion_branch"), "graph")

    def test_equity_agent_graph_branch_degraded(self):
        original_execute_live_tool = equity_agent_module.execute_live_tool
        original_detect_companion_branch = equity_agent_module.detect_companion_branch
        equity_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "graph",
                "status": "degraded",
                "reason": "graph_template_empty_result",
            }
        )
        equity_agent_module.detect_companion_branch = lambda branch, tool_probe: None
        try:
            result = run_equity_agent_stub(
                branch="graph",
                request=_Request(),
                route_decision={"matched_symbols": ["AAPL"]},
                context_meta={},
            )
        finally:
            equity_agent_module.execute_live_tool = original_execute_live_tool
            equity_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("status"), "degraded")
        self.assertEqual(result.get("primary_store"), "neo4j")
        self.assertFalse(result.get("needs_companion_branch"))
        self.assertIsNone(result.get("companion_branch"))


if __name__ == "__main__":
    unittest.main()
