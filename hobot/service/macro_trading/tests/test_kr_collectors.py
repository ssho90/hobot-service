import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from service.macro_trading.collectors.kr_macro_collector import KRMacroCollector
from service.macro_trading.collectors.kr_real_estate_collector import KRRealEstateCollector


class _FakeFREDCollector:
    def __init__(self):
        self.calls = []

    def fetch_indicator(self, indicator_code, start_date=None, end_date=None, use_rate_limit=True):
        self.calls.append((indicator_code, start_date, end_date))
        idx = pd.to_datetime(["2026-01-02", "2026-01-03"])
        return pd.Series([1450.1, 1452.2], index=idx)


class TestKRMacroCollector(unittest.TestCase):
    def test_fetch_usdkrw_via_fred_bridge(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)

        series = collector.fetch_indicator(
            "KR_USDKRW",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        self.assertEqual(len(series), 2)
        self.assertEqual(fake_fred.calls[0][0], "DEXKOUS")

    def test_build_observation_rows_sets_phase2_fields(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)
        series = pd.Series(
            [1450.1, 1452.2],
            index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
        )

        rows = collector.build_observation_rows(
            "KR_USDKRW",
            series,
            as_of_date=date(2026, 1, 5),
            revision_flag=True,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["indicator_code"], "KR_USDKRW")
        self.assertEqual(rows[0]["effective_date"], date(2026, 1, 2))
        self.assertEqual(rows[0]["as_of_date"], date(2026, 1, 5))
        self.assertTrue(rows[0]["revision_flag"])
        self.assertEqual(rows[0]["source"], "FRED")

    def test_fetch_kosis_indicator_adds_period_range(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)
        captured = {}

        def _fake_fetch_kosis_series(params, *, frequency, row_filter=None, aggregate=None):
            captured["params"] = dict(params)
            captured["frequency"] = frequency
            captured["row_filter"] = dict(row_filter or {})
            captured["aggregate"] = aggregate
            idx = pd.to_datetime(["2026-01-31"])
            return pd.Series([113.2], index=idx)

        collector.fetch_kosis_series = _fake_fetch_kosis_series  # type: ignore[method-assign]

        series = collector.fetch_indicator(
            "KR_CPI",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        self.assertEqual(len(series), 1)
        self.assertEqual(captured["frequency"], "monthly")
        self.assertEqual(captured["params"]["startPrdDe"], "202601")
        self.assertEqual(captured["params"]["endPrdDe"], "202603")
        self.assertEqual(captured["params"]["tblId"], "DT_1J22003")
        self.assertEqual(captured["row_filter"], {})
        self.assertEqual(captured["aggregate"], "")

    def test_supplemental_kosis_indicator_uses_default_mapping(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)
        captured = {}

        def _fake_fetch_kosis_series(params, *, frequency, row_filter=None, aggregate=None):
            captured["params"] = dict(params)
            captured["frequency"] = frequency
            captured["row_filter"] = dict(row_filter or {})
            captured["aggregate"] = aggregate
            idx = pd.to_datetime(["2026-01-31"])
            return pd.Series([100.0], index=idx)

        collector.fetch_kosis_series = _fake_fetch_kosis_series  # type: ignore[method-assign]

        with patch.dict("os.environ", {}, clear=True):
            series = collector.fetch_indicator(
                "KR_HOUSE_PRICE_INDEX",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )

        self.assertEqual(len(series), 1)
        self.assertEqual(captured["frequency"], "monthly")
        self.assertEqual(captured["params"]["orgId"], "408")
        self.assertEqual(captured["params"]["tblId"], "DT_30404_A012")
        self.assertEqual(captured["params"]["itmId"], "sales")
        self.assertEqual(captured["params"]["objL1"], "00")
        self.assertEqual(captured["params"]["objL2"], "a0")
        self.assertEqual(captured["params"]["startPrdDe"], "202601")
        self.assertEqual(captured["params"]["endPrdDe"], "202603")
        self.assertEqual(captured["row_filter"], {})
        self.assertEqual(captured["aggregate"], "")

    def test_supplemental_kosis_indicator_supports_env_overrides(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)
        captured = {}

        def _fake_fetch_kosis_series(params, *, frequency, row_filter=None, aggregate=None):
            captured["params"] = dict(params)
            captured["frequency"] = frequency
            captured["row_filter"] = dict(row_filter or {})
            captured["aggregate"] = aggregate
            idx = pd.to_datetime(["2026-01-31", "2026-02-28"])
            return pd.Series([100.0, 100.3], index=idx)

        collector.fetch_kosis_series = _fake_fetch_kosis_series  # type: ignore[method-assign]

        with patch.dict(
            "os.environ",
            {
                "KOSIS_KR_HOUSE_PRICE_ORG_ID": "116",
                "KOSIS_KR_HOUSE_PRICE_TBL_ID": "DT_KR_HPI_SAMPLE",
                "KOSIS_KR_HOUSE_PRICE_ITM_ID": "T01",
                "KOSIS_KR_HOUSE_PRICE_INDEX_PARAMS_JSON": '{"objL1":"00"}',
            },
            clear=True,
        ):
            series = collector.fetch_indicator(
                "KR_HOUSE_PRICE_INDEX",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 2, 28),
            )

        self.assertEqual(len(series), 2)
        self.assertEqual(captured["frequency"], "monthly")
        self.assertEqual(captured["params"]["orgId"], "116")
        self.assertEqual(captured["params"]["tblId"], "DT_KR_HPI_SAMPLE")
        self.assertEqual(captured["params"]["itmId"], "T01")
        self.assertEqual(captured["params"]["prdSe"], "M")
        self.assertEqual(captured["params"]["objL1"], "00")
        self.assertEqual(captured["row_filter"], {})
        self.assertEqual(captured["aggregate"], "")

    def test_supplemental_unsold_indicator_passes_filter_and_sum_aggregate(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)
        captured = {}

        def _fake_fetch_kosis_series(params, *, frequency, row_filter=None, aggregate=None):
            captured["params"] = dict(params)
            captured["frequency"] = frequency
            captured["row_filter"] = dict(row_filter or {})
            captured["aggregate"] = aggregate
            idx = pd.to_datetime(["2026-01-31"])
            return pd.Series([321.0], index=idx)

        collector.fetch_kosis_series = _fake_fetch_kosis_series  # type: ignore[method-assign]

        with patch.dict("os.environ", {}, clear=True):
            series = collector.fetch_indicator(
                "KR_UNSOLD_HOUSING",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )

        self.assertEqual(len(series), 1)
        self.assertEqual(captured["frequency"], "monthly")
        self.assertEqual(captured["params"]["orgId"], "116")
        self.assertEqual(captured["params"]["tblId"], "DT_MLTM_2082")
        self.assertEqual(captured["params"]["itmId"], "13103871087T1")
        self.assertEqual(captured["params"]["startPrdDe"], "202601")
        self.assertEqual(captured["row_filter"], {"C2_NM": "계"})
        self.assertEqual(captured["aggregate"], "sum")

    def test_supplemental_unsold_indicator_clamps_very_old_start(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)
        captured = {}

        def _fake_fetch_kosis_series(params, *, frequency, row_filter=None, aggregate=None):
            captured["params"] = dict(params)
            idx = pd.to_datetime(["2026-01-31"])
            return pd.Series([1.0], index=idx)

        collector.fetch_kosis_series = _fake_fetch_kosis_series  # type: ignore[method-assign]

        with patch.dict("os.environ", {}, clear=True):
            collector.fetch_indicator(
                "KR_UNSOLD_HOUSING",
                start_date=date(2016, 2, 1),
                end_date=date(2026, 2, 28),
            )

        self.assertEqual(captured["params"]["startPrdDe"], "202410")

    def test_fetch_kosis_series_row_filter_and_sum_aggregate(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)

        collector._fetch_json = lambda _url, _params=None: [  # type: ignore[method-assign]
            {"PRD_DE": "202601", "DT": "100", "C1_NM": "서울", "C2_NM": "계"},
            {"PRD_DE": "202601", "DT": "200", "C1_NM": "부산", "C2_NM": "계"},
            {"PRD_DE": "202601", "DT": "50", "C1_NM": "서울", "C2_NM": "60~85㎡"},
            {"PRD_DE": "202602", "DT": "120", "C1_NM": "서울", "C2_NM": "계"},
            {"PRD_DE": "202602", "DT": "220", "C1_NM": "부산", "C2_NM": "계"},
        ]

        with patch.dict("os.environ", {"KOSIS_API_KEY": "dummy-key"}, clear=True):
            series = collector.fetch_kosis_series(
                {"orgId": "116", "tblId": "DT_MLTM_2082", "itmId": "13103871087T1", "prdSe": "M"},
                frequency="monthly",
                row_filter={"C2_NM": "계"},
                aggregate="sum",
            )

        self.assertEqual(len(series), 2)
        self.assertEqual(series[date(2026, 1, 31)], 300.0)
        self.assertEqual(series[date(2026, 2, 28)], 340.0)

    def test_fetch_kosis_series_retries_when_latest_month_unpublished(self):
        fake_fred = _FakeFREDCollector()
        collector = KRMacroCollector(fred_collector=fake_fred)
        calls = []

        def _fake_fetch_json(_url, params=None):
            calls.append(dict(params or {}))
            if len(calls) == 1:
                return []
            return [{"PRD_DE": "202601", "DT": "77.7"}]

        collector._fetch_json = _fake_fetch_json  # type: ignore[method-assign]

        with patch.dict("os.environ", {"KOSIS_API_KEY": "dummy-key"}, clear=True):
            series = collector.fetch_kosis_series(
                {
                    "orgId": "408",
                    "tblId": "DT_30404_A012",
                    "itmId": "sales",
                    "prdSe": "M",
                    "startPrdDe": "202501",
                    "endPrdDe": "202602",
                },
                frequency="monthly",
            )

        self.assertEqual(len(series), 1)
        self.assertEqual(series[date(2026, 1, 31)], 77.7)
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[0]["endPrdDe"], "202602")
        self.assertEqual(calls[1]["endPrdDe"], "202601")


class TestKRRealEstateCollector(unittest.TestCase):
    def test_normalize_transaction_record(self):
        collector = KRRealEstateCollector()
        raw = {
            "LAWD_CD": "11680",
            "dealYear": "2026",
            "dealMonth": "01",
            "dealDay": "07",
            "property_type": "아파트",
            "거래유형": "매매",
            "거래금액": "120,000",
            "전용면적": "84.92",
            "층": "12",
            "건축년도": "2014",
        }

        normalized = collector.normalize_transaction_record(raw, source="MOLIT", as_of_date=date(2026, 1, 8))

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["region_code"], "1168000000")
        self.assertEqual(normalized["property_type"], "apartment")
        self.assertEqual(normalized["transaction_type"], "sale")
        self.assertEqual(normalized["contract_date"], date(2026, 1, 7))
        self.assertEqual(normalized["price"], 1_200_000_000)
        self.assertEqual(normalized["floor_no"], 12)
        self.assertEqual(normalized["build_year"], 2014)

    def test_normalize_region_code_variants(self):
        collector = KRRealEstateCollector()

        self.assertEqual(collector.normalize_region_code("11680"), "1168000000")
        self.assertEqual(collector.normalize_region_code("1168010100"), "1168010100")
        self.assertIsNone(collector.normalize_region_code(""))

    def test_molit_defaults_to_apartment_sale(self):
        collector = KRRealEstateCollector()
        raw = {
            "LAWD_CD": "11110",
            "dealYear": "2026",
            "dealMonth": "02",
            "dealDay": "01",
            "dealAmount": "63,400",
            "excluUseAr": "84.0284",
        }

        normalized = collector.normalize_transaction_record(raw, source="MOLIT", as_of_date=date(2026, 2, 15))

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["property_type"], "apartment")
        self.assertEqual(normalized["transaction_type"], "sale")
        self.assertEqual(normalized["price"], 634_000_000)

    def test_resolve_target_lawd_codes_policy_scope(self):
        collector = KRRealEstateCollector()
        codes = collector.resolve_target_lawd_codes(scope="seoul_gyeonggi_all_major_cities")

        self.assertIn("11110", codes)  # 서울 종로구
        self.assertIn("41135", codes)  # 경기 성남 분당구
        self.assertIn("26110", codes)  # 부산 중구
        self.assertEqual(len(codes), len(set(codes)))

    def test_resolve_target_lawd_codes_explicit_override(self):
        collector = KRRealEstateCollector()
        codes = collector.resolve_target_lawd_codes(
            lawd_codes=["11110", "26110", "1111000000", "bad-value"]
        )

        self.assertEqual(codes, ["11110", "26110"])

    def test_iter_deal_months(self):
        collector = KRRealEstateCollector()

        self.assertEqual(
            collector.iter_deal_months("202512", "202602"),
            ["202512", "202601", "202602"],
        )
        with self.assertRaises(ValueError):
            collector.iter_deal_months("202603", "202602")


if __name__ == "__main__":
    unittest.main()
