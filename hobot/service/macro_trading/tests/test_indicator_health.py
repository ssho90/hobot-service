import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from service.macro_trading.indicator_health import (
    _build_health,
    _coerce_reference_timestamp,
    get_macro_indicator_health_snapshot,
)


class TestIndicatorHealth(unittest.TestCase):
    def test_coerce_reference_timestamp_supports_iso_string_with_nanoseconds(self):
        reference_at = _coerce_reference_timestamp(
            "2026-02-20T03:03:35.951000000+00:00",
            "2026-02-19",
        )
        self.assertEqual(reference_at, datetime(2026, 2, 20, 3, 3, 35, 951000))

    def test_coerce_reference_timestamp_supports_to_native_temporal(self):
        class _NeoTemporal:
            def to_native(self):
                return datetime(2026, 2, 20, 3, 3, 35, tzinfo=timezone.utc)

        reference_at = _coerce_reference_timestamp(_NeoTemporal(), None)
        self.assertEqual(reference_at, datetime(2026, 2, 20, 3, 3, 35))

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
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        codes = {row["code"] for row in snapshot["indicators"]}
        self.assertIn("KR_TOP50_ENTITY_REGISTRY", codes)
        self.assertIn("TIER1_CORPORATE_EVENT_SYNC", codes)
        self.assertIn("KR_TOP50_TIER_STATE", codes)
        self.assertIn("KR_TOP50_UNIVERSE_SNAPSHOT", codes)
        self.assertIn("KR_TOP50_DAILY_OHLCV", codes)
        self.assertIn("KR_TOP50_CORP_CODE_MAPPING_VALIDATION", codes)
        self.assertIn("KR_DART_DPLUS1_SLA", codes)
        self.assertIn("KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE", codes)
        self.assertIn("KR_REAL_ESTATE_TRANSACTIONS", codes)
        self.assertIn("KR_REAL_ESTATE_MONTHLY_SUMMARY", codes)
        self.assertIn("US_TOP50_ENTITY_REGISTRY", codes)
        self.assertIn("US_TOP50_TIER_STATE", codes)
        self.assertIn("US_TOP50_UNIVERSE_SNAPSHOT", codes)
        self.assertIn("US_TOP50_DAILY_OHLCV", codes)
        self.assertIn("US_TOP50_FINANCIALS", codes)
        self.assertIn("US_SEC_CIK_MAPPING", codes)
        self.assertIn("US_TOP50_EARNINGS_EVENTS_CONFIRMED", codes)
        self.assertIn("US_TOP50_EARNINGS_EVENTS_EXPECTED", codes)
        self.assertIn("US_TOP50_EARNINGS_WATCH_SUCCESS_RATE", codes)
        self.assertIn("ECONOMIC_NEWS_STREAM", codes)
        self.assertIn("TIER1_CORPORATE_EVENT_FEED", codes)
        self.assertIn("EQUITY_GRAPH_PROJECTION_SYNC", codes)
        self.assertIn("GRAPH_NEWS_EXTRACTION_SYNC", codes)
        self.assertIn("GRAPH_RAG_PHASE5_WEEKLY_REPORT", codes)
        self.assertIn("GRAPH_DOCUMENT_EMBEDDING_COVERAGE", codes)
        self.assertIn("GRAPH_RAG_VECTOR_INDEX_READY", codes)

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
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
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
        self.assertIn("실행상태 warning", row["note"])

    def test_snapshot_formats_extended_dataset_notes(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={
                "KR_TOP50_DAILY_OHLCV": {
                    "last_observation_date": datetime(2026, 2, 18).date(),
                    "last_collected_at": datetime(2026, 2, 18, 16, 30, 0),
                    "latest_value": 50,
                    "symbol_count": 50,
                },
                "US_TOP50_DAILY_OHLCV": {
                    "last_observation_date": datetime(2026, 2, 18).date(),
                    "last_collected_at": datetime(2026, 2, 19, 7, 15, 0),
                    "latest_value": 50,
                    "symbol_count": 50,
                },
                "ECONOMIC_NEWS_STREAM": {
                    "last_observation_date": datetime(2026, 2, 19).date(),
                    "last_collected_at": datetime(2026, 2, 19, 23, 0, 0),
                    "latest_value": 127,
                    "source_count": 4,
                    "category_count": 9,
                },
                "TIER1_CORPORATE_EVENT_FEED": {
                    "last_observation_date": datetime(2026, 2, 19).date(),
                    "last_collected_at": datetime(2026, 2, 19, 23, 10, 0),
                    "latest_value": 88,
                    "symbol_count": 31,
                    "country_count": 2,
                },
                "KR_REAL_ESTATE_TRANSACTIONS": {
                    "last_observation_date": datetime(2026, 2, 18).date(),
                    "last_collected_at": datetime(2026, 2, 18, 20, 0, 0),
                    "latest_value": 3160,
                    "region_count": 41,
                },
                "KR_REAL_ESTATE_MONTHLY_SUMMARY": {
                    "last_observation_date": datetime(2026, 2, 19).date(),
                    "last_collected_at": datetime(2026, 2, 19, 2, 0, 0),
                    "latest_value": 520,
                    "region_count": 85,
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        row_map = {item["code"]: item for item in snapshot["indicators"]}
        self.assertIn("커버리지 50종목", row_map["KR_TOP50_DAILY_OHLCV"]["note"])
        self.assertIn("커버리지 50종목", row_map["US_TOP50_DAILY_OHLCV"]["note"])
        self.assertIn("최근 관측일 127건", row_map["ECONOMIC_NEWS_STREAM"]["note"])
        self.assertIn("종목 31개", row_map["TIER1_CORPORATE_EVENT_FEED"]["note"])
        self.assertIn("최근 계약일 3160건", row_map["KR_REAL_ESTATE_TRANSACTIONS"]["note"])
        self.assertIn("최근 통계월 520건", row_map["KR_REAL_ESTATE_MONTHLY_SUMMARY"]["note"])

    def test_snapshot_formats_tier1_event_sync_note(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={
                "TIER1_CORPORATE_EVENT_SYNC": {
                    "last_observation_date": datetime(2026, 2, 18).date(),
                    "last_collected_at": datetime(2026, 2, 18, 14, 48, 0),
                    "latest_value": 100.0,
                    "run_count": 12,
                    "success_run_count": 12,
                    "failed_run_count": 0,
                    "success_count": 606,
                    "failure_count": 0,
                    "last_status": "healthy",
                    "last_error": None,
                    "details_json": '{"health_status":"healthy","retry_failure_count":0,"dlq_recorded_count":0,"normalized_rows":606}',
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "TIER1_CORPORATE_EVENT_SYNC"
        )
        self.assertIn("일간 실행 12회", row["note"])
        self.assertIn("재시도실패/DLQ 0/0", row["note"])
        self.assertIn("표준이벤트 606건", row["note"])
        self.assertIn("헬스상태 healthy", row["note"])

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
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
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

    def test_snapshot_formats_graph_notes(self):
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
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={
                "GRAPH_DOCUMENT_EMBEDDING_COVERAGE": {
                    "last_observation_date": datetime(2026, 2, 18).date(),
                    "last_collected_at": datetime(2026, 2, 18, 10, 0, 0),
                    "latest_value": 97.1,
                    "total_docs": 1000,
                    "embedded_docs": 971,
                    "failed_docs": 4,
                },
                "GRAPH_RAG_VECTOR_INDEX_READY": {
                    "last_observation_date": datetime(2026, 2, 18).date(),
                    "last_collected_at": datetime(2026, 2, 18, 10, 0, 0),
                    "latest_value": 1,
                    "index_state": "ONLINE",
                    "population_percent": 100.0,
                    "index_name": "document_text_embedding_idx",
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        embedding_row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "GRAPH_DOCUMENT_EMBEDDING_COVERAGE"
        )
        vector_row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "GRAPH_RAG_VECTOR_INDEX_READY"
        )
        self.assertIn("임베딩 971/1000건", embedding_row["note"])
        self.assertIn("실패 4건", embedding_row["note"])
        self.assertIn("document_text_embedding_idx", vector_row["note"])
        self.assertIn("ONLINE", vector_row["note"])

    def test_snapshot_formats_graph_news_sync_note(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={
                "GRAPH_NEWS_EXTRACTION_SYNC": {
                    "last_observation_date": datetime(2026, 2, 18).date(),
                    "last_collected_at": datetime(2026, 2, 18, 15, 0, 0),
                    "latest_value": 98.2,
                    "run_count": 12,
                    "success_run_count": 12,
                    "failed_run_count": 0,
                    "success_count": 1200,
                    "failure_count": 22,
                    "last_status": "warning",
                    "last_error": "",
                    "details_json": '{"sync_documents":730,"extraction_success_docs":700,"extraction_failed_docs":3,"embedding_embedded_docs":497,"embedding_failed_docs":19,"embedding_status":"partial_success"}',
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "GRAPH_NEWS_EXTRACTION_SYNC"
        )
        self.assertIn("동기화 문서 730건", row["note"])
        self.assertIn("추출 성공/실패 700/3", row["note"])
        self.assertIn("임베딩 성공/실패 497/19", row["note"])
        self.assertIn("임베딩상태 partial_success", row["note"])
        self.assertEqual(row["run_health_status"], "warning")
        self.assertEqual(row["health"], "stale")

    def test_snapshot_formats_equity_graph_projection_sync_note(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={
                "EQUITY_GRAPH_PROJECTION_SYNC": {
                    "last_observation_date": datetime(2026, 2, 19).date(),
                    "last_collected_at": datetime(2026, 2, 19, 16, 45, 0),
                    "latest_value": 100.0,
                    "run_count": 1,
                    "success_run_count": 1,
                    "failed_run_count": 0,
                    "success_count": 510,
                    "failure_count": 0,
                    "last_status": "warning",
                    "last_error": None,
                    "details_json": '{"lag_hours":48.0,"latest_graph_date":"2026-02-17","max_trade_date":"2026-02-17","max_event_date":"2026-02-19","projection_health_status":"warning"}',
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "EQUITY_GRAPH_PROJECTION_SYNC"
        )
        self.assertIn("lag 48.0h", row["note"])
        self.assertIn("최신 그래프일 2026-02-17", row["note"])
        self.assertIn("max_trade 2026-02-17", row["note"])
        self.assertIn("max_event 2026-02-19", row["note"])
        self.assertIn("projection상태 warning", row["note"])
        self.assertEqual(row["run_health_status"], "warning")
        self.assertEqual(row["health"], "stale")

    def test_snapshot_formats_graph_phase5_weekly_report_note(self):
        with patch(
            "service.macro_trading.indicator_health._build_us_registry",
            return_value=[],
        ), patch(
            "service.macro_trading.indicator_health._load_latest_fred_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_corporate_rows",
            return_value={
                "GRAPH_RAG_PHASE5_WEEKLY_REPORT": {
                    "last_observation_date": datetime(2026, 2, 20).date(),
                    "last_collected_at": datetime(2026, 2, 20, 8, 20, 0),
                    "latest_value": 91.67,
                    "run_count": 1,
                    "success_run_count": 1,
                    "failed_run_count": 0,
                    "success_count": 11,
                    "failure_count": 1,
                    "last_status": "warning",
                    "last_error": None,
                    "details_json": '{"total_runs":4,"warning_runs":1,"failed_runs":0,"avg_pass_rate_pct":91.67,"routing_mismatch_count":1,"avg_structured_citation_count":1.25,"status_reason":"routing_mismatch:1>0","top_failure_categories":[{"category":"freshness_stale","count":2}],"top_failed_cases":[{"case_id":"Q1_US_SINGLE_STOCK_DROP_CAUSE_001","count":2}]}',
                },
            },
        ), patch(
            "service.macro_trading.indicator_health._load_latest_graph_rows",
            return_value={},
        ), patch(
            "service.macro_trading.indicator_health._load_latest_expectation_source_breakdown",
            return_value=None,
        ):
            snapshot = get_macro_indicator_health_snapshot()

        row = next(
            item
            for item in snapshot["indicators"]
            if item["code"] == "GRAPH_RAG_PHASE5_WEEKLY_REPORT"
        )
        self.assertIn("주간 집계 4회", row["note"])
        self.assertIn("경고/실패 1/0", row["note"])
        self.assertIn("평균통과율 91.67%", row["note"])
        self.assertIn("routing_mismatch 1건", row["note"])
        self.assertIn("평균 structured_citation 1.250", row["note"])
        self.assertIn("Top실패 freshness_stale:2", row["note"])
        self.assertIn("Top케이스 Q1_US_SINGLE_STOCK_DROP_CAUSE_001:2", row["note"])
        self.assertIn("상태사유 routing_mismatch:1>0", row["note"])
        self.assertEqual(row["run_health_status"], "warning")
        self.assertEqual(row["health"], "stale")


if __name__ == "__main__":
    unittest.main()
