import unittest

import service.graph.rag.agents.macro_agent as macro_agent_module
from service.graph.rag.agents.macro_agent import run_macro_agent_stub


class _Request:
    question = "금리 영향 알려줘"


class TestPhaseDMacroAgent(unittest.TestCase):
    def test_macro_agent_sql_branch_executes_and_requests_companion(self):
        original_execute_live_tool = macro_agent_module.execute_live_tool
        original_detect_companion_branch = macro_agent_module.detect_companion_branch
        macro_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "sql",
                "status": "ok",
                "reason": "sql_template_executed",
                "row_count": 3,
            }
        )
        macro_agent_module.detect_companion_branch = lambda branch, tool_probe: "graph"
        try:
            result = run_macro_agent_stub(
                branch="sql",
                request=_Request(),
                route_decision={"selected_type": "general_macro"},
                context_meta={},
            )
        finally:
            macro_agent_module.execute_live_tool = original_execute_live_tool
            macro_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("agent"), "macro_economy_agent")
        self.assertEqual(result.get("branch"), "sql")
        self.assertEqual(result.get("status"), "executed")
        self.assertEqual(result.get("primary_store"), "rdb")
        self.assertTrue(result.get("needs_companion_branch"))
        self.assertEqual(result.get("companion_branch"), "graph")

    def test_macro_agent_graph_branch_degraded_without_companion(self):
        original_execute_live_tool = macro_agent_module.execute_live_tool
        original_detect_companion_branch = macro_agent_module.detect_companion_branch
        macro_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "graph",
                "status": "degraded",
                "reason": "graph_template_empty_result",
            }
        )
        macro_agent_module.detect_companion_branch = lambda branch, tool_probe: None
        try:
            result = run_macro_agent_stub(
                branch="graph",
                request=_Request(),
                route_decision={"selected_type": "general_macro"},
                context_meta={"counts": {"nodes": 1}},
            )
        finally:
            macro_agent_module.execute_live_tool = original_execute_live_tool
            macro_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("status"), "degraded")
        self.assertFalse(result.get("needs_companion_branch"))
        self.assertIsNone(result.get("companion_branch"))
        self.assertEqual(result.get("primary_store"), "neo4j")


if __name__ == "__main__":
    unittest.main()
