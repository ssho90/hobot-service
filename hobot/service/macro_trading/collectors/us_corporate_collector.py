"""
US corporate earnings collector.

Phase 2.5:
- expected earnings dates (yfinance calendar)
- confirmed earnings-related filings (SEC submissions)
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_no_dash}/{primary_document}"

DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS = 30
DEFAULT_US_EARNINGS_LOOKBACK_DAYS = 30
DEFAULT_US_EARNINGS_LOOKAHEAD_DAYS = 120
DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT = 50
DEFAULT_US_FINANCIALS_MAX_SYMBOL_COUNT = 50
DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT = 12
US_TOP50_DEFAULT_MARKET = "US"
US_TOP50_DEFAULT_SOURCE_URL = "internal://us-top50-fixed"

# Fixed US Top50-ish large caps for phase 2.5 baseline operation.
DEFAULT_US_TOP50_FIXED_SYMBOLS: Sequence[str] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "BRK-B", "TSLA", "AVGO",
    "JPM", "WMT", "LLY", "V", "XOM", "MA", "COST", "NFLX", "PG", "JNJ",
    "HD", "ABBV", "BAC", "KO", "ORCL", "CRM", "CVX", "AMD", "MRK", "PEP",
    "TMO", "ADBE", "MCD", "CSCO", "WFC", "ACN", "ABT", "IBM", "LIN", "INTU",
    "QCOM", "DHR", "AMAT", "GE", "DIS", "CAT", "TXN", "VZ", "NOW", "PFE",
)

SEC_EARNINGS_FORMS = {"8-K", "10-Q", "10-K"}
US_FINANCIAL_STATEMENT_SPECS: Sequence[tuple[str, str, str]] = (
    ("income_statement", "annual", "financials"),
    ("income_statement", "quarterly", "quarterly_financials"),
    ("balance_sheet", "annual", "balance_sheet"),
    ("balance_sheet", "quarterly", "quarterly_balance_sheet"),
    ("cashflow", "annual", "cashflow"),
    ("cashflow", "quarterly", "quarterly_cashflow"),
)


def _normalize_symbol(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if not text:
        return None
    sanitized = "".join(ch for ch in text if ch.isalnum() or ch in {".", "-"})
    if not sanitized:
        return None
    return sanitized


def _normalize_cik(value: Any) -> Optional[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _safe_market_cap(value: Any) -> Optional[int]:
    parsed = _safe_int(value)
    if parsed is None:
        return None
    return parsed if parsed > 0 else None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        return parsed
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        parsed = float(text)
        if not math.isfinite(parsed):
            return None
        return parsed
    except ValueError:
        return None


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_account_key(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not normalized:
        return None
    return normalized[:120]


def _extract_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = _parse_date(value)
    if parsed:
        return parsed
    if hasattr(value, "to_pydatetime"):
        try:
            dt_value = value.to_pydatetime()
            if isinstance(dt_value, datetime):
                return dt_value.date()
            if isinstance(dt_value, date):
                return dt_value
        except Exception:
            return None
    return None


def _parse_sec_acceptance_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _chunked(values: Sequence[str], chunk_size: int) -> Iterable[List[str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    for idx in range(0, len(values), chunk_size):
        yield list(values[idx : idx + chunk_size])


class USCorporateCollector:
    def __init__(self, db_connection_factory=None):
        self._db_connection_factory = db_connection_factory or get_db_connection

    def _get_db_connection(self):
        return self._db_connection_factory()

    def _sec_headers(self) -> Dict[str, str]:
        # SEC requires a clear user-agent string with contact.
        user_agent = (
            os.getenv("SEC_API_USER_AGENT", "").strip()
            or "hobot-service/1.0 (research@hobot.local)"
        )
        return {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    def _fetch_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Any:
        req = Request(url, headers=headers or {"User-Agent": "hobot-us-corporate-collector/1.0"})
        with urlopen(req, timeout=40) as response:  # nosec B310
            payload = response.read().decode("utf-8")
        return json.loads(payload)

    def ensure_tables(self):
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS us_sec_cik_mapping (
                    symbol VARCHAR(16) PRIMARY KEY,
                    cik CHAR(10) NOT NULL,
                    company_name VARCHAR(255) NULL,
                    metadata_json JSON NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_cik (cik),
                    INDEX idx_company_name (company_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS us_corporate_earnings_events (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    symbol VARCHAR(16) NOT NULL,
                    cik CHAR(10) NULL,
                    event_date DATE NOT NULL,
                    event_status VARCHAR(16) NOT NULL,
                    event_type VARCHAR(64) NOT NULL,
                    source VARCHAR(32) NOT NULL,
                    source_ref VARCHAR(96) NOT NULL DEFAULT '',
                    filed_at DATETIME NULL,
                    report_date DATE NULL,
                    as_of_date DATE NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_us_earnings_event (
                        symbol, event_date, event_status, source, event_type, source_ref
                    ),
                    INDEX idx_us_earnings_status_date (event_status, event_date),
                    INDEX idx_us_earnings_symbol_date (symbol, event_date),
                    INDEX idx_us_earnings_source (source)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS us_corporate_financials (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    symbol VARCHAR(16) NOT NULL,
                    cik CHAR(10) NULL,
                    company_name VARCHAR(255) NULL,
                    statement_type VARCHAR(32) NOT NULL,
                    statement_cadence VARCHAR(16) NOT NULL,
                    period_end_date DATE NOT NULL,
                    fiscal_year CHAR(4) NOT NULL,
                    fiscal_period VARCHAR(8) NOT NULL,
                    account_key VARCHAR(128) NOT NULL,
                    account_label VARCHAR(255) NULL,
                    value_numeric DOUBLE NULL,
                    currency VARCHAR(16) NULL,
                    unit VARCHAR(16) NULL DEFAULT 'USD',
                    source VARCHAR(32) NOT NULL DEFAULT 'yfinance',
                    source_ref VARCHAR(128) NOT NULL DEFAULT '',
                    as_of_date DATE NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_us_financial_row (
                        symbol, statement_type, statement_cadence, period_end_date, account_key
                    ),
                    INDEX idx_us_financial_symbol_period (symbol, period_end_date),
                    INDEX idx_us_financial_statement_period (statement_type, period_end_date),
                    INDEX idx_us_financial_account (account_key)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS us_top50_universe_snapshot (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    snapshot_date DATE NOT NULL,
                    market VARCHAR(16) NOT NULL DEFAULT 'US',
                    rank_position SMALLINT NOT NULL,
                    symbol VARCHAR(16) NOT NULL,
                    company_name VARCHAR(255) NULL,
                    cik CHAR(10) NULL,
                    market_cap BIGINT NULL,
                    source_url VARCHAR(255) NULL,
                    captured_at DATETIME NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_us_snapshot_rank (market, snapshot_date, rank_position),
                    UNIQUE KEY uniq_us_snapshot_symbol (market, snapshot_date, symbol),
                    INDEX idx_us_market_snapshot (market, snapshot_date),
                    INDEX idx_us_market_symbol (market, symbol),
                    INDEX idx_us_market_cik (market, cik)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

    @staticmethod
    def _coerce_snapshot_date(value: Any) -> Optional[date]:
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_symbols(values: Optional[Iterable[str]]) -> List[str]:
        normalized: List[str] = []
        for value in values or []:
            symbol = _normalize_symbol(value)
            if symbol:
                normalized.append(symbol)
        return list(dict.fromkeys(normalized))

    def fetch_market_caps_from_yfinance(
        self,
        symbols: Sequence[str],
    ) -> Dict[str, Optional[int]]:
        try:
            import yfinance as yf
        except Exception:
            logger.warning(
                "yfinance is unavailable. US Top50 snapshot will keep input order without market-cap ranking."
            )
            return {}

        market_caps: Dict[str, Optional[int]] = {}
        for symbol in symbols:
            normalized_symbol = _normalize_symbol(symbol)
            if not normalized_symbol:
                continue
            market_cap: Optional[int] = None
            try:
                ticker = yf.Ticker(normalized_symbol)
                fast_info = getattr(ticker, "fast_info", None)
                if fast_info is not None and hasattr(fast_info, "get"):
                    market_cap = _safe_market_cap(fast_info.get("market_cap"))
                if market_cap is None:
                    info = getattr(ticker, "info", None)
                    if info is not None and hasattr(info, "get"):
                        market_cap = _safe_market_cap(info.get("marketCap"))
            except Exception as exc:
                logger.warning("Failed to fetch market cap(symbol=%s): %s", normalized_symbol, exc)
            market_caps[normalized_symbol] = market_cap
        return market_caps

    def load_latest_top50_snapshot_rows(
        self,
        *,
        market: str = US_TOP50_DEFAULT_MARKET,
        limit: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    ) -> List[Dict[str, Any]]:
        self.ensure_tables()
        resolved_market = str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT snapshot_date
                FROM us_top50_universe_snapshot
                WHERE market = %s
                ORDER BY snapshot_date DESC, captured_at DESC, id DESC
                LIMIT 1
                """,
                (resolved_market,),
            )
            snapshot_row = cursor.fetchone() or {}
            snapshot_date = snapshot_row.get("snapshot_date")
            if not snapshot_date:
                return []
            cursor.execute(
                """
                SELECT
                    snapshot_date,
                    market,
                    rank_position,
                    symbol,
                    company_name,
                    cik,
                    market_cap,
                    source_url,
                    captured_at
                FROM us_top50_universe_snapshot
                WHERE market = %s
                  AND snapshot_date = %s
                ORDER BY rank_position ASC
                LIMIT %s
                """,
                (resolved_market, snapshot_date, max(int(limit), 1)),
            )
            rows = cursor.fetchall() or []
        return list(rows)

    def load_recent_top50_snapshot_dates(
        self,
        *,
        market: str = US_TOP50_DEFAULT_MARKET,
        limit: int = 2,
    ) -> List[date]:
        self.ensure_tables()
        resolved_market = str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT snapshot_date
                FROM us_top50_universe_snapshot
                WHERE market = %s
                ORDER BY snapshot_date DESC
                LIMIT %s
                """,
                (resolved_market, max(int(limit), 1)),
            )
            rows = cursor.fetchall() or []
        dates: List[date] = []
        for row in rows:
            snapshot_date = self._coerce_snapshot_date(row.get("snapshot_date"))
            if snapshot_date:
                dates.append(snapshot_date)
        return dates

    def load_top50_snapshot_rows_by_date(
        self,
        *,
        snapshot_date: date,
        market: str = US_TOP50_DEFAULT_MARKET,
        limit: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    ) -> List[Dict[str, Any]]:
        self.ensure_tables()
        resolved_market = str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET
        resolved_date = self._coerce_snapshot_date(snapshot_date)
        if not resolved_date:
            return []
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    snapshot_date,
                    market,
                    rank_position,
                    symbol,
                    company_name,
                    cik,
                    market_cap,
                    source_url,
                    captured_at
                FROM us_top50_universe_snapshot
                WHERE market = %s
                  AND snapshot_date = %s
                ORDER BY rank_position ASC
                LIMIT %s
                """,
                (resolved_market, resolved_date, max(int(limit), 1)),
            )
            rows = cursor.fetchall() or []
        return list(rows)

    def build_top50_snapshot_diff(
        self,
        *,
        market: str = US_TOP50_DEFAULT_MARKET,
        latest_snapshot_date: Optional[date] = None,
        previous_snapshot_date: Optional[date] = None,
        limit: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        resolved_market = str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET
        recent_dates = self.load_recent_top50_snapshot_dates(
            market=resolved_market,
            limit=2,
        )
        if latest_snapshot_date:
            latest = self._coerce_snapshot_date(latest_snapshot_date)
        else:
            latest = recent_dates[0] if recent_dates else None

        if previous_snapshot_date:
            previous = self._coerce_snapshot_date(previous_snapshot_date)
        else:
            previous = None
            for candidate in recent_dates:
                if latest and candidate != latest:
                    previous = candidate
                    break

        latest_rows = (
            self.load_top50_snapshot_rows_by_date(
                snapshot_date=latest,
                market=resolved_market,
                limit=limit,
            )
            if latest
            else []
        )
        previous_rows = (
            self.load_top50_snapshot_rows_by_date(
                snapshot_date=previous,
                market=resolved_market,
                limit=limit,
            )
            if previous
            else []
        )

        latest_rank_by_symbol: Dict[str, int] = {}
        previous_rank_by_symbol: Dict[str, int] = {}
        latest_name_by_symbol: Dict[str, str] = {}
        previous_name_by_symbol: Dict[str, str] = {}

        for row in latest_rows:
            symbol = _normalize_symbol(row.get("symbol"))
            rank_position = _safe_int(row.get("rank_position"))
            if not symbol or rank_position is None:
                continue
            latest_rank_by_symbol[symbol] = int(rank_position)
            latest_name_by_symbol[symbol] = str(row.get("company_name") or "").strip()

        for row in previous_rows:
            symbol = _normalize_symbol(row.get("symbol"))
            rank_position = _safe_int(row.get("rank_position"))
            if not symbol or rank_position is None:
                continue
            previous_rank_by_symbol[symbol] = int(rank_position)
            previous_name_by_symbol[symbol] = str(row.get("company_name") or "").strip()

        latest_symbols = set(latest_rank_by_symbol.keys())
        previous_symbols = set(previous_rank_by_symbol.keys())
        added = sorted(latest_symbols - previous_symbols)
        removed = sorted(previous_symbols - latest_symbols)
        common = sorted(latest_symbols & previous_symbols)

        rank_changes: List[Dict[str, Any]] = []
        for symbol in common:
            latest_rank = latest_rank_by_symbol.get(symbol)
            previous_rank = previous_rank_by_symbol.get(symbol)
            if latest_rank is None or previous_rank is None or latest_rank == previous_rank:
                continue
            rank_changes.append(
                {
                    "symbol": symbol,
                    "company_name": latest_name_by_symbol.get(symbol) or previous_name_by_symbol.get(symbol) or None,
                    "previous_rank": int(previous_rank),
                    "current_rank": int(latest_rank),
                    "delta": int(previous_rank - latest_rank),
                }
            )

        rank_changes.sort(
            key=lambda item: abs(int(item.get("delta") or 0)),
            reverse=True,
        )

        def _convert_symbol_list(symbols: List[str], name_map: Dict[str, str]) -> List[Dict[str, Any]]:
            return [
                {
                    "symbol": symbol,
                    "company_name": name_map.get(symbol) or None,
                }
                for symbol in symbols
            ]

        return {
            "market": resolved_market,
            "latest_snapshot_date": latest.isoformat() if latest else None,
            "previous_snapshot_date": previous.isoformat() if previous else None,
            "has_previous_snapshot": bool(previous),
            "latest_count": len(latest_rank_by_symbol),
            "previous_count": len(previous_rank_by_symbol),
            "added_count": len(added),
            "removed_count": len(removed),
            "rank_changed_count": len(rank_changes),
            "added_symbols": _convert_symbol_list(added, latest_name_by_symbol),
            "removed_symbols": _convert_symbol_list(removed, previous_name_by_symbol),
            "rank_changes": rank_changes,
        }

    def upsert_top50_snapshot_rows(
        self,
        *,
        rows: Sequence[Dict[str, Any]],
        snapshot_date: date,
        market: str = US_TOP50_DEFAULT_MARKET,
        source_url: str = US_TOP50_DEFAULT_SOURCE_URL,
        captured_at: Optional[datetime] = None,
    ) -> int:
        self.ensure_tables()
        resolved_market = str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET
        resolved_captured_at = captured_at or datetime.now(timezone.utc).replace(tzinfo=None)

        normalized_rows: List[tuple] = []
        for row in rows:
            rank_position = _safe_int(row.get("rank_position"))
            symbol = _normalize_symbol(row.get("symbol"))
            if rank_position is None or not symbol:
                continue
            company_name = str(row.get("company_name") or "").strip() or None
            cik = _normalize_cik(row.get("cik"))
            market_cap = _safe_market_cap(row.get("market_cap"))
            metadata = row.get("metadata") or {}
            normalized_rows.append(
                (
                    snapshot_date,
                    resolved_market,
                    int(rank_position),
                    symbol,
                    company_name,
                    cik,
                    market_cap,
                    source_url,
                    resolved_captured_at,
                    _to_json(metadata),
                )
            )
        if not normalized_rows:
            return 0

        query = """
            INSERT INTO us_top50_universe_snapshot (
                snapshot_date,
                market,
                rank_position,
                symbol,
                company_name,
                cik,
                market_cap,
                source_url,
                captured_at,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                company_name = VALUES(company_name),
                cik = VALUES(cik),
                market_cap = VALUES(market_cap),
                source_url = VALUES(source_url),
                captured_at = VALUES(captured_at),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, normalized_rows)
            return int(cursor.rowcount or 0)

    def capture_top50_snapshot(
        self,
        *,
        snapshot_date: date,
        symbols: Optional[Iterable[str]] = None,
        rebalance_candidates: Optional[Iterable[str]] = None,
        max_symbol_count: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
        market: str = US_TOP50_DEFAULT_MARKET,
        source_url: str = US_TOP50_DEFAULT_SOURCE_URL,
        rank_by_market_cap: bool = True,
        refresh_sec_mapping: bool = True,
        sec_mapping_max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        resolved_max_symbol_count = max(int(max_symbol_count), 1)
        candidate_symbols = self._normalize_symbols(rebalance_candidates)
        if not candidate_symbols:
            explicit_symbols = self._normalize_symbols(symbols)
            if explicit_symbols:
                candidate_symbols = explicit_symbols
            else:
                candidate_symbols = self.resolve_target_symbols(
                    symbols=None,
                    max_symbol_count=resolved_max_symbol_count,
                )

        if not candidate_symbols:
            raise ValueError("No target US symbols resolved for Top50 snapshot.")

        market_cap_by_symbol: Dict[str, Optional[int]] = {}
        if rank_by_market_cap:
            market_cap_by_symbol = self.fetch_market_caps_from_yfinance(candidate_symbols)

        scored_symbols: List[Dict[str, Any]] = []
        for idx, symbol in enumerate(candidate_symbols, start=1):
            scored_symbols.append(
                {
                    "symbol": symbol,
                    "input_order": idx,
                    "market_cap": market_cap_by_symbol.get(symbol),
                }
            )

        if rank_by_market_cap and any(item.get("market_cap") is not None for item in scored_symbols):
            scored_symbols = sorted(
                scored_symbols,
                key=lambda item: (
                    item.get("market_cap") is None,
                    -(item.get("market_cap") or 0),
                    int(item.get("input_order") or 0),
                ),
            )

        selected_symbols = scored_symbols[:resolved_max_symbol_count]
        resolved_symbol_list = [item["symbol"] for item in selected_symbols if item.get("symbol")]

        if refresh_sec_mapping:
            self.refresh_sec_cik_mapping(
                force=False,
                max_age_days=sec_mapping_max_age_days,
            )
        mapping_rows = self.load_symbol_mapping_rows(resolved_symbol_list)

        snapshot_rows: List[Dict[str, Any]] = []
        for rank_position, item in enumerate(selected_symbols, start=1):
            symbol = _normalize_symbol(item.get("symbol"))
            if not symbol:
                continue
            symbol_meta = mapping_rows.get(symbol) or {}
            snapshot_rows.append(
                {
                    "rank_position": rank_position,
                    "symbol": symbol,
                    "company_name": symbol_meta.get("company_name"),
                    "cik": symbol_meta.get("cik"),
                    "market_cap": item.get("market_cap"),
                    "metadata": {
                        "source": "us_top50_snapshot",
                        "ranked_by_market_cap": bool(rank_by_market_cap),
                        "market_cap_source": "yfinance" if rank_by_market_cap else "input_order",
                        "input_order": item.get("input_order"),
                        "candidate_count": len(candidate_symbols),
                    },
                }
            )

        affected = self.upsert_top50_snapshot_rows(
            rows=snapshot_rows,
            snapshot_date=snapshot_date,
            market=market,
            source_url=source_url,
        )
        return {
            "snapshot_date": snapshot_date.isoformat(),
            "market": str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET,
            "candidate_count": len(candidate_symbols),
            "row_count": len(snapshot_rows),
            "saved_rows": int(affected),
            "ranked_by_market_cap": bool(rank_by_market_cap),
        }

    def fetch_sec_company_tickers(self) -> List[Dict[str, Any]]:
        payload = self._fetch_json(
            SEC_COMPANY_TICKERS_URL,
            headers=self._sec_headers(),
        )
        if not isinstance(payload, dict):
            return []
        rows: List[Dict[str, Any]] = []
        for _, item in payload.items():
            if not isinstance(item, dict):
                continue
            symbol = _normalize_symbol(item.get("ticker"))
            cik = _normalize_cik(item.get("cik_str"))
            if not symbol or not cik:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "cik": cik,
                    "company_name": str(item.get("title") or "").strip() or None,
                    "metadata_json": _to_json(item),
                }
            )
        return rows

    def upsert_sec_cik_mapping(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO us_sec_cik_mapping (symbol, cik, company_name, metadata_json)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cik = VALUES(cik),
                company_name = VALUES(company_name),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("symbol"),
                row.get("cik"),
                row.get("company_name"),
                row.get("metadata_json"),
            )
            for row in rows
        ]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def refresh_sec_cik_mapping(
        self,
        *,
        force: bool = False,
        max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        current_rows = 0
        last_updated_at: Optional[datetime] = None
        cache_hit = False

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS row_count, MAX(updated_at) AS last_updated_at
                FROM us_sec_cik_mapping
                """
            )
            stats = cursor.fetchone() or {}
            current_rows = int(stats.get("row_count") or 0)
            last_updated_at = stats.get("last_updated_at")

        if not force and current_rows > 0 and isinstance(last_updated_at, datetime):
            stale_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(max_age_days, 1))
            if last_updated_at >= stale_cutoff:
                cache_hit = True

        if cache_hit:
            return {
                "cache_hit": True,
                "current_rows": current_rows,
                "last_updated_at": last_updated_at.isoformat() if last_updated_at else None,
                "upserted_rows": 0,
            }

        rows = self.fetch_sec_company_tickers()
        affected = self.upsert_sec_cik_mapping(rows)

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS row_count, MAX(updated_at) AS last_updated_at
                FROM us_sec_cik_mapping
                """
            )
            stats = cursor.fetchone() or {}
            current_rows = int(stats.get("row_count") or 0)
            last_updated_at = stats.get("last_updated_at")

        return {
            "cache_hit": False,
            "current_rows": current_rows,
            "last_updated_at": last_updated_at.isoformat() if isinstance(last_updated_at, datetime) else None,
            "upserted_rows": int(affected),
        }

    def resolve_target_symbols(
        self,
        *,
        symbols: Optional[Iterable[str]] = None,
        max_symbol_count: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    ) -> List[str]:
        explicit = [
            symbol
            for symbol in (_normalize_symbol(value) for value in (symbols or []))
            if symbol
        ]
        if explicit:
            return list(dict.fromkeys(explicit))[: max(int(max_symbol_count), 1)]

        env_symbols = [
            symbol.strip()
            for symbol in str(os.getenv("US_TOP50_FIXED_SYMBOLS", "") or "").split(",")
            if symbol.strip()
        ]
        baseline = env_symbols if env_symbols else list(DEFAULT_US_TOP50_FIXED_SYMBOLS)
        normalized = [
            symbol
            for symbol in (_normalize_symbol(value) for value in baseline)
            if symbol
        ]
        return list(dict.fromkeys(normalized))[: max(int(max_symbol_count), 1)]

    def load_cik_by_symbol(self, symbols: Sequence[str]) -> Dict[str, str]:
        normalized_symbols = [
            symbol
            for symbol in (_normalize_symbol(value) for value in (symbols or []))
            if symbol
        ]
        if not normalized_symbols:
            return {}

        self.ensure_tables()
        symbol_to_cik: Dict[str, str] = {}
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            for chunk in _chunked(normalized_symbols, 200):
                placeholders = ", ".join(["%s"] * len(chunk))
                cursor.execute(
                    f"""
                    SELECT symbol, cik
                    FROM us_sec_cik_mapping
                    WHERE symbol IN ({placeholders})
                    """,
                    tuple(chunk),
                )
                for row in cursor.fetchall() or []:
                    symbol = _normalize_symbol(row.get("symbol"))
                    cik = _normalize_cik(row.get("cik"))
                    if symbol and cik:
                        symbol_to_cik[symbol] = cik
        return symbol_to_cik

    def load_symbol_mapping_rows(self, symbols: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        normalized_symbols = [
            symbol
            for symbol in (_normalize_symbol(value) for value in (symbols or []))
            if symbol
        ]
        if not normalized_symbols:
            return {}

        self.ensure_tables()
        mapping: Dict[str, Dict[str, Any]] = {}
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            for chunk in _chunked(normalized_symbols, 200):
                placeholders = ", ".join(["%s"] * len(chunk))
                cursor.execute(
                    f"""
                    SELECT symbol, cik, company_name
                    FROM us_sec_cik_mapping
                    WHERE symbol IN ({placeholders})
                    """,
                    tuple(chunk),
                )
                for row in cursor.fetchall() or []:
                    symbol = _normalize_symbol(row.get("symbol"))
                    if not symbol:
                        continue
                    mapping[symbol] = {
                        "symbol": symbol,
                        "cik": _normalize_cik(row.get("cik")),
                        "company_name": str(row.get("company_name") or "").strip() or None,
                    }
        return mapping

    def fetch_sec_submissions(self, *, cik: str) -> Dict[str, Any]:
        normalized_cik = _normalize_cik(cik)
        if not normalized_cik:
            raise ValueError(f"Invalid cik: {cik}")
        url = SEC_SUBMISSIONS_URL_TEMPLATE.format(cik=normalized_cik)
        return self._fetch_json(url, headers=self._sec_headers())

    @staticmethod
    def _is_earnings_related_8k(item_text: str, description_text: str) -> bool:
        combined = f"{item_text or ''} {description_text or ''}".lower()
        if "2.02" in combined:
            return True
        return "results of operations" in combined or "earnings" in combined

    def extract_sec_earnings_events(
        self,
        *,
        symbol: str,
        cik: str,
        submission_payload: Dict[str, Any],
        as_of_date: date,
    ) -> List[Dict[str, Any]]:
        normalized_symbol = _normalize_symbol(symbol)
        normalized_cik = _normalize_cik(cik)
        if not normalized_symbol or not normalized_cik:
            return []

        recent = (
            ((submission_payload or {}).get("filings") or {}).get("recent") or {}
        )
        if not isinstance(recent, dict):
            return []

        accession_numbers = list(recent.get("accessionNumber") or [])
        forms = list(recent.get("form") or [])
        filing_dates = list(recent.get("filingDate") or [])
        acceptance_datetimes = list(recent.get("acceptanceDateTime") or [])
        report_dates = list(recent.get("reportDate") or [])
        primary_documents = list(recent.get("primaryDocument") or [])
        items = list(recent.get("items") or [])
        primary_doc_desc = list(recent.get("primaryDocDescription") or [])

        max_len = max(
            len(accession_numbers),
            len(forms),
            len(filing_dates),
            len(acceptance_datetimes),
            len(report_dates),
            len(primary_documents),
            len(items),
            len(primary_doc_desc),
            0,
        )

        rows: List[Dict[str, Any]] = []
        cik_int = str(int(normalized_cik))
        for idx in range(max_len):
            accession_no = str(accession_numbers[idx] if idx < len(accession_numbers) else "").strip()
            form = str(forms[idx] if idx < len(forms) else "").strip().upper()
            filing_date = _parse_date(filing_dates[idx] if idx < len(filing_dates) else None)
            if not accession_no or form not in SEC_EARNINGS_FORMS or not filing_date:
                continue

            item_text = str(items[idx] if idx < len(items) else "").strip()
            description_text = str(primary_doc_desc[idx] if idx < len(primary_doc_desc) else "").strip()
            if form == "8-K" and not self._is_earnings_related_8k(item_text, description_text):
                continue

            if form == "8-K":
                event_type = "sec_8k_earnings"
            elif form == "10-Q":
                event_type = "sec_10q"
            else:
                event_type = "sec_10k"

            acceptance_dt = _parse_sec_acceptance_datetime(
                acceptance_datetimes[idx] if idx < len(acceptance_datetimes) else None
            )
            report_date = _parse_date(report_dates[idx] if idx < len(report_dates) else None)
            primary_document = str(
                primary_documents[idx] if idx < len(primary_documents) else ""
            ).strip()
            accession_no_no_dash = accession_no.replace("-", "")
            source_url = (
                SEC_ARCHIVES_URL_TEMPLATE.format(
                    cik_int=cik_int,
                    accession_no_no_dash=accession_no_no_dash,
                    primary_document=primary_document,
                )
                if primary_document
                else None
            )

            metadata = {
                "accession_no": accession_no,
                "form": form,
                "filing_date": filing_date.isoformat(),
                "acceptance_datetime": acceptance_dt.isoformat() if acceptance_dt else None,
                "report_date": report_date.isoformat() if report_date else None,
                "items": item_text or None,
                "primary_document": primary_document or None,
                "primary_doc_description": description_text or None,
                "source_url": source_url,
            }
            rows.append(
                {
                    "symbol": normalized_symbol,
                    "cik": normalized_cik,
                    "event_date": filing_date,
                    "event_status": "confirmed",
                    "event_type": event_type,
                    "source": "sec",
                    "source_ref": accession_no,
                    "filed_at": acceptance_dt,
                    "report_date": report_date,
                    "as_of_date": as_of_date,
                    "metadata_json": _to_json(metadata),
                }
            )
        return rows

    def fetch_expected_earnings_rows_from_yfinance(
        self,
        *,
        symbols: Sequence[str],
        as_of_date: date,
        lookback_days: int = DEFAULT_US_EARNINGS_LOOKBACK_DAYS,
        lookahead_days: int = DEFAULT_US_EARNINGS_LOOKAHEAD_DAYS,
    ) -> List[Dict[str, Any]]:
        try:
            import yfinance as yf
        except Exception:
            logger.warning("yfinance is unavailable. expected earnings calendar will be skipped.")
            return []

        window_start = as_of_date - timedelta(days=max(int(lookback_days), 0))
        window_end = as_of_date + timedelta(days=max(int(lookahead_days), 1))
        rows: List[Dict[str, Any]] = []

        for symbol in symbols:
            normalized_symbol = _normalize_symbol(symbol)
            if not normalized_symbol:
                continue
            try:
                ticker = yf.Ticker(normalized_symbol)
                frame = ticker.get_earnings_dates(limit=16)
            except Exception as exc:
                logger.warning("yfinance earnings calendar fetch failed(symbol=%s): %s", normalized_symbol, exc)
                continue

            if frame is None or len(frame) == 0:
                continue

            for index_value, value_row in frame.iterrows():
                try:
                    event_date = index_value.date()
                except Exception:
                    continue
                if event_date < window_start or event_date > window_end:
                    continue

                eps_estimate = _safe_float(value_row.get("EPS Estimate"))
                reported_eps = _safe_float(value_row.get("Reported EPS"))
                surprise_pct = _safe_float(value_row.get("Surprise(%)"))
                metadata = {
                    "eps_estimate": eps_estimate,
                    "reported_eps": reported_eps,
                    "surprise_pct": surprise_pct,
                }
                rows.append(
                    {
                        "symbol": normalized_symbol,
                        "cik": None,
                        "event_date": event_date,
                        "event_status": "expected",
                        "event_type": "yfinance_earnings_calendar",
                        "source": "yfinance",
                        "source_ref": f"{normalized_symbol}:{event_date.isoformat()}",
                        "filed_at": None,
                        "report_date": None,
                        "as_of_date": as_of_date,
                        "metadata_json": _to_json(metadata),
                    }
                )
        return rows

    @staticmethod
    def _derive_fiscal_period(period_end_date: date, cadence: str) -> str:
        if str(cadence or "").lower() == "annual":
            return "FY"
        quarter = ((int(period_end_date.month) - 1) // 3) + 1
        return f"Q{quarter}"

    @staticmethod
    def _resolve_ticker_currency(ticker: Any) -> Optional[str]:
        try:
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info is not None and hasattr(fast_info, "get"):
                currency = str(fast_info.get("currency") or "").strip().upper()
                if currency:
                    return currency
        except Exception:
            pass
        try:
            info = getattr(ticker, "info", None)
            if info is not None and hasattr(info, "get"):
                currency = str(info.get("currency") or "").strip().upper()
                if currency:
                    return currency
        except Exception:
            pass
        return None

    def extract_financial_rows_from_frame(
        self,
        *,
        symbol: str,
        cik: Optional[str],
        company_name: Optional[str],
        statement_type: str,
        statement_cadence: str,
        frame: Any,
        currency: Optional[str],
        as_of_date: date,
        max_periods_per_statement: int = DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT,
    ) -> List[Dict[str, Any]]:
        if frame is None:
            return []
        if not hasattr(frame, "iterrows") or not hasattr(frame, "columns"):
            return []
        if len(frame) == 0:
            return []

        period_columns: List[tuple[Any, date]] = []
        for column in list(frame.columns):
            period_end_date = _extract_date(column)
            if not period_end_date:
                continue
            period_columns.append((column, period_end_date))
        if not period_columns:
            return []

        resolved_max_periods = max(int(max_periods_per_statement), 1)
        period_columns = sorted(period_columns, key=lambda item: item[1], reverse=True)
        period_columns = period_columns[:resolved_max_periods]

        normalized_symbol = _normalize_symbol(symbol)
        normalized_cik = _normalize_cik(cik) if cik else None
        if not normalized_symbol:
            return []
        resolved_statement_type = str(statement_type or "").strip() or "unknown_statement"
        resolved_cadence = str(statement_cadence or "").strip() or "unknown"
        resolved_currency = str(currency or "").strip().upper() or "USD"

        rows: List[Dict[str, Any]] = []
        for account_label, value_row in frame.iterrows():
            account_label_text = str(account_label or "").strip()
            account_key = _normalize_account_key(account_label_text)
            if not account_key:
                continue
            for column_name, period_end_date in period_columns:
                try:
                    value_raw = value_row.get(column_name)
                except Exception:
                    continue
                value_numeric = _safe_float(value_raw)
                if value_numeric is None:
                    continue
                fiscal_year = str(period_end_date.year)
                fiscal_period = self._derive_fiscal_period(period_end_date, resolved_cadence)
                source_ref = (
                    f"{normalized_symbol}:{resolved_statement_type}:{resolved_cadence}:"
                    f"{period_end_date.isoformat()}:{account_key}"
                )
                metadata = {
                    "raw_account_label": account_label_text,
                    "statement_type": resolved_statement_type,
                    "statement_cadence": resolved_cadence,
                    "period_end_date": period_end_date.isoformat(),
                    "currency": resolved_currency,
                }
                rows.append(
                    {
                        "symbol": normalized_symbol,
                        "cik": normalized_cik,
                        "company_name": company_name,
                        "statement_type": resolved_statement_type,
                        "statement_cadence": resolved_cadence,
                        "period_end_date": period_end_date,
                        "fiscal_year": fiscal_year,
                        "fiscal_period": fiscal_period,
                        "account_key": account_key,
                        "account_label": account_label_text or None,
                        "value_numeric": value_numeric,
                        "currency": resolved_currency,
                        "unit": resolved_currency,
                        "source": "yfinance",
                        "source_ref": source_ref,
                        "as_of_date": as_of_date,
                        "metadata_json": _to_json(metadata),
                    }
                )
        return rows

    def fetch_financial_rows_from_yfinance(
        self,
        *,
        symbols: Sequence[str],
        symbol_mapping: Optional[Dict[str, Dict[str, Any]]] = None,
        as_of_date: date,
        max_periods_per_statement: int = DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT,
    ) -> Dict[str, Any]:
        try:
            import yfinance as yf
        except Exception:
            logger.warning("yfinance is unavailable. US financials collection will be skipped.")
            return {
                "rows": [],
                "rows_by_statement": {},
                "rows_by_symbol": {},
                "failed_symbols": [
                    {"symbol": "__all__", "reason": "yfinance_unavailable"}
                ],
            }

        mapping = symbol_mapping or {}
        all_rows: List[Dict[str, Any]] = []
        rows_by_statement: Dict[str, int] = {}
        rows_by_symbol: Dict[str, int] = {}
        failed_symbols: List[Dict[str, str]] = []

        for symbol in symbols:
            normalized_symbol = _normalize_symbol(symbol)
            if not normalized_symbol:
                continue
            symbol_meta = mapping.get(normalized_symbol) or {}
            cik = symbol_meta.get("cik")
            company_name = symbol_meta.get("company_name")

            try:
                ticker = yf.Ticker(normalized_symbol)
            except Exception as exc:
                failed_symbols.append(
                    {"symbol": normalized_symbol, "reason": f"ticker_init_failed:{exc}"}
                )
                continue

            resolved_currency = self._resolve_ticker_currency(ticker)
            symbol_row_count = 0
            for statement_type, statement_cadence, attribute_name in US_FINANCIAL_STATEMENT_SPECS:
                try:
                    frame = getattr(ticker, attribute_name, None)
                except Exception as exc:
                    failed_symbols.append(
                        {
                            "symbol": normalized_symbol,
                            "reason": f"{attribute_name}_fetch_failed:{exc}",
                        }
                    )
                    continue

                rows = self.extract_financial_rows_from_frame(
                    symbol=normalized_symbol,
                    cik=cik,
                    company_name=company_name,
                    statement_type=statement_type,
                    statement_cadence=statement_cadence,
                    frame=frame,
                    currency=resolved_currency,
                    as_of_date=as_of_date,
                    max_periods_per_statement=max_periods_per_statement,
                )
                if not rows:
                    continue
                key = f"{statement_type}:{statement_cadence}"
                rows_by_statement[key] = int(rows_by_statement.get(key, 0)) + len(rows)
                symbol_row_count += len(rows)
                all_rows.extend(rows)
            if symbol_row_count > 0:
                rows_by_symbol[normalized_symbol] = symbol_row_count

        return {
            "rows": all_rows,
            "rows_by_statement": rows_by_statement,
            "rows_by_symbol": rows_by_symbol,
            "failed_symbols": failed_symbols,
        }

    def upsert_financial_rows(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO us_corporate_financials (
                symbol,
                cik,
                company_name,
                statement_type,
                statement_cadence,
                period_end_date,
                fiscal_year,
                fiscal_period,
                account_key,
                account_label,
                value_numeric,
                currency,
                unit,
                source,
                source_ref,
                as_of_date,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cik = VALUES(cik),
                company_name = VALUES(company_name),
                fiscal_year = VALUES(fiscal_year),
                fiscal_period = VALUES(fiscal_period),
                account_label = VALUES(account_label),
                value_numeric = VALUES(value_numeric),
                currency = VALUES(currency),
                unit = VALUES(unit),
                source = VALUES(source),
                source_ref = VALUES(source_ref),
                as_of_date = VALUES(as_of_date),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("symbol"),
                row.get("cik"),
                row.get("company_name"),
                row.get("statement_type"),
                row.get("statement_cadence"),
                row.get("period_end_date"),
                row.get("fiscal_year"),
                row.get("fiscal_period"),
                row.get("account_key"),
                row.get("account_label"),
                row.get("value_numeric"),
                row.get("currency"),
                row.get("unit"),
                row.get("source"),
                row.get("source_ref") or "",
                row.get("as_of_date"),
                row.get("metadata_json"),
            )
            for row in rows
        ]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def collect_financials(
        self,
        *,
        symbols: Optional[Iterable[str]] = None,
        max_symbol_count: int = DEFAULT_US_FINANCIALS_MAX_SYMBOL_COUNT,
        refresh_sec_mapping: bool = True,
        sec_mapping_max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
        max_periods_per_statement: int = DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        run_as_of = as_of_date or date.today()
        resolved_symbols = self.resolve_target_symbols(
            symbols=symbols,
            max_symbol_count=max_symbol_count,
        )
        if not resolved_symbols:
            raise ValueError("No target US symbols resolved.")

        summary: Dict[str, Any] = {
            "as_of_date": run_as_of.isoformat(),
            "target_symbol_count": len(resolved_symbols),
            "target_symbols": resolved_symbols,
            "max_periods_per_statement": int(max(max_periods_per_statement, 1)),
            "rows_by_statement": {},
            "rows_by_symbol": {},
            "fetched_rows": 0,
            "upserted_rows": 0,
            "failed_symbols": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        if refresh_sec_mapping:
            summary["sec_mapping"] = self.refresh_sec_cik_mapping(
                force=False,
                max_age_days=sec_mapping_max_age_days,
            )

        mapping_rows = self.load_symbol_mapping_rows(resolved_symbols)
        fetch_result = self.fetch_financial_rows_from_yfinance(
            symbols=resolved_symbols,
            symbol_mapping=mapping_rows,
            as_of_date=run_as_of,
            max_periods_per_statement=max_periods_per_statement,
        )
        rows = list(fetch_result.get("rows") or [])
        summary["rows_by_statement"] = dict(fetch_result.get("rows_by_statement") or {})
        summary["rows_by_symbol"] = dict(fetch_result.get("rows_by_symbol") or {})
        summary["failed_symbols"] = list(fetch_result.get("failed_symbols") or [])
        summary["fetched_rows"] = len(rows)
        summary["upserted_rows"] = self.upsert_financial_rows(rows)
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary

    def upsert_earnings_events(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO us_corporate_earnings_events (
                symbol,
                cik,
                event_date,
                event_status,
                event_type,
                source,
                source_ref,
                filed_at,
                report_date,
                as_of_date,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cik = VALUES(cik),
                filed_at = VALUES(filed_at),
                report_date = VALUES(report_date),
                as_of_date = VALUES(as_of_date),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("symbol"),
                row.get("cik"),
                row.get("event_date"),
                row.get("event_status"),
                row.get("event_type"),
                row.get("source"),
                row.get("source_ref") or "",
                row.get("filed_at"),
                row.get("report_date"),
                row.get("as_of_date"),
                row.get("metadata_json"),
            )
            for row in rows
        ]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def collect_earnings_events(
        self,
        *,
        symbols: Optional[Iterable[str]] = None,
        max_symbol_count: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
        refresh_sec_mapping: bool = True,
        sec_mapping_max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
        include_expected: bool = True,
        include_confirmed: bool = True,
        lookback_days: int = DEFAULT_US_EARNINGS_LOOKBACK_DAYS,
        lookahead_days: int = DEFAULT_US_EARNINGS_LOOKAHEAD_DAYS,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        run_as_of = as_of_date or date.today()
        resolved_symbols = self.resolve_target_symbols(
            symbols=symbols,
            max_symbol_count=max_symbol_count,
        )
        if not resolved_symbols:
            raise ValueError("No target US symbols resolved.")

        summary: Dict[str, Any] = {
            "as_of_date": run_as_of.isoformat(),
            "target_symbol_count": len(resolved_symbols),
            "target_symbols": resolved_symbols,
            "include_expected": bool(include_expected),
            "include_confirmed": bool(include_confirmed),
            "api_requests": 0,
            "expected_rows": 0,
            "confirmed_rows": 0,
            "upserted_rows": 0,
            "failed_symbols": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        if include_confirmed:
            if refresh_sec_mapping:
                mapping_result = self.refresh_sec_cik_mapping(
                    force=False,
                    max_age_days=sec_mapping_max_age_days,
                )
                summary["sec_mapping"] = mapping_result

            cik_by_symbol = self.load_cik_by_symbol(resolved_symbols)
            confirmed_rows: List[Dict[str, Any]] = []
            for symbol in resolved_symbols:
                cik = cik_by_symbol.get(symbol)
                if not cik:
                    continue
                try:
                    payload = self.fetch_sec_submissions(cik=cik)
                    summary["api_requests"] += 1
                    confirmed_rows.extend(
                        self.extract_sec_earnings_events(
                            symbol=symbol,
                            cik=cik,
                            submission_payload=payload,
                            as_of_date=run_as_of,
                        )
                    )
                except HTTPError as exc:
                    summary["failed_symbols"].append(
                        {"symbol": symbol, "reason": f"http_error:{exc.code}"}
                    )
                except Exception as exc:
                    summary["failed_symbols"].append(
                        {"symbol": symbol, "reason": str(exc)}
                    )
            summary["confirmed_rows"] = len(confirmed_rows)
            summary["upserted_rows"] += self.upsert_earnings_events(confirmed_rows)

        if include_expected:
            expected_rows = self.fetch_expected_earnings_rows_from_yfinance(
                symbols=resolved_symbols,
                as_of_date=run_as_of,
                lookback_days=lookback_days,
                lookahead_days=lookahead_days,
            )
            summary["expected_rows"] = len(expected_rows)
            summary["upserted_rows"] += self.upsert_earnings_events(expected_rows)

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary


_us_corporate_collector_singleton: Optional[USCorporateCollector] = None


def get_us_corporate_collector() -> USCorporateCollector:
    global _us_corporate_collector_singleton
    if _us_corporate_collector_singleton is None:
        _us_corporate_collector_singleton = USCorporateCollector()
    return _us_corporate_collector_singleton
