"""
KR corporate fundamentals collector (Open DART).

Phase 2.5 (P3):
- corp_code cache (Open DART corpCode.xml)
- major account ingestion (fnlttMultiAcnt.json)
- canonical persistence for KR corporate fundamentals
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)

DART_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_MULTI_ACCOUNT_URL = "https://opendart.fss.or.kr/api/fnlttMultiAcnt.json"
DART_DISCLOSURE_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
NAVER_KOSPI_MARKET_CAP_URL = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1"
NAVER_ITEM_MAIN_URL_TEMPLATE = "https://finance.naver.com/item/main.naver?code={stock_code}"
NAVER_FINANCIAL_VALUE_UNIT_MULTIPLIER = 100_000_000
KR_TOP50_DEFAULT_MARKET = "KOSPI"
KR_TOP50_DEFAULT_SOURCE_URL = NAVER_KOSPI_MARKET_CAP_URL
DEFAULT_EARNINGS_EXPECTATION_LOOKBACK_YEARS = 3
DEFAULT_REQUIRE_EXPECTATION_FEED = True
DEFAULT_ALLOW_BASELINE_FALLBACK = False
DEFAULT_EXPECTATION_FEED_URL = "internal://kr-top50-ondemand"
DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT = 100
INTERNAL_EXPECTATION_FEED_URLS = {
    DEFAULT_EXPECTATION_FEED_URL,
    "internal://default",
    "internal://top50-on-demand",
}
DEFAULT_DART_CORPCODE_MAX_AGE_DAYS = 30
DEFAULT_DART_BATCH_SIZE = 100
DEFAULT_DART_DISCLOSURE_PAGE_COUNT = 100
DEFAULT_KR_TOP50_DAILY_OHLCV_LOOKBACK_DAYS = 365
DEFAULT_KR_TOP50_OHLCV_CONTINUITY_DAYS = 120
EARNINGS_SURPRISE_MEET_THRESHOLD_PCT = 2.0

EARNINGS_DISCLOSURE_KEYWORDS = (
    "영업(잠정)실적",
    "잠정실적",
    "잠정",
    "실적",
    "매출액또는손익구조",
)
EARNINGS_METRIC_ACCOUNT_MAP = {
    "revenue": ("매출액", "영업수익"),
    "operating_income": ("영업이익",),
    "net_income": ("당기순이익", "분기순이익", "당기순이익(손실)"),
}
EARNINGS_METRIC_ALIASES = {
    "revenue": "revenue",
    "sales": "revenue",
    "매출": "revenue",
    "매출액": "revenue",
    "영업수익": "revenue",
    "operating_income": "operating_income",
    "op_income": "operating_income",
    "영업이익": "operating_income",
    "net_income": "net_income",
    "netprofit": "net_income",
    "순이익": "net_income",
    "당기순이익": "net_income",
    "분기순이익": "net_income",
}


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _normalize_corp_code(value: Any) -> Optional[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) != 8:
        return None
    return digits


def _normalize_stock_code(value: Any) -> Optional[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) == 6:
        return digits
    return None


def _chunked(values: Sequence[str], chunk_size: int) -> Iterable[List[str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    for idx in range(0, len(values), chunk_size):
        yield list(values[idx : idx + chunk_size])


def _contains_earnings_keyword(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in EARNINGS_DISCLOSURE_KEYWORDS)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
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


def _safe_decimal_pct(value: Any, ndigits: int = 4) -> Optional[float]:
    number = _safe_float(value)
    if number is None:
        return None
    return round(number, ndigits)


class KRCorporateCollector:
    """Open DART collector for KR corporate fundamentals."""

    def __init__(self, db_connection_factory=None):
        self._db_connection_factory = db_connection_factory or get_db_connection

    def _get_db_connection(self):
        return self._db_connection_factory()

    @staticmethod
    def _ensure_column_exists(cursor, table_name: str, column_name: str, column_definition: str):
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE %s", (column_name,))
        exists = cursor.fetchone()
        if exists:
            return
        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN {column_definition}")

    @staticmethod
    def _ensure_index_exists(cursor, table_name: str, index_name: str, index_definition: str):
        cursor.execute(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = %s", (index_name,))
        exists = cursor.fetchone()
        if exists:
            return
        cursor.execute(f"ALTER TABLE `{table_name}` ADD INDEX {index_definition}")

    @staticmethod
    def _sanitize_log_params(params: Dict[str, Any]) -> Dict[str, Any]:
        safe = dict(params)
        if "crtfc_key" in safe:
            safe["crtfc_key"] = "***REDACTED***"
        return safe

    @staticmethod
    def _build_naver_page_url(base_url: str, page: int) -> str:
        normalized_page = max(int(page), 1)
        split = urlsplit(str(base_url or NAVER_KOSPI_MARKET_CAP_URL).strip() or NAVER_KOSPI_MARKET_CAP_URL)
        query_dict = parse_qs(split.query, keep_blank_values=True)
        query_dict["page"] = [str(normalized_page)]
        rebuilt_query = urlencode(query_dict, doseq=True)
        return urlunsplit((split.scheme, split.netloc, split.path, rebuilt_query, split.fragment))

    @staticmethod
    def _decode_naver_html(payload: bytes) -> str:
        for encoding in ("euc-kr", "cp949", "utf-8"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="ignore")

    def _fetch_json(self, url: str, params: Dict[str, Any]) -> Any:
        query = urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        request_url = f"{url}?{query}" if query else url

        safe_query = urlencode(self._sanitize_log_params(params), doseq=True)
        safe_url = f"{url}?{safe_query}" if safe_query else url
        logger.info("[KRCorporateCollector] requesting %s", safe_url)

        request = Request(request_url, headers={"User-Agent": "hobot-kr-corporate-collector/1.0"})
        with urlopen(request, timeout=40) as response:  # nosec B310
            payload = response.read().decode("utf-8")
        return json.loads(payload)

    def _fetch_corp_code_zip(self, *, api_key: str) -> bytes:
        params = {"crtfc_key": api_key}
        query = urlencode(params)
        request_url = f"{DART_CORPCODE_URL}?{query}"
        logger.info("[KRCorporateCollector] requesting %s?crtfc_key=***REDACTED***", DART_CORPCODE_URL)
        request = Request(request_url, headers={"User-Agent": "hobot-kr-corporate-collector/1.0"})
        with urlopen(request, timeout=60) as response:  # nosec B310
            return response.read()

    @staticmethod
    def parse_corp_code_zip(content: bytes) -> List[Dict[str, Any]]:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_members = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            if not xml_members:
                raise ValueError("No XML member found in DART corpCode zip")
            xml_payload = archive.read(xml_members[0])

        root = ET.fromstring(xml_payload)
        rows: List[Dict[str, Any]] = []
        for node in root.findall(".//list"):
            corp_code = _normalize_corp_code((node.findtext("corp_code") or "").strip())
            corp_name = (node.findtext("corp_name") or "").strip()
            if not corp_code or not corp_name:
                continue
            stock_code = _normalize_stock_code((node.findtext("stock_code") or "").strip())
            modify_date_text = (node.findtext("modify_date") or "").strip()
            modify_date: Optional[date] = None
            if len(modify_date_text) == 8 and modify_date_text.isdigit():
                try:
                    modify_date = datetime.strptime(modify_date_text, "%Y%m%d").date()
                except ValueError:
                    modify_date = None

            raw_payload = {
                "corp_code": corp_code,
                "corp_name": corp_name,
                "stock_code": stock_code,
                "modify_date": modify_date_text,
            }
            rows.append(
                {
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "stock_code": stock_code,
                    "modify_date": modify_date,
                    "metadata_json": json.dumps(raw_payload, ensure_ascii=False),
                }
            )
        return rows

    def ensure_tables(self):
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_dart_corp_codes (
                    corp_code CHAR(8) PRIMARY KEY,
                    corp_name VARCHAR(255) NOT NULL,
                    stock_code CHAR(6) NULL,
                    modify_date DATE NULL,
                    metadata_json JSON NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_stock_code (stock_code),
                    INDEX idx_corp_name (corp_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_corporate_financials (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    corp_code CHAR(8) NOT NULL,
                    stock_code CHAR(6) NULL,
                    corp_name VARCHAR(255) NULL,
                    bsns_year CHAR(4) NOT NULL,
                    reprt_code CHAR(5) NOT NULL,
                    account_nm VARCHAR(128) NOT NULL,
                    fs_div VARCHAR(8) NULL,
                    fs_nm VARCHAR(64) NULL,
                    sj_div VARCHAR(8) NULL,
                    sj_nm VARCHAR(64) NULL,
                    thstrm_amount BIGINT NULL,
                    thstrm_add_amount BIGINT NULL,
                    frmtrm_amount BIGINT NULL,
                    frmtrm_add_amount BIGINT NULL,
                    bfefrmtrm_amount BIGINT NULL,
                    currency VARCHAR(16) NULL,
                    rcept_no VARCHAR(20) NULL,
                    as_of_date DATE NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_financial_row (
                        corp_code, bsns_year, reprt_code, fs_div, sj_div, account_nm
                    ),
                    INDEX idx_stock_year (stock_code, bsns_year, reprt_code),
                    INDEX idx_year_report (bsns_year, reprt_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_corporate_disclosures (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    rcept_no VARCHAR(20) NOT NULL,
                    corp_code CHAR(8) NOT NULL,
                    stock_code CHAR(6) NULL,
                    corp_name VARCHAR(255) NULL,
                    corp_cls VARCHAR(8) NULL,
                    report_nm VARCHAR(255) NOT NULL,
                    flr_nm VARCHAR(255) NULL,
                    rcept_dt DATE NULL,
                    event_type VARCHAR(64) NOT NULL DEFAULT 'corporate_disclosure',
                    is_earnings_event TINYINT(1) NOT NULL DEFAULT 0,
                    period_year CHAR(4) NULL,
                    fiscal_quarter TINYINT NULL,
                    metric_actual_json JSON NULL,
                    metric_expected_json JSON NULL,
                    metric_surprise_json JSON NULL,
                    surprise_label VARCHAR(16) NULL,
                    source_url VARCHAR(255) NULL,
                    as_of_date DATE NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_rcept_no (rcept_no),
                    INDEX idx_corp_date (corp_code, rcept_dt),
                    INDEX idx_stock_date (stock_code, rcept_dt),
                    INDEX idx_event_date (event_type, rcept_dt),
                    INDEX idx_period (period_year, fiscal_quarter)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            # Existing environments may already have this table without earnings comparison columns.
            self._ensure_column_exists(
                cursor,
                "kr_corporate_disclosures",
                "period_year",
                "`period_year` CHAR(4) NULL AFTER `is_earnings_event`",
            )
            self._ensure_column_exists(
                cursor,
                "kr_corporate_disclosures",
                "fiscal_quarter",
                "`fiscal_quarter` TINYINT NULL AFTER `period_year`",
            )
            self._ensure_column_exists(
                cursor,
                "kr_corporate_disclosures",
                "metric_actual_json",
                "`metric_actual_json` JSON NULL AFTER `fiscal_quarter`",
            )
            self._ensure_column_exists(
                cursor,
                "kr_corporate_disclosures",
                "metric_expected_json",
                "`metric_expected_json` JSON NULL AFTER `metric_actual_json`",
            )
            self._ensure_column_exists(
                cursor,
                "kr_corporate_disclosures",
                "metric_surprise_json",
                "`metric_surprise_json` JSON NULL AFTER `metric_expected_json`",
            )
            self._ensure_column_exists(
                cursor,
                "kr_corporate_disclosures",
                "surprise_label",
                "`surprise_label` VARCHAR(16) NULL AFTER `metric_surprise_json`",
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_corporate_earnings_expectations (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    corp_code CHAR(8) NOT NULL,
                    stock_code CHAR(6) NULL,
                    period_year CHAR(4) NOT NULL,
                    fiscal_quarter TINYINT NOT NULL,
                    metric_key VARCHAR(32) NOT NULL,
                    expected_value BIGINT NULL,
                    expected_source VARCHAR(64) NOT NULL DEFAULT 'manual',
                    expected_as_of_date DATE NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_expectation (
                        corp_code, period_year, fiscal_quarter, metric_key, expected_source
                    ),
                    INDEX idx_expectation_lookup (
                        corp_code, period_year, fiscal_quarter, metric_key
                    ),
                    INDEX idx_expectation_stock (
                        stock_code, period_year, fiscal_quarter
                    )
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            self._ensure_index_exists(
                cursor,
                "kr_corporate_earnings_expectations",
                "idx_expectation_feed_lookup",
                (
                    "`idx_expectation_feed_lookup` "
                    "(`corp_code`, `expected_source`, `period_year`, "
                    "`fiscal_quarter`, `expected_as_of_date`, `updated_at`)"
                ),
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_top50_universe_snapshot (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    snapshot_date DATE NOT NULL,
                    market VARCHAR(16) NOT NULL DEFAULT 'KOSPI',
                    rank_position SMALLINT NOT NULL,
                    stock_code CHAR(6) NOT NULL,
                    stock_name VARCHAR(255) NULL,
                    corp_code CHAR(8) NULL,
                    source_url VARCHAR(255) NULL,
                    captured_at DATETIME NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_market_snapshot_rank (market, snapshot_date, rank_position),
                    UNIQUE KEY uniq_market_snapshot_stock (market, snapshot_date, stock_code),
                    INDEX idx_market_snapshot (market, snapshot_date),
                    INDEX idx_market_stock (market, stock_code),
                    INDEX idx_market_corp (market, corp_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_top50_daily_ohlcv (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    market VARCHAR(16) NOT NULL DEFAULT 'KOSPI',
                    stock_code CHAR(6) NOT NULL,
                    trade_date DATE NOT NULL,
                    open_price DOUBLE NULL,
                    high_price DOUBLE NULL,
                    low_price DOUBLE NULL,
                    close_price DOUBLE NULL,
                    adjusted_close DOUBLE NULL,
                    volume BIGINT NULL,
                    source VARCHAR(32) NOT NULL DEFAULT 'yfinance',
                    source_ref VARCHAR(128) NOT NULL DEFAULT '',
                    as_of_date DATE NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_kr_top50_daily_ohlcv (market, stock_code, trade_date),
                    INDEX idx_kr_top50_daily_ohlcv_date (market, trade_date),
                    INDEX idx_kr_top50_daily_ohlcv_stock (market, stock_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_corp_code_mapping_reports (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    report_date DATE NOT NULL,
                    market VARCHAR(16) NOT NULL DEFAULT 'KOSPI',
                    top_limit SMALLINT NOT NULL DEFAULT 50,
                    snapshot_date DATE NULL,
                    snapshot_row_count INT NOT NULL DEFAULT 0,
                    snapshot_with_corp_count INT NOT NULL DEFAULT 0,
                    snapshot_missing_corp_count INT NOT NULL DEFAULT 0,
                    snapshot_missing_in_dart_count INT NOT NULL DEFAULT 0,
                    snapshot_corp_code_mismatch_count INT NOT NULL DEFAULT 0,
                    dart_duplicate_stock_count INT NOT NULL DEFAULT 0,
                    status VARCHAR(16) NOT NULL DEFAULT 'healthy',
                    details_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_report_market_limit (report_date, market, top_limit),
                    INDEX idx_market_report_date (market, report_date),
                    INDEX idx_status_date (status, report_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_dart_dplus1_sla_reports (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    report_date DATE NOT NULL,
                    market VARCHAR(16) NOT NULL DEFAULT 'KOSPI',
                    top_limit SMALLINT NOT NULL DEFAULT 50,
                    lookback_days SMALLINT NOT NULL DEFAULT 30,
                    snapshot_date DATE NULL,
                    checked_event_count INT NOT NULL DEFAULT 0,
                    met_sla_count INT NOT NULL DEFAULT 0,
                    violated_sla_count INT NOT NULL DEFAULT 0,
                    missing_financial_count INT NOT NULL DEFAULT 0,
                    late_financial_count INT NOT NULL DEFAULT 0,
                    status VARCHAR(16) NOT NULL DEFAULT 'healthy',
                    details_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_report_market_limit_lookback (
                        report_date, market, top_limit, lookback_days
                    ),
                    INDEX idx_sla_market_report_date (market, report_date),
                    INDEX idx_sla_status_date (status, report_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

    def upsert_corp_codes(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()

        query = """
            INSERT INTO kr_dart_corp_codes (
                corp_code, corp_name, stock_code, modify_date, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                corp_name = VALUES(corp_name),
                stock_code = VALUES(stock_code),
                modify_date = VALUES(modify_date),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("corp_code"),
                row.get("corp_name"),
                row.get("stock_code"),
                row.get("modify_date"),
                row.get("metadata_json"),
            )
            for row in rows
        ]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def refresh_corp_code_cache(
        self,
        *,
        force: bool = False,
        max_age_days: int = DEFAULT_DART_CORPCODE_MAX_AGE_DAYS,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        cache_hit = False
        current_rows = 0
        last_updated_at: Optional[datetime] = None

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS row_count, MAX(updated_at) AS last_updated_at
                FROM kr_dart_corp_codes
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

        api_key = os.getenv("DART_API_KEY", "").strip()
        if not api_key:
            raise ValueError("DART_API_KEY is required")

        zip_payload = self._fetch_corp_code_zip(api_key=api_key)
        parsed_rows = self.parse_corp_code_zip(zip_payload)
        affected = self.upsert_corp_codes(parsed_rows)

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS row_count, MAX(updated_at) AS last_updated_at FROM kr_dart_corp_codes")
            stats = cursor.fetchone() or {}
            current_rows = int(stats.get("row_count") or 0)
            last_updated_at = stats.get("last_updated_at")

        return {
            "cache_hit": False,
            "current_rows": current_rows,
            "last_updated_at": last_updated_at.isoformat() if isinstance(last_updated_at, datetime) else None,
            "upserted_rows": int(affected),
        }

    def resolve_target_corp_codes(
        self,
        *,
        corp_codes: Optional[Iterable[str]] = None,
        stock_codes: Optional[Iterable[str]] = None,
        max_corp_count: Optional[int] = None,
    ) -> List[str]:
        explicit_corp_codes = []
        if corp_codes:
            for value in corp_codes:
                normalized = _normalize_corp_code(value)
                if normalized:
                    explicit_corp_codes.append(normalized)
        if explicit_corp_codes:
            return list(dict.fromkeys(explicit_corp_codes))

        normalized_stock_codes = []
        if stock_codes:
            for value in stock_codes:
                normalized = _normalize_stock_code(value)
                if normalized:
                    normalized_stock_codes.append(normalized)
        normalized_stock_codes = list(dict.fromkeys(normalized_stock_codes))

        self.ensure_tables()
        query = """
            SELECT corp_code
            FROM kr_dart_corp_codes
            WHERE stock_code IS NOT NULL
              AND stock_code <> ''
        """
        params: List[Any] = []
        if normalized_stock_codes:
            placeholders = ", ".join(["%s"] * len(normalized_stock_codes))
            query += f" AND stock_code IN ({placeholders})"
            params.extend(normalized_stock_codes)
        query += " ORDER BY stock_code ASC"
        if max_corp_count and max_corp_count > 0:
            query += " LIMIT %s"
            params.append(int(max_corp_count))

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [row["corp_code"] for row in rows if row.get("corp_code")]

    def fetch_multi_account_rows(
        self,
        *,
        corp_codes: Sequence[str],
        bsns_year: str,
        reprt_code: str,
    ) -> List[Dict[str, Any]]:
        if not corp_codes:
            return []
        api_key = os.getenv("DART_API_KEY", "").strip()
        if not api_key:
            raise ValueError("DART_API_KEY is required")

        params = {
            "crtfc_key": api_key,
            "corp_code": ",".join(corp_codes),
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
        }
        payload = self._fetch_json(DART_MULTI_ACCOUNT_URL, params)
        status = str(payload.get("status", ""))
        message = str(payload.get("message", ""))
        if status == "000":
            rows = payload.get("list") or []
            return rows if isinstance(rows, list) else []
        if status == "013":
            return []
        raise ValueError(f"DART multi-account failed(status={status}, message={message})")

    def normalize_financial_row(
        self,
        raw: Dict[str, Any],
        *,
        as_of_date: date,
    ) -> Optional[Dict[str, Any]]:
        corp_code = _normalize_corp_code(raw.get("corp_code"))
        if not corp_code:
            return None
        account_nm = str(raw.get("account_nm") or "").strip()
        bsns_year = str(raw.get("bsns_year") or "").strip()
        reprt_code = str(raw.get("reprt_code") or "").strip()
        if not account_nm or len(bsns_year) != 4 or len(reprt_code) != 5:
            return None

        normalized = {
            "corp_code": corp_code,
            "stock_code": _normalize_stock_code(raw.get("stock_code")),
            "corp_name": str(raw.get("corp_name") or "").strip() or None,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "account_nm": account_nm,
            "fs_div": str(raw.get("fs_div") or "").strip() or None,
            "fs_nm": str(raw.get("fs_nm") or "").strip() or None,
            "sj_div": str(raw.get("sj_div") or "").strip() or None,
            "sj_nm": str(raw.get("sj_nm") or "").strip() or None,
            "thstrm_amount": _safe_int(raw.get("thstrm_amount")),
            "thstrm_add_amount": _safe_int(raw.get("thstrm_add_amount")),
            "frmtrm_amount": _safe_int(raw.get("frmtrm_amount")),
            "frmtrm_add_amount": _safe_int(raw.get("frmtrm_add_amount")),
            "bfefrmtrm_amount": _safe_int(raw.get("bfefrmtrm_amount")),
            "currency": str(raw.get("currency") or "").strip() or None,
            "rcept_no": str(raw.get("rcept_no") or "").strip() or None,
            "as_of_date": as_of_date,
            "metadata_json": json.dumps(raw, ensure_ascii=False, default=str),
        }
        return normalized

    def save_financial_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()

        columns = [
            "corp_code",
            "stock_code",
            "corp_name",
            "bsns_year",
            "reprt_code",
            "account_nm",
            "fs_div",
            "fs_nm",
            "sj_div",
            "sj_nm",
            "thstrm_amount",
            "thstrm_add_amount",
            "frmtrm_amount",
            "frmtrm_add_amount",
            "bfefrmtrm_amount",
            "currency",
            "rcept_no",
            "as_of_date",
            "metadata_json",
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        update_columns = [col for col in columns if col not in {"corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div", "account_nm"}]
        updates = ", ".join([f"`{col}` = VALUES(`{col}`)" for col in update_columns])
        query = f"""
            INSERT INTO kr_corporate_financials ({", ".join([f"`{c}`" for c in columns])})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE
                {updates},
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [tuple(row.get(col) for col in columns) for row in rows]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    @staticmethod
    def classify_disclosure_event(report_nm: str) -> str:
        name = (report_nm or "").strip()
        if not name:
            return "corporate_disclosure"
        if _contains_earnings_keyword(name):
            return "earnings_announcement"
        if "기업설명회" in name or "IR" in name or "투자설명회" in name:
            return "ir_event"
        if "사업보고서" in name or "반기보고서" in name or "분기보고서" in name:
            return "periodic_report"
        return "corporate_disclosure"

    @staticmethod
    def infer_reporting_period(
        report_nm: str,
        rcept_dt: Optional[date] = None,
    ) -> Dict[str, Optional[int]]:
        """
        Infer period year/quarter from DART report name.
        Quarter mapping:
        - 1, 2, 3, 4 for quarterly/annual
        - None when unknown
        """
        name = (report_nm or "").strip()
        detected_year: Optional[int] = None
        year_match = re.search(r"(20\d{2})", name)
        if year_match:
            detected_year = _safe_int(year_match.group(1))
        elif rcept_dt is not None:
            detected_year = rcept_dt.year

        quarter: Optional[int] = None
        if "사업보고서" in name:
            quarter = 4
        elif "반기보고서" in name:
            quarter = 2
        elif "분기보고서" in name:
            if "1분기" in name:
                quarter = 1
            elif "3분기" in name:
                quarter = 3
            else:
                quarter = 1 if rcept_dt and rcept_dt.month <= 5 else 3
        elif _contains_earnings_keyword(name):
            if "1분기" in name:
                quarter = 1
            elif "2분기" in name:
                quarter = 2
            elif "3분기" in name:
                quarter = 3
            elif "4분기" in name or "연간" in name:
                quarter = 4
            elif rcept_dt is not None:
                # Fallback by filing month when quarter token is omitted.
                month = rcept_dt.month
                if month <= 3:
                    quarter = 4
                    detected_year = (detected_year or rcept_dt.year) - 1
                elif month <= 5:
                    quarter = 1
                elif month <= 8:
                    quarter = 2
                elif month <= 11:
                    quarter = 3
                else:
                    quarter = 4

        period_year = int(detected_year) if detected_year else None
        return {
            "period_year": period_year,
            "fiscal_quarter": quarter,
        }

    @staticmethod
    def quarter_to_reprt_code(fiscal_quarter: Optional[int]) -> Optional[str]:
        mapping = {
            1: "11013",  # 1Q report
            2: "11012",  # half-year report
            3: "11014",  # 3Q report
            4: "11011",  # annual report
        }
        return mapping.get(int(fiscal_quarter)) if fiscal_quarter else None

    @staticmethod
    def reprt_code_to_quarter(reprt_code: Optional[str]) -> Optional[int]:
        mapping = {
            "11013": 1,
            "11012": 2,
            "11014": 3,
            "11011": 4,
        }
        return mapping.get(str(reprt_code or "").strip())

    @staticmethod
    def normalize_metric_key(value: Any) -> Optional[str]:
        text = str(value or "").strip().lower()
        if not text:
            return None
        if text in EARNINGS_METRIC_ALIASES:
            return EARNINGS_METRIC_ALIASES[text]
        return None

    def normalize_expectation_row(
        self,
        raw: Dict[str, Any],
        *,
        default_source: str = "feed",
        default_as_of_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        corp_code = _normalize_corp_code(raw.get("corp_code"))
        stock_code = _normalize_stock_code(raw.get("stock_code"))
        period_year = str(
            raw.get("period_year")
            or raw.get("year")
            or raw.get("bsns_year")
            or ""
        ).strip()
        fiscal_quarter = _safe_int(raw.get("fiscal_quarter") or raw.get("quarter"))
        if fiscal_quarter is None:
            fiscal_quarter = self.reprt_code_to_quarter(raw.get("reprt_code"))
        metric_key = self.normalize_metric_key(
            raw.get("metric_key") or raw.get("metric") or raw.get("account_nm")
        )
        expected_value = _safe_int(
            raw.get("expected_value")
            or raw.get("consensus")
            or raw.get("value")
        )

        expected_source = str(raw.get("expected_source") or default_source or "feed").strip() or "feed"
        expected_as_of_date = raw.get("expected_as_of_date") or raw.get("as_of_date") or default_as_of_date
        if isinstance(expected_as_of_date, str):
            stripped = "".join(ch for ch in expected_as_of_date if ch.isdigit())
            if len(stripped) == 8:
                try:
                    expected_as_of_date = datetime.strptime(stripped, "%Y%m%d").date()
                except ValueError:
                    expected_as_of_date = default_as_of_date
            else:
                expected_as_of_date = default_as_of_date
        if not isinstance(expected_as_of_date, date):
            expected_as_of_date = default_as_of_date

        normalized_updated_at: Optional[datetime] = None
        raw_updated_at = raw.get("updated_at")
        if isinstance(raw_updated_at, datetime):
            normalized_updated_at = raw_updated_at
        elif isinstance(raw_updated_at, date):
            normalized_updated_at = datetime.combine(raw_updated_at, time.min)
        elif isinstance(raw_updated_at, str):
            updated_text = raw_updated_at.strip()
            if updated_text:
                try:
                    normalized_updated_at = datetime.fromisoformat(updated_text.replace("Z", "+00:00"))
                except ValueError:
                    normalized_updated_at = None

        if not corp_code:
            # Feed may provide stock_code only.
            if stock_code:
                with self._get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT corp_code
                        FROM kr_dart_corp_codes
                        WHERE stock_code = %s
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (stock_code,),
                    )
                    row = cursor.fetchone() or {}
                corp_code = _normalize_corp_code(row.get("corp_code"))

        if (
            not corp_code
            or len(period_year) != 4
            or not fiscal_quarter
            or metric_key not in EARNINGS_METRIC_ACCOUNT_MAP
            or expected_value is None
        ):
            return None

        return {
            "corp_code": corp_code,
            "stock_code": stock_code,
            "period_year": period_year,
            "fiscal_quarter": int(fiscal_quarter),
            "metric_key": metric_key,
            "expected_value": int(expected_value),
            "expected_source": expected_source,
            "expected_as_of_date": expected_as_of_date,
            "_updated_at": normalized_updated_at,
            "metadata": raw,
        }

    def fetch_expectation_rows_from_feed(
        self,
        *,
        url: str,
        expected_as_of_date: Optional[date] = None,
        target_corp_codes: Optional[Sequence[str]] = None,
        candidate_periods: Optional[Sequence[tuple[int, int]]] = None,
        top_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[Dict[str, Any]]:
        resolved_url = str(url or "").strip()
        if not resolved_url:
            return []
        if resolved_url in INTERNAL_EXPECTATION_FEED_URLS:
            return self.fetch_expectation_rows_from_internal_feed(
                target_corp_codes=target_corp_codes or [],
                candidate_periods=candidate_periods or [],
                expected_as_of_date=expected_as_of_date,
                top_corp_count=top_corp_count,
            )
        if resolved_url.startswith("file://"):
            file_path = resolved_url[len("file://") :]
            with open(file_path, "r", encoding="utf-8") as fp:
                payload = fp.read()
        elif resolved_url.startswith("/") or resolved_url.startswith("./") or resolved_url.startswith("../"):
            with open(resolved_url, "r", encoding="utf-8") as fp:
                payload = fp.read()
        else:
            request = Request(resolved_url, headers={"User-Agent": "hobot-kr-corporate-collector/1.0"})
            with urlopen(request, timeout=40) as response:  # nosec B310
                payload = response.read().decode("utf-8")
        decoded = json.loads(payload)

        if isinstance(decoded, list):
            rows = decoded
        elif isinstance(decoded, dict):
            rows = decoded.get("rows") or decoded.get("items") or decoded.get("data") or []
        else:
            rows = []
        if not isinstance(rows, list):
            return []

        normalized_rows: List[Dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            normalized = self.normalize_expectation_row(
                raw,
                default_source="feed",
                default_as_of_date=expected_as_of_date,
            )
            if normalized is None:
                continue
            normalized_rows.append(normalized)
        return normalized_rows

    def resolve_top_corp_codes_for_expectation_feed(
        self,
        *,
        top_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[str]:
        limit = max(int(top_corp_count or DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT), 1)
        latest_snapshot_rows = self.load_latest_top50_snapshot_rows(
            market=KR_TOP50_DEFAULT_MARKET,
            limit=limit,
        )
        if latest_snapshot_rows:
            codes = [
                _normalize_corp_code(row.get("corp_code"))
                for row in latest_snapshot_rows
            ]
            normalized_codes = [code for code in codes if code]
            if normalized_codes:
                return list(dict.fromkeys(normalized_codes))[:limit]

        # 최초 실행 시에만 스냅샷을 생성하고 이후에는 테이블 최신 스냅샷을 고정 사용한다.
        try:
            created = self.capture_top50_snapshot_from_naver(
                snapshot_date=date.today(),
                market=KR_TOP50_DEFAULT_MARKET,
                source_url=KR_TOP50_DEFAULT_SOURCE_URL,
                limit=limit,
            )
            if created.get("saved_rows", 0) > 0:
                latest_snapshot_rows = self.load_latest_top50_snapshot_rows(
                    market=KR_TOP50_DEFAULT_MARKET,
                    limit=limit,
                )
                codes = [
                    _normalize_corp_code(row.get("corp_code"))
                    for row in latest_snapshot_rows
                ]
                normalized_codes = [code for code in codes if code]
                if normalized_codes:
                    return list(dict.fromkeys(normalized_codes))[:limit]
        except Exception as exc:
            logger.warning("Failed to initialize top50 snapshot from Naver. fallback=financials err=%s", exc)

        revenue_accounts = list(EARNINGS_METRIC_ACCOUNT_MAP.get("revenue", ()))
        if not revenue_accounts:
            return []

        account_placeholders = ", ".join(["%s"] * len(revenue_accounts))
        query = f"""
            SELECT financials.corp_code, MAX(COALESCE(financials.thstrm_add_amount, financials.thstrm_amount)) AS revenue
            FROM kr_corporate_financials AS financials
            INNER JOIN (
                SELECT corp_code, MAX(bsns_year) AS latest_year
                FROM kr_corporate_financials
                WHERE reprt_code = '11011'
                GROUP BY corp_code
            ) AS latest
                ON latest.corp_code = financials.corp_code
               AND latest.latest_year = financials.bsns_year
            WHERE financials.reprt_code = '11011'
              AND financials.account_nm IN ({account_placeholders})
            GROUP BY financials.corp_code
            HAVING revenue IS NOT NULL
            ORDER BY revenue DESC
            LIMIT %s
        """
        params: List[Any] = list(revenue_accounts) + [limit]
        top_corp_codes: List[str] = []
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                for row in rows:
                    corp_code = _normalize_corp_code(row.get("corp_code"))
                    if corp_code:
                        top_corp_codes.append(corp_code)
            except Exception as exc:
                logger.warning(
                    "Failed to resolve revenue-ranked corp codes. fallback=stock_code err=%s",
                    exc,
                )

            # Financial rows can be sparse in 초기 단계, so fallback to listed corp order.
            if len(top_corp_codes) < limit:
                cursor.execute(
                    """
                    SELECT corp_code
                    FROM kr_dart_corp_codes
                    WHERE stock_code IS NOT NULL
                      AND stock_code <> ''
                    ORDER BY stock_code ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                fallback_rows = cursor.fetchall()
                for row in fallback_rows:
                    corp_code = _normalize_corp_code(row.get("corp_code"))
                    if corp_code:
                        top_corp_codes.append(corp_code)

        return list(dict.fromkeys(top_corp_codes))[:limit]

    @staticmethod
    def parse_naver_market_cap_stock_rows(
        html_text: str,
        *,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[Dict[str, Any]]:
        if not html_text:
            return []
        soup = BeautifulSoup(html_text, "html.parser")
        table = soup.find("table", class_=lambda x: x and "type_2" in x)
        if table is None:
            fallback_codes = re.findall(r"/item/main\.naver\?code=(\d{6})", html_text)
            rows: List[Dict[str, Any]] = []
            for code in fallback_codes:
                stock_code = _normalize_stock_code(code)
                if not stock_code:
                    continue
                if any(item.get("stock_code") == stock_code for item in rows):
                    continue
                rows.append(
                    {
                        "rank_position": len(rows) + 1,
                        "stock_code": stock_code,
                        "stock_name": None,
                    }
                )
                if len(rows) >= max(int(limit or DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT), 1):
                    break
            return rows

        rows: List[Dict[str, Any]] = []
        seen_codes = set()
        for anchor in table.find_all("a", class_=lambda x: x and "tltle" in x):
            href = str(anchor.get("href") or "")
            match = re.search(r"code=(\d{6})", href)
            if not match:
                continue
            stock_code = _normalize_stock_code(match.group(1))
            if not stock_code or stock_code in seen_codes:
                continue
            stock_name = str(anchor.get_text(strip=True) or "").strip() or None
            rows.append(
                {
                    "rank_position": len(rows) + 1,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                }
            )
            seen_codes.add(stock_code)
            if len(rows) >= max(int(limit or DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT), 1):
                break
        return rows

    @staticmethod
    def parse_naver_market_cap_stock_codes(
        html_text: str,
        *,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[str]:
        rows = KRCorporateCollector.parse_naver_market_cap_stock_rows(
            html_text,
            limit=limit,
        )
        return [row["stock_code"] for row in rows if row.get("stock_code")]

    def fetch_top_stock_rows_from_naver(
        self,
        *,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        url: str = NAVER_KOSPI_MARKET_CAP_URL,
    ) -> List[Dict[str, Any]]:
        resolved_limit = max(int(limit or DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT), 1)
        per_page_guess = 50
        max_pages = max((resolved_limit + per_page_guess - 1) // per_page_guess, 1)
        # Keep a small buffer to survive sparse/duplicate pages.
        max_pages = min(max_pages + 2, 20)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; hobot-kr-corporate-collector/1.0)",
            "Referer": "https://finance.naver.com/",
        }

        collected_rows: List[Dict[str, Any]] = []
        seen_stock_codes: set[str] = set()
        for page in range(1, max_pages + 1):
            page_url = self._build_naver_page_url(url, page)
            request = Request(page_url, headers=headers)
            with urlopen(request, timeout=25) as response:  # nosec B310
                payload = response.read()
            decoded_html = self._decode_naver_html(payload)
            page_rows = self.parse_naver_market_cap_stock_rows(decoded_html, limit=resolved_limit)
            if not page_rows:
                if page == 1:
                    break
                # Stop paging when further pages are empty.
                break

            added_in_page = 0
            for row in page_rows:
                stock_code = _normalize_stock_code(row.get("stock_code"))
                if not stock_code or stock_code in seen_stock_codes:
                    continue
                seen_stock_codes.add(stock_code)
                collected_rows.append(
                    {
                        "rank_position": len(collected_rows) + 1,
                        "stock_code": stock_code,
                        "stock_name": row.get("stock_name"),
                    }
                )
                added_in_page += 1
                if len(collected_rows) >= resolved_limit:
                    return collected_rows[:resolved_limit]

            if added_in_page == 0:
                # Defensive break for repeated duplicate pages.
                break

        return collected_rows[:resolved_limit]

    def fetch_top_stock_codes_from_naver(
        self,
        *,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        url: str = NAVER_KOSPI_MARKET_CAP_URL,
    ) -> List[str]:
        rows = self.fetch_top_stock_rows_from_naver(limit=limit, url=url)
        return [row["stock_code"] for row in rows if row.get("stock_code")]

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

    def load_latest_top50_snapshot_rows(
        self,
        *,
        market: str = KR_TOP50_DEFAULT_MARKET,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[Dict[str, Any]]:
        self.ensure_tables()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT snapshot_date
                FROM kr_top50_universe_snapshot
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
                SELECT snapshot_date, market, rank_position, stock_code, stock_name, corp_code, source_url, captured_at
                FROM kr_top50_universe_snapshot
                WHERE market = %s
                  AND snapshot_date = %s
                ORDER BY rank_position ASC
                LIMIT %s
                """,
                (resolved_market, snapshot_date, max(int(limit), 1)),
            )
            rows = cursor.fetchall()
        return list(rows or [])

    def load_recent_top50_snapshot_dates(
        self,
        *,
        market: str = KR_TOP50_DEFAULT_MARKET,
        limit: int = 2,
    ) -> List[date]:
        self.ensure_tables()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT snapshot_date
                FROM kr_top50_universe_snapshot
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
        market: str = KR_TOP50_DEFAULT_MARKET,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[Dict[str, Any]]:
        self.ensure_tables()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        resolved_date = self._coerce_snapshot_date(snapshot_date)
        if not resolved_date:
            return []
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT snapshot_date, market, rank_position, stock_code, stock_name, corp_code, source_url, captured_at
                FROM kr_top50_universe_snapshot
                WHERE market = %s
                  AND snapshot_date = %s
                ORDER BY rank_position ASC
                LIMIT %s
                """,
                (resolved_market, resolved_date, max(int(limit), 1)),
            )
            rows = cursor.fetchall() or []
        return list(rows)

    def load_top50_stock_codes_in_snapshot_window(
        self,
        *,
        market: str = KR_TOP50_DEFAULT_MARKET,
        start_date: date,
        end_date: Optional[date] = None,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[str]:
        self.ensure_tables()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        resolved_start_date = self._coerce_snapshot_date(start_date)
        resolved_end_date = self._coerce_snapshot_date(end_date or date.today())
        if not resolved_start_date or not resolved_end_date or resolved_start_date > resolved_end_date:
            return []

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT stock_code
                FROM kr_top50_universe_snapshot
                WHERE market = %s
                  AND snapshot_date BETWEEN %s AND %s
                  AND rank_position <= %s
                ORDER BY snapshot_date DESC, rank_position ASC
                """,
                (
                    resolved_market,
                    resolved_start_date,
                    resolved_end_date,
                    max(int(limit), 1),
                ),
            )
            rows = cursor.fetchall() or []

        normalized_stock_codes = [
            code
            for code in (_normalize_stock_code(row.get("stock_code")) for row in rows)
            if code
        ]
        return list(dict.fromkeys(normalized_stock_codes))

    def build_top50_snapshot_diff(
        self,
        *,
        market: str = KR_TOP50_DEFAULT_MARKET,
        latest_snapshot_date: Optional[date] = None,
        previous_snapshot_date: Optional[date] = None,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
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

        latest_rank_by_stock: Dict[str, int] = {}
        previous_rank_by_stock: Dict[str, int] = {}
        latest_name_by_stock: Dict[str, str] = {}
        previous_name_by_stock: Dict[str, str] = {}

        for row in latest_rows:
            stock_code = _normalize_stock_code(row.get("stock_code"))
            rank_position = _safe_int(row.get("rank_position"))
            if not stock_code or rank_position is None:
                continue
            latest_rank_by_stock[stock_code] = int(rank_position)
            latest_name_by_stock[stock_code] = str(row.get("stock_name") or "").strip()
        for row in previous_rows:
            stock_code = _normalize_stock_code(row.get("stock_code"))
            rank_position = _safe_int(row.get("rank_position"))
            if not stock_code or rank_position is None:
                continue
            previous_rank_by_stock[stock_code] = int(rank_position)
            previous_name_by_stock[stock_code] = str(row.get("stock_name") or "").strip()

        latest_stocks = set(latest_rank_by_stock.keys())
        previous_stocks = set(previous_rank_by_stock.keys())
        added = sorted(latest_stocks - previous_stocks)
        removed = sorted(previous_stocks - latest_stocks)
        common = sorted(latest_stocks & previous_stocks)

        rank_changes: List[Dict[str, Any]] = []
        for stock_code in common:
            latest_rank = latest_rank_by_stock.get(stock_code)
            previous_rank = previous_rank_by_stock.get(stock_code)
            if latest_rank is None or previous_rank is None or latest_rank == previous_rank:
                continue
            rank_changes.append(
                {
                    "stock_code": stock_code,
                    "stock_name": latest_name_by_stock.get(stock_code) or previous_name_by_stock.get(stock_code) or None,
                    "previous_rank": int(previous_rank),
                    "current_rank": int(latest_rank),
                    "delta": int(previous_rank - latest_rank),
                }
            )

        rank_changes.sort(
            key=lambda item: abs(int(item.get("delta") or 0)),
            reverse=True,
        )

        def _convert_stock_list(stock_codes: List[str], name_map: Dict[str, str]) -> List[Dict[str, Any]]:
            return [
                {
                    "stock_code": stock_code,
                    "stock_name": name_map.get(stock_code) or None,
                }
                for stock_code in stock_codes
            ]

        return {
            "market": resolved_market,
            "latest_snapshot_date": latest.isoformat() if latest else None,
            "previous_snapshot_date": previous.isoformat() if previous else None,
            "has_previous_snapshot": bool(previous),
            "latest_count": len(latest_rank_by_stock),
            "previous_count": len(previous_rank_by_stock),
            "added_count": len(added),
            "removed_count": len(removed),
            "rank_changed_count": len(rank_changes),
            "added_stocks": _convert_stock_list(added, latest_name_by_stock),
            "removed_stocks": _convert_stock_list(removed, previous_name_by_stock),
            "rank_changes": rank_changes,
        }

    def upsert_top50_snapshot_rows(
        self,
        *,
        rows: Sequence[Dict[str, Any]],
        snapshot_date: date,
        market: str = KR_TOP50_DEFAULT_MARKET,
        source_url: str = KR_TOP50_DEFAULT_SOURCE_URL,
        captured_at: Optional[datetime] = None,
    ) -> int:
        self.ensure_tables()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        resolved_captured_at = captured_at or datetime.now(timezone.utc).replace(tzinfo=None)

        normalized_rows: List[tuple] = []
        for row in rows:
            rank_position = _safe_int(row.get("rank_position"))
            stock_code = _normalize_stock_code(row.get("stock_code"))
            if rank_position is None or stock_code is None:
                continue
            stock_name = str(row.get("stock_name") or "").strip() or None
            corp_code = _normalize_corp_code(row.get("corp_code"))
            metadata = row.get("metadata") or {}
            normalized_rows.append(
                (
                    snapshot_date,
                    resolved_market,
                    int(rank_position),
                    stock_code,
                    stock_name,
                    corp_code,
                    source_url,
                    resolved_captured_at,
                    json.dumps(metadata, ensure_ascii=False, default=str),
                )
            )
        if not normalized_rows:
            return 0

        query = """
            INSERT INTO kr_top50_universe_snapshot (
                snapshot_date,
                market,
                rank_position,
                stock_code,
                stock_name,
                corp_code,
                source_url,
                captured_at,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                stock_name = VALUES(stock_name),
                corp_code = VALUES(corp_code),
                source_url = VALUES(source_url),
                captured_at = VALUES(captured_at),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, normalized_rows)
            return int(cursor.rowcount or 0)

    def capture_top50_snapshot_from_naver(
        self,
        *,
        snapshot_date: date,
        market: str = KR_TOP50_DEFAULT_MARKET,
        source_url: str = KR_TOP50_DEFAULT_SOURCE_URL,
        limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> Dict[str, Any]:
        crawled_rows = self.fetch_top_stock_rows_from_naver(limit=limit, url=source_url)
        stock_codes = [row["stock_code"] for row in crawled_rows if row.get("stock_code")]
        corp_code_by_stock: Dict[str, str] = {}
        if stock_codes:
            placeholders = ", ".join(["%s"] * len(stock_codes))
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT stock_code, corp_code
                    FROM kr_dart_corp_codes
                    WHERE stock_code IN ({placeholders})
                    """,
                    tuple(stock_codes),
                )
                mapping_rows = cursor.fetchall()
            for row in mapping_rows:
                stock_code = _normalize_stock_code(row.get("stock_code"))
                corp_code = _normalize_corp_code(row.get("corp_code"))
                if stock_code and corp_code:
                    corp_code_by_stock[stock_code] = corp_code

        snapshot_rows: List[Dict[str, Any]] = []
        for row in crawled_rows:
            stock_code = _normalize_stock_code(row.get("stock_code"))
            if not stock_code:
                continue
            snapshot_rows.append(
                {
                    "rank_position": row.get("rank_position"),
                    "stock_code": stock_code,
                    "stock_name": row.get("stock_name"),
                    "corp_code": corp_code_by_stock.get(stock_code),
                    "metadata": {
                        "source": "naver_market_cap",
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
            "market": str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET,
            "row_count": len(snapshot_rows),
            "saved_rows": int(affected),
        }

    @staticmethod
    def _resolve_kr_yfinance_suffix(market: str) -> str:
        normalized_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper()
        if normalized_market in {"KOSDAQ", "KQ"}:
            return ".KQ"
        return ".KS"

    def resolve_top50_stock_codes_for_ohlcv(
        self,
        *,
        stock_codes: Optional[Iterable[str]] = None,
        extra_stock_codes: Optional[Iterable[str]] = None,
        max_stock_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        market: str = KR_TOP50_DEFAULT_MARKET,
        source_url: str = KR_TOP50_DEFAULT_SOURCE_URL,
        continuity_days: int = DEFAULT_KR_TOP50_OHLCV_CONTINUITY_DAYS,
        reference_end_date: Optional[date] = None,
    ) -> List[str]:
        resolved_limit = max(int(max_stock_count), 1)
        normalized_extra_stock_codes = [
            code
            for code in (_normalize_stock_code(value) for value in (extra_stock_codes or []))
            if code
        ]
        normalized_extra_stock_codes = list(dict.fromkeys(normalized_extra_stock_codes))

        def _merge_with_extra(base_codes: Sequence[str]) -> List[str]:
            merged = list(dict.fromkeys([*base_codes, *normalized_extra_stock_codes]))
            return merged

        explicit_stock_codes = [
            code
            for code in (_normalize_stock_code(value) for value in (stock_codes or []))
            if code
        ]
        explicit_stock_codes = list(dict.fromkeys(explicit_stock_codes))
        if explicit_stock_codes:
            return _merge_with_extra(explicit_stock_codes[:resolved_limit])

        snapshot_rows = self.load_latest_top50_snapshot_rows(
            market=market,
            limit=resolved_limit,
        )
        snapshot_stock_codes = [
            code
            for code in (_normalize_stock_code(row.get("stock_code")) for row in snapshot_rows)
            if code
        ]
        snapshot_stock_codes = list(dict.fromkeys(snapshot_stock_codes))
        resolved_continuity_days = max(int(continuity_days), 0)
        if snapshot_stock_codes:
            if resolved_continuity_days <= 0:
                return _merge_with_extra(snapshot_stock_codes[:resolved_limit])

            continuity_end_date = self._coerce_snapshot_date(reference_end_date or date.today()) or date.today()
            continuity_start_date = continuity_end_date - timedelta(days=resolved_continuity_days - 1)
            continuity_stock_codes = self.load_top50_stock_codes_in_snapshot_window(
                market=market,
                start_date=continuity_start_date,
                end_date=continuity_end_date,
                limit=resolved_limit,
            )
            if continuity_stock_codes:
                merged_stock_codes = list(
                    dict.fromkeys([*snapshot_stock_codes, *continuity_stock_codes])
                )
                if merged_stock_codes:
                    return _merge_with_extra(merged_stock_codes)
            return _merge_with_extra(snapshot_stock_codes[:resolved_limit])

        if resolved_continuity_days > 0:
            continuity_end_date = self._coerce_snapshot_date(reference_end_date or date.today()) or date.today()
            continuity_start_date = continuity_end_date - timedelta(days=resolved_continuity_days - 1)
            continuity_stock_codes = self.load_top50_stock_codes_in_snapshot_window(
                market=market,
                start_date=continuity_start_date,
                end_date=continuity_end_date,
                limit=resolved_limit,
            )
            if continuity_stock_codes:
                return _merge_with_extra(continuity_stock_codes)

        try:
            crawled_stock_codes = self.fetch_top_stock_codes_from_naver(
                limit=resolved_limit,
                url=source_url,
            )
        except Exception as exc:
            logger.warning("Failed to fetch KR top stock codes for OHLCV fallback: %s", exc)
            return _merge_with_extra([])
        normalized_crawled = [
            code
            for code in (_normalize_stock_code(value) for value in crawled_stock_codes)
            if code
        ]
        return _merge_with_extra(list(dict.fromkeys(normalized_crawled))[:resolved_limit])

    def fetch_daily_ohlcv_rows_from_yfinance(
        self,
        *,
        stock_codes: Sequence[str],
        market: str = KR_TOP50_DEFAULT_MARKET,
        start_date: date,
        end_date: date,
        as_of_date: date,
    ) -> Dict[str, Any]:
        try:
            import yfinance as yf
        except Exception:
            logger.warning("yfinance is unavailable. KR Top50 daily OHLCV collection will be skipped.")
            return {
                "rows": [],
                "rows_by_stock_code": {},
                "failed_stock_codes": [
                    {"stock_code": "__all__", "reason": "yfinance_unavailable"}
                ],
            }

        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        normalized_stock_codes = [
            code
            for code in (_normalize_stock_code(value) for value in (stock_codes or []))
            if code
        ]
        normalized_stock_codes = list(dict.fromkeys(normalized_stock_codes))
        if not normalized_stock_codes:
            return {"rows": [], "rows_by_stock_code": {}, "failed_stock_codes": []}

        suffix = self._resolve_kr_yfinance_suffix(resolved_market)
        yf_symbol_to_stock = {
            f"{stock_code}{suffix}": stock_code
            for stock_code in normalized_stock_codes
        }
        yf_symbols = list(yf_symbol_to_stock.keys())
        request_end_date = end_date + timedelta(days=1)
        try:
            downloaded = yf.download(
                tickers=yf_symbols,
                start=start_date.isoformat(),
                end=request_end_date.isoformat(),
                interval="1d",
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as exc:
            logger.warning("yfinance KR OHLCV download failed(symbol_count=%s): %s", len(yf_symbols), exc)
            return {
                "rows": [],
                "rows_by_stock_code": {},
                "failed_stock_codes": [
                    {"stock_code": stock_code, "reason": f"download_failed:{exc}"}
                    for stock_code in normalized_stock_codes
                ],
            }

        rows: List[Dict[str, Any]] = []
        rows_by_stock_code: Dict[str, int] = {}
        failed_stock_codes: List[Dict[str, str]] = []
        single_symbol_mode = len(yf_symbols) == 1

        for yf_symbol in yf_symbols:
            stock_code = yf_symbol_to_stock.get(yf_symbol)
            if not stock_code:
                continue

            symbol_frame = None
            try:
                columns = getattr(downloaded, "columns", None)
                if hasattr(columns, "nlevels") and int(columns.nlevels) > 1:
                    level0_values = list(columns.get_level_values(0))
                    if yf_symbol in level0_values:
                        symbol_frame = downloaded[yf_symbol]
                    else:
                        try:
                            symbol_frame = downloaded.xs(yf_symbol, axis=1, level=-1)
                        except Exception:
                            symbol_frame = None
                elif single_symbol_mode:
                    symbol_frame = downloaded
            except Exception:
                symbol_frame = None

            if symbol_frame is None or getattr(symbol_frame, "empty", True):
                failed_stock_codes.append({"stock_code": stock_code, "reason": "no_ohlcv_rows"})
                continue

            stock_row_count = 0
            try:
                for index_value, value_row in symbol_frame.iterrows():
                    trade_date = index_value.date() if isinstance(index_value, datetime) else None
                    if trade_date is None and isinstance(index_value, date):
                        trade_date = index_value
                    if trade_date is None and hasattr(index_value, "to_pydatetime"):
                        try:
                            dt_value = index_value.to_pydatetime()
                            trade_date = dt_value.date() if isinstance(dt_value, datetime) else dt_value
                        except Exception:
                            trade_date = None
                    if not isinstance(trade_date, date):
                        continue
                    if trade_date < start_date or trade_date > end_date:
                        continue

                    open_price = _safe_float(value_row.get("Open"))
                    high_price = _safe_float(value_row.get("High"))
                    low_price = _safe_float(value_row.get("Low"))
                    close_price = _safe_float(value_row.get("Close"))
                    adjusted_close = _safe_float(value_row.get("Adj Close"))
                    if adjusted_close is None:
                        adjusted_close = close_price
                    volume_raw = _safe_int(value_row.get("Volume"))
                    volume = volume_raw if volume_raw is not None and volume_raw >= 0 else None
                    if (
                        open_price is None
                        and high_price is None
                        and low_price is None
                        and close_price is None
                        and adjusted_close is None
                        and volume is None
                    ):
                        continue

                    rows.append(
                        {
                            "market": resolved_market,
                            "stock_code": stock_code,
                            "trade_date": trade_date,
                            "open_price": open_price,
                            "high_price": high_price,
                            "low_price": low_price,
                            "close_price": close_price,
                            "adjusted_close": adjusted_close,
                            "volume": volume,
                            "source": "yfinance",
                            "source_ref": f"{stock_code}:{trade_date.isoformat()}",
                            "as_of_date": as_of_date,
                            "metadata_json": json.dumps(
                                {
                                    "yf_symbol": yf_symbol,
                                    "market": resolved_market,
                                },
                                ensure_ascii=False,
                                default=str,
                            ),
                        }
                    )
                    stock_row_count += 1
            except Exception as exc:
                failed_stock_codes.append({"stock_code": stock_code, "reason": f"parse_failed:{exc}"})
                continue

            if stock_row_count <= 0:
                failed_stock_codes.append({"stock_code": stock_code, "reason": "no_rows_in_window"})
                continue
            rows_by_stock_code[stock_code] = stock_row_count

        return {
            "rows": rows,
            "rows_by_stock_code": rows_by_stock_code,
            "failed_stock_codes": failed_stock_codes,
        }

    def upsert_top50_daily_ohlcv_rows(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO kr_top50_daily_ohlcv (
                market,
                stock_code,
                trade_date,
                open_price,
                high_price,
                low_price,
                close_price,
                adjusted_close,
                volume,
                source,
                source_ref,
                as_of_date,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                open_price = VALUES(open_price),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                close_price = VALUES(close_price),
                adjusted_close = VALUES(adjusted_close),
                volume = VALUES(volume),
                source = VALUES(source),
                source_ref = VALUES(source_ref),
                as_of_date = VALUES(as_of_date),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("market"),
                row.get("stock_code"),
                row.get("trade_date"),
                row.get("open_price"),
                row.get("high_price"),
                row.get("low_price"),
                row.get("close_price"),
                row.get("adjusted_close"),
                row.get("volume"),
                row.get("source") or "yfinance",
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

    def collect_top50_daily_ohlcv(
        self,
        *,
        stock_codes: Optional[Iterable[str]] = None,
        extra_stock_codes: Optional[Iterable[str]] = None,
        max_stock_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        market: str = KR_TOP50_DEFAULT_MARKET,
        source_url: str = KR_TOP50_DEFAULT_SOURCE_URL,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        lookback_days: int = DEFAULT_KR_TOP50_DAILY_OHLCV_LOOKBACK_DAYS,
        continuity_days: int = DEFAULT_KR_TOP50_OHLCV_CONTINUITY_DAYS,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        run_as_of = as_of_date or date.today()
        resolved_end_date = end_date or run_as_of
        explicit_stock_codes = [
            code
            for code in (_normalize_stock_code(value) for value in (stock_codes or []))
            if code
        ]
        explicit_stock_codes = list(dict.fromkeys(explicit_stock_codes))
        normalized_extra_stock_codes = [
            code
            for code in (_normalize_stock_code(value) for value in (extra_stock_codes or []))
            if code
        ]
        normalized_extra_stock_codes = list(dict.fromkeys(normalized_extra_stock_codes))
        resolved_continuity_days = max(int(continuity_days), 0)
        if start_date:
            resolved_start_date = start_date
        else:
            resolved_lookback = max(int(lookback_days), 1)
            resolved_start_date = resolved_end_date - timedelta(days=resolved_lookback - 1)
        if resolved_start_date > resolved_end_date:
            raise ValueError("start_date must be <= end_date")

        resolved_stock_codes = self.resolve_top50_stock_codes_for_ohlcv(
            stock_codes=explicit_stock_codes or None,
            extra_stock_codes=normalized_extra_stock_codes or None,
            max_stock_count=max_stock_count,
            market=market,
            source_url=source_url,
            continuity_days=resolved_continuity_days,
            reference_end_date=resolved_end_date,
        )
        if not resolved_stock_codes:
            raise ValueError("No target KR stock codes resolved for daily OHLCV collection.")

        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        latest_snapshot_stock_codes: List[str] = []
        if not explicit_stock_codes:
            latest_snapshot_rows = self.load_latest_top50_snapshot_rows(
                market=market,
                limit=max(int(max_stock_count), 1),
            )
            latest_snapshot_stock_codes = [
                code
                for code in (_normalize_stock_code(row.get("stock_code")) for row in latest_snapshot_rows)
                if code
            ]
            latest_snapshot_stock_codes = list(dict.fromkeys(latest_snapshot_stock_codes))
        latest_snapshot_set = set(latest_snapshot_stock_codes)
        continuity_extra_stock_codes = [
            stock_code for stock_code in resolved_stock_codes
            if latest_snapshot_set and stock_code not in latest_snapshot_set
        ]

        summary: Dict[str, Any] = {
            "market": resolved_market,
            "as_of_date": run_as_of.isoformat(),
            "start_date": resolved_start_date.isoformat(),
            "end_date": resolved_end_date.isoformat(),
            "lookback_days": max((resolved_end_date - resolved_start_date).days + 1, 1),
            "continuity_days": resolved_continuity_days,
            "continuity_enabled": bool(resolved_continuity_days > 0 and not explicit_stock_codes),
            "target_stock_count": len(resolved_stock_codes),
            "target_stock_codes": resolved_stock_codes,
            "extra_stock_code_count": len(normalized_extra_stock_codes),
            "extra_stock_codes": normalized_extra_stock_codes,
            "latest_snapshot_stock_count": len(latest_snapshot_stock_codes),
            "continuity_extra_stock_count": len(continuity_extra_stock_codes),
            "continuity_extra_stock_codes": continuity_extra_stock_codes,
            "rows_by_stock_code": {},
            "fetched_rows": 0,
            "upserted_rows": 0,
            "failed_stock_codes": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        fetch_result = self.fetch_daily_ohlcv_rows_from_yfinance(
            stock_codes=resolved_stock_codes,
            market=resolved_market,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            as_of_date=run_as_of,
        )
        rows = list(fetch_result.get("rows") or [])
        summary["rows_by_stock_code"] = dict(fetch_result.get("rows_by_stock_code") or {})
        summary["failed_stock_codes"] = list(fetch_result.get("failed_stock_codes") or [])
        summary["fetched_rows"] = len(rows)
        summary["upserted_rows"] = self.upsert_top50_daily_ohlcv_rows(rows)
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary

    def resolve_corp_codes_from_stock_codes(self, stock_codes: Sequence[str]) -> List[str]:
        normalized_stock_codes = [
            stock_code
            for stock_code in (_normalize_stock_code(code) for code in (stock_codes or []))
            if stock_code
        ]
        if not normalized_stock_codes:
            return []

        placeholders = ", ".join(["%s"] * len(normalized_stock_codes))
        query = f"""
            SELECT stock_code, corp_code
            FROM kr_dart_corp_codes
            WHERE stock_code IN ({placeholders})
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(normalized_stock_codes))
            rows = cursor.fetchall()

        corp_code_by_stock: Dict[str, str] = {}
        for row in rows:
            stock_code = _normalize_stock_code(row.get("stock_code"))
            corp_code = _normalize_corp_code(row.get("corp_code"))
            if not stock_code or not corp_code:
                continue
            corp_code_by_stock[stock_code] = corp_code

        corp_codes_in_order: List[str] = []
        for stock_code in normalized_stock_codes:
            corp_code = corp_code_by_stock.get(stock_code)
            if corp_code:
                corp_codes_in_order.append(corp_code)
        return list(dict.fromkeys(corp_codes_in_order))

    def resolve_stock_codes_from_corp_codes(self, corp_codes: Sequence[str]) -> List[str]:
        normalized_corp_codes = [
            corp_code
            for corp_code in (_normalize_corp_code(code) for code in (corp_codes or []))
            if corp_code
        ]
        if not normalized_corp_codes:
            return []

        placeholders = ", ".join(["%s"] * len(normalized_corp_codes))
        query = f"""
            SELECT corp_code, stock_code
            FROM kr_dart_corp_codes
            WHERE corp_code IN ({placeholders})
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(normalized_corp_codes))
            rows = cursor.fetchall()

        stock_code_by_corp: Dict[str, str] = {}
        for row in rows:
            corp_code = _normalize_corp_code(row.get("corp_code"))
            stock_code = _normalize_stock_code(row.get("stock_code"))
            if not corp_code or not stock_code:
                continue
            stock_code_by_corp[corp_code] = stock_code

        stock_codes_in_order: List[str] = []
        for corp_code in normalized_corp_codes:
            stock_code = stock_code_by_corp.get(corp_code)
            if stock_code:
                stock_codes_in_order.append(stock_code)
        return list(dict.fromkeys(stock_codes_in_order))

    def upsert_corp_code_mapping_report(self, report: Dict[str, Any]) -> int:
        self.ensure_tables()
        query = """
            INSERT INTO kr_corp_code_mapping_reports (
                report_date,
                market,
                top_limit,
                snapshot_date,
                snapshot_row_count,
                snapshot_with_corp_count,
                snapshot_missing_corp_count,
                snapshot_missing_in_dart_count,
                snapshot_corp_code_mismatch_count,
                dart_duplicate_stock_count,
                status,
                details_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                snapshot_date = VALUES(snapshot_date),
                snapshot_row_count = VALUES(snapshot_row_count),
                snapshot_with_corp_count = VALUES(snapshot_with_corp_count),
                snapshot_missing_corp_count = VALUES(snapshot_missing_corp_count),
                snapshot_missing_in_dart_count = VALUES(snapshot_missing_in_dart_count),
                snapshot_corp_code_mismatch_count = VALUES(snapshot_corp_code_mismatch_count),
                dart_duplicate_stock_count = VALUES(dart_duplicate_stock_count),
                status = VALUES(status),
                details_json = VALUES(details_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = (
            report.get("report_date"),
            report.get("market"),
            report.get("top_limit"),
            report.get("snapshot_date"),
            report.get("snapshot_row_count", 0),
            report.get("snapshot_with_corp_count", 0),
            report.get("snapshot_missing_corp_count", 0),
            report.get("snapshot_missing_in_dart_count", 0),
            report.get("snapshot_corp_code_mismatch_count", 0),
            report.get("dart_duplicate_stock_count", 0),
            report.get("status", "healthy"),
            report.get("details_json"),
        )
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, payload)
            return int(cursor.rowcount or 0)

    def upsert_dart_dplus1_sla_report(self, report: Dict[str, Any]) -> int:
        self.ensure_tables()
        query = """
            INSERT INTO kr_dart_dplus1_sla_reports (
                report_date,
                market,
                top_limit,
                lookback_days,
                snapshot_date,
                checked_event_count,
                met_sla_count,
                violated_sla_count,
                missing_financial_count,
                late_financial_count,
                status,
                details_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                snapshot_date = VALUES(snapshot_date),
                checked_event_count = VALUES(checked_event_count),
                met_sla_count = VALUES(met_sla_count),
                violated_sla_count = VALUES(violated_sla_count),
                missing_financial_count = VALUES(missing_financial_count),
                late_financial_count = VALUES(late_financial_count),
                status = VALUES(status),
                details_json = VALUES(details_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = (
            report.get("report_date"),
            report.get("market"),
            report.get("top_limit"),
            report.get("lookback_days"),
            report.get("snapshot_date"),
            report.get("checked_event_count", 0),
            report.get("met_sla_count", 0),
            report.get("violated_sla_count", 0),
            report.get("missing_financial_count", 0),
            report.get("late_financial_count", 0),
            report.get("status", "healthy"),
            report.get("details_json"),
        )
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, payload)
            return int(cursor.rowcount or 0)

    def validate_dart_disclosure_dplus1_sla(
        self,
        *,
        report_date: Optional[date] = None,
        market: str = KR_TOP50_DEFAULT_MARKET,
        top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        lookback_days: int = 30,
        hydrate_disclosures_if_empty: bool = True,
        hydrate_per_corp_max_pages: int = 2,
        hydrate_page_count: int = DEFAULT_DART_DISCLOSURE_PAGE_COUNT,
        persist: bool = True,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        resolved_report_date = report_date or date.today()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        resolved_top_limit = max(int(top_limit), 1)
        resolved_lookback_days = max(int(lookback_days), 1)
        resolved_hydrate_pages = max(int(hydrate_per_corp_max_pages), 1)
        resolved_hydrate_page_count = max(min(int(hydrate_page_count), 100), 1)
        start_date = resolved_report_date - timedelta(days=resolved_lookback_days - 1)

        snapshot_rows = self.load_latest_top50_snapshot_rows(
            market=resolved_market,
            limit=resolved_top_limit,
        )
        snapshot_date = (
            self._coerce_snapshot_date(snapshot_rows[0].get("snapshot_date"))
            if snapshot_rows
            else None
        )
        target_corp_codes = [
            _normalize_corp_code(row.get("corp_code"))
            for row in snapshot_rows
            if _normalize_corp_code(row.get("corp_code"))
        ]
        target_corp_codes = list(dict.fromkeys(target_corp_codes))

        def _load_disclosures_map() -> Dict[tuple[str, str, int], Dict[str, Any]]:
            disclosures_map: Dict[tuple[str, str, int], Dict[str, Any]] = {}
            if not target_corp_codes:
                return disclosures_map

            placeholders = ", ".join(["%s"] * len(target_corp_codes))
            query = f"""
                SELECT corp_code, rcept_no, rcept_dt, period_year, fiscal_quarter, report_nm, event_type, is_earnings_event
                FROM kr_corporate_disclosures
                WHERE corp_code IN ({placeholders})
                  AND rcept_dt BETWEEN %s AND %s
                  AND period_year IS NOT NULL
                  AND fiscal_quarter IS NOT NULL
                ORDER BY rcept_dt ASC, rcept_no ASC
            """
            params: List[Any] = list(target_corp_codes) + [start_date, resolved_report_date]
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall() or []

            for row in rows:
                corp_code = _normalize_corp_code(row.get("corp_code"))
                period_year = str(row.get("period_year") or "").strip()
                fiscal_quarter = _safe_int(row.get("fiscal_quarter"))
                report_nm = str(row.get("report_nm") or "").strip()
                event_type = str(row.get("event_type") or "").strip().lower()
                is_earnings_event = int(row.get("is_earnings_event") or 0)
                rcept_dt = row.get("rcept_dt")
                if not corp_code or len(period_year) != 4 or fiscal_quarter not in (1, 2, 3, 4):
                    continue
                if not isinstance(rcept_dt, date):
                    continue

                is_periodic = ("분기보고서" in report_nm) or ("반기보고서" in report_nm) or ("사업보고서" in report_nm)
                if not (
                    is_earnings_event == 1
                    or event_type in {"earnings_announcement", "periodic_report"}
                    or is_periodic
                ):
                    continue

                key = (corp_code, period_year, fiscal_quarter)
                # 동일 분기 이벤트가 여러건이면 가장 이른 공시 시점을 SLA 기준으로 사용
                if key not in disclosures_map:
                    disclosures_map[key] = {
                        "corp_code": corp_code,
                        "period_year": period_year,
                        "fiscal_quarter": fiscal_quarter,
                        "rcept_dt": rcept_dt,
                        "rcept_no": str(row.get("rcept_no") or "").strip() or None,
                    }
            return disclosures_map

        disclosures = _load_disclosures_map()
        hydrate_summary: Optional[Dict[str, Any]] = None
        hydrate_attempted = False
        if not disclosures and bool(hydrate_disclosures_if_empty) and target_corp_codes:
            hydrate_attempted = True
            try:
                hydrate_summary = self.collect_disclosure_events(
                    start_date=start_date,
                    end_date=resolved_report_date,
                    corp_codes=target_corp_codes,
                    max_corp_count=len(target_corp_codes),
                    refresh_corp_codes=False,
                    page_count=resolved_hydrate_page_count,
                    per_corp_max_pages=resolved_hydrate_pages,
                    only_earnings=False,
                    auto_expectations=False,
                    as_of_date=resolved_report_date,
                )
            except Exception as exc:
                hydrate_summary = {
                    "status": "failed",
                    "error": str(exc),
                }
            disclosures = _load_disclosures_map()

        earliest_financial_at: Dict[tuple[str, str, int], datetime] = {}
        if disclosures:
            corp_codes = sorted({key[0] for key in disclosures.keys()})
            period_years = sorted({key[1] for key in disclosures.keys()})
            corp_placeholders = ", ".join(["%s"] * len(corp_codes))
            year_placeholders = ", ".join(["%s"] * len(period_years))
            query = f"""
                SELECT corp_code, bsns_year, reprt_code, MIN(updated_at) AS first_financial_at
                FROM kr_corporate_financials
                WHERE corp_code IN ({corp_placeholders})
                  AND bsns_year IN ({year_placeholders})
                GROUP BY corp_code, bsns_year, reprt_code
            """
            params = list(corp_codes) + list(period_years)
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall() or []
            for row in rows:
                corp_code = _normalize_corp_code(row.get("corp_code"))
                period_year = str(row.get("bsns_year") or "").strip()
                fiscal_quarter = self.reprt_code_to_quarter(row.get("reprt_code"))
                first_financial_at = row.get("first_financial_at")
                if not corp_code or len(period_year) != 4 or fiscal_quarter not in (1, 2, 3, 4):
                    continue
                if not isinstance(first_financial_at, datetime):
                    continue
                key = (corp_code, period_year, fiscal_quarter)
                previous = earliest_financial_at.get(key)
                if previous is None or first_financial_at < previous:
                    earliest_financial_at[key] = first_financial_at

        met_count = 0
        missing_count = 0
        late_count = 0
        violation_samples: List[Dict[str, Any]] = []
        for key, disclosure in disclosures.items():
            rcept_dt = disclosure.get("rcept_dt")
            if not isinstance(rcept_dt, date):
                continue
            deadline_at = datetime.combine(rcept_dt + timedelta(days=1), time.max)
            first_financial_at = earliest_financial_at.get(key)
            if first_financial_at is None:
                missing_count += 1
                if len(violation_samples) < 50:
                    violation_samples.append(
                        {
                            **disclosure,
                            "violation_type": "missing_financial",
                            "deadline_at": deadline_at.isoformat(),
                            "first_financial_at": None,
                        }
                    )
                continue
            if first_financial_at <= deadline_at:
                met_count += 1
                continue
            late_count += 1
            if len(violation_samples) < 50:
                violation_samples.append(
                    {
                        **disclosure,
                        "violation_type": "late_financial",
                        "deadline_at": deadline_at.isoformat(),
                        "first_financial_at": first_financial_at.isoformat(),
                    }
                )

        checked_event_count = len(disclosures)
        violated_count = missing_count + late_count
        if checked_event_count == 0:
            status = "no_events" if snapshot_rows else "no_snapshot"
        else:
            status = "healthy" if violated_count == 0 else "warning"

        result = {
            "report_date": resolved_report_date,
            "market": resolved_market,
            "top_limit": resolved_top_limit,
            "lookback_days": resolved_lookback_days,
            "snapshot_date": snapshot_date,
            "checked_event_count": checked_event_count,
            "met_sla_count": met_count,
            "violated_sla_count": violated_count,
            "missing_financial_count": missing_count,
            "late_financial_count": late_count,
            "status": status,
            "details": {
                "start_date": start_date.isoformat(),
                "end_date": resolved_report_date.isoformat(),
                "target_corp_count": len(target_corp_codes),
                "hydrate_attempted": hydrate_attempted,
                "hydrate_summary": hydrate_summary,
                "violation_samples": violation_samples,
            },
        }
        result["details_json"] = json.dumps(result["details"], ensure_ascii=False, default=str)
        if persist:
            affected = self.upsert_dart_dplus1_sla_report(result)
            result["db_affected"] = int(affected)
        return result

    def validate_top50_corp_code_mapping(
        self,
        *,
        report_date: Optional[date] = None,
        market: str = KR_TOP50_DEFAULT_MARKET,
        top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        persist: bool = True,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        resolved_report_date = report_date or date.today()
        resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
        resolved_top_limit = max(int(top_limit), 1)

        snapshot_rows = self.load_latest_top50_snapshot_rows(
            market=resolved_market,
            limit=resolved_top_limit,
        )
        snapshot_date = (
            self._coerce_snapshot_date(snapshot_rows[0].get("snapshot_date"))
            if snapshot_rows
            else None
        )

        snapshot_stock_to_corp: Dict[str, Optional[str]] = {}
        snapshot_missing_corp_stocks: List[str] = []
        for row in snapshot_rows:
            stock_code = _normalize_stock_code(row.get("stock_code"))
            if not stock_code:
                continue
            corp_code = _normalize_corp_code(row.get("corp_code"))
            snapshot_stock_to_corp[stock_code] = corp_code
            if not corp_code:
                snapshot_missing_corp_stocks.append(stock_code)

        snapshot_stock_codes = list(snapshot_stock_to_corp.keys())
        dart_stock_to_corp: Dict[str, str] = {}
        dart_duplicate_stock_codes: List[str] = []
        if snapshot_stock_codes:
            placeholders = ", ".join(["%s"] * len(snapshot_stock_codes))
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT stock_code, corp_code
                    FROM kr_dart_corp_codes
                    WHERE stock_code IN ({placeholders})
                    ORDER BY stock_code ASC, corp_code ASC
                    """,
                    tuple(snapshot_stock_codes),
                )
                rows = cursor.fetchall() or []
                for row in rows:
                    stock_code = _normalize_stock_code(row.get("stock_code"))
                    corp_code = _normalize_corp_code(row.get("corp_code"))
                    if not stock_code or not corp_code:
                        continue
                    if stock_code in dart_stock_to_corp and dart_stock_to_corp[stock_code] != corp_code:
                        dart_duplicate_stock_codes.append(stock_code)
                        continue
                    dart_stock_to_corp[stock_code] = corp_code

                cursor.execute(
                    f"""
                    SELECT stock_code, COUNT(DISTINCT corp_code) AS corp_count
                    FROM kr_dart_corp_codes
                    WHERE stock_code IN ({placeholders})
                    GROUP BY stock_code
                    HAVING COUNT(DISTINCT corp_code) > 1
                    """,
                    tuple(snapshot_stock_codes),
                )
                dup_rows = cursor.fetchall() or []
                for row in dup_rows:
                    stock_code = _normalize_stock_code(row.get("stock_code"))
                    if stock_code:
                        dart_duplicate_stock_codes.append(stock_code)
        dart_duplicate_stock_codes = sorted(set(dart_duplicate_stock_codes))

        snapshot_missing_in_dart: List[str] = []
        snapshot_corp_code_mismatches: List[Dict[str, str]] = []
        for stock_code, snapshot_corp in snapshot_stock_to_corp.items():
            dart_corp = dart_stock_to_corp.get(stock_code)
            if not dart_corp:
                snapshot_missing_in_dart.append(stock_code)
                continue
            if snapshot_corp and snapshot_corp != dart_corp:
                snapshot_corp_code_mismatches.append(
                    {
                        "stock_code": stock_code,
                        "snapshot_corp_code": snapshot_corp,
                        "dart_corp_code": dart_corp,
                    }
                )

        issue_count = (
            len(snapshot_missing_corp_stocks)
            + len(snapshot_missing_in_dart)
            + len(snapshot_corp_code_mismatches)
            + len(dart_duplicate_stock_codes)
        )
        status = "healthy" if issue_count == 0 else "warning"
        if not snapshot_rows:
            status = "no_snapshot"

        result = {
            "report_date": resolved_report_date,
            "market": resolved_market,
            "top_limit": resolved_top_limit,
            "snapshot_date": snapshot_date,
            "snapshot_row_count": len(snapshot_stock_to_corp),
            "snapshot_with_corp_count": len(
                [code for code in snapshot_stock_to_corp.values() if code]
            ),
            "snapshot_missing_corp_count": len(snapshot_missing_corp_stocks),
            "snapshot_missing_in_dart_count": len(snapshot_missing_in_dart),
            "snapshot_corp_code_mismatch_count": len(snapshot_corp_code_mismatches),
            "dart_duplicate_stock_count": len(dart_duplicate_stock_codes),
            "status": status,
            "details": {
                "snapshot_missing_corp_stocks": snapshot_missing_corp_stocks[:50],
                "snapshot_missing_in_dart_stocks": snapshot_missing_in_dart[:50],
                "snapshot_corp_code_mismatches": snapshot_corp_code_mismatches[:50],
                "dart_duplicate_stock_codes": dart_duplicate_stock_codes[:50],
            },
        }
        result["details_json"] = json.dumps(result["details"], ensure_ascii=False, default=str)
        if persist:
            affected = self.upsert_corp_code_mapping_report(result)
            result["db_affected"] = int(affected)
        return result

    @staticmethod
    def month_to_fiscal_quarter(month: int) -> Optional[int]:
        if month < 1 or month > 12:
            return None
        return ((month - 1) // 3) + 1

    @staticmethod
    def parse_naver_quarterly_consensus_rows(
        html_text: str,
        *,
        stock_code: str,
        corp_code: Optional[str] = None,
        expected_as_of_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        if not html_text:
            return []
        soup = BeautifulSoup(html_text, "html.parser")
        table = soup.find("table", class_=lambda x: x and "tb_type1_ifrs" in x)
        if table is None:
            return []

        thead = table.find("thead")
        tbody = table.find("tbody")
        if thead is None or tbody is None:
            return []

        header_rows = thead.find_all("tr")
        if len(header_rows) < 2:
            return []
        period_headers_raw = header_rows[1].find_all("th")
        period_headers: List[Dict[str, Any]] = []
        for th in period_headers_raw:
            label = "".join(th.stripped_strings).replace(" ", "")
            match = re.search(r"(\d{4})\.(\d{2})", label)
            if not match:
                continue
            year = int(match.group(1))
            month = int(match.group(2))
            quarter = KRCorporateCollector.month_to_fiscal_quarter(month)
            if quarter is None:
                continue
            is_estimate = "(E)" in label or "E" in label
            period_headers.append(
                {
                    "period_year": str(year),
                    "fiscal_quarter": quarter,
                    "is_estimate": is_estimate,
                }
            )
        if len(period_headers) < 6:
            return []
        quarterly_headers = period_headers[-6:]
        estimate_indexes = [idx for idx, item in enumerate(quarterly_headers) if bool(item.get("is_estimate"))]
        if not estimate_indexes:
            estimate_indexes = [len(quarterly_headers) - 1]

        metric_name_map = {
            "매출액": "revenue",
            "영업이익": "operating_income",
            "당기순이익": "net_income",
        }
        rows: List[Dict[str, Any]] = []
        for tr in tbody.find_all("tr"):
            header = tr.find("th")
            if header is None:
                continue
            metric_name = "".join(header.stripped_strings)
            metric_key = metric_name_map.get(metric_name)
            if not metric_key:
                continue

            cells = tr.find_all("td")
            if len(cells) < 6:
                continue
            quarterly_cells = cells[-6:]
            for idx in estimate_indexes:
                if idx >= len(quarterly_cells):
                    continue
                raw_value = "".join(quarterly_cells[idx].stripped_strings)
                normalized_value = _safe_int(raw_value)
                if normalized_value is None:
                    continue
                header_info = quarterly_headers[idx]
                rows.append(
                    {
                        "corp_code": corp_code,
                        "stock_code": stock_code,
                        "period_year": header_info["period_year"],
                        "fiscal_quarter": header_info["fiscal_quarter"],
                        "metric_key": metric_key,
                        "expected_value": int(normalized_value) * NAVER_FINANCIAL_VALUE_UNIT_MULTIPLIER,
                        "expected_source": "consensus_feed",
                        "expected_as_of_date": expected_as_of_date,
                        "metadata": {
                            "provider": "naver_finance",
                            "source": "item_main_ifrs_table",
                            "raw_value_uk": int(normalized_value),
                            "unit": "KRW",
                        },
                    }
                )
        return rows

    def fetch_expectation_rows_from_naver_stock_codes(
        self,
        *,
        stock_codes: Sequence[str],
        expected_as_of_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        normalized_stock_codes = [
            stock_code
            for stock_code in (_normalize_stock_code(code) for code in (stock_codes or []))
            if stock_code
        ]
        if not normalized_stock_codes:
            return []

        corp_codes = self.resolve_corp_codes_from_stock_codes(normalized_stock_codes)
        stock_codes_in_order = self.resolve_stock_codes_from_corp_codes(corp_codes)
        corp_code_by_stock = {stock: corp for stock, corp in zip(stock_codes_in_order, corp_codes)}

        expectation_rows: List[Dict[str, Any]] = []
        for stock_code in normalized_stock_codes:
            item_url = NAVER_ITEM_MAIN_URL_TEMPLATE.format(stock_code=stock_code)
            try:
                request = Request(
                    item_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; hobot-kr-corporate-collector/1.0)",
                        "Referer": "https://finance.naver.com/",
                    },
                )
                with urlopen(request, timeout=25) as response:  # nosec B310
                    payload = response.read()
                html_text: Optional[str] = None
                for encoding in ("utf-8", "euc-kr", "cp949"):
                    try:
                        html_text = payload.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                if not html_text:
                    html_text = payload.decode("utf-8", errors="ignore")
                parsed_rows = self.parse_naver_quarterly_consensus_rows(
                    html_text,
                    stock_code=stock_code,
                    corp_code=corp_code_by_stock.get(stock_code),
                    expected_as_of_date=expected_as_of_date,
                )
                expectation_rows.extend(parsed_rows)
            except Exception as exc:
                logger.warning(
                    "Failed to crawl Naver consensus for stock_code=%s err=%s",
                    stock_code,
                    exc,
                )
        return expectation_rows

    def fetch_expectation_rows_from_internal_feed(
        self,
        *,
        target_corp_codes: Sequence[str],
        candidate_periods: Sequence[tuple[int, int]],
        expected_as_of_date: Optional[date] = None,
        top_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[Dict[str, Any]]:
        normalized_target_codes = [
            corp_code
            for corp_code in (_normalize_corp_code(code) for code in (target_corp_codes or []))
            if corp_code
        ]
        top_corp_codes = self.resolve_top_corp_codes_for_expectation_feed(
            top_corp_count=top_corp_count,
        )
        feed_target_corp_codes = list(dict.fromkeys(top_corp_codes + normalized_target_codes))
        if not feed_target_corp_codes:
            return []

        valid_periods = {
            (int(year), int(quarter))
            for year, quarter in (candidate_periods or [])
            if int(quarter) in (1, 2, 3, 4)
        }
        period_years = sorted({str(year) for year, _ in valid_periods})
        period_quarters = sorted({int(quarter) for _, quarter in valid_periods})

        corp_placeholders = ", ".join(["%s"] * len(feed_target_corp_codes))
        query = f"""
            SELECT
                corp_code,
                stock_code,
                period_year,
                fiscal_quarter,
                metric_key,
                expected_value,
                expected_source,
                expected_as_of_date,
                updated_at
            FROM kr_corporate_earnings_expectations
            WHERE corp_code IN ({corp_placeholders})
              AND expected_source IN ('feed', 'consensus_feed', 'manual')
        """
        params: List[Any] = list(feed_target_corp_codes)

        if period_years:
            year_placeholders = ", ".join(["%s"] * len(period_years))
            query += f" AND period_year IN ({year_placeholders})"
            params.extend(period_years)
        if period_quarters:
            quarter_placeholders = ", ".join(["%s"] * len(period_quarters))
            query += f" AND fiscal_quarter IN ({quarter_placeholders})"
            params.extend(period_quarters)
        if expected_as_of_date:
            query += " AND (expected_as_of_date IS NULL OR expected_as_of_date <= %s)"
            params.append(expected_as_of_date)

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

        naver_feed_rows = self.fetch_expectation_rows_from_naver_stock_codes(
            stock_codes=self.resolve_stock_codes_from_corp_codes(feed_target_corp_codes),
            expected_as_of_date=expected_as_of_date,
        )

        normalized_by_key: Dict[tuple, Dict[str, Any]] = {}
        rank_by_key: Dict[tuple, tuple[date, datetime]] = {}
        min_date = date(1900, 1, 1)
        min_datetime = datetime(1900, 1, 1)
        for row in list(naver_feed_rows) + list(rows):
            normalized = self.normalize_expectation_row(
                row if isinstance(row, dict) else {},
                default_source="feed",
                default_as_of_date=expected_as_of_date,
            )
            if normalized is None:
                continue
            if valid_periods and (
                int(normalized["period_year"]),
                int(normalized["fiscal_quarter"]),
            ) not in valid_periods:
                continue
            dedup_key = (
                normalized["corp_code"],
                normalized["period_year"],
                normalized["fiscal_quarter"],
                normalized["metric_key"],
                normalized["expected_source"],
            )
            rank_value = (
                normalized.get("expected_as_of_date") or min_date,
                normalized.get("_updated_at") or min_datetime,
            )
            previous_rank = rank_by_key.get(dedup_key)
            if previous_rank is None or rank_value > previous_rank:
                rank_by_key[dedup_key] = rank_value
                normalized_by_key[dedup_key] = normalized

        # 안정적인 결과 순서를 유지합니다.
        ordered_keys = sorted(
            normalized_by_key.keys(),
            key=lambda key: (key[0], key[1], int(key[2]), key[3], key[4]),
        )
        return [normalized_by_key[key] for key in ordered_keys]

    @staticmethod
    def build_expectation_candidate_periods(
        *,
        start_date: date,
        end_date: date,
    ) -> List[tuple[int, int]]:
        if start_date > end_date:
            return []
        periods = set()
        for year in range(start_date.year - 1, end_date.year + 1):
            for quarter in (1, 2, 3, 4):
                periods.add((year, quarter))
        return sorted(periods)

    def build_baseline_expectation_rows(
        self,
        *,
        corp_codes: Sequence[str],
        candidate_periods: Sequence[tuple[int, int]],
        lookback_years: int = DEFAULT_EARNINGS_EXPECTATION_LOOKBACK_YEARS,
        expected_as_of_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        if not corp_codes or not candidate_periods:
            return []

        cleaned_corp_codes = [_normalize_corp_code(code) for code in corp_codes]
        target_corp_codes = [code for code in cleaned_corp_codes if code]
        if not target_corp_codes:
            return []

        valid_periods = [
            (int(year), int(quarter))
            for year, quarter in candidate_periods
            if int(quarter) in (1, 2, 3, 4)
        ]
        if not valid_periods:
            return []

        min_year = min(year for year, _ in valid_periods) - max(int(lookback_years), 1)
        max_year = max(year for year, _ in valid_periods) - 1
        if min_year > max_year:
            return []

        reprt_codes = sorted({self.quarter_to_reprt_code(quarter) for _, quarter in valid_periods if self.quarter_to_reprt_code(quarter)})
        if not reprt_codes:
            return []

        account_names: List[str] = []
        for names in EARNINGS_METRIC_ACCOUNT_MAP.values():
            account_names.extend(list(names))

        corp_placeholders = ", ".join(["%s"] * len(target_corp_codes))
        reprt_placeholders = ", ".join(["%s"] * len(reprt_codes))
        account_placeholders = ", ".join(["%s"] * len(account_names))
        query = f"""
            SELECT
                corp_code,
                stock_code,
                bsns_year,
                reprt_code,
                account_nm,
                fs_div,
                thstrm_amount,
                thstrm_add_amount,
                updated_at
            FROM kr_corporate_financials
            WHERE corp_code IN ({corp_placeholders})
              AND reprt_code IN ({reprt_placeholders})
              AND bsns_year BETWEEN %s AND %s
              AND account_nm IN ({account_placeholders})
            ORDER BY corp_code ASC, bsns_year DESC, CASE fs_div WHEN 'CFS' THEN 0 ELSE 1 END ASC, updated_at DESC
        """
        params: List[Any] = (
            list(target_corp_codes)
            + list(reprt_codes)
            + [str(min_year), str(max_year)]
            + list(account_names)
        )
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

        metric_year_values: Dict[tuple[str, int, int, str], Dict[str, Any]] = {}
        for row in rows:
            corp_code = _normalize_corp_code(row.get("corp_code"))
            year = _safe_int(row.get("bsns_year"))
            quarter = self.reprt_code_to_quarter(row.get("reprt_code"))
            account_nm = str(row.get("account_nm") or "").strip()
            if not corp_code or not year or not quarter:
                continue

            metric_key: Optional[str] = None
            for candidate_metric, names in EARNINGS_METRIC_ACCOUNT_MAP.items():
                if account_nm in names:
                    metric_key = candidate_metric
                    break
            if not metric_key:
                continue

            value = _safe_int(row.get("thstrm_add_amount"))
            if value is None:
                value = _safe_int(row.get("thstrm_amount"))
            if value is None:
                continue

            key = (corp_code, int(year), int(quarter), metric_key)
            if key in metric_year_values:
                continue
            metric_year_values[key] = {
                "stock_code": _normalize_stock_code(row.get("stock_code")),
                "value": value,
            }

        normalized_rows: List[Dict[str, Any]] = []
        for corp_code in target_corp_codes:
            for period_year, fiscal_quarter in valid_periods:
                for metric_key in EARNINGS_METRIC_ACCOUNT_MAP:
                    history_values: List[int] = []
                    stock_code: Optional[str] = None
                    for lag_year in range(period_year - 1, period_year - max(int(lookback_years), 1) - 1, -1):
                        key = (corp_code, lag_year, fiscal_quarter, metric_key)
                        point = metric_year_values.get(key)
                        if not point:
                            continue
                        if stock_code is None:
                            stock_code = point.get("stock_code")
                        history_values.append(int(point["value"]))
                    if not history_values:
                        continue
                    expected_value = int(round(sum(history_values) / len(history_values)))
                    normalized_rows.append(
                        {
                            "corp_code": corp_code,
                            "stock_code": stock_code,
                            "period_year": str(period_year),
                            "fiscal_quarter": int(fiscal_quarter),
                            "metric_key": metric_key,
                            "expected_value": expected_value,
                            "expected_source": "auto_baseline",
                            "expected_as_of_date": expected_as_of_date,
                            "metadata": {
                                "model": "historical_same_quarter_average",
                                "lookback_years": int(lookback_years),
                                "history_values": history_values,
                            },
                        }
                    )
        return normalized_rows

    @staticmethod
    def build_surprise_payload(
        actual_metrics: Dict[str, Optional[int]],
        expected_metrics: Dict[str, Optional[int]],
    ) -> Dict[str, Dict[str, Any]]:
        surprise_payload: Dict[str, Dict[str, Any]] = {}
        for metric_key in EARNINGS_METRIC_ACCOUNT_MAP:
            actual_value = _safe_float(actual_metrics.get(metric_key))
            expected_value = _safe_float(expected_metrics.get(metric_key))
            if actual_value is None or expected_value in (None, 0):
                surprise_payload[metric_key] = {
                    "surprise_value": None,
                    "surprise_pct": None,
                    "label": "unknown",
                }
                continue
            surprise_value = actual_value - float(expected_value)
            surprise_pct = (surprise_value / abs(float(expected_value))) * 100.0
            if surprise_pct >= EARNINGS_SURPRISE_MEET_THRESHOLD_PCT:
                label = "beat"
            elif surprise_pct <= -EARNINGS_SURPRISE_MEET_THRESHOLD_PCT:
                label = "miss"
            else:
                label = "meet"
            surprise_payload[metric_key] = {
                "surprise_value": round(surprise_value, 2),
                "surprise_pct": _safe_decimal_pct(surprise_pct),
                "label": label,
            }
        return surprise_payload

    @staticmethod
    def summarize_surprise_label(surprise_payload: Dict[str, Dict[str, Any]]) -> str:
        labels = [str((item or {}).get("label") or "unknown") for item in surprise_payload.values()]
        if any(label == "beat" for label in labels):
            return "beat"
        if any(label == "miss" for label in labels):
            return "miss"
        if any(label == "meet" for label in labels):
            return "meet"
        return "unknown"

    def fetch_actual_metrics(
        self,
        *,
        corp_code: str,
        period_year: Optional[int],
        fiscal_quarter: Optional[int],
    ) -> Dict[str, Optional[int]]:
        metric_values: Dict[str, Optional[int]] = {key: None for key in EARNINGS_METRIC_ACCOUNT_MAP}
        if not period_year or not fiscal_quarter:
            return metric_values

        reprt_code = self.quarter_to_reprt_code(fiscal_quarter)
        if not reprt_code:
            return metric_values

        account_names: List[str] = []
        for names in EARNINGS_METRIC_ACCOUNT_MAP.values():
            account_names.extend(list(names))
        placeholders = ", ".join(["%s"] * len(account_names))
        query = f"""
            SELECT account_nm, thstrm_amount, thstrm_add_amount
            FROM kr_corporate_financials
            WHERE corp_code = %s
              AND bsns_year = %s
              AND reprt_code = %s
              AND account_nm IN ({placeholders})
            ORDER BY CASE fs_div WHEN 'CFS' THEN 0 ELSE 1 END ASC, updated_at DESC
        """
        params: List[Any] = [corp_code, str(period_year), reprt_code] + account_names
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

        if not rows:
            return metric_values

        for metric_key, candidates in EARNINGS_METRIC_ACCOUNT_MAP.items():
            selected_value: Optional[int] = None
            for row in rows:
                account_nm = str(row.get("account_nm") or "")
                if account_nm not in candidates:
                    continue
                selected_value = _safe_int(row.get("thstrm_add_amount"))
                if selected_value is None:
                    selected_value = _safe_int(row.get("thstrm_amount"))
                if selected_value is not None:
                    break
            metric_values[metric_key] = selected_value
        return metric_values

    def fetch_expected_metrics(
        self,
        *,
        corp_code: str,
        period_year: Optional[int],
        fiscal_quarter: Optional[int],
    ) -> Dict[str, Optional[int]]:
        metric_values: Dict[str, Optional[int]] = {key: None for key in EARNINGS_METRIC_ACCOUNT_MAP}
        if not period_year or not fiscal_quarter:
            return metric_values

        query = """
            SELECT metric_key, expected_value, expected_source, expected_as_of_date, updated_at
            FROM kr_corporate_earnings_expectations
            WHERE corp_code = %s
              AND period_year = %s
              AND fiscal_quarter = %s
            ORDER BY
              CASE
                WHEN expected_source = 'manual' THEN 0
                WHEN expected_source = 'feed' THEN 1
                WHEN expected_source = 'consensus_feed' THEN 1
                WHEN expected_source = 'auto_baseline' THEN 9
                ELSE 5
              END ASC,
              expected_as_of_date DESC,
              updated_at DESC
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (corp_code, str(period_year), int(fiscal_quarter)))
            rows = cursor.fetchall()

        for row in rows:
            metric_key = str(row.get("metric_key") or "").strip()
            if metric_key in metric_values and metric_values[metric_key] is None:
                metric_values[metric_key] = _safe_int(row.get("expected_value"))
        return metric_values

    def upsert_earnings_expectations(self, rows: Iterable[Dict[str, Any]]) -> int:
        payload_rows: List[tuple] = []
        for row in rows:
            corp_code = _normalize_corp_code(row.get("corp_code"))
            period_year = str(row.get("period_year") or "").strip()
            fiscal_quarter = _safe_int(row.get("fiscal_quarter"))
            metric_key = str(row.get("metric_key") or "").strip()
            if not corp_code or len(period_year) != 4 or not fiscal_quarter or metric_key not in EARNINGS_METRIC_ACCOUNT_MAP:
                continue
            payload_rows.append(
                (
                    corp_code,
                    _normalize_stock_code(row.get("stock_code")),
                    period_year,
                    int(fiscal_quarter),
                    metric_key,
                    _safe_int(row.get("expected_value")),
                    str(row.get("expected_source") or "manual").strip() or "manual",
                    row.get("expected_as_of_date"),
                    json.dumps(row.get("metadata") or {}, ensure_ascii=False, default=str),
                )
            )
        if not payload_rows:
            return 0

        self.ensure_tables()
        query = """
            INSERT INTO kr_corporate_earnings_expectations (
                corp_code,
                stock_code,
                period_year,
                fiscal_quarter,
                metric_key,
                expected_value,
                expected_source,
                expected_as_of_date,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                stock_code = VALUES(stock_code),
                expected_value = VALUES(expected_value),
                expected_as_of_date = VALUES(expected_as_of_date),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload_rows)
            return int(cursor.rowcount or 0)

    def fetch_disclosure_rows(
        self,
        *,
        corp_code: str,
        bgn_de: str,
        end_de: str,
        page_no: int = 1,
        page_count: int = DEFAULT_DART_DISCLOSURE_PAGE_COUNT,
        last_reprt_at: str = "N",
        pblntf_ty: str = "A",
    ) -> List[Dict[str, Any]]:
        normalized_corp_code = _normalize_corp_code(corp_code)
        if not normalized_corp_code:
            raise ValueError(f"Invalid corp_code: {corp_code}")

        api_key = os.getenv("DART_API_KEY", "").strip()
        if not api_key:
            raise ValueError("DART_API_KEY is required")

        params = {
            "crtfc_key": api_key,
            "corp_code": normalized_corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "last_reprt_at": last_reprt_at,
            "pblntf_ty": pblntf_ty,
            "page_no": page_no,
            "page_count": page_count,
        }
        payload = self._fetch_json(DART_DISCLOSURE_LIST_URL, params)
        status = str(payload.get("status", ""))
        message = str(payload.get("message", ""))
        if status == "000":
            rows = payload.get("list") or []
            return rows if isinstance(rows, list) else []
        if status == "013":
            return []
        raise ValueError(f"DART disclosure list failed(status={status}, message={message})")

    def normalize_disclosure_row(
        self,
        raw: Dict[str, Any],
        *,
        as_of_date: date,
    ) -> Optional[Dict[str, Any]]:
        rcept_no = str(raw.get("rcept_no") or "").strip()
        corp_code = _normalize_corp_code(raw.get("corp_code"))
        report_nm = str(raw.get("report_nm") or "").strip()
        if not rcept_no or not corp_code or not report_nm:
            return None

        rcept_dt_text = "".join(ch for ch in str(raw.get("rcept_dt") or "") if ch.isdigit())
        rcept_dt: Optional[date] = None
        if len(rcept_dt_text) == 8:
            try:
                rcept_dt = datetime.strptime(rcept_dt_text, "%Y%m%d").date()
            except ValueError:
                rcept_dt = None

        event_type = self.classify_disclosure_event(report_nm)
        stock_code = _normalize_stock_code(raw.get("stock_code"))
        source_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        period_info = self.infer_reporting_period(report_nm, rcept_dt=rcept_dt)
        period_year = period_info.get("period_year")
        fiscal_quarter = period_info.get("fiscal_quarter")

        metric_actual: Dict[str, Optional[int]] = {}
        metric_expected: Dict[str, Optional[int]] = {}
        metric_surprise: Dict[str, Dict[str, Any]] = {}
        surprise_label: Optional[str] = None
        if event_type == "earnings_announcement":
            metric_actual = self.fetch_actual_metrics(
                corp_code=corp_code,
                period_year=period_year,
                fiscal_quarter=fiscal_quarter,
            )
            metric_expected = self.fetch_expected_metrics(
                corp_code=corp_code,
                period_year=period_year,
                fiscal_quarter=fiscal_quarter,
            )
            metric_surprise = self.build_surprise_payload(metric_actual, metric_expected)
            surprise_label = self.summarize_surprise_label(metric_surprise)

        return {
            "rcept_no": rcept_no,
            "corp_code": corp_code,
            "stock_code": stock_code,
            "corp_name": str(raw.get("corp_name") or "").strip() or None,
            "corp_cls": str(raw.get("corp_cls") or "").strip() or None,
            "report_nm": report_nm,
            "flr_nm": str(raw.get("flr_nm") or "").strip() or None,
            "rcept_dt": rcept_dt,
            "event_type": event_type,
            "is_earnings_event": 1 if event_type == "earnings_announcement" else 0,
            "period_year": str(period_year) if period_year else None,
            "fiscal_quarter": int(fiscal_quarter) if fiscal_quarter else None,
            "metric_actual_json": json.dumps(metric_actual, ensure_ascii=False, default=str) if metric_actual else None,
            "metric_expected_json": json.dumps(metric_expected, ensure_ascii=False, default=str) if metric_expected else None,
            "metric_surprise_json": json.dumps(metric_surprise, ensure_ascii=False, default=str) if metric_surprise else None,
            "surprise_label": surprise_label,
            "source_url": source_url,
            "as_of_date": as_of_date,
            "metadata_json": json.dumps(raw, ensure_ascii=False, default=str),
        }

    @staticmethod
    def _to_earnings_event_meta(normalized: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if int(normalized.get("is_earnings_event") or 0) != 1:
            return None

        rcept_no = str(normalized.get("rcept_no") or "").strip()
        corp_code = _normalize_corp_code(normalized.get("corp_code"))
        if not rcept_no or not corp_code:
            return None

        stock_code = _normalize_stock_code(normalized.get("stock_code"))
        period_year = str(normalized.get("period_year") or "").strip()
        fiscal_quarter = _safe_int(normalized.get("fiscal_quarter"))
        if fiscal_quarter not in (1, 2, 3, 4):
            fiscal_quarter = None
        if len(period_year) != 4 or not period_year.isdigit():
            period_year = ""

        rcept_dt_value = normalized.get("rcept_dt")
        rcept_dt_text: Optional[str] = None
        if isinstance(rcept_dt_value, date):
            rcept_dt_text = rcept_dt_value.isoformat()
        elif rcept_dt_value:
            rcept_dt_text = str(rcept_dt_value).strip() or None

        return {
            "rcept_no": rcept_no,
            "corp_code": corp_code,
            "stock_code": stock_code,
            "period_year": period_year or None,
            "fiscal_quarter": fiscal_quarter,
            "rcept_dt": rcept_dt_text,
        }

    @staticmethod
    def _dedupe_earnings_event_meta(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            rcept_no = str(row.get("rcept_no") or "").strip()
            if not rcept_no or rcept_no in seen:
                continue
            seen.add(rcept_no)
            deduped.append(row)
        return deduped

    def save_disclosure_rows_with_stats(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {
                "db_affected": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "inserted_rcept_nos": [],
            }

        self.ensure_tables()

        columns = [
            "rcept_no",
            "corp_code",
            "stock_code",
            "corp_name",
            "corp_cls",
            "report_nm",
            "flr_nm",
            "rcept_dt",
            "event_type",
            "is_earnings_event",
            "period_year",
            "fiscal_quarter",
            "metric_actual_json",
            "metric_expected_json",
            "metric_surprise_json",
            "surprise_label",
            "source_url",
            "as_of_date",
            "metadata_json",
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        update_columns = [col for col in columns if col != "rcept_no"]
        updates = ", ".join([f"`{col}` = VALUES(`{col}`)" for col in update_columns])
        query = f"""
            INSERT INTO kr_corporate_disclosures ({", ".join([f"`{c}`" for c in columns])})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE
                {updates},
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [tuple(row.get(col) for col in columns) for row in rows]
        rcept_no_candidates = [
            str(row.get("rcept_no") or "").strip()
            for row in rows
            if str(row.get("rcept_no") or "").strip()
        ]
        unique_rcept_nos = list(dict.fromkeys(rcept_no_candidates))

        existing_rcept_nos: set[str] = set()
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            if unique_rcept_nos:
                for chunk in _chunked(unique_rcept_nos, 200):
                    chunk_placeholders = ", ".join(["%s"] * len(chunk))
                    cursor.execute(
                        f"SELECT rcept_no FROM kr_corporate_disclosures WHERE rcept_no IN ({chunk_placeholders})",
                        tuple(chunk),
                    )
                    for found in cursor.fetchall() or []:
                        value = str(found.get("rcept_no") or "").strip()
                        if value:
                            existing_rcept_nos.add(value)

            cursor.executemany(query, payload)
            affected = int(cursor.rowcount or 0)

        inserted_rcept_nos = [value for value in unique_rcept_nos if value not in existing_rcept_nos]
        inserted_count = len(inserted_rcept_nos)
        updated_count = max(len(unique_rcept_nos) - inserted_count, 0)
        return {
            "db_affected": affected,
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "inserted_rcept_nos": inserted_rcept_nos,
        }

    def save_disclosure_rows(self, rows: List[Dict[str, Any]]) -> int:
        result = self.save_disclosure_rows_with_stats(rows)
        return int(result.get("db_affected") or 0)

    def ingest_disclosure_rows(
        self,
        rows: Iterable[Dict[str, Any]],
        *,
        as_of_date: Optional[date] = None,
        only_earnings: bool = True,
    ) -> Dict[str, Any]:
        target_as_of = as_of_date or date.today()
        normalized_rows: List[Dict[str, Any]] = []
        total_input = 0
        skipped = 0
        filtered_out = 0
        for row in rows:
            total_input += 1
            normalized = self.normalize_disclosure_row(row, as_of_date=target_as_of)
            if normalized is None:
                skipped += 1
                continue
            if only_earnings and int(normalized.get("is_earnings_event") or 0) != 1:
                filtered_out += 1
                continue
            normalized_rows.append(normalized)

        all_earnings_events = self._dedupe_earnings_event_meta(
            [
                event
                for event in (
                    self._to_earnings_event_meta(row) for row in normalized_rows
                )
                if event is not None
            ]
        )
        save_stats = self.save_disclosure_rows_with_stats(normalized_rows)
        inserted_rcept_nos = {
            str(value).strip()
            for value in (save_stats.get("inserted_rcept_nos") or [])
            if str(value).strip()
        }
        new_earnings_events = self._dedupe_earnings_event_meta(
            [
                event
                for event in all_earnings_events
                if str(event.get("rcept_no") or "").strip() in inserted_rcept_nos
            ]
        )

        all_earnings_corp_codes = sorted(
            {
                str(event.get("corp_code") or "").strip()
                for event in all_earnings_events
                if str(event.get("corp_code") or "").strip()
            }
        )
        new_earnings_corp_codes = sorted(
            {
                str(event.get("corp_code") or "").strip()
                for event in new_earnings_events
                if str(event.get("corp_code") or "").strip()
            }
        )

        return {
            "input_rows": total_input,
            "normalized_rows": len(normalized_rows),
            "skipped_rows": skipped,
            "filtered_out_rows": filtered_out,
            "db_affected": int(save_stats.get("db_affected") or 0),
            "inserted_rows": int(save_stats.get("inserted_count") or 0),
            "updated_rows": int(save_stats.get("updated_count") or 0),
            "earnings_event_count": len(all_earnings_events),
            "new_earnings_event_count": len(new_earnings_events),
            "earnings_event_corp_codes": all_earnings_corp_codes,
            "new_earnings_event_corp_codes": new_earnings_corp_codes,
            "earnings_events": all_earnings_events,
            "new_earnings_events": new_earnings_events,
        }

    def ingest_financial_rows(
        self,
        rows: Iterable[Dict[str, Any]],
        *,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        target_as_of = as_of_date or date.today()
        normalized_rows: List[Dict[str, Any]] = []
        total_input = 0
        skipped = 0
        for row in rows:
            total_input += 1
            normalized = self.normalize_financial_row(row, as_of_date=target_as_of)
            if normalized is None:
                skipped += 1
                continue
            normalized_rows.append(normalized)

        affected = self.save_financial_rows(normalized_rows)
        return {
            "input_rows": total_input,
            "normalized_rows": len(normalized_rows),
            "skipped_rows": skipped,
            "db_affected": affected,
        }

    def collect_major_accounts(
        self,
        *,
        bsns_year: str,
        reprt_code: str = "11011",
        corp_codes: Optional[Iterable[str]] = None,
        stock_codes: Optional[Iterable[str]] = None,
        max_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        refresh_corp_codes: bool = True,
        corp_code_max_age_days: int = DEFAULT_DART_CORPCODE_MAX_AGE_DAYS,
        as_of_date: Optional[date] = None,
        batch_size: int = DEFAULT_DART_BATCH_SIZE,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        if refresh_corp_codes:
            self.refresh_corp_code_cache(
                force=False,
                max_age_days=corp_code_max_age_days,
            )

        resolved_corp_codes = self.resolve_target_corp_codes(
            corp_codes=corp_codes,
            stock_codes=stock_codes,
            max_corp_count=max_corp_count,
        )
        if not resolved_corp_codes:
            raise ValueError("No target corp_code resolved. refresh corp_code cache first.")

        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        batch_size = min(batch_size, 100)

        run_as_of = as_of_date or date.today()
        summary: Dict[str, Any] = {
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "target_corp_count": len(resolved_corp_codes),
            "batch_size": batch_size,
            "api_requests": 0,
            "fetched_rows": 0,
            "normalized_rows": 0,
            "skipped_rows": 0,
            "db_affected": 0,
            "failed_batches": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        for corp_batch in _chunked(resolved_corp_codes, batch_size):
            try:
                rows = self.fetch_multi_account_rows(
                    corp_codes=corp_batch,
                    bsns_year=bsns_year,
                    reprt_code=reprt_code,
                )
            except Exception as exc:
                summary["failed_batches"] += 1
                logger.warning(
                    "DART 수집 배치 실패: year=%s reprt=%s batch_size=%s err=%s",
                    bsns_year,
                    reprt_code,
                    len(corp_batch),
                    exc,
                )
                continue

            summary["api_requests"] += 1
            summary["fetched_rows"] += len(rows)
            ingest_result = self.ingest_financial_rows(rows, as_of_date=run_as_of)
            summary["normalized_rows"] += int(ingest_result.get("normalized_rows", 0))
            summary["skipped_rows"] += int(ingest_result.get("skipped_rows", 0))
            summary["db_affected"] += int(ingest_result.get("db_affected", 0))

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary

    def collect_disclosure_events(
        self,
        *,
        start_date: date,
        end_date: date,
        corp_codes: Optional[Iterable[str]] = None,
        stock_codes: Optional[Iterable[str]] = None,
        max_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        refresh_corp_codes: bool = False,
        corp_code_max_age_days: int = DEFAULT_DART_CORPCODE_MAX_AGE_DAYS,
        page_count: int = DEFAULT_DART_DISCLOSURE_PAGE_COUNT,
        per_corp_max_pages: int = 3,
        only_earnings: bool = True,
        expectation_rows: Optional[Iterable[Dict[str, Any]]] = None,
        auto_expectations: bool = True,
        expectation_feed_url: Optional[str] = None,
        require_feed_expectations: bool = DEFAULT_REQUIRE_EXPECTATION_FEED,
        allow_baseline_fallback: bool = DEFAULT_ALLOW_BASELINE_FALLBACK,
        baseline_lookback_years: int = DEFAULT_EARNINGS_EXPECTATION_LOOKBACK_YEARS,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")
        if page_count <= 0 or page_count > 100:
            raise ValueError("page_count must be between 1 and 100")
        if per_corp_max_pages <= 0:
            raise ValueError("per_corp_max_pages must be > 0")

        self.ensure_tables()
        if refresh_corp_codes:
            self.refresh_corp_code_cache(
                force=False,
                max_age_days=corp_code_max_age_days,
            )

        target_corp_codes = self.resolve_target_corp_codes(
            corp_codes=corp_codes,
            stock_codes=stock_codes,
            max_corp_count=max_corp_count,
        )
        if not target_corp_codes:
            raise ValueError("No target corp_code resolved. refresh corp_code cache first.")

        run_as_of = as_of_date or date.today()
        candidate_expectation_rows: List[Dict[str, Any]] = []
        explicit_expectation_rows = list(expectation_rows or [])
        normalized_explicit_rows = [
            row
            for row in (
                self.normalize_expectation_row(
                    raw if isinstance(raw, dict) else {},
                    default_source="manual",
                    default_as_of_date=run_as_of,
                )
                for raw in explicit_expectation_rows
            )
            if row is not None
        ]
        candidate_expectation_rows.extend(normalized_explicit_rows)

        feed_expectation_rows: List[Dict[str, Any]] = []
        baseline_expectation_rows: List[Dict[str, Any]] = []
        if auto_expectations:
            candidate_periods = self.build_expectation_candidate_periods(
                start_date=start_date,
                end_date=end_date,
            )
            resolved_feed_url = (
                expectation_feed_url
                or os.getenv("KR_EARNINGS_EXPECTATION_FEED_URL", "").strip()
                or DEFAULT_EXPECTATION_FEED_URL
            )
            if require_feed_expectations and not resolved_feed_url:
                raise ValueError(
                    "KR earnings expectation feed is required. "
                    "Set expectation_feed_url or KR_EARNINGS_EXPECTATION_FEED_URL."
                )
            if resolved_feed_url:
                try:
                    feed_expectation_rows = self.fetch_expectation_rows_from_feed(
                        url=resolved_feed_url,
                        expected_as_of_date=run_as_of,
                        target_corp_codes=target_corp_codes,
                        candidate_periods=candidate_periods,
                        top_corp_count=max(int(max_corp_count), 1),
                    )
                except Exception as exc:
                    if require_feed_expectations:
                        raise ValueError(f"Earnings expectation feed fetch failed: {exc}") from exc
                    logger.warning("Earnings expectation feed fetch failed: %s", exc)

            if require_feed_expectations and len(feed_expectation_rows) == 0:
                raise ValueError("Earnings expectation feed returned no rows.")

            candidate_expectation_rows.extend(feed_expectation_rows)
            if allow_baseline_fallback and len(feed_expectation_rows) == 0:
                baseline_expectation_rows = self.build_baseline_expectation_rows(
                    corp_codes=target_corp_codes,
                    candidate_periods=candidate_periods,
                    lookback_years=max(int(baseline_lookback_years), 1),
                    expected_as_of_date=run_as_of,
                )
                candidate_expectation_rows.extend(baseline_expectation_rows)

        expectation_upserted = self.upsert_earnings_expectations(candidate_expectation_rows)

        bgn_de = start_date.strftime("%Y%m%d")
        end_de = end_date.strftime("%Y%m%d")
        summary: Dict[str, Any] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "target_corp_count": len(target_corp_codes),
            "only_earnings": bool(only_earnings),
            "auto_expectations": bool(auto_expectations),
            "require_feed_expectations": bool(require_feed_expectations),
            "allow_baseline_fallback": bool(allow_baseline_fallback),
            "expectation_feed_url": resolved_feed_url if auto_expectations else None,
            "expectation_explicit_rows": len(normalized_explicit_rows),
            "expectation_feed_rows": len(feed_expectation_rows),
            "expectation_baseline_rows": len(baseline_expectation_rows),
            "expectation_upserted": int(expectation_upserted),
            "api_requests": 0,
            "fetched_rows": 0,
            "normalized_rows": 0,
            "filtered_out_rows": 0,
            "skipped_rows": 0,
            "db_affected": 0,
            "inserted_rows": 0,
            "updated_rows": 0,
            "failed_requests": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        all_earnings_events: List[Dict[str, Any]] = []
        new_earnings_events: List[Dict[str, Any]] = []

        for corp_code in target_corp_codes:
            for page_no in range(1, per_corp_max_pages + 1):
                try:
                    rows = self.fetch_disclosure_rows(
                        corp_code=corp_code,
                        bgn_de=bgn_de,
                        end_de=end_de,
                        page_no=page_no,
                        page_count=page_count,
                    )
                except Exception as exc:
                    summary["failed_requests"] += 1
                    logger.warning(
                        "DART 공시 이벤트 수집 실패: corp_code=%s page=%s err=%s",
                        corp_code,
                        page_no,
                        exc,
                    )
                    break

                summary["api_requests"] += 1
                if not rows:
                    break
                summary["fetched_rows"] += len(rows)
                ingest_result = self.ingest_disclosure_rows(
                    rows,
                    as_of_date=run_as_of,
                    only_earnings=only_earnings,
                )
                summary["normalized_rows"] += int(ingest_result.get("normalized_rows", 0))
                summary["filtered_out_rows"] += int(ingest_result.get("filtered_out_rows", 0))
                summary["skipped_rows"] += int(ingest_result.get("skipped_rows", 0))
                summary["db_affected"] += int(ingest_result.get("db_affected", 0))
                summary["inserted_rows"] += int(ingest_result.get("inserted_rows", 0))
                summary["updated_rows"] += int(ingest_result.get("updated_rows", 0))
                all_earnings_events.extend(ingest_result.get("earnings_events", []) or [])
                new_earnings_events.extend(ingest_result.get("new_earnings_events", []) or [])

                if len(rows) < page_count:
                    break

        all_earnings_events = self._dedupe_earnings_event_meta(all_earnings_events)
        new_earnings_events = self._dedupe_earnings_event_meta(new_earnings_events)
        summary["earnings_event_count"] = len(all_earnings_events)
        summary["new_earnings_event_count"] = len(new_earnings_events)
        summary["earnings_event_corp_codes"] = sorted(
            {
                str(event.get("corp_code") or "").strip()
                for event in all_earnings_events
                if str(event.get("corp_code") or "").strip()
            }
        )
        summary["new_earnings_event_corp_codes"] = sorted(
            {
                str(event.get("corp_code") or "").strip()
                for event in new_earnings_events
                if str(event.get("corp_code") or "").strip()
            }
        )
        summary["earnings_events"] = all_earnings_events
        summary["new_earnings_events"] = new_earnings_events

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary


_kr_corporate_collector_singleton: Optional[KRCorporateCollector] = None


def get_kr_corporate_collector() -> KRCorporateCollector:
    global _kr_corporate_collector_singleton
    if _kr_corporate_collector_singleton is None:
        _kr_corporate_collector_singleton = KRCorporateCollector()
    return _kr_corporate_collector_singleton
