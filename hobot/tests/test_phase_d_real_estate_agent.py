import unittest

import service.graph.rag.agents.real_estate_agent as real_estate_agent_module
from service.graph.rag.agents.real_estate_agent import run_real_estate_agent_stub


class _Request:
    def __init__(self, region_code: str = "11680", property_type: str = "apartment"):
        self.region_code = region_code
        self.property_type = property_type


class TestPhaseDRealEstateAgent(unittest.TestCase):
    def test_real_estate_agent_sql_branch_includes_region_and_property_type(self):
        original_execute_live_tool = real_estate_agent_module.execute_live_tool
        original_detect_companion_branch = real_estate_agent_module.detect_companion_branch
        real_estate_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "sql",
                "status": "ok",
                "template_id": "real_estate.latest_price.v1",
                "row_count": 2,
            }
        )
        real_estate_agent_module.detect_companion_branch = lambda branch, tool_probe: "graph"
        try:
            result = run_real_estate_agent_stub(
                branch="sql",
                request=_Request(),
                route_decision={"selected_type": "real_estate_detail"},
                context_meta={},
            )
        finally:
            real_estate_agent_module.execute_live_tool = original_execute_live_tool
            real_estate_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("agent"), "real_estate_agent")
        self.assertEqual(result.get("status"), "executed")
        self.assertEqual(result.get("primary_store"), "rdb")
        self.assertEqual(result.get("region_code"), "11680")
        self.assertEqual(result.get("property_type"), "apartment")
        self.assertTrue(result.get("needs_companion_branch"))
        self.assertEqual(result.get("companion_branch"), "graph")

    def test_real_estate_agent_graph_branch_degraded(self):
        original_execute_live_tool = real_estate_agent_module.execute_live_tool
        original_detect_companion_branch = real_estate_agent_module.detect_companion_branch
        real_estate_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "graph",
                "status": "degraded",
                "reason": "graph_template_empty_result",
            }
        )
        real_estate_agent_module.detect_companion_branch = lambda branch, tool_probe: None
        try:
            result = run_real_estate_agent_stub(
                branch="graph",
                request=_Request(region_code="11110", property_type="jeonse"),
                route_decision={"selected_type": "real_estate_detail"},
                context_meta={},
            )
        finally:
            real_estate_agent_module.execute_live_tool = original_execute_live_tool
            real_estate_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("status"), "degraded")
        self.assertEqual(result.get("primary_store"), "neo4j")
        self.assertFalse(result.get("needs_companion_branch"))
        self.assertIsNone(result.get("companion_branch"))


if __name__ == "__main__":
    unittest.main()
