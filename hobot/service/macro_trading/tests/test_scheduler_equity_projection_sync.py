import unittest
from datetime import date
from unittest.mock import patch

from service.macro_trading import scheduler


class TestEquityProjectionSyncScheduler(unittest.TestCase):
    def test_sync_records_warning_status_when_lag_exceeds_warn_threshold(self):
        projection_result = {
            "sync_result": {
                "status": "success",
                "row_counts": {
                    "company_rows": 120,
                    "universe_rows": 50,
                    "daily_bar_rows": 500,
                    "earnings_rows": 18,
                },
            },
            "verification": {
                "summary": {
                    "max_trade_date": date(2026, 2, 17),
                    "max_event_date": date(2026, 2, 19),
                }
            },
        }

        with patch.dict(
            "os.environ",
            {
                "EQUITY_GRAPH_PROJECTION_WARN_LAG_HOURS": "24",
                "EQUITY_GRAPH_PROJECTION_FAIL_LAG_HOURS": "96",
                "EQUITY_GRAPH_PROJECTION_SYNC_REPORT_ENABLED": "1",
            },
            clear=False,
        ), patch(
            "service.graph.equity_loader.sync_equity_projection",
            return_value=projection_result,
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report"
        ) as report_mock:
            result = scheduler.sync_equity_projection_to_graph.__wrapped__(
                start_date=date(2026, 2, 10),
                end_date=date(2026, 2, 19),
                country_codes=("KR",),
                include_universe=True,
                include_daily_bars=True,
                include_earnings_events=False,
            )

        health = result["projection_health"]
        self.assertEqual(health["status"], "warning")
        self.assertEqual(health["lag_hours"], 48.0)
        self.assertEqual(health["latest_graph_date"], "2026-02-17")

        report_kwargs = report_mock.call_args.kwargs
        self.assertEqual(
            report_kwargs["job_code"],
            scheduler.EQUITY_GRAPH_PROJECTION_SYNC_JOB_CODE,
        )
        self.assertTrue(report_kwargs["run_success"])
        self.assertEqual(report_kwargs["status_override"], "warning")
        self.assertEqual(report_kwargs["details"]["lag_hours"], 48.0)

    def test_sync_records_failure_report_when_projection_raises(self):
        with patch(
            "service.graph.equity_loader.sync_equity_projection",
            side_effect=RuntimeError("forced sync failure"),
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report"
        ) as report_mock:
            with self.assertRaises(RuntimeError):
                scheduler.sync_equity_projection_to_graph.__wrapped__(
                    start_date=date(2026, 2, 10),
                    end_date=date(2026, 2, 19),
                    country_codes=("US",),
                )

        report_kwargs = report_mock.call_args.kwargs
        self.assertEqual(
            report_kwargs["job_code"],
            scheduler.EQUITY_GRAPH_PROJECTION_SYNC_JOB_CODE,
        )
        self.assertFalse(report_kwargs["run_success"])
        self.assertEqual(report_kwargs["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
