import json
import tempfile
import unittest
from pathlib import Path

from service.graph.monitoring.phase5_regression import (
    FAILURE_CITATION_MISSING,
    FAILURE_EVALUATOR_ERROR,
    FAILURE_FRESHNESS_STALE,
    FAILURE_GUARDRAIL_VIOLATION,
    FAILURE_ROUTING_MISMATCH,
    FAILURE_SCHEMA_MISMATCH,
    FAILURE_SCOPE_VIOLATION,
    GOLDEN_SET_DEFAULT_PATH,
    GoldenQuestionCase,
    evaluate_golden_case_response,
    load_golden_question_cases,
    run_phase5_golden_set_regression,
    run_phase5_golden_set_regression_from_file,
)


class TestPhase5GoldenRegression(unittest.TestCase):
    def test_default_golden_set_file_exists_and_loads(self):
        self.assertTrue(Path(GOLDEN_SET_DEFAULT_PATH).exists())
        cases = load_golden_question_cases(GOLDEN_SET_DEFAULT_PATH)
        self.assertGreaterEqual(len(cases), 14)
        question_ids = {case.question_id for case in cases}
        self.assertTrue({"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}.issubset(question_ids))
        expected_modes = {case.expected_tool_mode for case in cases if case.expected_tool_mode}
        self.assertTrue({"single", "parallel"}.issubset(expected_modes))
        coverage = {}
        for case in cases:
            for agent_name in case.expected_target_agents:
                coverage.setdefault(agent_name, set()).add(case.expected_tool_mode)
        for required_agent in (
            "macro_economy_agent",
            "equity_analyst_agent",
            "real_estate_agent",
            "ontology_master_agent",
        ):
            self.assertTrue(
                {"single", "parallel"}.issubset(coverage.get(required_agent, set())),
                msg=f"{required_agent} coverage missing: {coverage.get(required_agent, set())}",
            )

    def test_evaluate_case_response_detects_failure_categories(self):
        case = GoldenQuestionCase(
            case_id="case_1",
            question_id="Q6",
            question="질문",
            expected_country_codes=["US"],
            min_citations=3,
            required_keys=["answer.conclusion", "answer.key_points"],
            disallowed_phrases=["무조건 매수"],
            max_data_age_hours=72,
        )
        response = {
            "answer": {
                "uncertainty": "근거 불충분",
            },
            "citations": [{"id": 1}],
            "data_freshness": {"status": "stale", "age_hours": 200},
            "context_meta": {"resolved_country_codes": ["KR"]},
            "conclusion": "지금은 무조건 매수",
        }

        result = evaluate_golden_case_response(case, response)
        self.assertFalse(result["passed"])
        categories = {item["category"] for item in result["failures"]}
        self.assertIn(FAILURE_SCHEMA_MISMATCH, categories)
        self.assertIn(FAILURE_CITATION_MISSING, categories)
        self.assertIn(FAILURE_FRESHNESS_STALE, categories)
        self.assertIn(FAILURE_SCOPE_VIOLATION, categories)
        self.assertIn(FAILURE_GUARDRAIL_VIOLATION, categories)
        self.assertIsNone(result["recent_guard_enabled"])
        self.assertEqual(result["structured_citation_count"], 0)
        self.assertIsNone(result["tool_mode"])
        self.assertEqual(result["target_agents"], [])

    def test_evaluate_case_response_includes_recent_guard_debug_fields(self):
        case = GoldenQuestionCase(
            case_id="case_2",
            question_id="Q1",
            question="질문",
            expected_country_codes=["US"],
            min_citations=1,
            required_keys=["answer.conclusion"],
        )
        response = {
            "answer": {"conclusion": "ok"},
            "citations": [{"id": 1}],
            "structured_citations": [
                {"dataset_code": "US_TOP50_DAILY_OHLCV"},
                {"dataset_code": "US_TOP50_FINANCIALS"},
            ],
            "context_meta": {
                "resolved_country_codes": ["US"],
                "query_route": {
                    "tool_mode": "parallel",
                    "target_agents": ["equity_analyst_agent", "ontology_master_agent"],
                },
                "recent_citation_guard": {
                    "enabled": True,
                    "target_count": 1,
                    "max_age_hours": 168,
                    "require_focus_match": True,
                    "candidate_recent_evidence_count": 0,
                    "selected_recent_citation_count": 0,
                    "added_recent_citation_count": 0,
                    "target_satisfied": False,
                },
            },
        }

        result = evaluate_golden_case_response(case, response)
        self.assertEqual(result["recent_guard_enabled"], True)
        self.assertEqual(result["recent_guard_target_count"], 1)
        self.assertEqual(result["recent_guard_max_age_hours"], 168)
        self.assertEqual(result["recent_guard_require_focus_match"], True)
        self.assertEqual(result["recent_guard_candidate_recent_evidence_count"], 0)
        self.assertEqual(result["recent_guard_selected_recent_citation_count"], 0)
        self.assertEqual(result["recent_guard_added_recent_citation_count"], 0)
        self.assertEqual(result["recent_guard_target_satisfied"], False)
        self.assertEqual(result["structured_citation_count"], 2)
        self.assertEqual(result["tool_mode"], "parallel")
        self.assertEqual(
            result["target_agents"],
            ["equity_analyst_agent", "ontology_master_agent"],
        )

    def test_evaluate_case_response_detects_tool_mode_mismatch(self):
        case = GoldenQuestionCase(
            case_id="case_3",
            question_id="Q5",
            question="질문",
            expected_country_codes=["US"],
            min_citations=1,
            required_keys=["answer.conclusion"],
            expected_tool_mode="parallel",
        )
        response = {
            "answer": {"conclusion": "ok"},
            "citations": [{"id": 1}],
            "context_meta": {
                "resolved_country_codes": ["US"],
                "query_route": {
                    "tool_mode": "single",
                    "target_agents": ["macro_economy_agent"],
                },
            },
        }

        result = evaluate_golden_case_response(case, response)
        self.assertFalse(result["passed"])
        categories = {item["category"] for item in result["failures"]}
        self.assertIn(FAILURE_ROUTING_MISMATCH, categories)
        self.assertEqual(result["expected_tool_mode"], "parallel")
        self.assertEqual(result["tool_mode"], "single")

    def test_evaluate_case_response_detects_target_agent_mismatch(self):
        case = GoldenQuestionCase(
            case_id="case_4",
            question_id="Q3",
            question="질문",
            expected_country_codes=["US"],
            min_citations=1,
            required_keys=["answer.conclusion"],
            expected_target_agents=["ontology_master_agent", "macro_economy_agent"],
        )
        response = {
            "answer": {"conclusion": "ok"},
            "citations": [{"id": 1}],
            "context_meta": {
                "resolved_country_codes": ["US"],
                "query_route": {
                    "tool_mode": "single",
                    "target_agents": ["macro_economy_agent"],
                },
            },
        }

        result = evaluate_golden_case_response(case, response)
        self.assertFalse(result["passed"])
        categories = {item["category"] for item in result["failures"]}
        self.assertIn(FAILURE_ROUTING_MISMATCH, categories)
        self.assertEqual(result["expected_target_agents"], ["ontology_master_agent", "macro_economy_agent"])
        self.assertEqual(result["missing_target_agents"], ["ontology_master_agent"])

    def test_run_regression_aggregates_failure_counts_and_evaluator_errors(self):
        cases = [
            GoldenQuestionCase(case_id="ok", question_id="Q1", question="a", required_keys=["answer.conclusion"]),
            GoldenQuestionCase(case_id="err", question_id="Q2", question="b", required_keys=["answer.conclusion"]),
        ]

        def evaluator(case: GoldenQuestionCase):
            if case.case_id == "err":
                raise RuntimeError("boom")
            return {
                "answer": {"conclusion": "ok"},
                "citations": [{"id": 1}, {"id": 2}, {"id": 3}],
                "structured_citations": [{"dataset_code": "FRED_DATA"}],
                "context_meta": {"resolved_country_codes": ["US"]},
                "query_route": {
                    "tool_mode": "single",
                    "target_agents": ["macro_economy_agent"],
                },
            }

        report = run_phase5_golden_set_regression(cases=cases, evaluator=evaluator)
        self.assertEqual(report["total_cases"], 2)
        self.assertEqual(report["passed_cases"], 1)
        self.assertEqual(report["failed_cases"], 1)
        self.assertEqual(report["failure_counts"].get(FAILURE_EVALUATOR_ERROR), 1)
        self.assertEqual(report["tool_mode_counts"], {"single": 1, "unknown": 1})
        self.assertEqual(report["target_agent_counts"], {"macro_economy_agent": 1})
        self.assertEqual(report["freshness_status_counts"], {"unknown": 2})
        self.assertEqual(
            report["structured_citation_stats"],
            {
                "total_count": 1,
                "average_count": 0.5,
                "max_count": 1,
                "cases_with_structured_citations": 1,
            },
        )

    def test_run_regression_from_file_uses_loaded_cases(self):
        payload = [
            {
                "case_id": "QX_001",
                "question_id": "QX",
                "question": "테스트 질문",
                "expected_country_codes": ["US"],
                "min_citations": 1,
                "required_keys": ["answer.conclusion"],
            }
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        try:
            report = run_phase5_golden_set_regression_from_file(
                golden_set_path=tmp_path,
                evaluator=lambda _case: {
                    "answer": {"conclusion": "ok"},
                    "citations": [{"id": 1}],
                    "context_meta": {"resolved_country_codes": ["US"]},
                },
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        self.assertEqual(report["total_cases"], 1)
        self.assertEqual(report["passed_cases"], 1)
        self.assertEqual(report["failed_cases"], 0)


if __name__ == "__main__":
    unittest.main()
