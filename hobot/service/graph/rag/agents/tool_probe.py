"""Branch-level tool probe helpers for multi-agent execution."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import pymysql
from pymysql.cursors import DictCursor

from service.database import db as db_module
from service.graph.neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)
_SQL_FAILURE_LOGGED: set[str] = set()
_GRAPH_FAILURE_LOGGED: set[str] = set()


DEFAULT_SQL_PROBES: Dict[str, List[Tuple[str, str]]] = {
    "macro_economy_agent": [
        ("fred_data", "obs_date"),
        ("ecos_data", "obs_date"),
        ("kosis_data", "obs_date"),
    ],
    "equity_analyst_agent": [
        ("kr_top50_daily_ohlcv", "trade_date"),
        ("us_top50_daily_ohlcv", "trade_date"),
        ("kr_corporate_financials", "period_end_date"),
        ("us_corporate_financials", "period_end_date"),
    ],
    "real_estate_agent": [
        ("kr_real_estate_monthly_summary", "summary_month"),
        ("kr_real_estate_transactions", "contract_date"),
    ],
    "ontology_master_agent": [
        ("economic_news", "published_at"),
        ("corporate_event_feed", "event_date"),
    ],
}


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _connect_mysql():
    return pymysql.connect(
        host=db_module.DB_HOST,
        port=db_module.DB_PORT,
        user=db_module.DB_USER,
        password=db_module.DB_PASSWORD,
        database=db_module.DB_NAME,
        charset=db_module.DB_CHARSET,
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=max(_safe_int_env("GRAPH_RAG_AGENT_SQL_TIMEOUT_SEC", 3), 1),
    )


def _fetch_existing_tables(cursor, table_names: List[str]) -> List[str]:
    if not table_names:
        return []
    placeholders = ", ".join(["%s"] * len(table_names))
    query = (
        "SELECT table_name "
        "FROM information_schema.tables "
        "WHERE table_schema=%s "
        f"AND table_name IN ({placeholders})"
    )
    params: List[Any] = [db_module.DB_NAME, *table_names]
    cursor.execute(query, params)
    rows = cursor.fetchall() or []
    return [str(row.get("table_name") or "").strip() for row in rows if str(row.get("table_name") or "").strip()]


def run_sql_probe(agent_name: str) -> Dict[str, Any]:
    started_at = time.time()
    table_specs = DEFAULT_SQL_PROBES.get(agent_name, [])
    table_map = {table: date_col for table, date_col in table_specs}
    table_names = [table for table, _ in table_specs]
    max_tables = max(_safe_int_env("GRAPH_RAG_AGENT_SQL_PROBE_MAX_TABLES", 2), 1)

    if not table_names:
        return {
            "tool": "sql",
            "status": "degraded",
            "reason": "sql_probe_table_specs_missing",
            "duration_ms": int((time.time() - started_at) * 1000),
            "checks": [],
        }

    try:
        with _connect_mysql() as conn:
            with conn.cursor() as cursor:
                existing_tables = _fetch_existing_tables(cursor, table_names)
                if not existing_tables:
                    return {
                        "tool": "sql",
                        "status": "degraded",
                        "reason": "sql_probe_tables_not_found",
                        "duration_ms": int((time.time() - started_at) * 1000),
                        "checks": [],
                    }

                checks: List[Dict[str, Any]] = []
                for table_name in existing_tables[:max_tables]:
                    date_col = table_map.get(table_name) or ""
                    if date_col:
                        query = (
                            f"SELECT COUNT(*) AS row_count, MAX(`{date_col}`) AS latest_date "
                            f"FROM `{table_name}`"
                        )
                    else:
                        query = f"SELECT COUNT(*) AS row_count FROM `{table_name}`"
                    cursor.execute(query)
                    row = cursor.fetchone() or {}
                    checks.append(
                        {
                            "table": table_name,
                            "row_count": int(row.get("row_count") or 0),
                            "latest_date": row.get("latest_date"),
                        }
                    )

                return {
                    "tool": "sql",
                    "status": "ok",
                    "duration_ms": int((time.time() - started_at) * 1000),
                    "checks": checks,
                }
    except Exception as error:
        log_key = f"{agent_name}:{type(error).__name__}"
        if log_key not in _SQL_FAILURE_LOGGED:
            logger.warning("[GraphRAGAgentProbe] sql probe failed (%s): %s", agent_name, error)
            _SQL_FAILURE_LOGGED.add(log_key)
        else:
            logger.debug("[GraphRAGAgentProbe] sql probe failed (%s): %s", agent_name, error)
        return {
            "tool": "sql",
            "status": "error",
            "reason": "sql_probe_failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "duration_ms": int((time.time() - started_at) * 1000),
            "checks": [],
        }


def run_graph_probe(
    *,
    agent_name: str,
    context_meta: Dict[str, Any],
) -> Dict[str, Any]:
    started_at = time.time()
    probe: Dict[str, Any] = {
        "tool": "graph",
        "status": "degraded",
        "reason": "graph_probe_no_live_data",
        "duration_ms": 0,
        "counts": {},
    }

    counts = context_meta.get("counts") if isinstance(context_meta.get("counts"), dict) else {}
    if counts:
        probe["counts"] = {
            "nodes": int(counts.get("nodes") or 0),
            "links": int(counts.get("links") or 0),
            "events": int(counts.get("events") or 0),
            "documents": int(counts.get("documents") or 0),
            "evidences": int(counts.get("evidences") or 0),
        }
        probe["status"] = "ok"
        probe["reason"] = "graph_probe_from_context_counts"

    live_probe_enabled = str(os.getenv("GRAPH_RAG_AGENT_GRAPH_LIVE_PROBE_ENABLED", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if live_probe_enabled:
        try:
            neo4j_client = get_neo4j_client()
            query = "MATCH (n) RETURN count(n) AS node_count LIMIT 1"
            records = neo4j_client.run_read(query)
            row = records[0] if records else {}
            probe["status"] = "ok"
            probe["reason"] = "graph_probe_live_ping_ok"
            probe["live_node_count"] = int(row.get("node_count") or 0)
        except Exception as error:
            log_key = f"{agent_name}:{type(error).__name__}"
            if log_key not in _GRAPH_FAILURE_LOGGED:
                logger.warning("[GraphRAGAgentProbe] graph probe failed (%s): %s", agent_name, error)
                _GRAPH_FAILURE_LOGGED.add(log_key)
            else:
                logger.debug("[GraphRAGAgentProbe] graph probe failed (%s): %s", agent_name, error)
            if probe["status"] != "ok":
                probe["status"] = "error"
                probe["reason"] = "graph_probe_failed"
            probe["error_type"] = type(error).__name__
            probe["error"] = str(error)

    probe["duration_ms"] = int((time.time() - started_at) * 1000)
    return probe


def detect_companion_branch(branch: str, probe: Dict[str, Any]) -> Optional[str]:
    status = str(probe.get("status") or "").strip().lower()
    if status == "ok":
        return None
    if branch == "sql":
        return "graph"
    if branch == "graph":
        return "sql"
    return None
