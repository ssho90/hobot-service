"""
Corporate entity registry collector.

Phase 2.5:
- enforce canonical company PK: (country_code, symbol)
- build searchable alias dictionary from Tier-1 membership
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)

DEFAULT_ENTITY_TIER_LEVEL = 1
DEFAULT_ENTITY_SYNC_SOURCE = "tier1_sync"
DEFAULT_ENTITY_COUNTRIES: Tuple[str, ...] = ("KR", "US")


def _normalize_country_code(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if text in {"KR", "US"}:
        return text
    return None


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


def _normalize_alias_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    # Keep Hangul/ASCII alnum; drop separators/spaces for robust matching.
    folded = unicodedata.normalize("NFKC", text).lower().strip()
    compact = re.sub(r"\s+", "", folded)
    compact = re.sub(r"[^0-9a-z가-힣]", "", compact)
    return compact or None


class CorporateEntityCollector:
    def __init__(self, db_connection_factory=None):
        self._db_connection_factory = db_connection_factory or get_db_connection

    def _get_db_connection(self):
        return self._db_connection_factory()

    @staticmethod
    def _index_exists(cursor, table_name: str, index_name: str) -> bool:
        cursor.execute(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = %s", (index_name,))
        return bool(cursor.fetchone())

    @classmethod
    def _drop_index_if_exists(cls, cursor, table_name: str, index_name: str):
        if cls._index_exists(cursor, table_name, index_name):
            cursor.execute(f"ALTER TABLE `{table_name}` DROP INDEX `{index_name}`")

    @classmethod
    def _create_index_if_missing(cls, cursor, table_name: str, index_name: str, columns_sql: str):
        if cls._index_exists(cursor, table_name, index_name):
            return
        cursor.execute(f"ALTER TABLE `{table_name}` ADD INDEX `{index_name}` ({columns_sql})")

    def ensure_tables(self):
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS corporate_entity_registry (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    country_code CHAR(2) NOT NULL,
                    symbol VARCHAR(16) NOT NULL,
                    market VARCHAR(16) NULL,
                    company_name VARCHAR(255) NULL,
                    corp_code CHAR(8) NULL,
                    cik CHAR(10) NULL,
                    latest_tier_level TINYINT NULL,
                    latest_tier_source VARCHAR(64) NULL,
                    latest_as_of_date DATE NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_country_symbol (country_code, symbol),
                    INDEX idx_country_active (country_code, is_active),
                    INDEX idx_country_market (country_code, market),
                    INDEX idx_country_company (country_code, company_name),
                    INDEX idx_country_corp_code (country_code, corp_code),
                    INDEX idx_country_cik (country_code, cik)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS corporate_entity_aliases (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    country_code CHAR(2) NOT NULL,
                    symbol VARCHAR(16) NOT NULL,
                    alias VARCHAR(255) NOT NULL,
                    alias_normalized VARCHAR(255) NOT NULL,
                    alias_type VARCHAR(32) NOT NULL,
                    priority SMALLINT NOT NULL DEFAULT 100,
                    source VARCHAR(64) NOT NULL DEFAULT 'tier1_sync',
                    as_of_date DATE NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_alias_entry (
                        country_code, symbol, alias_normalized, alias_type, source
                    ),
                    INDEX idx_alias_lookup (country_code, alias_normalized, is_active),
                    INDEX idx_alias_symbol (country_code, symbol, is_active)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            # Multiple symbols can share one corp_code/cik (e.g. dual class shares).
            # Ensure those fields are indexed, not unique-constrained.
            self._drop_index_if_exists(cursor, "corporate_entity_registry", "uniq_country_corp_code")
            self._drop_index_if_exists(cursor, "corporate_entity_registry", "uniq_country_cik")
            self._create_index_if_missing(
                cursor,
                "corporate_entity_registry",
                "idx_country_corp_code",
                "`country_code`, `corp_code`",
            )
            self._create_index_if_missing(
                cursor,
                "corporate_entity_registry",
                "idx_country_cik",
                "`country_code`, `cik`",
            )

    @staticmethod
    def _resolve_countries(countries: Optional[Iterable[str]]) -> List[str]:
        values = list(countries or DEFAULT_ENTITY_COUNTRIES)
        normalized = [
            country
            for country in (_normalize_country_code(value) for value in values)
            if country
        ]
        deduped = list(dict.fromkeys(normalized))
        return deduped if deduped else list(DEFAULT_ENTITY_COUNTRIES)

    def load_active_tier_rows(
        self,
        *,
        as_of_date: Optional[date] = None,
        countries: Optional[Iterable[str]] = None,
        tier_level: int = DEFAULT_ENTITY_TIER_LEVEL,
    ) -> List[Dict[str, Any]]:
        self.ensure_tables()
        resolved_countries = self._resolve_countries(countries)
        country_placeholders = ", ".join(["%s"] * len(resolved_countries))
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            if as_of_date is None:
                query = f"""
                    SELECT
                        as_of_date,
                        country_code,
                        market,
                        symbol,
                        company_name,
                        corp_code,
                        cik,
                        tier_level,
                        tier_source,
                        membership_rank,
                        metadata_json
                    FROM corporate_tier_state
                    WHERE tier_level = %s
                      AND is_active = 1
                      AND country_code IN ({country_placeholders})
                      AND as_of_date = (
                          SELECT MAX(as_of_date)
                          FROM corporate_tier_state
                          WHERE tier_level = %s
                            AND is_active = 1
                            AND country_code IN ({country_placeholders})
                      )
                    ORDER BY country_code ASC, membership_rank ASC, symbol ASC
                """
                params = (
                    [int(tier_level)]
                    + resolved_countries
                    + [int(tier_level)]
                    + resolved_countries
                )
                cursor.execute(query, tuple(params))
            else:
                query = f"""
                    SELECT
                        as_of_date,
                        country_code,
                        market,
                        symbol,
                        company_name,
                        corp_code,
                        cik,
                        tier_level,
                        tier_source,
                        membership_rank,
                        metadata_json
                    FROM corporate_tier_state
                    WHERE as_of_date = %s
                      AND tier_level = %s
                      AND is_active = 1
                      AND country_code IN ({country_placeholders})
                    ORDER BY country_code ASC, membership_rank ASC, symbol ASC
                """
                params = [as_of_date, int(tier_level)] + resolved_countries
                cursor.execute(query, tuple(params))
            rows = cursor.fetchall() or []
        return list(rows)

    @staticmethod
    def build_registry_rows(tier_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in tier_rows:
            country_code = _normalize_country_code(item.get("country_code"))
            symbol = _normalize_symbol(item.get("symbol"))
            if not country_code or not symbol:
                continue
            rows.append(
                {
                    "country_code": country_code,
                    "symbol": symbol,
                    "market": str(item.get("market") or "").strip().upper() or None,
                    "company_name": str(item.get("company_name") or "").strip() or None,
                    "corp_code": _normalize_corp_code(item.get("corp_code")),
                    "cik": _normalize_cik(item.get("cik")),
                    "latest_tier_level": int(item.get("tier_level") or 0) or None,
                    "latest_tier_source": str(item.get("tier_source") or "").strip() or None,
                    "latest_as_of_date": item.get("as_of_date"),
                    "is_active": 1,
                    "metadata_json": json.dumps(
                        {
                            "membership_rank": item.get("membership_rank"),
                            "tier_metadata_json": item.get("metadata_json"),
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )
        return rows

    @staticmethod
    def _append_alias_candidate(
        *,
        container: List[Dict[str, Any]],
        seen: set[tuple[str, str]],
        country_code: str,
        symbol: str,
        alias: Optional[str],
        alias_type: str,
        priority: int,
        source: str,
        as_of_date: Optional[date],
    ):
        alias_text = str(alias or "").strip()
        if not alias_text:
            return
        alias_normalized = _normalize_alias_text(alias_text)
        if not alias_normalized:
            return
        dedupe_key = (alias_type, alias_normalized)
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        container.append(
            {
                "country_code": country_code,
                "symbol": symbol,
                "alias": alias_text,
                "alias_normalized": alias_normalized,
                "alias_type": alias_type,
                "priority": int(priority),
                "source": source,
                "as_of_date": as_of_date,
                "is_active": 1,
                "metadata_json": None,
            }
        )

    @classmethod
    def build_alias_rows(
        cls,
        registry_rows: Sequence[Dict[str, Any]],
        *,
        source: str = DEFAULT_ENTITY_SYNC_SOURCE,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in registry_rows:
            country_code = _normalize_country_code(item.get("country_code"))
            symbol = _normalize_symbol(item.get("symbol"))
            if not country_code or not symbol:
                continue
            as_of_date = item.get("latest_as_of_date")
            company_name = str(item.get("company_name") or "").strip() or None
            corp_code = _normalize_corp_code(item.get("corp_code"))
            cik = _normalize_cik(item.get("cik"))

            seen: set[tuple[str, str]] = set()
            cls._append_alias_candidate(
                container=rows,
                seen=seen,
                country_code=country_code,
                symbol=symbol,
                alias=symbol,
                alias_type="symbol",
                priority=10,
                source=source,
                as_of_date=as_of_date,
            )
            compact_symbol = symbol.replace("-", "").replace(".", "")
            if compact_symbol and compact_symbol != symbol:
                cls._append_alias_candidate(
                    container=rows,
                    seen=seen,
                    country_code=country_code,
                    symbol=symbol,
                    alias=compact_symbol,
                    alias_type="symbol_compact",
                    priority=15,
                    source=source,
                    as_of_date=as_of_date,
                )
            cls._append_alias_candidate(
                container=rows,
                seen=seen,
                country_code=country_code,
                symbol=symbol,
                alias=company_name,
                alias_type="company_name",
                priority=20,
                source=source,
                as_of_date=as_of_date,
            )
            if corp_code:
                cls._append_alias_candidate(
                    container=rows,
                    seen=seen,
                    country_code=country_code,
                    symbol=symbol,
                    alias=corp_code,
                    alias_type="corp_code",
                    priority=30,
                    source=source,
                    as_of_date=as_of_date,
                )
            if cik:
                cls._append_alias_candidate(
                    container=rows,
                    seen=seen,
                    country_code=country_code,
                    symbol=symbol,
                    alias=cik,
                    alias_type="cik",
                    priority=30,
                    source=source,
                    as_of_date=as_of_date,
                )
        return rows

    def upsert_registry_rows(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO corporate_entity_registry (
                country_code,
                symbol,
                market,
                company_name,
                corp_code,
                cik,
                latest_tier_level,
                latest_tier_source,
                latest_as_of_date,
                is_active,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                market = VALUES(market),
                company_name = VALUES(company_name),
                corp_code = VALUES(corp_code),
                cik = VALUES(cik),
                latest_tier_level = VALUES(latest_tier_level),
                latest_tier_source = VALUES(latest_tier_source),
                latest_as_of_date = VALUES(latest_as_of_date),
                is_active = VALUES(is_active),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("country_code"),
                row.get("symbol"),
                row.get("market"),
                row.get("company_name"),
                row.get("corp_code"),
                row.get("cik"),
                row.get("latest_tier_level"),
                row.get("latest_tier_source"),
                row.get("latest_as_of_date"),
                row.get("is_active", 1),
                row.get("metadata_json"),
            )
            for row in rows
        ]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def deactivate_registry_missing_symbols(
        self,
        *,
        active_symbols_by_country: Dict[str, List[str]],
    ) -> int:
        self.ensure_tables()
        affected = 0
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            for country_code, symbols in active_symbols_by_country.items():
                resolved_country = _normalize_country_code(country_code)
                if not resolved_country:
                    continue
                if symbols:
                    placeholders = ", ".join(["%s"] * len(symbols))
                    query = f"""
                        UPDATE corporate_entity_registry
                        SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                        WHERE country_code = %s
                          AND is_active = 1
                          AND symbol NOT IN ({placeholders})
                    """
                    cursor.execute(query, tuple([resolved_country] + list(symbols)))
                else:
                    cursor.execute(
                        """
                        UPDATE corporate_entity_registry
                        SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                        WHERE country_code = %s
                          AND is_active = 1
                        """,
                        (resolved_country,),
                    )
                affected += int(cursor.rowcount or 0)
        return affected

    def deactivate_aliases_for_symbols(
        self,
        *,
        symbol_keys: Sequence[tuple[str, str]],
        source: str = DEFAULT_ENTITY_SYNC_SOURCE,
    ) -> int:
        if not symbol_keys:
            return 0
        self.ensure_tables()
        query = """
            UPDATE corporate_entity_aliases
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE country_code = %s
              AND symbol = %s
              AND source = %s
              AND is_active = 1
        """
        payload = [
            (
                _normalize_country_code(country_code),
                _normalize_symbol(symbol),
                source,
            )
            for country_code, symbol in symbol_keys
        ]
        payload = [item for item in payload if item[0] and item[1]]
        if not payload:
            return 0
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def deactivate_aliases_missing_symbols(
        self,
        *,
        active_symbols_by_country: Dict[str, List[str]],
        source: str = DEFAULT_ENTITY_SYNC_SOURCE,
    ) -> int:
        self.ensure_tables()
        affected = 0
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            for country_code, symbols in active_symbols_by_country.items():
                resolved_country = _normalize_country_code(country_code)
                if not resolved_country:
                    continue
                if symbols:
                    placeholders = ", ".join(["%s"] * len(symbols))
                    query = f"""
                        UPDATE corporate_entity_aliases
                        SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                        WHERE country_code = %s
                          AND source = %s
                          AND is_active = 1
                          AND symbol NOT IN ({placeholders})
                    """
                    cursor.execute(query, tuple([resolved_country, source] + list(symbols)))
                else:
                    cursor.execute(
                        """
                        UPDATE corporate_entity_aliases
                        SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                        WHERE country_code = %s
                          AND source = %s
                          AND is_active = 1
                        """,
                        (resolved_country, source),
                    )
                affected += int(cursor.rowcount or 0)
        return affected

    def upsert_alias_rows(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO corporate_entity_aliases (
                country_code,
                symbol,
                alias,
                alias_normalized,
                alias_type,
                priority,
                source,
                as_of_date,
                is_active,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                alias = VALUES(alias),
                priority = VALUES(priority),
                as_of_date = VALUES(as_of_date),
                is_active = VALUES(is_active),
                metadata_json = VALUES(metadata_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("country_code"),
                row.get("symbol"),
                row.get("alias"),
                row.get("alias_normalized"),
                row.get("alias_type"),
                row.get("priority", 100),
                row.get("source") or DEFAULT_ENTITY_SYNC_SOURCE,
                row.get("as_of_date"),
                row.get("is_active", 1),
                row.get("metadata_json"),
            )
            for row in rows
        ]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def sync_from_tier1(
        self,
        *,
        as_of_date: Optional[date] = None,
        countries: Optional[Iterable[str]] = None,
        tier_level: int = DEFAULT_ENTITY_TIER_LEVEL,
        source: str = DEFAULT_ENTITY_SYNC_SOURCE,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        resolved_countries = self._resolve_countries(countries)
        tier_rows = self.load_active_tier_rows(
            as_of_date=as_of_date,
            countries=resolved_countries,
            tier_level=tier_level,
        )
        registry_rows = self.build_registry_rows(tier_rows)
        alias_rows = self.build_alias_rows(registry_rows, source=source)

        active_symbols_by_country: Dict[str, List[str]] = {}
        for row in registry_rows:
            country = row.get("country_code")
            symbol = row.get("symbol")
            if not country or not symbol:
                continue
            active_symbols_by_country.setdefault(country, []).append(symbol)
        for country, symbols in active_symbols_by_country.items():
            active_symbols_by_country[country] = list(dict.fromkeys(symbols))

        registry_affected = self.upsert_registry_rows(registry_rows)
        registry_deactivated = self.deactivate_registry_missing_symbols(
            active_symbols_by_country=active_symbols_by_country
        )

        touched_symbol_keys = [
            (row.get("country_code"), row.get("symbol"))
            for row in registry_rows
            if row.get("country_code") and row.get("symbol")
        ]
        aliases_deactivated_touched = self.deactivate_aliases_for_symbols(
            symbol_keys=touched_symbol_keys,
            source=source,
        )
        aliases_deactivated_missing = self.deactivate_aliases_missing_symbols(
            active_symbols_by_country=active_symbols_by_country,
            source=source,
        )
        alias_affected = self.upsert_alias_rows(alias_rows)

        country_counts: Dict[str, int] = {}
        for row in registry_rows:
            country = str(row.get("country_code") or "").strip().upper()
            if not country:
                continue
            country_counts[country] = int(country_counts.get(country, 0)) + 1

        latest_as_of_date = None
        if tier_rows:
            latest_as_of_date = max(
                (row.get("as_of_date") for row in tier_rows if row.get("as_of_date")),
                default=None,
            )

        return {
            "countries": resolved_countries,
            "tier_level": int(tier_level),
            "source": source,
            "as_of_date": latest_as_of_date.isoformat() if isinstance(latest_as_of_date, date) else None,
            "source_row_count": len(tier_rows),
            "country_counts": country_counts,
            "registry_upsert_affected": int(registry_affected),
            "registry_deactivated": int(registry_deactivated),
            "alias_upsert_affected": int(alias_affected),
            "alias_deactivated_touched": int(aliases_deactivated_touched),
            "alias_deactivated_missing": int(aliases_deactivated_missing),
        }

    def lookup_alias(
        self,
        *,
        alias: str,
        country_code: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        alias_normalized = _normalize_alias_text(alias)
        if not alias_normalized:
            return []
        resolved_country = _normalize_country_code(country_code) if country_code else None
        self.ensure_tables()
        query = """
            SELECT
                a.country_code,
                a.symbol,
                a.alias,
                a.alias_type,
                a.priority,
                r.market,
                r.company_name,
                r.corp_code,
                r.cik,
                r.latest_as_of_date
            FROM corporate_entity_aliases a
            INNER JOIN corporate_entity_registry r
              ON r.country_code = a.country_code
             AND r.symbol = a.symbol
            WHERE a.alias_normalized = %s
              AND a.is_active = 1
              AND r.is_active = 1
        """
        params: List[Any] = [alias_normalized]
        if resolved_country:
            query += " AND a.country_code = %s"
            params.append(resolved_country)
        query += """
            ORDER BY a.priority ASC, a.country_code ASC, a.symbol ASC
            LIMIT %s
        """
        params.append(max(int(limit), 1))
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall() or []
        return list(rows)


_corporate_entity_collector_singleton: Optional[CorporateEntityCollector] = None


def get_corporate_entity_collector() -> CorporateEntityCollector:
    global _corporate_entity_collector_singleton
    if _corporate_entity_collector_singleton is None:
        _corporate_entity_collector_singleton = CorporateEntityCollector()
    return _corporate_entity_collector_singleton
