import unittest
from datetime import datetime
from unittest.mock import patch

from service.macro_trading.indicator_health import _build_health, get_macro_indicator_health_snapshot


class TestIndicatorHealth(unittest.TestCase):
    def test_daily_weekend_adds_grace(self):
        # Saturday 기준, daily 지표는 주말 48시간 grace가 추가되어 stale이 완화되어야 한다.
        now_at = datetime(2026, 2, 15, 12, 0, 0)  # Sunday
        reference_at = datetime(2026, 2, 13, 12, 0, 0)  # Friday

        health = _build_health(
            reference_at,
            expected_interval_hours=24,
            collection_enabled=True,
            frequency="daily",
            now_at=now_at,
        )

        self.assertEqual(health["stale_threshold_hours"], 84)
        self.assertFalse(health["is_stale"])
        self.assertEqual(health["health"], "healthy")

    def test_daily_weekday_keeps_original_threshold(self):
        now_at = datetime(2026, 2, 13, 12, 0, 0)  # Friday
        reference_at = datetime(2026, 2, 11, 23, 0, 0)  # ~37h lag

        health = _build_health(
            reference_at,
            expected_interval_hours=24,
            collection_enabled=True,
            frequency="daily",
            now_at=now_at,
        )

        self.assertEqual(health["stale_threshold_hours"], 36)
        self.assertTrue(health["is_stale"])
        self.assertEqual(health["health"], "stale")

    def test_snapshot_includes_us_corporate_registry_codes(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        codes = {row["code"] for row in snapshot["indicators"]}
        self.assertIn("KR_TOP50_ENTITY_REGISTRY", codes)
        self.assertIn("KR_TOP50_TIER_STATE", codes)
        self.assertIn("KR_TOP50_CORP_CODE_MAPPING_VALIDATION", codes)
        self.assertIn("KR_DART_DPLUS1_SLA", codes)
        self.assertIn("KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE", codes)
        self.assertIn("US_TOP50_ENTITY_REGISTRY", codes)
        self.assertIn("US_TOP50_TIER_STATE", codes)
        self.assertIn("US_TOP50_UNIVERSE_SNAPSHOT", codes)
        self.assertIn("US_TOP50_FINANCIALS", codes)
        self.assertIn("US_SEC_CIK_MAPPING", codes)
        self.assertIn("US_TOP50_EARNINGS_EVENTS_CONFIRMED", codes)
        self.assertIn("US_TOP50_EARNINGS_EVENTS_EXPECTED", codes)
        self.assertIn("US_TOP50_EARNINGS_WATCH_SUCCESS_RATE", codes)

    def test_snapshot_formats_watch_success_rate_note(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={
                "KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE": {
                    "last_observation_date": datetime(2026, 2, 17).date(),
                    "last_collected_at": datetime(2026, 2, 17, 6, 40, 0),
                    "latest_value": 93.5,
                    "run_count": 8,
                    "success_run_count": 7,
                    "failed_run_count": 1,
                    "success_count": 187,
                    "failure_count": 13,
                    "last_status": "warning",
                    "last_error": "timeout",
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE"
        )
        self.assertIn("일간 실행 8회", row["note"])
        self.assertIn("성공/실패 7/1", row["note"])
        self.assertIn("요청 성공 187/200", row["note"])
        self.assertIn("최근상태 warning", row["note"])

    def test_snapshot_formats_dplus1_sla_note(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={
                "KR_DART_DPLUS1_SLA": {
                    "last_observation_date": datetime(2026, 2, 17).date(),
                    "last_collected_at": datetime(2026, 2, 17, 6, 25, 0),
                    "latest_value": 2,
                    "checked_event_count": 24,
                    "met_sla_count": 22,
                    "violated_sla_count": 2,
                    "missing_financial_count": 1,
                    "late_financial_count": 1,
                    "status": "warning",
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "KR_DART_DPLUS1_SLA"
        )
        self.assertIn("점검대상 24건", row["note"])
        self.assertIn("준수/위반 22/2", row["note"])
        self.assertIn("미수집 1건", row["note"])
        self.assertIn("지연반영 1건", row["note"])


if __name__ == "__main__":
    unittest.main()
