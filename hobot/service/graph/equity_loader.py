"""
KR/US equity projection loader.

RDB 원천 테이블 -> Neo4j 투영:
- Company
- EquityUniverseSnapshot
- EquityDailyBar
- EarningsEvent
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .neo4j_client import get_neo4j_client
from .rag.security_id import to_security_id

logger = logging.getLogger(__name__)

_KR = "KR"
_US = "US"
_SUPPORTED_COUNTRIES = (_KR, _US)


class EquityProjectionLoader:
    """MySQL 주식 원천 데이터를 Neo4j 주식 도메인으로 동기화한다."""

    def __init__(self, neo4j_client=None, db_connection_factory=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()
        self._db_connection_factory = db_connection_factory or self._default_db_connection_factory

    @staticmethod
    def _default_db_connection_factory():
        from service.database.db import get_db_connection

        return get_db_connection()

    def _get_mysql_connection(self):
        return self._db_connection_factory()

    @staticmethod
    def _normalize_country_codes(country_codes: Optional[Iterable[str]]) -> List[str]:
        if not country_codes:
            return list(_SUPPORTED_COUNTRIES)
        normalized: List[str] = []
        for raw in country_codes:
            code = str(raw or "").strip().upper()
            if code in _SUPPORTED_COUNTRIES and code not in normalized:
                normalized.append(code)
        return normalized or list(_SUPPORTED_COUNTRIES)

    @staticmethod
    def _coerce_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
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
    def _to_iso_date(value: Any, fallback: date) -> str:
        resolved = EquityProjectionLoader._coerce_date(value) or fallback
        return resolved.isoformat()

    @staticmethod
    def _to_iso_datetime(value: Any) -> Optional[str]:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return f"{value.isoformat()}T00:00:00"
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (float, int)):
            return float(value)
        text = str(value).strip().replace(",", "")
        if not text or text == "-":
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
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

    @staticmethod
    def _with_batches(rows: List[Dict[str, Any]], batch_size: int) -> Iterable[List[Dict[str, Any]]]:
        size = max(int(batch_size), 1)
        for idx in range(0, len(rows), size):
            yield rows[idx : idx + size]

    def ensure_graph_schema(self) -> Dict[str, int]:
        statements = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.security_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (u:EquityUniverseSnapshot) REQUIRE u.snapshot_key IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (b:EquityDailyBar) REQUIRE b.bar_key IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:EarningsEvent) REQUIRE e.event_key IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (u:EquityUniverseSnapshot) ON (u.snapshot_date)",
            "CREATE INDEX IF NOT EXISTS FOR (b:EquityDailyBar) ON (b.trade_date)",
            "CREATE INDEX IF NOT EXISTS FOR (e:EarningsEvent) ON (e.event_date)",
        ]
        summary = {
            "constraints_added": 0,
            "indexes_added": 0,
            "nodes_created": 0,
            "relationships_created": 0,
            "properties_set": 0,
        }
        for statement in statements:
            result = self.neo4j_client.run_write(statement)
            summary["constraints_added"] += int(result.get("constraints_added", 0))
            summary["indexes_added"] += int(result.get("indexes_added", 0))
            summary["nodes_created"] += int(result.get("nodes_created", 0))
            summary["relationships_created"] += int(result.get("relationships_created", 0))
            summary["properties_set"] += int(result.get("properties_set", 0))
        return summary

    def fetch_universe_snapshots(
        self,
        *,
        country_codes: Sequence[str],
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()
            if _KR in country_codes:
                cursor.execute(
                    """
                    SELECT
                        snapshot_date,
                        market,
                        rank_position,
                        stock_code AS native_code,
                        stock_name AS company_name,
                        corp_code,
                        source_url
                    FROM kr_top50_universe_snapshot
                    WHERE snapshot_date >= %s
                      AND snapshot_date <= %s
                    ORDER BY snapshot_date, market, rank_position
                    """,
                    (start_date, end_date),
                )
                for row in cursor.fetchall() or []:
                    native_code = str(row.get("native_code") or "").strip()
                    security_id = to_security_id(_KR, native_code)
                    if not security_id:
                        continue
                    snapshot_date = self._coerce_date(row.get("snapshot_date")) or end_date
                    rows.append(
                        {
                            "country_code": _KR,
                            "security_id": security_id,
                            "native_code": native_code,
                            "market": str(row.get("market") or "KOSPI").strip().upper(),
                            "snapshot_date": snapshot_date.isoformat(),
                            "rank_position": int(row.get("rank_position") or 0),
                            "company_name": str(row.get("company_name") or "").strip() or None,
                            "corp_code": str(row.get("corp_code") or "").strip() or None,
                            "source_url": str(row.get("source_url") or "").strip() or None,
                            "snapshot_key": f"{security_id}:{snapshot_date.isoformat()}",
                        }
                    )

            if _US in country_codes:
                cursor.execute(
                    """
                    SELECT
                        snapshot_date,
                        market,
                        rank_position,
                        symbol AS native_code,
                        company_name,
                        cik,
                        source_url
                    FROM us_top50_universe_snapshot
                    WHERE snapshot_date >= %s
                      AND snapshot_date <= %s
                    ORDER BY snapshot_date, market, rank_position
                    """,
                    (start_date, end_date),
                )
                for row in cursor.fetchall() or []:
                    native_code = str(row.get("native_code") or "").strip().upper()
                    security_id = to_security_id(_US, native_code)
                    if not security_id:
                        continue
                    snapshot_date = self._coerce_date(row.get("snapshot_date")) or end_date
                    rows.append(
                        {
                            "country_code": _US,
                            "security_id": security_id,
                            "native_code": native_code,
                            "market": str(row.get("market") or "US").strip().upper(),
                            "snapshot_date": snapshot_date.isoformat(),
                            "rank_position": int(row.get("rank_position") or 0),
                            "company_name": str(row.get("company_name") or "").strip() or None,
                            "cik": str(row.get("cik") or "").strip() or None,
                            "source_url": str(row.get("source_url") or "").strip() or None,
                            "snapshot_key": f"{security_id}:{snapshot_date.isoformat()}",
                        }
                    )
        return rows

    def fetch_daily_bars(
        self,
        *,
        country_codes: Sequence[str],
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()
            if _KR in country_codes:
                cursor.execute(
                    """
                    SELECT
                        market,
                        stock_code AS native_code,
                        trade_date,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        adjusted_close,
                        volume,
                        source,
                        source_ref,
                        as_of_date
                    FROM kr_top50_daily_ohlcv
                    WHERE trade_date >= %s
                      AND trade_date <= %s
                    ORDER BY trade_date, market, stock_code
                    """,
                    (start_date, end_date),
                )
                for row in cursor.fetchall() or []:
                    native_code = str(row.get("native_code") or "").strip()
                    security_id = to_security_id(_KR, native_code)
                    if not security_id:
                        continue
                    trade_date = self._coerce_date(row.get("trade_date")) or end_date
                    rows.append(
                        {
                            "country_code": _KR,
                            "security_id": security_id,
                            "native_code": native_code,
                            "market": str(row.get("market") or "KOSPI").strip().upper(),
                            "trade_date": trade_date.isoformat(),
                            "bar_key": f"{security_id}:{trade_date.isoformat()}",
                            "open_price": self._safe_float(row.get("open_price")),
                            "high_price": self._safe_float(row.get("high_price")),
                            "low_price": self._safe_float(row.get("low_price")),
                            "close_price": self._safe_float(row.get("close_price")),
                            "adjusted_close": self._safe_float(row.get("adjusted_close")),
                            "volume": self._safe_int(row.get("volume")),
                            "source": str(row.get("source") or "yfinance").strip(),
                            "source_ref": str(row.get("source_ref") or "").strip(),
                            "as_of_date": self._to_iso_date(row.get("as_of_date"), fallback=trade_date),
                        }
                    )

            if _US in country_codes:
                cursor.execute(
                    """
                    SELECT
                        market,
                        symbol AS native_code,
                        trade_date,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        adjusted_close,
                        volume,
                        source,
                        source_ref,
                        as_of_date
                    FROM us_top50_daily_ohlcv
                    WHERE trade_date >= %s
                      AND trade_date <= %s
                    ORDER BY trade_date, market, symbol
                    """,
                    (start_date, end_date),
                )
                for row in cursor.fetchall() or []:
                    native_code = str(row.get("native_code") or "").strip().upper()
                    security_id = to_security_id(_US, native_code)
                    if not security_id:
                        continue
                    trade_date = self._coerce_date(row.get("trade_date")) or end_date
                    rows.append(
                        {
                            "country_code": _US,
                            "security_id": security_id,
                            "native_code": native_code,
                            "market": str(row.get("market") or "US").strip().upper(),
                            "trade_date": trade_date.isoformat(),
                            "bar_key": f"{security_id}:{trade_date.isoformat()}",
                            "open_price": self._safe_float(row.get("open_price")),
                            "high_price": self._safe_float(row.get("high_price")),
                            "low_price": self._safe_float(row.get("low_price")),
                            "close_price": self._safe_float(row.get("close_price")),
                            "adjusted_close": self._safe_float(row.get("adjusted_close")),
                            "volume": self._safe_int(row.get("volume")),
                            "source": str(row.get("source") or "yfinance").strip(),
                            "source_ref": str(row.get("source_ref") or "").strip(),
                            "as_of_date": self._to_iso_date(row.get("as_of_date"), fallback=trade_date),
                        }
                    )
        return rows

    def fetch_earnings_events(
        self,
        *,
        country_codes: Sequence[str],
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()
            if _KR in country_codes:
                cursor.execute(
                    """
                    SELECT
                        stock_code AS native_code,
                        corp_code,
                        corp_name AS company_name,
                        report_nm,
                        event_type,
                        rcept_dt AS event_date,
                        source_url,
                        rcept_no AS source_ref,
                        as_of_date
                    FROM kr_corporate_disclosures
                    WHERE is_earnings_event = 1
                      AND stock_code IS NOT NULL
                      AND stock_code <> ''
                      AND rcept_dt >= %s
                      AND rcept_dt <= %s
                    ORDER BY rcept_dt, stock_code, rcept_no
                    """,
                    (start_date, end_date),
                )
                for row in cursor.fetchall() or []:
                    native_code = str(row.get("native_code") or "").strip()
                    security_id = to_security_id(_KR, native_code)
                    if not security_id:
                        continue
                    event_date = self._coerce_date(row.get("event_date")) or end_date
                    source_ref = str(row.get("source_ref") or "").strip()
                    event_type = str(row.get("event_type") or "earnings_disclosure").strip()
                    event_key = f"{security_id}:{event_date.isoformat()}:{event_type}:{source_ref or 'na'}"
                    rows.append(
                        {
                            "country_code": _KR,
                            "security_id": security_id,
                            "native_code": native_code,
                            "market": "KOSPI",
                            "event_key": event_key,
                            "event_date": event_date.isoformat(),
                            "event_type": event_type,
                            "event_status": "confirmed",
                            "company_name": str(row.get("company_name") or "").strip() or None,
                            "corp_code": str(row.get("corp_code") or "").strip() or None,
                            "report_name": str(row.get("report_nm") or "").strip() or None,
                            "source": "dart",
                            "source_ref": source_ref or None,
                            "source_url": str(row.get("source_url") or "").strip() or None,
                            "as_of_date": self._to_iso_date(row.get("as_of_date"), fallback=event_date),
                        }
                    )

            if _US in country_codes:
                cursor.execute(
                    """
                    SELECT
                        symbol AS native_code,
                        cik,
                        event_type,
                        event_status,
                        event_date,
                        source,
                        source_ref,
                        filed_at,
                        report_date,
                        as_of_date
                    FROM us_corporate_earnings_events
                    WHERE event_date >= %s
                      AND event_date <= %s
                    ORDER BY event_date, symbol, source_ref
                    """,
                    (start_date, end_date),
                )
                for row in cursor.fetchall() or []:
                    native_code = str(row.get("native_code") or "").strip().upper()
                    security_id = to_security_id(_US, native_code)
                    if not security_id:
                        continue
                    event_date = self._coerce_date(row.get("event_date")) or end_date
                    event_type = str(row.get("event_type") or "earnings_event").strip()
                    event_status = str(row.get("event_status") or "unknown").strip()
                    source_ref = str(row.get("source_ref") or "").strip()
                    event_key = f"{security_id}:{event_date.isoformat()}:{event_type}:{event_status}:{source_ref or 'na'}"
                    rows.append(
                        {
                            "country_code": _US,
                            "security_id": security_id,
                            "native_code": native_code,
                            "market": "US",
                            "event_key": event_key,
                            "event_date": event_date.isoformat(),
                            "event_type": event_type,
                            "event_status": event_status,
                            "cik": str(row.get("cik") or "").strip() or None,
                            "source": str(row.get("source") or "sec").strip(),
                            "source_ref": source_ref or None,
                            "filed_at": self._to_iso_datetime(row.get("filed_at")),
                            "report_date": self._to_iso_date(row.get("report_date"), fallback=event_date),
                            "as_of_date": self._to_iso_date(row.get("as_of_date"), fallback=event_date),
                        }
                    )
        return rows

    @staticmethod
    def _dedupe_companies(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            security_id = str(row.get("security_id") or "").strip()
            if not security_id:
                continue
            existing = deduped.get(security_id)
            if not existing:
                deduped[security_id] = {
                    "security_id": security_id,
                    "country_code": row.get("country_code"),
                    "native_code": row.get("native_code"),
                    "market": row.get("market"),
                    "company_name": row.get("company_name"),
                    "corp_code": row.get("corp_code"),
                    "cik": row.get("cik"),
                }
                continue
            for field in ("market", "company_name", "corp_code", "cik"):
                if not existing.get(field) and row.get(field):
                    existing[field] = row.get(field)
        return list(deduped.values())

    def upsert_companies(self, rows: List[Dict[str, Any]], *, batch_size: int = 500) -> Dict[str, int]:
        if not rows:
            return {
                "rows": 0,
                "nodes_created": 0,
                "relationships_created": 0,
                "properties_set": 0,
            }
        query = """
        UNWIND $rows AS row
        MERGE (c:Company {security_id: row.security_id})
          ON CREATE SET c.created_at = datetime()
        SET c.country_code = row.country_code,
            c.native_code = row.native_code,
            c.market = coalesce(row.market, c.market),
            c.company_name = coalesce(row.company_name, c.company_name),
            c.corp_code = coalesce(row.corp_code, c.corp_code),
            c.cik = coalesce(row.cik, c.cik),
            c.updated_at = datetime()
        """
        return self._run_batch_write(query=query, rows=rows, batch_size=batch_size)

    def upsert_universe_snapshots(self, rows: List[Dict[str, Any]], *, batch_size: int = 500) -> Dict[str, int]:
        if not rows:
            return {
                "rows": 0,
                "nodes_created": 0,
                "relationships_created": 0,
                "properties_set": 0,
            }
        query = """
        UNWIND $rows AS row
        MERGE (c:Company {security_id: row.security_id})
          ON CREATE SET c.created_at = datetime()
        SET c.country_code = row.country_code,
            c.native_code = row.native_code,
            c.market = coalesce(row.market, c.market),
            c.company_name = coalesce(row.company_name, c.company_name),
            c.corp_code = coalesce(row.corp_code, c.corp_code),
            c.cik = coalesce(row.cik, c.cik),
            c.updated_at = datetime()

        MERGE (u:EquityUniverseSnapshot {snapshot_key: row.snapshot_key})
          ON CREATE SET u.created_at = datetime()
        SET u.snapshot_date = date(row.snapshot_date),
            u.market = row.market,
            u.rank_position = toInteger(row.rank_position),
            u.source_url = row.source_url,
            u.updated_at = datetime()

        MERGE (c)-[r:IN_UNIVERSE {snapshot_key: row.snapshot_key}]->(u)
          ON CREATE SET r.created_at = datetime()
        SET r.market = row.market,
            r.rank_position = toInteger(row.rank_position),
            r.updated_at = datetime()
        """
        return self._run_batch_write(query=query, rows=rows, batch_size=batch_size)

    def upsert_daily_bars(self, rows: List[Dict[str, Any]], *, batch_size: int = 500) -> Dict[str, int]:
        if not rows:
            return {
                "rows": 0,
                "nodes_created": 0,
                "relationships_created": 0,
                "properties_set": 0,
            }
        query = """
        UNWIND $rows AS row
        MERGE (c:Company {security_id: row.security_id})
          ON CREATE SET c.created_at = datetime()
        SET c.country_code = row.country_code,
            c.native_code = row.native_code,
            c.market = coalesce(row.market, c.market),
            c.updated_at = datetime()

        MERGE (b:EquityDailyBar {bar_key: row.bar_key})
          ON CREATE SET b.created_at = datetime()
        SET b.security_id = row.security_id,
            b.country_code = row.country_code,
            b.native_code = row.native_code,
            b.market = row.market,
            b.trade_date = date(row.trade_date),
            b.open_price = toFloat(row.open_price),
            b.high_price = toFloat(row.high_price),
            b.low_price = toFloat(row.low_price),
            b.close_price = toFloat(row.close_price),
            b.adjusted_close = toFloat(row.adjusted_close),
            b.volume = toInteger(row.volume),
            b.source = row.source,
            b.source_ref = row.source_ref,
            b.as_of_date = date(row.as_of_date),
            b.updated_at = datetime()

        MERGE (c)-[:HAS_DAILY_BAR]->(b)
        """
        return self._run_batch_write(query=query, rows=rows, batch_size=batch_size)

    def upsert_earnings_events(self, rows: List[Dict[str, Any]], *, batch_size: int = 500) -> Dict[str, int]:
        if not rows:
            return {
                "rows": 0,
                "nodes_created": 0,
                "relationships_created": 0,
                "properties_set": 0,
            }
        query = """
        UNWIND $rows AS row
        MERGE (c:Company {security_id: row.security_id})
          ON CREATE SET c.created_at = datetime()
        SET c.country_code = row.country_code,
            c.native_code = row.native_code,
            c.market = coalesce(row.market, c.market),
            c.company_name = coalesce(row.company_name, c.company_name),
            c.corp_code = coalesce(row.corp_code, c.corp_code),
            c.cik = coalesce(row.cik, c.cik),
            c.updated_at = datetime()

        MERGE (e:EarningsEvent {event_key: row.event_key})
          ON CREATE SET e.created_at = datetime()
        SET e.security_id = row.security_id,
            e.country_code = row.country_code,
            e.native_code = row.native_code,
            e.market = row.market,
            e.event_date = date(row.event_date),
            e.event_type = row.event_type,
            e.event_status = row.event_status,
            e.report_name = row.report_name,
            e.source = row.source,
            e.source_ref = row.source_ref,
            e.source_url = row.source_url,
            e.filed_at = CASE
              WHEN row.filed_at IS NULL OR row.filed_at = '' THEN NULL
              ELSE datetime(row.filed_at)
            END,
            e.report_date = CASE
              WHEN row.report_date IS NULL OR row.report_date = '' THEN NULL
              ELSE date(row.report_date)
            END,
            e.as_of_date = date(row.as_of_date),
            e.updated_at = datetime()

        MERGE (c)-[:HAS_EARNINGS_EVENT]->(e)
        """
        return self._run_batch_write(query=query, rows=rows, batch_size=batch_size)

    def _run_batch_write(self, *, query: str, rows: List[Dict[str, Any]], batch_size: int) -> Dict[str, int]:
        total_nodes_created = 0
        total_relationships_created = 0
        total_properties_set = 0
        for batch in self._with_batches(rows, batch_size=batch_size):
            result = self.neo4j_client.run_write(query, {"rows": batch})
            total_nodes_created += int(result.get("nodes_created", 0))
            total_relationships_created += int(result.get("relationships_created", 0))
            total_properties_set += int(result.get("properties_set", 0))
        return {
            "rows": len(rows),
            "nodes_created": total_nodes_created,
            "relationships_created": total_relationships_created,
            "properties_set": total_properties_set,
        }

    def sync_projection(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        country_codes: Optional[Iterable[str]] = None,
        include_universe: bool = True,
        include_daily_bars: bool = True,
        include_earnings_events: bool = True,
        ensure_schema: bool = True,
        batch_size: int = 500,
    ) -> Dict[str, Any]:
        resolved_end_date = end_date or date.today()
        resolved_start_date = start_date or (resolved_end_date - timedelta(days=365))
        if resolved_start_date > resolved_end_date:
            raise ValueError("start_date must be <= end_date")

        resolved_country_codes = self._normalize_country_codes(country_codes)
        schema_result = self.ensure_graph_schema() if ensure_schema else {}

        universe_rows: List[Dict[str, Any]] = []
        daily_bar_rows: List[Dict[str, Any]] = []
        earnings_rows: List[Dict[str, Any]] = []

        if include_universe:
            universe_rows = self.fetch_universe_snapshots(
                country_codes=resolved_country_codes,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
            )
        if include_daily_bars:
            daily_bar_rows = self.fetch_daily_bars(
                country_codes=resolved_country_codes,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
            )
        if include_earnings_events:
            earnings_rows = self.fetch_earnings_events(
                country_codes=resolved_country_codes,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
            )

        company_rows = self._dedupe_companies([*universe_rows, *daily_bar_rows, *earnings_rows])
        company_upsert_result = self.upsert_companies(company_rows, batch_size=batch_size)
        universe_upsert_result = self.upsert_universe_snapshots(universe_rows, batch_size=batch_size)
        daily_bar_upsert_result = self.upsert_daily_bars(daily_bar_rows, batch_size=batch_size)
        earnings_upsert_result = self.upsert_earnings_events(earnings_rows, batch_size=batch_size)

        row_counts = {
            "company_rows": len(company_rows),
            "universe_rows": len(universe_rows),
            "daily_bar_rows": len(daily_bar_rows),
            "earnings_rows": len(earnings_rows),
        }
        is_no_data = all(count == 0 for count in row_counts.values())
        return {
            "status": "no_data" if is_no_data else "success",
            "country_codes": resolved_country_codes,
            "start_date": resolved_start_date.isoformat(),
            "end_date": resolved_end_date.isoformat(),
            "schema_result": schema_result,
            "row_counts": row_counts,
            "upsert_result": {
                "companies": company_upsert_result,
                "universe": universe_upsert_result,
                "daily_bars": daily_bar_upsert_result,
                "earnings_events": earnings_upsert_result,
            },
        }

    def verify_projection(
        self,
        *,
        country_codes: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        resolved_country_codes = self._normalize_country_codes(country_codes)
        query = """
        MATCH (c:Company)
        WHERE c.country_code IN $country_codes
        OPTIONAL MATCH (c)-[:HAS_DAILY_BAR]->(b:EquityDailyBar)
        OPTIONAL MATCH (c)-[:HAS_EARNINGS_EVENT]->(e:EarningsEvent)
        OPTIONAL MATCH (c)-[:IN_UNIVERSE]->(u:EquityUniverseSnapshot)
        RETURN
          count(DISTINCT c) AS company_count,
          count(DISTINCT b) AS daily_bar_count,
          count(DISTINCT e) AS earnings_event_count,
          count(DISTINCT u) AS universe_snapshot_count,
          min(b.trade_date) AS min_trade_date,
          max(b.trade_date) AS max_trade_date,
          min(e.event_date) AS min_event_date,
          max(e.event_date) AS max_event_date
        """
        rows = self.neo4j_client.run_read(query, {"country_codes": resolved_country_codes})
        payload = rows[0] if rows else {}
        return {
            "country_codes": resolved_country_codes,
            "summary": payload,
        }


def sync_equity_projection(
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    country_codes: Optional[Iterable[str]] = None,
    include_universe: bool = True,
    include_daily_bars: bool = True,
    include_earnings_events: bool = True,
    ensure_schema: bool = True,
    batch_size: int = 500,
) -> Dict[str, Any]:
    loader = EquityProjectionLoader()
    sync_result = loader.sync_projection(
        start_date=start_date,
        end_date=end_date,
        country_codes=country_codes,
        include_universe=include_universe,
        include_daily_bars=include_daily_bars,
        include_earnings_events=include_earnings_events,
        ensure_schema=ensure_schema,
        batch_size=batch_size,
    )
    verification = loader.verify_projection(country_codes=country_codes)
    return {
        "sync_result": sync_result,
        "verification": verification,
    }


__all__ = [
    "EquityProjectionLoader",
    "sync_equity_projection",
]
