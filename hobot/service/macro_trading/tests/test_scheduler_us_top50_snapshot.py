import unittest
from datetime import date
from unittest.mock import patch

from service.macro_trading import scheduler


class _FakeUSCollector:
    def __init__(self, diff_result):
        self._diff_result = diff_result

    def build_top50_snapshot_diff(self, **kwargs):
        return dict(self._diff_result, kwargs=kwargs)


class TestUSTop50SnapshotScheduler(unittest.TestCase):
    def test_monthly_snapshot_job_skips_on_non_target_day(self):
        with patch(
            "service.macro_trading.scheduler.capture_us_top50_snapshot"
        ) as capture_mock, patch(
            "service.macro_trading.scheduler.get_us_corporate_collector"
        ) as collector_mock:
            result = scheduler.run_us_top50_monthly_snapshot_job(
                target_day_of_month=1,
                run_date=date(2026, 2, 17),
            )

        capture_mock.assert_not_called()
        collector_mock.assert_not_called()
        self.assertEqual(result["status"], "skipped")

    def test_monthly_snapshot_job_captures_and_builds_diff_on_target_day(self):
        fake_collector = _FakeUSCollector(
            {
                "latest_snapshot_date": "2026-02-01",
                "previous_snapshot_date": "2026-01-01",
                "added_count": 1,
                "removed_count": 2,
                "rank_changed_count": 7,
            }
        )
        with patch(
            "service.macro_trading.scheduler.capture_us_top50_snapshot",
            return_value={"saved_rows": 50, "snapshot_date": "2026-02-01"},
        ) as capture_mock, patch(
            "service.macro_trading.scheduler.get_us_corporate_collector",
            return_value=fake_collector,
        ):
            result = scheduler.run_us_top50_monthly_snapshot_job(
                target_day_of_month=1,
                market="US",
                max_symbol_count=50,
                run_date=date(2026, 2, 1),
            )

        self.assertEqual(result["status"], "completed")
        capture_mock.assert_called_once()
        self.assertEqual(result["capture"]["saved_rows"], 50)
        self.assertEqual(result["diff"]["added_count"], 1)
        self.assertEqual(result["diff"]["removed_count"], 2)
        self.assertEqual(result["diff"]["rank_changed_count"], 7)


if __name__ == "__main__":
    unittest.main()
