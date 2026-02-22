import json
import types
import unittest
from datetime import date, datetime
from unittest.mock import Mock, patch

from service.macro_trading.collectors.corporate_event_collector import (
    CorporateEventCollector,
)


class TestCorporateEventCollector(unittest.TestCase):
    def test_build_kr_standard_event(self):
        row = CorporateEventCollector.build_kr_standard_event(
            {
                "rcept_no": "20260218000123",
                "corp_code": "00126380",
                "stock_code": "005930",
                "report_nm": "분기보고서 (2025.12)",
                "rcept_dt": date(2026, 2, 18),
                "event_type": "periodic_report",
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260218000123",
                "as_of_date": date(2026, 2, 18),
                "metadata_json": {"raw": 1},
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["country_code"], "KR")
        self.assertEqual(row["symbol"], "005930")
        self.assertEqual(row["event_type"], "periodic_report")
        self.assertEqual(row["source"], "dart")
        self.assertEqual(row["source_ref"], "20260218000123")
        self.assertIsInstance(row["effective_date"], datetime)
        payload = json.loads(str(row["payload_json"]))
        self.assertEqual(payload["event_category"], "periodic_report")
        self.assertEqual(payload["event_domain"], "ir")
        self.assertEqual(payload["summary_ko"], "분기보고서 (2025.12)")
        self.assertTrue(isinstance(payload["keywords_ko"], list))

    def test_build_kr_standard_event_infers_ir_event_from_report_name(self):
        row = CorporateEventCollector.build_kr_standard_event(
            {
                "rcept_no": "20260218000124",
                "corp_code": "00126380",
                "stock_code": "005930",
                "report_nm": "기업설명회(IR) 개최",
                "rcept_dt": date(2026, 2, 18),
                "event_type": "corporate_disclosure",
                "as_of_date": date(2026, 2, 18),
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["event_type"], "ir_event")
        payload = json.loads(str(row["payload_json"]))
        self.assertEqual(payload["event_category"], "ir_event")

    def test_build_us_standard_event(self):
        row = CorporateEventCollector.build_us_standard_event(
            {
                "symbol": "AAPL",
                "cik": "320193",
                "event_date": date(2026, 2, 17),
                "event_status": "confirmed",
                "event_type": "sec_10q",
                "source": "sec",
                "source_ref": "0000320193-26-000001",
                "filed_at": datetime(2026, 2, 17, 8, 30, 0),
                "report_date": date(2025, 12, 31),
                "as_of_date": date(2026, 2, 17),
                "metadata_json": json.dumps({"source_url": "https://www.sec.gov/ixviewer"}),
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["country_code"], "US")
        self.assertEqual(row["symbol"], "AAPL")
        self.assertEqual(row["event_type"], "sec_10q")
        self.assertEqual(row["source_url"], "https://www.sec.gov/ixviewer")
        self.assertEqual(row["cik"], "0000320193")
        payload = json.loads(str(row["payload_json"]))
        self.assertEqual(payload["event_category"], "periodic_report")
        self.assertEqual(payload["event_domain"], "ir")
        self.assertEqual(payload["title_en"], "AAPL sec_10q")

    def test_fetch_us_yfinance_news_rows_supports_nested_payload(self):
        class FakeTicker:
            def __init__(self, _symbol: str):
                self.news = [
                    {
                        "id": "uuid-001",
                        "content": {
                            "title": "Apple earnings preview",
                            "canonicalUrl": {"url": "/news/apple-earnings-preview-123.html"},
                            "pubDate": "2026-02-17T13:45:00Z",
                            "summary": "Consensus ahead of quarterly release",
                            "provider": {"displayName": "Yahoo Finance"},
                            "finance": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
                        },
                    },
                    {
                        "id": "uuid-001",
                        "content": {
                            "title": "Apple earnings preview",
                            "canonicalUrl": {"url": "/news/apple-earnings-preview-123.html"},
                            "pubDate": "2026-02-17T13:45:00Z",
                        },
                    },
                    {
                        "title": "Apple event recap",
                        "link": "https://finance.yahoo.com/news/apple-event-recap-456.html",
                        "providerPublishTime": 1771352400000,
                        "summary": "Highlights from the event",
                    },
                ]

        fake_yfinance = types.SimpleNamespace(Ticker=lambda symbol: FakeTicker(symbol))
        collector = CorporateEventCollector()
        with patch.dict("sys.modules", {"yfinance": fake_yfinance}):
            rows = collector.fetch_us_yfinance_news_rows(
                symbols=["AAPL"],
                start_date=date(2026, 2, 17),
                end_date=date(2026, 2, 18),
                as_of_date=date(2026, 2, 18),
            )

        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["event_type"], "yfinance_news")
        self.assertEqual(first["source"], "yfinance")
        self.assertEqual(
            first["source_url"],
            "https://finance.yahoo.com/news/apple-earnings-preview-123.html",
        )
        payload = json.loads(str(first["payload_json"]))
        self.assertEqual(payload["event_category"], "news")
        self.assertEqual(payload["event_domain"], "news")
        self.assertEqual(payload["provider"], "Yahoo Finance")
        self.assertIn("AAPL", payload["relatedTickers"])
        self.assertIn("MSFT", payload["relatedTickers"])
        self.assertEqual(payload["title_en"], "Apple earnings preview")
        self.assertEqual(payload["body_en"], "Consensus ahead of quarterly release")
        self.assertIsNone(payload["summary_ko"])

    def test_fetch_kr_ir_news_rows_maps_to_top50_symbol(self):
        collector = CorporateEventCollector()
        collector.load_kr_top_company_rows = lambda **_kwargs: [  # type: ignore[method-assign]
            {
                "symbol": "005930",
                "stock_name": "삼성전자",
                "corp_name": "삼성전자",
                "corp_code": "00126380",
            }
        ]
        collector._fetch_feed_xml = lambda _url: """<?xml version="1.0" encoding="utf-8"?>
            <rss><channel>
                <item>
                    <title>삼성전자, 2026년 1분기 IR 개최 안내</title>
                    <link>https://example.com/ir/samsung-q1</link>
                    <description>기관투자자 대상 실적 설명회</description>
                    <guid>KR-IR-001</guid>
                    <pubDate>Tue, 18 Feb 2026 09:00:00 +0900</pubDate>
                </item>
            </channel></rss>
        """  # type: ignore[method-assign]
        rows = collector.fetch_kr_ir_news_rows(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            market="KOSPI",
            top_limit=50,
            as_of_date=date(2026, 2, 28),
            feed_urls=["https://example.com/ir-feed.xml"],
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["country_code"], "KR")
        self.assertEqual(row["symbol"], "005930")
        self.assertEqual(row["event_type"], "ir_news")
        self.assertEqual(row["source"], "kr_ir_feed")
        self.assertEqual(len(str(row["source_ref"])), 40)
        rows_repeat = collector.fetch_kr_ir_news_rows(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            market="KOSPI",
            top_limit=50,
            as_of_date=date(2026, 2, 28),
            feed_urls=["https://example.com/ir-feed.xml"],
        )
        self.assertEqual(rows_repeat[0]["source_ref"], row["source_ref"])
        payload = json.loads(str(row["payload_json"]))
        self.assertEqual(payload["event_category"], "ir_event")
        self.assertEqual(payload["event_domain"], "ir")
        self.assertEqual(payload["summary_ko"], "기관투자자 대상 실적 설명회")
        self.assertTrue(len(payload["keywords_ko"]) > 0)

    def test_dedupe_similar_news_rows_by_similarity(self):
        collector = CorporateEventCollector()
        rows = [
            {
                "country_code": "US",
                "symbol": "AAPL",
                "event_date": date(2026, 2, 18),
                "event_type": "yfinance_news",
                "source_url": "https://example.com/news/1",
                "title": "Apple quarterly earnings beat expectations",
                "payload_json": json.dumps({"summary": "Revenue rose and EPS beat consensus."}),
            },
            {
                "country_code": "US",
                "symbol": "AAPL",
                "event_date": date(2026, 2, 18),
                "event_type": "yfinance_news",
                "source_url": "https://example.com/news/2",
                "title": "Apple quarterly earnings beat expectation",
                "payload_json": json.dumps({"summary": "Revenue increased and EPS beat consensus."}),
            },
            {
                "country_code": "US",
                "symbol": "AAPL",
                "event_date": date(2026, 2, 18),
                "event_type": "yfinance_news",
                "source_url": "https://example.com/news/3",
                "title": "Apple unveils new product lineup",
                "payload_json": json.dumps({"summary": "Product-focused event summary."}),
            },
        ]
        kept_rows, dropped_count = collector.dedupe_similar_news_rows(rows, similarity_threshold=0.95)
        self.assertEqual(len(kept_rows), 2)
        self.assertEqual(dropped_count, 1)

    def test_run_with_source_retry_records_dlq_on_final_failure(self):
        collector = CorporateEventCollector()
        collector._resolve_source_retry_delays_seconds = lambda: [0, 0]  # type: ignore[method-assign]
        dlq_mock = Mock()
        collector.record_dlq = dlq_mock  # type: ignore[method-assign]

        def _always_fail():
            raise RuntimeError("forced-failure")

        result = collector._run_with_source_retry(
            operation=_always_fail,
            source_key="unit_test_source",
            country_code="KR",
            event_type="ir_news",
            payload={"k": "v"},
        )
        self.assertIsNone(result)
        self.assertEqual(collector._last_run_retry_failure_count, 1)
        self.assertEqual(dlq_mock.call_count, 1)
        self.assertEqual(dlq_mock.call_args.kwargs["source_key"], "unit_test_source")
        self.assertEqual(dlq_mock.call_args.kwargs["retry_count"], 3)

    def test_sync_tier1_events_summary(self):
        collector = CorporateEventCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.load_kr_tier1_rows = lambda **_kwargs: [  # type: ignore[method-assign]
            {
                "country_code": "KR",
                "symbol": "005930",
                "event_date": date(2026, 2, 18),
                "effective_date": datetime(2026, 2, 18, 0, 0, 0),
                "event_type": "periodic_report",
                "event_status": "confirmed",
                "source": "dart",
                "source_ref": "A",
            }
        ]
        collector.load_us_tier1_rows = lambda **_kwargs: [  # type: ignore[method-assign]
            {
                "country_code": "US",
                "symbol": "AAPL",
                "event_date": date(2026, 2, 18),
                "effective_date": datetime(2026, 2, 18, 8, 0, 0),
                "event_type": "sec_10q",
                "event_status": "confirmed",
                "source": "sec",
                "source_ref": "B",
            }
        ]
        collector.load_us_top_symbols = lambda **_kwargs: ["AAPL"]  # type: ignore[method-assign]
        collector.fetch_us_yfinance_news_rows = lambda **_kwargs: [  # type: ignore[method-assign]
            {
                "country_code": "US",
                "symbol": "AAPL",
                "event_date": date(2026, 2, 18),
                "effective_date": datetime(2026, 2, 18, 9, 0, 0),
                "event_type": "yfinance_news",
                "event_status": "published",
                "source": "yfinance",
                "source_ref": "NEWS1",
                "source_url": "https://example.com/news/aapl-earnings",
                "title": "AAPL earnings preview",
                "payload_json": json.dumps({"summary": "Consensus beats expected"}),
            },
            {
                "country_code": "US",
                "symbol": "AAPL",
                "event_date": date(2026, 2, 18),
                "effective_date": datetime(2026, 2, 18, 9, 3, 0),
                "event_type": "yfinance_news",
                "event_status": "published",
                "source": "yfinance",
                "source_ref": "NEWS2",
                "source_url": "https://example.com/news/aapl-earnings",
                "title": "AAPL earnings preview",
                "payload_json": json.dumps({"summary": "Consensus beats expected"}),
            }
        ]
        collector.upsert_standard_events = lambda rows: len(list(rows))  # type: ignore[method-assign]

        summary = collector.sync_tier1_events(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 18),
            lookback_days=30,
            include_us_expected=True,
            include_us_news=True,
            include_kr_ir_news=False,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["kr_event_count"], 1)
        self.assertEqual(summary["us_event_count"], 1)
        self.assertEqual(summary["us_news_event_count"], 1)
        self.assertEqual(summary["us_news_deduped_count"], 1)
        self.assertEqual(summary["normalized_rows"], 3)
        self.assertEqual(summary["db_affected"], 3)
        self.assertEqual(summary["event_category_counts"]["periodic_report"], 2)
        self.assertEqual(summary["event_category_counts"]["news"], 1)
        self.assertEqual(summary["kr_ir_news_event_count"], 0)
        self.assertEqual(summary["kr_ir_news_deduped_count"], 0)
        self.assertEqual(summary["retry_failure_count"], 0)
        self.assertEqual(summary["dlq_recorded_count"], 0)


if __name__ == "__main__":
    unittest.main()
