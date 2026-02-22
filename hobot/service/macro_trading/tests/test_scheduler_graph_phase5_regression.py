import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import schedule

from service.macro_trading import scheduler


class TestGraphPhase5RegressionScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_run_graph_rag_phase5_regression_records_report(self):
        fake_report = {
            "total_cases": 6,
            "passed_cases": 5,
            "failed_cases": 1,
            "pass_rate_pct": 83.33,
            "failure_counts": {"freshness_stale": 1},
            "tool_mode_counts": {"parallel": 4, "single": 2},
            "target_agent_counts": {"equity_analyst_agent": 3, "macro_economy_agent": 4},
            "freshness_status_counts": {"healthy": 5, "stale": 1},
            "structured_citation_stats": {
                "total_count": 9,
                "average_count": 1.5,
                "max_count": 3,
                "cases_with_structured_citations": 6,
            },
            "selected_case_ids": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"],
            "golden_set_path": "/tmp/phase5.json",
            "request_config": {"model": "gemini-3-flash-preview"},
            "case_results": [
                {
                    "case_id": "Q1_US_SINGLE_STOCK_DROP_CAUSE_001",
                    "question_id": "Q1",
                    "passed": False,
                    "citation_count": 1,
                    "structured_citation_count": 2,
                    "tool_mode": "parallel",
                    "expected_tool_mode": "parallel",
                    "target_agents": ["equity_analyst_agent", "ontology_master_agent"],
                    "freshness_status": "stale",
                    "freshness_age_hours": 201.2,
                    "latest_evidence_published_at": "2026-02-12T00:03:46+00:00",
                    "recent_guard_enabled": True,
                    "recent_guard_target_count": 1,
                    "recent_guard_max_age_hours": 168,
                    "recent_guard_require_focus_match": False,
                    "recent_guard_candidate_recent_evidence_count": 0,
                    "recent_guard_selected_recent_citation_count": 0,
                    "recent_guard_added_recent_citation_count": 0,
                    "recent_guard_target_satisfied": False,
                    "failures": [
                        {"category": "freshness_stale", "message": "data_age_exceeded:200>168"},
                        {"category": "citation_missing", "message": "min_citations_not_met:1<3"},
                    ],
                }
            ],
        }
        with patch(
            "service.macro_trading.scheduler.run_phase5_golden_regression_jobs",
            return_value=fake_report,
        ) as run_mock, patch(
            "service.macro_trading.scheduler._record_collection_run_report",
        ) as report_mock, patch(
            "service.macro_trading.scheduler._send_phase5_regression_alert",
            return_value=True,
        ) as alert_mock:
            result = scheduler.run_graph_rag_phase5_regression()

        self.assertEqual(result["total_cases"], 6)
        run_mock.assert_called_once()
        report_mock.assert_called_once()
        alert_mock.assert_called_once()
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["job_code"], scheduler.GRAPH_RAG_PHASE5_REGRESSION_JOB_CODE)
        self.assertEqual(kwargs["success_count"], 5)
        self.assertEqual(kwargs["failure_count"], 1)
        self.assertTrue(kwargs["run_success"])
        self.assertEqual(kwargs["status_override"], "warning")
        details = kwargs["details"]
        self.assertEqual(details["failed_case_debug_total"], 1)
        self.assertEqual(details["failed_case_debug_returned"], 1)
        self.assertEqual(len(details["failed_case_debug_entries"]), 1)
        self.assertEqual(details["tool_mode_counts"], {"parallel": 4, "single": 2})
        self.assertEqual(
            details["target_agent_counts"],
            {"equity_analyst_agent": 3, "macro_economy_agent": 4},
        )
        self.assertEqual(details["freshness_status_counts"], {"healthy": 5, "stale": 1})
        self.assertEqual(
            details["structured_citation_stats"],
            {
                "total_count": 9,
                "average_count": 1.5,
                "max_count": 3,
                "cases_with_structured_citations": 6,
            },
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["case_id"],
            "Q1_US_SINGLE_STOCK_DROP_CAUSE_001",
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["freshness_status"],
            "stale",
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["freshness_age_hours"],
            201.2,
        )
        self.assertIn(
            "freshness_stale",
            details["failed_case_debug_entries"][0]["failure_categories"],
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["recent_guard_candidate_recent_evidence_count"],
            0,
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["recent_guard_target_satisfied"],
            False,
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["structured_citation_count"],
            2,
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["tool_mode"],
            "parallel",
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["expected_tool_mode"],
            "parallel",
        )
        self.assertEqual(
            details["failed_case_debug_entries"][0]["target_agents"],
            ["equity_analyst_agent", "ontology_master_agent"],
        )

    def test_run_graph_rag_phase5_regression_records_failure_on_exception(self):
        with patch(
            "service.macro_trading.scheduler.run_phase5_golden_regression_jobs",
            side_effect=RuntimeError("phase5 failed"),
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report",
        ) as report_mock, patch(
            "service.macro_trading.scheduler._send_phase5_regression_alert",
            return_value=True,
        ) as alert_mock:
            with self.assertRaises(RuntimeError):
                scheduler.run_graph_rag_phase5_regression.__wrapped__()

        report_mock.assert_called_once()
        alert_mock.assert_called_once()
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["job_code"], scheduler.GRAPH_RAG_PHASE5_REGRESSION_JOB_CODE)
        self.assertFalse(kwargs["run_success"])

    def test_setup_graph_rag_phase5_regression_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "GRAPH_RAG_PHASE5_REGRESSION_ENABLED": "1",
                "GRAPH_RAG_PHASE5_REGRESSION_SCHEDULE_TIME": "",
            },
            clear=False,
        ):
            scheduler.setup_graph_rag_phase5_regression_scheduler()

        jobs = [
            job
            for job in schedule.get_jobs()
            if "graph_rag_phase5_regression_daily" in job.tags
        ]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "days")
        self.assertEqual(str(jobs[0].at_time), "08:10:00")

    def test_run_graph_rag_phase5_weekly_report_records_summary(self):
        class _Cursor:
            def __init__(self, rows):
                self._rows = rows

            def execute(self, *_args, **_kwargs):
                return None

            def fetchall(self):
                return self._rows

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class _Connection:
            def __init__(self, rows):
                self._rows = rows

            def cursor(self):
                return _Cursor(self._rows)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        now = datetime.now()
        rows = [
            {
                "run_count": 2,
                "success_run_count": 2,
                "failed_run_count": 0,
                "success_count": 6,
                "failure_count": 0,
                "last_success_rate_pct": 0.0,
                "last_status": "healthy",
                "details_json": {
                    "failure_counts": {"routing_mismatch": 0},
                    "tool_mode_counts": {"parallel": 3, "single": 2},
                    "target_agent_counts": {"macro_economy_agent": 4},
                    "freshness_status_counts": {"healthy": 5},
                    "structured_citation_stats": {"average_count": 1.4, "total_count": 8},
                    "failed_case_debug_entries": [
                        {
                            "case_id": "Q3_US_MULTI_STOCK_PARALLEL_001",
                            "question_id": "Q3",
                            "tool_mode": "parallel",
                            "freshness_status": "healthy",
                            "failure_categories": ["citation_missing"],
                        }
                    ],
                },
                "report_date": (now - timedelta(days=1)).date(),
                "updated_at": now - timedelta(days=1),
            },
            {
                "run_count": 1,
                "success_run_count": 1,
                "failed_run_count": 0,
                "success_count": 5,
                "failure_count": 1,
                "last_success_rate_pct": 83.33,
                "last_status": "warning",
                "details_json": {
                    "failure_counts": {"citation_missing": 1},
                    "tool_mode_counts": {"parallel": 2, "single": 1},
                    "target_agent_counts": {"equity_analyst_agent": 3},
                    "freshness_status_counts": {"healthy": 4, "warning": 1},
                    "structured_citation_stats": {"average_count": 1.1, "total_count": 6},
                    "failed_case_debug_entries": [
                        {
                            "case_id": "Q3_US_MULTI_STOCK_PARALLEL_001",
                            "question_id": "Q3",
                            "tool_mode": "parallel",
                            "freshness_status": "warning",
                            "failure_categories": ["citation_missing"],
                        },
                        {
                            "case_id": "Q2_US_SINGLE_STOCK_PARALLEL_001",
                            "question_id": "Q2",
                            "tool_mode": "parallel",
                            "freshness_status": "warning",
                            "failure_categories": ["freshness_stale"],
                        },
                    ],
                },
                "report_date": (now - timedelta(days=2)).date(),
                "updated_at": now - timedelta(days=2),
            },
        ]
        with patch(
            "service.macro_trading.scheduler.get_db_connection",
            return_value=_Connection(rows),
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report",
        ) as report_mock, patch.dict(
            os.environ,
            {
                "GRAPH_RAG_PHASE5_WEEKLY_MIN_RUNS": "2",
                "GRAPH_RAG_PHASE5_WEEKLY_MIN_AVG_PASS_RATE": "80",
                "GRAPH_RAG_PHASE5_WEEKLY_MAX_WARNING_RUNS": "2",
                "GRAPH_RAG_PHASE5_WEEKLY_MAX_ROUTING_MISMATCH": "0",
                "GRAPH_RAG_PHASE5_WEEKLY_MIN_STRUCTURED_CITATION_AVG": "0.5",
            },
            clear=False,
        ):
            result = scheduler.run_graph_rag_phase5_weekly_report.__wrapped__(days=7)

        self.assertEqual(result["total_runs"], 3)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["routing_mismatch_count"], 0)
        self.assertEqual(result["tool_mode_counts"], {"parallel": 5, "single": 3})
        self.assertEqual(result["avg_pass_rate_pct"], 94.44)
        self.assertEqual(
            result["top_failure_categories"],
            [{"category": "citation_missing", "count": 1}],
        )
        self.assertEqual(result["top_failed_cases"][0]["case_id"], "Q3_US_MULTI_STOCK_PARALLEL_001")
        self.assertEqual(result["top_failed_cases"][0]["count"], 2)
        report_kwargs = report_mock.call_args.kwargs
        self.assertEqual(report_kwargs["job_code"], scheduler.GRAPH_RAG_PHASE5_WEEKLY_REPORT_JOB_CODE)
        self.assertEqual(report_kwargs["status_override"], "healthy")

    def test_run_graph_rag_phase5_weekly_report_warns_on_routing_mismatch(self):
        class _Cursor:
            def __init__(self, rows):
                self._rows = rows

            def execute(self, *_args, **_kwargs):
                return None

            def fetchall(self):
                return self._rows

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class _Connection:
            def __init__(self, rows):
                self._rows = rows

            def cursor(self):
                return _Cursor(self._rows)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        rows = [
            {
                "run_count": 1,
                "success_run_count": 1,
                "failed_run_count": 0,
                "success_count": 4,
                "failure_count": 2,
                "last_success_rate_pct": 66.67,
                "last_status": "warning",
                "details_json": {
                    "failure_counts": {"routing_mismatch": 2},
                    "structured_citation_stats": {"average_count": 1.0, "total_count": 4},
                },
                "report_date": (datetime.now() - timedelta(days=1)).date(),
                "updated_at": datetime.now() - timedelta(days=1),
            }
        ]
        with patch(
            "service.macro_trading.scheduler.get_db_connection",
            return_value=_Connection(rows),
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report",
        ) as report_mock, patch.dict(
            os.environ,
            {
                "GRAPH_RAG_PHASE5_WEEKLY_MIN_RUNS": "1",
                "GRAPH_RAG_PHASE5_WEEKLY_MIN_AVG_PASS_RATE": "60",
                "GRAPH_RAG_PHASE5_WEEKLY_MAX_WARNING_RUNS": "2",
                "GRAPH_RAG_PHASE5_WEEKLY_MAX_ROUTING_MISMATCH": "0",
            },
            clear=False,
        ):
            result = scheduler.run_graph_rag_phase5_weekly_report.__wrapped__(days=7)

        self.assertEqual(result["status"], "warning")
        self.assertIn("routing_mismatch", result["status_reason"])
        report_kwargs = report_mock.call_args.kwargs
        self.assertEqual(report_kwargs["status_override"], "warning")

    def test_setup_graph_rag_phase5_weekly_report_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "GRAPH_RAG_PHASE5_WEEKLY_REPORT_ENABLED": "1",
                "GRAPH_RAG_PHASE5_WEEKLY_REPORT_SCHEDULE_DAY": "sunday",
                "GRAPH_RAG_PHASE5_WEEKLY_REPORT_SCHEDULE_TIME": "09:15",
                "GRAPH_RAG_PHASE5_WEEKLY_REPORT_WINDOW_DAYS": "9",
            },
            clear=False,
        ):
            scheduler.setup_graph_rag_phase5_weekly_report_scheduler()

        jobs = [
            job
            for job in schedule.get_jobs()
            if "graph_rag_phase5_weekly_report" in job.tags
        ]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(str(jobs[0].at_time), "09:15:00")


if __name__ == "__main__":
    unittest.main()
