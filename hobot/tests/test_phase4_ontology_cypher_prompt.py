import unittest

import service.graph.rag.agents.ontology_agent as ontology_agent_module
from service.graph.rag.agents.ontology_agent import run_ontology_agent_stub
from service.graph.rag.templates.cypher_schema_prompt import (
    PROMPT_VERSION,
    build_ontology_cypher_prompt_contract,
    validate_cypher_direction,
)


class _Request:
    def __init__(self, question: str):
        self.question = question


class TestPhase4OntologyCypherPrompt(unittest.TestCase):
    def test_build_contract_contains_direction_schema_and_few_shot(self):
        contract = build_ontology_cypher_prompt_contract("AAPL 일봉 추이 알려줘")
        self.assertEqual(contract.get("prompt_version"), PROMPT_VERSION)
        schema_text = str(contract.get("schema_string") or "")
        self.assertIn("(Company)-[:HAS_DAILY_BAR]->(EquityDailyBar)", schema_text)
        few_shots = contract.get("few_shots") or []
        self.assertGreaterEqual(len(few_shots), 1)
        self.assertIn("Wrong:", str(contract.get("system_prompt") or ""))
        self.assertIn("Correct:", str(contract.get("system_prompt") or ""))

    def test_validate_cypher_direction_detects_reverse_relation(self):
        reversed_query = (
            "MATCH (c:Company)<-[:HAS_DAILY_BAR]-(b:EquityDailyBar) "
            "WHERE c.security_id='US:AAPL' RETURN count(b)"
        )
        result = validate_cypher_direction(reversed_query)
        self.assertFalse(result.get("is_valid"))
        violations = result.get("violations") or []
        self.assertGreaterEqual(len(violations), 1)
        self.assertTrue(any(item.get("relation") == "HAS_DAILY_BAR" for item in violations))

    def test_ontology_agent_graph_branch_includes_prompt_contract_and_validation(self):
        original_execute_live_tool = ontology_agent_module.execute_live_tool
        ontology_agent_module.execute_live_tool = (
            lambda **kwargs: {
                "tool": "graph",
                "status": "ok",
                "query": "MATCH (e:Event)-[:ABOUT_THEME]->(t:MacroTheme) RETURN count(t) AS metric_value",
            }
        )
        try:
            result = run_ontology_agent_stub(
                branch="graph",
                request=_Request("이벤트와 테마 연결 경로 보여줘"),
                route_decision={"selected_type": "general_macro"},
                context_meta={},
            )
        finally:
            ontology_agent_module.execute_live_tool = original_execute_live_tool

        contract = result.get("cypher_prompt_contract") or {}
        self.assertEqual(contract.get("prompt_version"), PROMPT_VERSION)
        self.assertGreaterEqual(int(contract.get("schema_line_count") or 0), 1)
        self.assertGreaterEqual(int(contract.get("few_shot_count") or 0), 1)
        self.assertTrue(contract.get("schema_hash"))

        tool_probe = result.get("tool_probe") or {}
        self.assertEqual(tool_probe.get("schema_prompt_version"), PROMPT_VERSION)
        direction_validation = tool_probe.get("cypher_direction_validation") or {}
        self.assertTrue(direction_validation.get("is_valid"))


if __name__ == "__main__":
    unittest.main()
