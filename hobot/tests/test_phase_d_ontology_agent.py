import unittest

import service.graph.rag.agents.ontology_agent as ontology_agent_module
from service.graph.rag.agents.ontology_agent import run_ontology_agent_stub
from service.graph.rag.templates.cypher_schema_prompt import PROMPT_VERSION


class _Request:
    question = "이벤트-테마-지표 경로 보여줘"


class TestPhaseDOntologyAgent(unittest.TestCase):
    def test_ontology_agent_graph_branch_includes_direction_validation(self):
        original_execute_live_tool = ontology_agent_module.execute_live_tool
        original_detect_companion_branch = ontology_agent_module.detect_companion_branch
        ontology_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "graph",
                "status": "ok",
                "query": "MATCH (e:Event)-[:ABOUT_THEME]->(t:MacroTheme) RETURN count(t) AS metric_value",
            }
        )
        ontology_agent_module.detect_companion_branch = lambda branch, tool_probe: None
        try:
            result = run_ontology_agent_stub(
                branch="graph",
                request=_Request(),
                route_decision={"selected_type": "general_macro"},
                context_meta={},
            )
        finally:
            ontology_agent_module.execute_live_tool = original_execute_live_tool
            ontology_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("agent"), "ontology_master_agent")
        self.assertEqual(result.get("status"), "executed")
        self.assertEqual(result.get("primary_store"), "neo4j")
        self.assertFalse(result.get("needs_companion_branch"))
        self.assertIsNone(result.get("companion_branch"))

        contract = result.get("cypher_prompt_contract") or {}
        self.assertEqual(contract.get("prompt_version"), PROMPT_VERSION)
        self.assertGreaterEqual(int(contract.get("schema_line_count") or 0), 1)
        self.assertGreaterEqual(int(contract.get("few_shot_count") or 0), 1)
        self.assertTrue(contract.get("schema_hash"))

        tool_probe = result.get("tool_probe") or {}
        self.assertEqual(tool_probe.get("schema_prompt_version"), PROMPT_VERSION)
        validation = tool_probe.get("cypher_direction_validation") or {}
        self.assertTrue(validation.get("is_valid"))

    def test_ontology_agent_sql_branch_can_request_companion(self):
        original_execute_live_tool = ontology_agent_module.execute_live_tool
        original_detect_companion_branch = ontology_agent_module.detect_companion_branch
        ontology_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "sql",
                "status": "degraded",
                "reason": "sql_template_empty_result",
            }
        )
        ontology_agent_module.detect_companion_branch = lambda branch, tool_probe: "graph"
        try:
            result = run_ontology_agent_stub(
                branch="sql",
                request=_Request(),
                route_decision={"selected_type": "general_macro"},
                context_meta={},
            )
        finally:
            ontology_agent_module.execute_live_tool = original_execute_live_tool
            ontology_agent_module.detect_companion_branch = original_detect_companion_branch

        self.assertEqual(result.get("status"), "degraded")
        self.assertTrue(result.get("needs_companion_branch"))
        self.assertEqual(result.get("companion_branch"), "graph")


if __name__ == "__main__":
    unittest.main()
