"""
Corporate tier state collector.

Phase 2.5:
- store and sync tier membership state (Tier-1/2/3 schema-ready)
- current population scope: KR Top50 snapshot + US fixed Top50 (Tier-1)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from service.database.db import get_db_connection
from service.macro_trading.collectors.kr_corporate_collector import (
    KR_TOP50_DEFAULT_MARKET,
    KR_TOP50_DEFAULT_SOURCE_URL,
    get_kr_corporate_collector,
)
from service.macro_trading.collectors.us_corporate_collector import (
    DEFAULT_US_TOP50_FIXED_SYMBOLS,
    get_us_corporate_collector,
)

logger = logging.getLogger(__name__)

DEFAULT_TIER_KR_LIMIT = 50
DEFAULT_TIER_US_LIMIT = 50
DEFAULT_TIER_LEVEL = 1
DEFAULT_TIER_LABEL = "tier1"
DEFAULT_TIER_SOURCE_KR = "kr_top50_snapshot"
DEFAULT_TIER_SOURCE_US = "us_top50_fixed"


def _normalize_symbol(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if not text:
        return None
    normalized = "".join(ch for ch in text if ch.isalnum() or ch in {".", "-"})
    return normalized or None


def _normalize_corp_code(value: Any) -> Optional[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) == 8:
        return digits
    return None


def _normalize_cik(value: Any) -> Optional[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


class CorporateTierCollector:
    def __init__(self, db_connection_factory=None):
        self._db_connection_factory = db_connection_factory or get_db_connection

    def _get_db_connection(self):
        return self._db_connection_factory()

    def ensure_tables(self):
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS corporate_tier_state (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    as_of_date DATE NOT NULL,
                    country_code CHAR(2) NOT NULL,
                    market VARCHAR(16) NULL,
                    symbol VARCHAR(16) NOT NULL,
                    company_name VARCHAR(255) NULL,
                    corp_code CHAR(8) NULL,
                    cik CHAR(10) NULL,
                    tier_level TINYINT NOT NULL,
                    tier_label VARCHAR(16) NOT NULL,
                    tier_source VARCHAR(64) NOT NULL,
                    membership_rank SMALLINT NULL,
                    snapshot_date DATE NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_tier_state (
                        as_of_date, country_code, symbol, tier_level, tier_source
                    ),
                    INDEX idx_tier_lookup (country_code, tier_level, is_active),
                    INDEX idx_tier_asof (as_of_date, country_code),
                    INDEX idx_tier_symbol (country_code, symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

    def load_latest_kr_top50_rows(
        self,
        *,
        market: str = KR_TOP50_DEFAULT_MARKET,
        limit: int = DEFAULT_TIER_KR_LIMIT,
    ) -> List[Dict[str, Any]]:
        collector = get_kr_corporate_collector()
        recent_dates = collector.load_recent_top50_snapshot_dates(
            market=market,
            limit=1,
        )
        if not recent_dates:
            return []
        latest_snapshot_date = recent_dates[0]
        rows = collector.load_top50_snapshot_rows_by_date(
            snapshot_date=latest_snapshot_date,
            market=market,
            limit=max(int(limit), 1),
        )
        if not rows:
            return []

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            symbol = _normalize_symbol(row.get("stock_code"))
            if not symbol:
                continue
            rank_position = row.get("rank_position")
            try:
                normalized_rank = int(rank_position) if rank_position is not None else None
            except (TypeError, ValueError):
                normalized_rank = None
            normalized_rows.append(
                {
                    "country_code": "KR",
                    "market": str(market or KR_TOP50_DEFAULT_MARKET).upper(),
                    "symbol": symbol,
                    "company_name": str(row.get("stock_name") or "").strip() or None,
                    "corp_code": _normalize_corp_code(row.get("corp_code")),
                    "cik": None,
                    "membership_rank": normalized_rank,
                    "snapshot_date": row.get("snapshot_date"),
                    "source_url": row.get("source_url") or KR_TOP50_DEFAULT_SOURCE_URL,
                    "source_metadata": row,
                }
            )
        return normalized_rows

    def load_us_top50_rows(
        self,
        *,
        symbols: Optional[Iterable[str]] = None,
        max_symbol_count: int = DEFAULT_TIER_US_LIMIT,
    ) -> List[Dict[str, Any]]:
        us_collector = get_us_corporate_collector()
        resolved_symbols = us_collector.resolve_target_symbols(
            symbols=symbols or list(DEFAULT_US_TOP50_FIXED_SYMBOLS),
            max_symbol_count=max_symbol_count,
        )
        mapping_rows = us_collector.load_symbol_mapping_rows(resolved_symbols)

        rows: List[Dict[str, Any]] = []
        for idx, symbol in enumerate(resolved_symbols, start=1):
            normalized_symbol = _normalize_symbol(symbol)
            if not normalized_symbol:
                continue
            mapped = mapping_rows.get(normalized_symbol) or {}
            rows.append(
                {
                    "country_code": "US",
                    "market": "US",
                    "symbol": normalized_symbol,
                    "company_name": str(mapped.get("company_name") or "").strip() or None,
                    "corp_code": None,
                    "cik": _normalize_cik(mapped.get("cik")),
                    "membership_rank": idx,
                    "snapshot_date": None,
                    "source_url": None,
                    "source_metadata": mapped,
                }
            )
        return rows

    @staticmethod
    def build_tier_rows(
        *,
        as_of_date: date,
        source_rows: Sequence[Dict[str, Any]],
        tier_level: int = DEFAULT_TIER_LEVEL,
        tier_source: str,
    ) -> List[Dict[str, Any]]:
        tier_label = f"tier{int(tier_level)}"
        rows: List[Dict[str, Any]] = []
        for item in source_rows:
            country_code = str(item.get("country_code") or "").strip().upper()
            symbol = _normalize_symbol(item.get("symbol"))
            if country_code not in {"KR", "US"} or not symbol:
                continue
            metadata = {
                "source_metadata": item.get("source_metadata"),
                "source_url": item.get("source_url"),
            }
            rows.append(
                {
                    "as_of_date": as_of_date,
                    "country_code": country_code,
                    "market": str(item.get("market") or "").strip().upper() or None,
                    "symbol": symbol,
                    "company_name": str(item.get("company_name") or "").strip() or None,
                    "corp_code": _normalize_corp_code(item.get("corp_code")),
                    "cik": _normalize_cik(item.get("cik")),
                    "tier_level": int(tier_level),
                    "tier_label": tier_label,
                    "tier_source": str(tier_source or "").strip() or "unknown",
                    "membership_rank": item.get("membership_rank"),
                    "snapshot_date": item.get("snapshot_date"),
                    "is_active": 1,
                    "metadata_json": json.dumps(metadata, ensure_ascii=False, default=str),
                }
            )
        return rows

    def deactivate_existing_rows(
        self,
        *,
        as_of_date: date,
        country_code: str,
        tier_level: int,
        tier_source: str,
    ) -> int:
        self.ensure_tables()
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE corporate_tier_state
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE as_of_date = %s
                  AND country_code = %s
                  AND tier_level = %s
                  AND tier_source = %s
                  AND is_active = 1
                """,
                (
                    as_of_date,
                    str(country_code or "").strip().upper(),
                    int(tier_level),
                    str(tier_source or "").strip(),
                ),
            )
            return int(cursor.rowcount or 0)

    def upsert_tier_rows(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO corporate_tier_state (
                as_of_date,
                country_code,
                market,
                symbol,
                company_name,
                corp_code,
                cik,
                tier_level,
                tier_label,
                tier_source,
                membership_rank,
                snapshot_date,
                is_active,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                market = VALUES(market),
                company_name = VALUES(company_name),
                corp_code = VALUES(corp_code),
                cik = VALUES(cik),
                tier_label = VALUES(tier_label),
                membership_rank = VALUES(membership_rank),
                snapshot_date = VALUES(snapshot_date),
                is_active = VALUES(is_active),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("as_of_date"),
                row.get("country_code"),
                row.get("market"),
                row.get("symbol"),
                row.get("company_name"),
                row.get("corp_code"),
                row.get("cik"),
                row.get("tier_level"),
                row.get("tier_label"),
                row.get("tier_source"),
                row.get("membership_rank"),
                row.get("snapshot_date"),
                row.get("is_active", 1),
                row.get("metadata_json"),
            )
            for row in rows
        ]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def sync_tier1_state(
        self,
        *,
        as_of_date: Optional[date] = None,
        kr_market: str = KR_TOP50_DEFAULT_MARKET,
        kr_limit: int = DEFAULT_TIER_KR_LIMIT,
        us_symbols: Optional[Iterable[str]] = None,
        us_limit: int = DEFAULT_TIER_US_LIMIT,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        target_as_of = as_of_date or datetime.now(timezone.utc).date()

        kr_source_rows = self.load_latest_kr_top50_rows(
            market=kr_market,
            limit=kr_limit,
        )
        us_source_rows = self.load_us_top50_rows(
            symbols=us_symbols,
            max_symbol_count=us_limit,
        )

        kr_tier_rows = self.build_tier_rows(
            as_of_date=target_as_of,
            source_rows=kr_source_rows,
            tier_level=DEFAULT_TIER_LEVEL,
            tier_source=DEFAULT_TIER_SOURCE_KR,
        )
        us_tier_rows = self.build_tier_rows(
            as_of_date=target_as_of,
            source_rows=us_source_rows,
            tier_level=DEFAULT_TIER_LEVEL,
            tier_source=DEFAULT_TIER_SOURCE_US,
        )

        deactivated_kr = self.deactivate_existing_rows(
            as_of_date=target_as_of,
            country_code="KR",
            tier_level=DEFAULT_TIER_LEVEL,
            tier_source=DEFAULT_TIER_SOURCE_KR,
        )
        deactivated_us = self.deactivate_existing_rows(
            as_of_date=target_as_of,
            country_code="US",
            tier_level=DEFAULT_TIER_LEVEL,
            tier_source=DEFAULT_TIER_SOURCE_US,
        )

        affected_kr = self.upsert_tier_rows(kr_tier_rows)
        affected_us = self.upsert_tier_rows(us_tier_rows)

        return {
            "as_of_date": target_as_of.isoformat(),
            "tier_level": DEFAULT_TIER_LEVEL,
            "kr_market": str(kr_market or KR_TOP50_DEFAULT_MARKET).upper(),
            "kr_source_count": len(kr_source_rows),
            "us_source_count": len(us_source_rows),
            "kr_deactivated": int(deactivated_kr),
            "us_deactivated": int(deactivated_us),
            "kr_db_affected": int(affected_kr),
            "us_db_affected": int(affected_us),
            "db_affected_total": int(affected_kr + affected_us),
            "tier_source_kr": DEFAULT_TIER_SOURCE_KR,
            "tier_source_us": DEFAULT_TIER_SOURCE_US,
        }

    def load_recent_country_symbols(
        self,
        *,
        country_code: str,
        as_of_date: Optional[date] = None,
        tier_level: int = DEFAULT_TIER_LEVEL,
        lookback_days: int = 365,
        max_symbol_count: Optional[int] = None,
    ) -> List[str]:
        """
        Tier 상태 이력에서 최근 lookback_days 범위 내 심볼을 조회합니다.
        최신 as_of_date에 가까운 심볼부터 반환됩니다.
        """
        self.ensure_tables()
        resolved_country = str(country_code or "").strip().upper()
        if resolved_country not in {"KR", "US"}:
            return []
        resolved_as_of = as_of_date or datetime.now(timezone.utc).date()
        resolved_lookback_days = max(int(lookback_days), 1)
        start_date = resolved_as_of - timedelta(days=resolved_lookback_days - 1)

        query = """
            SELECT
                symbol,
                MAX(as_of_date) AS latest_as_of_date
            FROM corporate_tier_state
            WHERE country_code = %s
              AND tier_level = %s
              AND is_active = 1
              AND as_of_date BETWEEN %s AND %s
            GROUP BY symbol
            ORDER BY latest_as_of_date DESC, symbol ASC
        """
        params: List[Any] = [
            resolved_country,
            int(tier_level),
            start_date,
            resolved_as_of,
        ]
        if max_symbol_count is not None:
            query += " LIMIT %s"
            params.append(max(int(max_symbol_count), 1))

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall() or []

        symbols: List[str] = []
        for row in rows:
            symbol = _normalize_symbol(row.get("symbol"))
            if symbol:
                symbols.append(symbol)
        return symbols


_corporate_tier_collector_singleton: Optional[CorporateTierCollector] = None


def get_corporate_tier_collector() -> CorporateTierCollector:
    global _corporate_tier_collector_singleton
    if _corporate_tier_collector_singleton is None:
        _corporate_tier_collector_singleton = CorporateTierCollector()
    return _corporate_tier_collector_singleton
