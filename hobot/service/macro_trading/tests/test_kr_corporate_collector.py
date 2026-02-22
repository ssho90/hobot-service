import io
import unittest
import zipfile
from datetime import date, datetime
from unittest.mock import patch

from service.macro_trading.collectors.kr_corporate_collector import (
    DEFAULT_EXPECTATION_FEED_URL,
    KRCorporateCollector,
)


class TestKRCorporateCollector(unittest.TestCase):
    def test_parse_corp_code_zip(self):
        xml_payload = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list>
    <corp_code>00126380</corp_code>
    <corp_name>삼성전자</corp_name>
    <stock_code>005930</stock_code>
    <modify_date>20260115</modify_date>
  </list>
  <list>
    <corp_code>00164779</corp_code>
    <corp_name>SK하이닉스</corp_name>
    <stock_code>000660</stock_code>
    <modify_date>20251230</modify_date>
  </list>
</result>
"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("CORPCODE.xml", xml_payload.encode("utf-8"))

        rows = KRCorporateCollector.parse_corp_code_zip(buffer.getvalue())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["corp_code"], "00126380")
        self.assertEqual(rows[0]["stock_code"], "005930")
        self.assertEqual(rows[0]["modify_date"], date(2026, 1, 15))

    def test_normalize_financial_row(self):
        collector = KRCorporateCollector()
        raw = {
            "corp_code": "00126380",
            "stock_code": "005930",
            "corp_name": "삼성전자",
            "bsns_year": "2025",
            "reprt_code": "11011",
            "account_nm": "매출액",
            "fs_div": "CFS",
            "sj_div": "IS",
            "thstrm_amount": "123,456,789",
            "frmtrm_amount": "100,000,000",
            "currency": "KRW",
            "rcept_no": "20260301000001",
        }
        normalized = collector.normalize_financial_row(raw, as_of_date=date(2026, 2, 15))

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["corp_code"], "00126380")
        self.assertEqual(normalized["stock_code"], "005930")
        self.assertEqual(normalized["account_nm"], "매출액")
        self.assertEqual(normalized["thstrm_amount"], 123_456_789)
        self.assertEqual(normalized["frmtrm_amount"], 100_000_000)
        self.assertEqual(normalized["as_of_date"], date(2026, 2, 15))

    def test_collect_major_accounts_batches(self):
        collector = KRCorporateCollector()
        calls = {"fetch": 0}

        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.refresh_corp_code_cache = lambda **_kwargs: {}  # type: ignore[method-assign]
        collector.resolve_target_corp_codes = lambda **_kwargs: [  # type: ignore[method-assign]
            "00126380",
            "00164779",
            "00123456",
        ]

        def _fake_fetch(*, corp_codes, bsns_year, reprt_code):
            calls["fetch"] += 1
            return [
                {
                    "corp_code": corp_codes[0],
                    "stock_code": "005930",
                    "corp_name": "테스트",
                    "bsns_year": bsns_year,
                    "reprt_code": reprt_code,
                    "account_nm": "매출액",
                }
            ]

        collector.fetch_multi_account_rows = _fake_fetch  # type: ignore[method-assign]
        def _fake_ingest(rows, as_of_date=None):
            row_list = list(rows)
            return {
                "normalized_rows": len(row_list),
                "skipped_rows": 0,
                "db_affected": len(row_list),
            }

        collector.ingest_financial_rows = _fake_ingest  # type: ignore[method-assign]

        summary = collector.collect_major_accounts(
            bsns_year="2025",
            reprt_code="11011",
            max_corp_count=3,
            batch_size=2,
        )

        self.assertEqual(summary["target_corp_count"], 3)
        self.assertEqual(summary["batch_size"], 2)
        self.assertEqual(summary["api_requests"], 2)
        self.assertEqual(summary["failed_batches"], 0)
        self.assertEqual(calls["fetch"], 2)

    def test_infer_reporting_period_from_report_name(self):
        collector = KRCorporateCollector()
        period = collector.infer_reporting_period(
            "분기보고서 (2025.09)",
            rcept_dt=date(2025, 11, 14),
        )
        self.assertEqual(period["period_year"], 2025)
        self.assertEqual(period["fiscal_quarter"], 3)

    def test_build_surprise_payload_labels(self):
        collector = KRCorporateCollector()
        surprise = collector.build_surprise_payload(
            {
                "revenue": 120,
                "operating_income": 100,
                "net_income": 88,
            },
            {
                "revenue": 100,
                "operating_income": 102,
                "net_income": 88,
            },
        )
        self.assertEqual(surprise["revenue"]["label"], "beat")
        self.assertEqual(surprise["operating_income"]["label"], "meet")
        self.assertEqual(surprise["net_income"]["label"], "meet")
        self.assertEqual(collector.summarize_surprise_label(surprise), "beat")

    def test_normalize_disclosure_row_attaches_actual_expected(self):
        collector = KRCorporateCollector()
        collector.fetch_actual_metrics = lambda **_kwargs: {  # type: ignore[method-assign]
            "revenue": 1000,
            "operating_income": 250,
            "net_income": 200,
        }
        collector.fetch_expected_metrics = lambda **_kwargs: {  # type: ignore[method-assign]
            "revenue": 900,
            "operating_income": 240,
            "net_income": 180,
        }
        normalized = collector.normalize_disclosure_row(
            {
                "rcept_no": "20260216000123",
                "corp_code": "00126380",
                "stock_code": "005930",
                "corp_name": "삼성전자",
                "report_nm": "영업(잠정)실적(공정공시) (2025년 4분기)",
                "rcept_dt": "20260216",
            },
            as_of_date=date(2026, 2, 16),
        )
        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["is_earnings_event"], 1)
        self.assertEqual(normalized["period_year"], "2025")
        self.assertEqual(normalized["fiscal_quarter"], 4)
        self.assertEqual(normalized["surprise_label"], "beat")
        self.assertIn("revenue", str(normalized["metric_actual_json"]))
        self.assertIn("revenue", str(normalized["metric_expected_json"]))
        self.assertIn("revenue", str(normalized["metric_surprise_json"]))

    def test_collect_disclosure_events_accepts_expectations(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.resolve_target_corp_codes = lambda **_kwargs: ["00126380"]  # type: ignore[method-assign]
        collector.fetch_disclosure_rows = lambda **_kwargs: []  # type: ignore[method-assign]
        collector.upsert_earnings_expectations = lambda rows: len(list(rows))  # type: ignore[method-assign]

        summary = collector.collect_disclosure_events(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            expectation_rows=[
                {
                    "corp_code": "00126380",
                    "period_year": "2025",
                    "fiscal_quarter": 4,
                    "metric_key": "revenue",
                    "expected_value": 123_000_000_000,
                }
            ],
            max_corp_count=1,
            per_corp_max_pages=1,
            auto_expectations=False,
        )
        self.assertEqual(summary["expectation_upserted"], 1)

    def test_ingest_disclosure_rows_exposes_new_earnings_event_summary(self):
        collector = KRCorporateCollector()
        collector.normalize_disclosure_row = (  # type: ignore[method-assign]
            lambda row, as_of_date=None: row
        )
        collector.save_disclosure_rows_with_stats = (  # type: ignore[method-assign]
            lambda rows: {
                "db_affected": len(list(rows)),
                "inserted_count": 1,
                "updated_count": 1,
                "inserted_rcept_nos": ["20260216000123"],
            }
        )

        result = collector.ingest_disclosure_rows(
            [
                {
                    "rcept_no": "20260216000123",
                    "corp_code": "00126380",
                    "stock_code": "005930",
                    "is_earnings_event": 1,
                    "period_year": "2025",
                    "fiscal_quarter": 4,
                    "rcept_dt": date(2026, 2, 16),
                },
                {
                    "rcept_no": "20260216000124",
                    "corp_code": "00164779",
                    "stock_code": "000660",
                    "is_earnings_event": 1,
                    "period_year": "2025",
                    "fiscal_quarter": 4,
                    "rcept_dt": date(2026, 2, 16),
                },
            ],
            only_earnings=True,
        )

        self.assertEqual(result["db_affected"], 2)
        self.assertEqual(result["inserted_rows"], 1)
        self.assertEqual(result["updated_rows"], 1)
        self.assertEqual(result["earnings_event_count"], 2)
        self.assertEqual(result["new_earnings_event_count"], 1)
        self.assertEqual(result["new_earnings_events"][0]["corp_code"], "00126380")

    def test_normalize_expectation_row_accepts_metric_alias(self):
        collector = KRCorporateCollector()
        row = collector.normalize_expectation_row(
            {
                "corp_code": "00126380",
                "year": "2025",
                "quarter": 4,
                "metric": "매출액",
                "consensus": "123,456,789",
            },
            default_source="feed",
            default_as_of_date=date(2026, 2, 16),
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["metric_key"], "revenue")
        self.assertEqual(row["expected_value"], 123_456_789)
        self.assertEqual(row["expected_source"], "feed")

    def test_parse_naver_market_cap_stock_codes(self):
        html = """
        <a href="/item/main.naver?code=005930">삼성전자</a>
        <a href="/item/main.naver?code=000660">SK하이닉스</a>
        <a href="/item/main.naver?code=005930">삼성전자</a>
        """
        codes = KRCorporateCollector.parse_naver_market_cap_stock_codes(html, limit=50)
        self.assertEqual(codes, ["005930", "000660"])

    def test_parse_naver_market_cap_stock_rows(self):
        html = """
        <table class="type_2">
          <tbody>
            <tr><td><a href="/item/main.naver?code=005930" class="tltle">삼성전자</a></td></tr>
            <tr><td><a href="/item/main.naver?code=000660" class="tltle">SK하이닉스</a></td></tr>
          </tbody>
        </table>
        """
        rows = KRCorporateCollector.parse_naver_market_cap_stock_rows(html, limit=50)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["rank_position"], 1)
        self.assertEqual(rows[0]["stock_code"], "005930")
        self.assertEqual(rows[0]["stock_name"], "삼성전자")

    def test_build_naver_page_url_updates_page_query(self):
        page_url = KRCorporateCollector._build_naver_page_url(
            "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
            2,
        )
        self.assertIn("sosok=0", page_url)
        self.assertIn("page=2", page_url)

    def test_fetch_top_stock_rows_from_naver_paginates_until_limit(self):
        collector = KRCorporateCollector()

        def _make_html(start: int, end: int) -> str:
            links = "".join(
                f'<tr><td><a href="/item/main.naver?code={idx:06d}" class="tltle">종목{idx:06d}</a></td></tr>'
                for idx in range(start, end + 1)
            )
            return f'<table class="type_2"><tbody>{links}</tbody></table>'

        html_page_1 = _make_html(1, 50).encode("utf-8")
        html_page_2 = _make_html(51, 100).encode("utf-8")

        class _FakeResponse:
            def __init__(self, payload: bytes):
                self._payload = payload

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def _fake_urlopen(request, timeout=25):  # noqa: ARG001
            request_url = getattr(request, "full_url", str(request))
            if "page=2" in request_url:
                return _FakeResponse(html_page_2)
            return _FakeResponse(html_page_1)

        with patch(
            "service.macro_trading.collectors.kr_corporate_collector.urlopen",
            side_effect=_fake_urlopen,
        ):
            rows = collector.fetch_top_stock_rows_from_naver(
                limit=100,
                url="https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
            )

        self.assertEqual(len(rows), 100)
        self.assertEqual(rows[0]["rank_position"], 1)
        self.assertEqual(rows[0]["stock_code"], "000001")
        self.assertEqual(rows[-1]["rank_position"], 100)
        self.assertEqual(rows[-1]["stock_code"], "000100")

    def test_parse_naver_quarterly_consensus_rows(self):
        html = """
        <table class="tb_type1 tb_num tb_type1_ifrs">
          <thead>
            <tr><th colspan="10">header</th></tr>
            <tr>
              <th>2024.12</th><th>2025.12(E)</th>
              <th>2024.09</th><th>2024.12</th><th>2025.03</th><th>2025.06</th><th>2025.09</th><th>2025.12(E)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th><strong>매출액</strong></th>
              <td>1</td><td>2</td><td>10</td><td>20</td><td>30</td><td>40</td><td>50</td><td>60</td>
            </tr>
            <tr>
              <th><strong>영업이익</strong></th>
              <td>1</td><td>2</td><td>11</td><td>21</td><td>31</td><td>41</td><td>51</td><td>61</td>
            </tr>
            <tr>
              <th><strong>당기순이익</strong></th>
              <td>1</td><td>2</td><td>12</td><td>22</td><td>32</td><td>42</td><td>52</td><td>62</td>
            </tr>
          </tbody>
        </table>
        """
        rows = KRCorporateCollector.parse_naver_quarterly_consensus_rows(
            html,
            stock_code="005930",
            corp_code="00126380",
            expected_as_of_date=date(2026, 2, 16),
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["expected_source"], "consensus_feed")
        self.assertEqual(rows[0]["period_year"], "2025")
        self.assertEqual(rows[0]["fiscal_quarter"], 4)
        self.assertEqual(rows[0]["expected_value"], 60 * 100_000_000)

    def test_collect_disclosure_events_auto_expectations_summary(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.resolve_target_corp_codes = lambda **_kwargs: ["00126380"]  # type: ignore[method-assign]
        collector.fetch_disclosure_rows = lambda **_kwargs: []  # type: ignore[method-assign]
        collector.fetch_expectation_rows_from_feed = lambda **_kwargs: [  # type: ignore[method-assign]
            {
                "corp_code": "00126380",
                "period_year": "2025",
                "fiscal_quarter": 4,
                "metric_key": "revenue",
                "expected_value": 1000,
                "expected_source": "feed",
                "expected_as_of_date": date(2026, 2, 16),
                "metadata": {},
            }
        ]
        collector.build_baseline_expectation_rows = lambda **_kwargs: [  # type: ignore[method-assign]
            {
                "corp_code": "00126380",
                "period_year": "2025",
                "fiscal_quarter": 4,
                "metric_key": "operating_income",
                "expected_value": 100,
                "expected_source": "auto_baseline",
                "expected_as_of_date": date(2026, 2, 16),
                "metadata": {},
            }
        ]
        collector.upsert_earnings_expectations = lambda rows: len(list(rows))  # type: ignore[method-assign]

        summary = collector.collect_disclosure_events(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 16),
            max_corp_count=1,
            per_corp_max_pages=1,
            auto_expectations=True,
            expectation_feed_url="https://example.com/expectations.json",
        )
        self.assertEqual(summary["expectation_feed_rows"], 1)
        self.assertEqual(summary["expectation_baseline_rows"], 0)
        self.assertEqual(summary["expectation_upserted"], 1)

    def test_collect_disclosure_events_requires_feed_by_default(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.resolve_target_corp_codes = lambda **_kwargs: ["00126380"]  # type: ignore[method-assign]
        collector.fetch_expectation_rows_from_feed = lambda **_kwargs: []  # type: ignore[method-assign]

        with self.assertRaises(ValueError):
            collector.collect_disclosure_events(
                start_date=date(2026, 2, 1),
                end_date=date(2026, 2, 16),
                max_corp_count=1,
                per_corp_max_pages=1,
                auto_expectations=True,
                expectation_feed_url=None,
            )

    def test_collect_disclosure_events_uses_internal_feed_default_url(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.resolve_target_corp_codes = lambda **_kwargs: ["00126380"]  # type: ignore[method-assign]
        collector.fetch_disclosure_rows = lambda **_kwargs: []  # type: ignore[method-assign]
        collector.upsert_earnings_expectations = lambda rows: len(list(rows))  # type: ignore[method-assign]
        captured = {"url": None}

        def _fake_fetch(**kwargs):
            captured["url"] = kwargs.get("url")
            return [
                {
                    "corp_code": "00126380",
                    "period_year": "2025",
                    "fiscal_quarter": 4,
                    "metric_key": "revenue",
                    "expected_value": 1000,
                    "expected_source": "feed",
                    "expected_as_of_date": date(2026, 2, 16),
                    "metadata": {},
                }
            ]

        collector.fetch_expectation_rows_from_feed = _fake_fetch  # type: ignore[method-assign]
        summary = collector.collect_disclosure_events(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 16),
            max_corp_count=1,
            per_corp_max_pages=1,
            auto_expectations=True,
            expectation_feed_url=None,
        )

        self.assertEqual(captured["url"], DEFAULT_EXPECTATION_FEED_URL)
        self.assertEqual(summary["expectation_feed_rows"], 1)

    def test_build_top50_snapshot_diff_detects_added_removed_and_rank_changes(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.load_recent_top50_snapshot_dates = lambda **_kwargs: [  # type: ignore[method-assign]
            date(2026, 2, 17),
            date(2026, 1, 17),
        ]

        def _fake_load_rows(*, snapshot_date, market, limit):
            if snapshot_date == date(2026, 2, 17):
                return [
                    {"stock_code": "005930", "stock_name": "삼성전자", "rank_position": 1},
                    {"stock_code": "000660", "stock_name": "SK하이닉스", "rank_position": 3},
                    {"stock_code": "035420", "stock_name": "NAVER", "rank_position": 2},
                ]
            return [
                {"stock_code": "005930", "stock_name": "삼성전자", "rank_position": 2},
                {"stock_code": "000660", "stock_name": "SK하이닉스", "rank_position": 1},
                {"stock_code": "005380", "stock_name": "현대차", "rank_position": 3},
            ]

        collector.load_top50_snapshot_rows_by_date = _fake_load_rows  # type: ignore[method-assign]

        diff = collector.build_top50_snapshot_diff(market="KOSPI", limit=50)
        self.assertEqual(diff["latest_snapshot_date"], "2026-02-17")
        self.assertEqual(diff["previous_snapshot_date"], "2026-01-17")
        self.assertEqual(diff["added_count"], 1)
        self.assertEqual(diff["removed_count"], 1)
        self.assertEqual(diff["rank_changed_count"], 2)
        self.assertEqual(diff["added_stocks"][0]["stock_code"], "035420")
        self.assertEqual(diff["removed_stocks"][0]["stock_code"], "005380")

    def test_build_top50_snapshot_diff_handles_single_snapshot(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.load_recent_top50_snapshot_dates = lambda **_kwargs: [date(2026, 2, 17)]  # type: ignore[method-assign]
        collector.load_top50_snapshot_rows_by_date = lambda **_kwargs: [  # type: ignore[method-assign]
            {"stock_code": "005930", "stock_name": "삼성전자", "rank_position": 1},
        ]

        diff = collector.build_top50_snapshot_diff(market="KOSPI", limit=50)
        self.assertEqual(diff["latest_snapshot_date"], "2026-02-17")
        self.assertIsNone(diff["previous_snapshot_date"])
        self.assertFalse(diff["has_previous_snapshot"])
        self.assertEqual(diff["added_count"], 1)
        self.assertEqual(diff["removed_count"], 0)

    def test_validate_top50_corp_code_mapping_detects_mapping_issues(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.load_latest_top50_snapshot_rows = lambda **_kwargs: [  # type: ignore[method-assign]
            {"snapshot_date": date(2026, 2, 17), "stock_code": "005930", "corp_code": "00126380"},
            {"snapshot_date": date(2026, 2, 17), "stock_code": "000660", "corp_code": None},
            {"snapshot_date": date(2026, 2, 17), "stock_code": "035420", "corp_code": "00987654"},
        ]

        fetch_batches = [
            [
                {"stock_code": "005930", "corp_code": "00126380"},
                {"stock_code": "035420", "corp_code": "00111111"},
                {"stock_code": "035420", "corp_code": "00222222"},
            ],
            [
                {"stock_code": "035420", "corp_count": 2},
            ],
        ]

        class _Cursor:
            def __init__(self, batches):
                self._batches = list(batches)

            def execute(self, _query, _params=None):
                return None

            def fetchall(self):
                if self._batches:
                    return self._batches.pop(0)
                return []

        class _Connection:
            def __init__(self, cursor):
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return self._cursor

        cursor = _Cursor(fetch_batches)
        collector._get_db_connection = lambda: _Connection(cursor)  # type: ignore[method-assign]

        result = collector.validate_top50_corp_code_mapping(
            report_date=date(2026, 2, 17),
            market="KOSPI",
            top_limit=50,
            persist=False,
        )

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["snapshot_row_count"], 3)
        self.assertEqual(result["snapshot_missing_corp_count"], 1)
        self.assertEqual(result["snapshot_missing_in_dart_count"], 1)
        self.assertEqual(result["snapshot_corp_code_mismatch_count"], 1)
        self.assertEqual(result["dart_duplicate_stock_count"], 1)
        details = result["details"]
        self.assertIn("000660", details["snapshot_missing_corp_stocks"])
        self.assertIn("000660", details["snapshot_missing_in_dart_stocks"])
        self.assertEqual(details["snapshot_corp_code_mismatches"][0]["stock_code"], "035420")
        self.assertIn("035420", details["dart_duplicate_stock_codes"])

    def test_validate_dart_disclosure_dplus1_sla_hydrates_and_includes_periodic_report(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.load_latest_top50_snapshot_rows = lambda **_kwargs: [  # type: ignore[method-assign]
            {"snapshot_date": date(2026, 2, 17), "stock_code": "005930", "corp_code": "00126380"},
        ]
        hydrate_calls = {}

        def _fake_collect_disclosure_events(**kwargs):
            hydrate_calls.update(kwargs)
            return {"status": "ok", "normalized_rows": 1, "db_affected": 1}

        collector.collect_disclosure_events = _fake_collect_disclosure_events  # type: ignore[method-assign]

        fetch_batches = [
            [],
            [
                {
                    "corp_code": "00126380",
                    "rcept_no": "20260216000123",
                    "rcept_dt": date(2026, 2, 16),
                    "period_year": "2025",
                    "fiscal_quarter": 4,
                    "report_nm": "분기보고서 (2025.09)",
                    "event_type": "",
                    "is_earnings_event": 0,
                }
            ],
            [
                {
                    "corp_code": "00126380",
                    "bsns_year": "2025",
                    "reprt_code": "11011",
                    "first_financial_at": datetime(2026, 2, 17, 10, 0, 0),
                }
            ],
        ]

        class _Cursor:
            def __init__(self, batches):
                self._batches = list(batches)

            def execute(self, _query, _params=None):
                return None

            def fetchall(self):
                if self._batches:
                    return self._batches.pop(0)
                return []

        class _Connection:
            def __init__(self, cursor):
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return self._cursor

        cursor = _Cursor(fetch_batches)
        collector._get_db_connection = lambda: _Connection(cursor)  # type: ignore[method-assign]

        result = collector.validate_dart_disclosure_dplus1_sla(
            report_date=date(2026, 2, 17),
            market="KOSPI",
            top_limit=50,
            lookback_days=30,
            hydrate_disclosures_if_empty=True,
            hydrate_per_corp_max_pages=2,
            hydrate_page_count=10,
            persist=False,
        )

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["checked_event_count"], 1)
        self.assertEqual(result["met_sla_count"], 1)
        self.assertEqual(result["violated_sla_count"], 0)
        self.assertTrue(result["details"]["hydrate_attempted"])
        self.assertEqual(result["details"]["hydrate_summary"]["status"], "ok")
        self.assertEqual(hydrate_calls["only_earnings"], False)
        self.assertEqual(hydrate_calls["per_corp_max_pages"], 2)
        self.assertEqual(hydrate_calls["page_count"], 10)

    def test_collect_top50_daily_ohlcv_aggregates_summary(self):
        collector = KRCorporateCollector()
        collector.ensure_tables = lambda: None  # type: ignore[method-assign]
        collector.resolve_top50_stock_codes_for_ohlcv = (  # type: ignore[method-assign]
            lambda **_kwargs: ["005930"]
        )
        collector.fetch_daily_ohlcv_rows_from_yfinance = (  # type: ignore[method-assign]
            lambda **_kwargs: {
                "rows": [
                    {
                        "market": "KOSPI",
                        "stock_code": "005930",
                        "trade_date": date(2026, 2, 18),
                        "open_price": 70000.0,
                        "high_price": 71000.0,
                        "low_price": 69500.0,
                        "close_price": 70500.0,
                        "adjusted_close": 70500.0,
                        "volume": 1000,
                        "source": "yfinance",
                        "source_ref": "005930:2026-02-18",
                        "as_of_date": date(2026, 2, 19),
                        "metadata_json": "{}",
                    }
                ],
                "rows_by_stock_code": {"005930": 1},
                "failed_stock_codes": [],
            }
        )
        collector.upsert_top50_daily_ohlcv_rows = lambda rows: len(list(rows))  # type: ignore[method-assign]

        result = collector.collect_top50_daily_ohlcv(
            stock_codes=["005930"],
            max_stock_count=1,
            lookback_days=10,
            as_of_date=date(2026, 2, 19),
        )

        self.assertEqual(result["target_stock_count"], 1)
        self.assertEqual(result["fetched_rows"], 1)
        self.assertEqual(result["upserted_rows"], 1)
        self.assertEqual(result["continuity_days"], 120)
        self.assertFalse(result["continuity_enabled"])
        self.assertEqual(result["continuity_extra_stock_count"], 0)
        self.assertEqual(result["rows_by_stock_code"]["005930"], 1)

    def test_resolve_top50_stock_codes_for_ohlcv_merges_recent_snapshot_universe(self):
        collector = KRCorporateCollector()
        with patch.object(
            collector,
            "load_latest_top50_snapshot_rows",
            return_value=[
                {"stock_code": "005930"},
                {"stock_code": "000660"},
            ],
        ), patch.object(
            collector,
            "load_top50_stock_codes_in_snapshot_window",
            return_value=["000660", "035420"],
        ), patch.object(
            collector,
            "fetch_top_stock_codes_from_naver",
            return_value=["005930", "000660"],
        ):
            result = collector.resolve_top50_stock_codes_for_ohlcv(
                max_stock_count=2,
                market="KOSPI",
                continuity_days=120,
                reference_end_date=date(2026, 2, 19),
            )

        self.assertEqual(result, ["005930", "000660", "035420"])

    def test_resolve_top50_stock_codes_for_ohlcv_appends_extra_stock_codes(self):
        collector = KRCorporateCollector()
        with patch.object(
            collector,
            "load_latest_top50_snapshot_rows",
            return_value=[
                {"stock_code": "005930"},
                {"stock_code": "000660"},
            ],
        ):
            result = collector.resolve_top50_stock_codes_for_ohlcv(
                max_stock_count=2,
                market="KOSPI",
                continuity_days=0,
                extra_stock_codes=["069500", "005930"],
            )

        self.assertEqual(result, ["005930", "000660", "069500"])


if __name__ == "__main__":
    unittest.main()
