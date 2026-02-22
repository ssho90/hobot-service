import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sys
import types

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.scheduler.phase5_regression_batch import (
    Phase5RegressionRequestConfig,
    run_phase5_golden_regression_jobs,
)


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class TestPhase5RegressionBatchRunner(unittest.TestCase):
    def _make_temp_golden_set(self) -> Path:
        payload = [
            {
                "case_id": "US_ONLY",
                "question_id": "Q1",
                "question": "팔란티어 전망",
                "expected_country_codes": ["US"],
                "min_citations": 1,
                "required_keys": ["answer.conclusion"],
            },
            {
                "case_id": "USKR_COMPARE",
                "question_id": "Q3",
                "question": "한미 비교",
                "expected_country_codes": ["US", "KR"],
                "min_citations": 1,
                "required_keys": ["answer.conclusion"],
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            return Path(tmp.name)

    def test_run_jobs_filters_case_ids_and_builds_request(self):
        golden_path = self._make_temp_golden_set()
        try:
            with patch(
                "service.graph.scheduler.phase5_regression_batch.generate_graph_rag_answer",
                return_value=_DummyResponse(
                    {
                        "answer": {"conclusion": "ok"},
                        "citations": [{"id": 1}],
                        "context_meta": {"resolved_country_codes": ["US"]},
                    }
                ),
            ) as answer_mock:
                report = run_phase5_golden_regression_jobs(
                    golden_set_path=golden_path,
                    case_ids=["US_ONLY"],
                    request_config=Phase5RegressionRequestConfig(
                        model="gemini-3-flash-preview",
                        time_range="30d",
                        as_of_date=date(2026, 2, 19),
                    ),
                )

            self.assertEqual(report["total_cases"], 1)
            self.assertEqual(report["passed_cases"], 1)
            self.assertEqual(report["selected_case_ids"], ["US_ONLY"])
            request = answer_mock.call_args.args[0]
            self.assertEqual(request.question_id, "Q1")
            self.assertEqual(request.country_code, "US")
            self.assertEqual(request.time_range, "30d")
            self.assertEqual(request.as_of_date, date(2026, 2, 19))
        finally:
            golden_path.unlink(missing_ok=True)

    def test_run_jobs_maps_country_scope_for_us_kr_case(self):
        golden_path = self._make_temp_golden_set()
        try:
            with patch(
                "service.graph.scheduler.phase5_regression_batch.generate_graph_rag_answer",
                side_effect=[
                    _DummyResponse(
                        {
                            "answer": {"conclusion": "ok"},
                            "citations": [{"id": 1}],
                            "context_meta": {"resolved_country_codes": ["US"]},
                        }
                    ),
                    _DummyResponse(
                        {
                            "answer": {"conclusion": "ok"},
                            "citations": [{"id": 1}],
                            "context_meta": {"resolved_country_codes": ["US", "KR"]},
                        }
                    ),
                ],
            ) as answer_mock:
                report = run_phase5_golden_regression_jobs(golden_set_path=golden_path)

            self.assertEqual(report["total_cases"], 2)
            requested_scopes = {call.args[0].country_code for call in answer_mock.call_args_list}
            self.assertEqual(requested_scopes, {"US", "US-KR"})
        finally:
            golden_path.unlink(missing_ok=True)

    def test_run_jobs_raises_when_case_id_not_found(self):
        golden_path = self._make_temp_golden_set()
        try:
            with self.assertRaises(ValueError):
                run_phase5_golden_regression_jobs(
                    golden_set_path=golden_path,
                    case_ids=["DOES_NOT_EXIST"],
                )
        finally:
            golden_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
