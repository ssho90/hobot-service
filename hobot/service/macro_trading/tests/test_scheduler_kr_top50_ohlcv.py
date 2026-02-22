import os
import unittest
from datetime import date
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestKRTop50OHLCVScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_run_kr_top50_ohlcv_hotpath_calls_collector(self):
        fake_collector = Mock()
        fake_collector.collect_top50_daily_ohlcv.return_value = {
            "target_stock_count": 1,
            "fetched_rows": 8,
            "upserted_rows": 8,
            "failed_stock_codes": [],
        }
        with patch(
            "service.macro_trading.scheduler.get_kr_corporate_collector",
            return_value=fake_collector,
        ), patch(
            "service.macro_trading.scheduler._resolve_country_sub_mp_symbols",
            return_value=[],
        ), patch(
            "service.macro_trading.scheduler.sync_equity_projection_to_graph",
            return_value={"sync_result": {"status": "success"}},
        ) as graph_sync_mock:
            result = scheduler.run_kr_top50_ohlcv_hotpath(
                stock_codes=["005930"],
                max_stock_count=5,
                lookback_days=7,
                continuity_days=120,
                start_date=date(2026, 2, 10),
                end_date=date(2026, 2, 19),
            )

        self.assertEqual(result["upserted_rows"], 8)
        self.assertTrue(result["graph_sync_enabled"])
        graph_sync_mock.assert_called_once()
        graph_kwargs = graph_sync_mock.call_args.kwargs
        self.assertEqual(graph_kwargs["country_codes"], ("KR",))
        self.assertEqual(graph_kwargs["start_date"], date(2026, 2, 10))
        self.assertEqual(graph_kwargs["end_date"], date(2026, 2, 19))
        kwargs = fake_collector.collect_top50_daily_ohlcv.call_args.kwargs
        self.assertEqual(kwargs["stock_codes"], ["005930"])
        self.assertEqual(kwargs["max_stock_count"], 5)
        self.assertEqual(kwargs["lookback_days"], 7)
        self.assertEqual(kwargs["continuity_days"], 120)
        self.assertEqual(kwargs["start_date"], date(2026, 2, 10))
        self.assertEqual(kwargs["end_date"], date(2026, 2, 19))
        self.assertEqual(kwargs["extra_stock_codes"], None)

    def test_run_kr_top50_ohlcv_hotpath_skips_graph_sync_when_disabled(self):
        fake_collector = Mock()
        fake_collector.collect_top50_daily_ohlcv.return_value = {
            "target_stock_count": 1,
            "fetched_rows": 8,
            "upserted_rows": 8,
            "failed_stock_codes": [],
        }
        with patch(
            "service.macro_trading.scheduler.get_kr_corporate_collector",
            return_value=fake_collector,
        ), patch(
            "service.macro_trading.scheduler._resolve_country_sub_mp_symbols",
            return_value=[],
        ), patch(
            "service.macro_trading.scheduler.sync_equity_projection_to_graph",
        ) as graph_sync_mock:
            result = scheduler.run_kr_top50_ohlcv_hotpath(
                stock_codes=["005930"],
                max_stock_count=5,
                lookback_days=7,
                continuity_days=120,
                start_date=date(2026, 2, 10),
                end_date=date(2026, 2, 19),
                graph_sync_enabled=False,
            )

        self.assertEqual(result["upserted_rows"], 8)
        self.assertFalse(result["graph_sync_enabled"])
        graph_sync_mock.assert_not_called()

    def test_run_kr_top50_ohlcv_hotpath_from_env(self):
        with patch.dict(
            os.environ,
            {
                "KR_TOP50_FIXED_STOCK_CODES": "005930,000660",
                "KR_TOP50_OHLCV_MAX_STOCK_COUNT": "12",
                "KR_TOP50_OHLCV_MARKET": "KOSPI",
                "KR_TOP50_OHLCV_SOURCE_URL": "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
                "KR_TOP50_OHLCV_LOOKBACK_DAYS": "45",
                "KR_TOP50_OHLCV_CONTINUITY_DAYS": "180",
                "KR_TOP50_OHLCV_START_DATE": "2026-01-01",
                "KR_TOP50_OHLCV_END_DATE": "2026-02-19",
                "KR_TOP50_OHLCV_INCLUDE_SUB_MP_UNIVERSE": "0",
                "KR_TOP50_OHLCV_SUB_MP_MAX_STOCK_COUNT": "88",
                "KR_TOP50_OHLCV_GRAPH_SYNC_ENABLED": "0",
                "KR_TOP50_OHLCV_GRAPH_SYNC_INCLUDE_UNIVERSE": "0",
                "KR_TOP50_OHLCV_GRAPH_SYNC_INCLUDE_EARNINGS": "0",
                "KR_TOP50_OHLCV_GRAPH_SYNC_ENSURE_SCHEMA": "0",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.run_kr_top50_ohlcv_hotpath",
            return_value={"status": "ok"},
        ) as run_mock:
            result = scheduler.run_kr_top50_ohlcv_hotpath_from_env()

        self.assertEqual(result["status"], "ok")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["stock_codes"], ["005930", "000660"])
        self.assertEqual(kwargs["max_stock_count"], 12)
        self.assertEqual(kwargs["market"], "KOSPI")
        self.assertEqual(kwargs["lookback_days"], 45)
        self.assertEqual(kwargs["continuity_days"], 180)
        self.assertEqual(kwargs["start_date"], date(2026, 1, 1))
        self.assertEqual(kwargs["end_date"], date(2026, 2, 19))
        self.assertFalse(kwargs["include_sub_mp_universe"])
        self.assertEqual(kwargs["sub_mp_max_stock_count"], 88)
        self.assertFalse(kwargs["graph_sync_enabled"])
        self.assertFalse(kwargs["graph_sync_include_universe"])
        self.assertFalse(kwargs["graph_sync_include_earnings_events"])
        self.assertFalse(kwargs["graph_sync_ensure_schema"])

    def test_run_kr_top50_ohlcv_hotpath_merges_sub_mp_stock_codes(self):
        fake_collector = Mock()
        fake_collector.collect_top50_daily_ohlcv.return_value = {
            "target_stock_count": 3,
            "fetched_rows": 24,
            "upserted_rows": 24,
            "failed_stock_codes": [],
        }
        with patch(
            "service.macro_trading.scheduler.get_kr_corporate_collector",
            return_value=fake_collector,
        ), patch(
            "service.macro_trading.scheduler._resolve_country_sub_mp_symbols",
            return_value=["069500", "360750"],
        ), patch(
            "service.macro_trading.scheduler.sync_equity_projection_to_graph",
            return_value={"sync_result": {"status": "success"}},
        ):
            result = scheduler.run_kr_top50_ohlcv_hotpath(
                stock_codes=["005930"],
                max_stock_count=5,
                include_sub_mp_universe=True,
                sub_mp_max_stock_count=20,
            )

        kwargs = fake_collector.collect_top50_daily_ohlcv.call_args.kwargs
        self.assertEqual(kwargs["stock_codes"], ["005930"])
        self.assertEqual(kwargs["extra_stock_codes"], ["069500", "360750"])
        self.assertTrue(result["sub_mp_universe_enabled"])
        self.assertEqual(result["sub_mp_extra_stock_count"], 2)

    def test_resolve_country_sub_mp_symbols_normalizes_kr_codes(self):
        with patch(
            "service.macro_trading.scheduler._load_active_sub_mp_tickers",
            return_value=["005930", "AAPL", "069500", "CASH", " 360750 "],
        ):
            result = scheduler._resolve_country_sub_mp_symbols(
                country_code="KR",
                max_symbol_count=10,
            )

        self.assertEqual(result, ["005930", "069500", "360750"])

    def test_setup_kr_top50_ohlcv_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "KR_TOP50_OHLCV_ENABLED": "1",
                "KR_TOP50_OHLCV_SCHEDULE_TIME": "",
            },
            clear=False,
        ):
            scheduler.setup_kr_top50_ohlcv_scheduler()

        jobs = [job for job in schedule.get_jobs() if "kr_top50_ohlcv_daily" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "days")
        self.assertEqual(str(jobs[0].at_time), "16:20:00")


if __name__ == "__main__":
    unittest.main()

