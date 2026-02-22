"""Live SQL/Cypher template executor for Phase 2 supervisor wiring."""

from __future__ import annotations

from bisect import bisect_left
from datetime import date, datetime
import logging
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from service.database.db import get_db_connection
from service.graph.neo4j_client import get_neo4j_client
from service.graph.rag.kr_region_scope import LAWD_NAME_BY_CODE, parse_region_input_to_lawd_codes
from service.graph.rag.security_id import build_equity_focus_identifiers
from service.graph.rag.templates import GRAPH_TEMPLATE_SPECS, SQL_TEMPLATE_SPECS

logger = logging.getLogger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_SQL_FAILURE_AT: Optional[float] = None
_GRAPH_FAILURE_AT: Optional[float] = None


def _safe_env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def _is_safe_identifier(identifier: str) -> bool:
    return bool(_IDENTIFIER_PATTERN.fullmatch(str(identifier or "")))


def _quote_identifier(identifier: str) -> str:
    text = str(identifier or "").strip()
    if not _is_safe_identifier(text):
        raise ValueError(f"invalid_identifier:{identifier}")
    return f"`{text}`"


def _safe_failure_gate(last_failed_at: Optional[float], key: str) -> bool:
    if last_failed_at is None:
        return False
    ttl_sec = max(_safe_env_int(key, 20), 1)
    return (time.time() - last_failed_at) <= ttl_sec


def _fetch_existing_tables(cursor, table_names: Iterable[str]) -> List[str]:
    names = [str(name).strip() for name in table_names if str(name).strip()]
    if not names:
        return []
    placeholders = ", ".join(["%s"] * len(names))
    query = (
        "SELECT table_name "
        "FROM information_schema.tables "
        "WHERE table_schema = DATABASE() "
        f"AND table_name IN ({placeholders})"
    )
    cursor.execute(query, tuple(names))
    rows = cursor.fetchall() or []
    resolved: List[str] = []
    for row in rows:
        value = _row_get_ci(row, "table_name")
        text = str(value or "").strip()
        if text:
            resolved.append(text)
    return resolved


def _fetch_table_columns(cursor, table_name: str) -> List[str]:
    query = (
        "SELECT column_name "
        "FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s "
        "ORDER BY ordinal_position ASC"
    )
    cursor.execute(query, (table_name,))
    rows = cursor.fetchall() or []
    resolved: List[str] = []
    for row in rows:
        value = _row_get_ci(row, "column_name")
        text = str(value or "").strip()
        if text:
            resolved.append(text)
    return resolved


def _row_get_ci(row: Any, key: str) -> Any:
    if not isinstance(row, dict):
        return None
    if key in row:
        return row.get(key)
    lowered_key = str(key or "").lower()
    for candidate_key, candidate_value in row.items():
        if str(candidate_key or "").lower() == lowered_key:
            return candidate_value
    return None


def _pick_first_existing(candidates: Iterable[str], available: Iterable[str]) -> Optional[str]:
    available_set = set(available)
    for candidate in candidates:
        if candidate in available_set:
            return candidate
    return None


def _pick_select_columns(columns: List[str], candidates: Iterable[str], max_columns: int = 8) -> List[str]:
    selected = [column for column in candidates if column in columns]
    if selected:
        return selected[:max_columns]
    return columns[:max_columns]


def _normalize_yyyymm(value: Any) -> str:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    return text[:6] if len(text) >= 6 else ""


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _calc_pct_change(latest: Optional[float], base: Optional[float]) -> Optional[float]:
    if latest is None or base is None:
        return None
    if abs(base) < 1e-9:
        return None
    return round(((latest - base) / base) * 100.0, 2)


def _to_calendar_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass

    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except Exception:
            return None
    return None


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _moving_average(values: List[float], window: int) -> Optional[float]:
    if window <= 0 or len(values) < window:
        return None
    return _mean(values[-window:])


def _infer_equity_country_code(
    *,
    explicit_country_code: Optional[str],
    table_name: str,
) -> Optional[str]:
    code = str(explicit_country_code or "").strip().upper()
    if code in {"KR", "US"}:
        return code
    table = str(table_name or "").strip().lower()
    if table.startswith("kr_"):
        return "KR"
    if table.startswith("us_"):
        return "US"
    return None


def _table_country_hint(table_name: str) -> Optional[str]:
    table = str(table_name or "").strip().lower()
    if table.startswith("kr_"):
        return "KR"
    if table.startswith("us_"):
        return "US"
    return None


def _prioritize_sql_specs(
    specs: List[Dict[str, Any]],
    *,
    available_tables: Iterable[str],
    preferred_country_code: Optional[str],
    selected_type: Optional[str],
    focus_symbol: Optional[str],
) -> List[Dict[str, Any]]:
    available_set = {str(name or "").strip() for name in available_tables if str(name or "").strip()}
    candidates: List[Dict[str, Any]] = []
    for spec in specs:
        table_name = str(spec.get("table") or "").strip()
        if table_name and table_name in available_set:
            candidates.append(spec)

    if len(candidates) <= 1:
        return candidates

    preferred_country = str(preferred_country_code or "").strip().upper() or None
    route_type = str(selected_type or "").strip().lower()
    symbol_token = str(focus_symbol or "").strip().upper()
    symbol_is_kr = bool(symbol_token) and symbol_token.isdigit() and len(symbol_token) <= 6
    symbol_is_us = bool(symbol_token) and bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", symbol_token))

    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    for index, spec in enumerate(candidates):
        table_name = str(spec.get("table") or "").strip()
        table_country = _table_country_hint(table_name)
        template_id = str(spec.get("template_id") or "").strip().lower()

        score = 0
        if preferred_country and table_country == preferred_country:
            score += 120
        if route_type == "us_single_stock" and table_country == "US":
            score += 100
        if symbol_is_kr and table_country == "KR":
            score += 80
        if symbol_is_us and table_country == "US":
            score += 50
        if "ohlcv" in template_id:
            score += 10

        scored.append((-score, index, spec))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored]


def _classify_equity_trend(
    *,
    latest_close: float,
    ma20: Optional[float],
    ma60: Optional[float],
    ma120: Optional[float],
) -> Dict[str, str]:
    short_term = "중립"
    if ma20 is not None and ma60 is not None:
        if ma20 > ma60 and latest_close >= ma20:
            short_term = "상승"
        elif ma20 < ma60 and latest_close <= ma20:
            short_term = "하락"

    long_term = "중립"
    if ma60 is not None and ma120 is not None:
        if ma60 > ma120 and latest_close >= ma60:
            long_term = "상승"
        elif ma60 < ma120 and latest_close <= ma60:
            long_term = "하락"

    return {
        "short_term": short_term,
        "long_term": long_term,
    }


def _build_equity_earnings_reaction_analysis(
    *,
    cursor: Any,
    country_code: Optional[str],
    focus_symbol: Optional[str],
    bars: List[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_country = str(country_code or "").strip().upper()
    symbol = str(focus_symbol or "").strip()
    if normalized_country not in {"KR", "US"} or not symbol:
        return {
            "status": "degraded",
            "reason": "earnings_scope_missing",
            "event_count": 0,
            "events": [],
        }
    if len(bars) < 3:
        return {
            "status": "degraded",
            "reason": "insufficient_price_bars",
            "event_count": 0,
            "events": [],
        }

    event_fetch_limit = max(_safe_env_int("GRAPH_RAG_EQUITY_EARNINGS_EVENT_FETCH_LIMIT", 12), 3)
    if normalized_country == "US":
        query = (
            "SELECT event_date "
            "FROM us_corporate_earnings_events "
            "WHERE symbol = %s AND event_date IS NOT NULL "
            "ORDER BY event_date DESC "
            "LIMIT %s"
        )
        params: Tuple[Any, ...] = (symbol, event_fetch_limit)
    else:
        query = (
            "SELECT rcept_dt AS event_date "
            "FROM kr_corporate_disclosures "
            "WHERE stock_code = %s "
            "  AND is_earnings_event = 1 "
            "  AND rcept_dt IS NOT NULL "
            "ORDER BY rcept_dt DESC "
            "LIMIT %s"
        )
        params = (symbol, event_fetch_limit)

    cursor.execute(query, params)
    event_rows = cursor.fetchall() or []
    event_dates: List[date] = []
    seen_dates: set[str] = set()
    for row in event_rows:
        if not isinstance(row, dict):
            continue
        event_date = _to_calendar_date(_row_get_ci(row, "event_date"))
        if event_date is None:
            continue
        key = event_date.isoformat()
        if key in seen_dates:
            continue
        seen_dates.add(key)
        event_dates.append(event_date)

    if not event_dates:
        return {
            "status": "degraded",
            "reason": "earnings_event_missing",
            "event_count": 0,
            "events": [],
        }

    trade_dates: List[date] = [bar["trade_date"] for bar in bars]
    closes: List[float] = [float(bar["close"]) for bar in bars]
    event_limit = max(_safe_env_int("GRAPH_RAG_EQUITY_EARNINGS_REACTION_MAX_EVENTS", 3), 1)

    reactions: List[Dict[str, Any]] = []
    for event_date in event_dates:
        if len(reactions) >= event_limit:
            break
        event_idx = bisect_left(trade_dates, event_date)
        if event_idx >= len(trade_dates):
            continue
        if event_idx == 0:
            continue

        pre_idx = event_idx - 1
        post1_idx = event_idx + 1 if event_idx + 1 < len(trade_dates) else None
        post5_idx = event_idx + 5 if event_idx + 5 < len(trade_dates) else None

        pre_close = closes[pre_idx]
        event_close = closes[event_idx]
        post1_close = closes[post1_idx] if post1_idx is not None else None
        post5_close = closes[post5_idx] if post5_idx is not None else None

        reactions.append(
            {
                "event_date": event_date.isoformat(),
                "event_trade_date": trade_dates[event_idx].isoformat(),
                "pre_trade_date": trade_dates[pre_idx].isoformat(),
                "pre_close": round(pre_close, 4),
                "event_close": round(event_close, 4),
                "post_1d_trade_date": trade_dates[post1_idx].isoformat() if post1_idx is not None else None,
                "post_1d_close": round(post1_close, 4) if post1_close is not None else None,
                "post_5d_trade_date": trade_dates[post5_idx].isoformat() if post5_idx is not None else None,
                "post_5d_close": round(post5_close, 4) if post5_close is not None else None,
                "event_day_pct_from_pre_close": _calc_pct_change(event_close, pre_close),
                "post_1d_pct_from_event_close": _calc_pct_change(post1_close, event_close)
                if post1_close is not None
                else None,
                "post_5d_pct_from_event_close": _calc_pct_change(post5_close, event_close)
                if post5_close is not None
                else None,
                "pre_to_post_5d_pct": _calc_pct_change(post5_close, pre_close)
                if post5_close is not None
                else None,
            }
        )

    if not reactions:
        return {
            "status": "degraded",
            "reason": "earnings_reaction_not_aligned",
            "event_count": 0,
            "events": [],
        }

    latest_reaction = reactions[0]
    return {
        "status": "ok",
        "reason": "earnings_reaction_available",
        "event_count": len(reactions),
        "latest_event_date": latest_reaction.get("event_date"),
        "latest_event_trade_date": latest_reaction.get("event_trade_date"),
        "latest_event_day_pct_from_pre_close": latest_reaction.get("event_day_pct_from_pre_close"),
        "latest_post_1d_pct_from_event_close": latest_reaction.get("post_1d_pct_from_event_close"),
        "latest_post_5d_pct_from_event_close": latest_reaction.get("post_5d_pct_from_event_close"),
        "events": reactions,
    }


def _build_equity_ohlcv_analysis(
    *,
    cursor: Any,
    table_name: str,
    columns: List[str],
    date_column: Optional[str],
    security_id_column: Optional[str],
    focus_security_id: Optional[str],
    symbol_column: Optional[str],
    focus_symbol: Optional[str],
    country_code: Optional[str],
) -> Optional[Dict[str, Any]]:
    normalized_table = str(table_name or "").strip().lower()
    if normalized_table not in {"kr_top50_daily_ohlcv", "us_top50_daily_ohlcv"}:
        return None
    if not date_column:
        return {
            "status": "degraded",
            "reason": "date_column_missing",
            "bars_available": 0,
            "events": [],
        }

    close_column = _pick_first_existing(("adjusted_close", "close_price", "close"), columns)
    volume_column = _pick_first_existing(("volume",), columns)
    if not close_column:
        return {
            "status": "degraded",
            "reason": "close_column_missing",
            "bars_available": 0,
            "events": [],
        }

    where_clauses: List[str] = []
    params: List[Any] = []
    if security_id_column and focus_security_id:
        where_clauses.append(f"{_quote_identifier(security_id_column)} = %s")
        params.append(focus_security_id)
    elif symbol_column and focus_symbol:
        where_clauses.append(f"{_quote_identifier(symbol_column)} = %s")
        params.append(focus_symbol)
    if not where_clauses:
        return {
            "status": "degraded",
            "reason": "focus_filter_missing",
            "bars_available": 0,
            "events": [],
        }

    lookback_bars = max(_safe_env_int("GRAPH_RAG_EQUITY_TREND_LOOKBACK_BARS", 260), 30)
    select_parts = [
        f"{_quote_identifier(date_column)} AS trade_date",
        f"{_quote_identifier(close_column)} AS close_value",
    ]
    if volume_column:
        select_parts.append(f"{_quote_identifier(volume_column)} AS volume_value")
    else:
        select_parts.append("NULL AS volume_value")

    query = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM {_quote_identifier(table_name)} "
        f"WHERE {' AND '.join(where_clauses)} "
        f"ORDER BY {_quote_identifier(date_column)} DESC "
        "LIMIT %s"
    )
    cursor.execute(query, (*params, lookback_bars))
    raw_rows = cursor.fetchall() or []

    bars: List[Dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        trade_date = _to_calendar_date(_row_get_ci(row, "trade_date"))
        close_value = _safe_float(_row_get_ci(row, "close_value"))
        if trade_date is None or close_value is None:
            continue
        bars.append(
            {
                "trade_date": trade_date,
                "close": close_value,
                "volume": _safe_int(_row_get_ci(row, "volume_value")),
            }
        )

    if not bars:
        return {
            "status": "degraded",
            "reason": "equity_ohlcv_empty",
            "bars_available": 0,
            "events": [],
            "query": query,
        }

    bars.sort(key=lambda item: item["trade_date"])
    closes = [float(item["close"]) for item in bars]
    latest_bar = bars[-1]
    latest_close = closes[-1]

    ma20 = _moving_average(closes, 20)
    ma60 = _moving_average(closes, 60)
    ma120 = _moving_average(closes, 120)

    returns: Dict[str, Optional[float]] = {}
    for horizon in (1, 5, 20, 60, 120):
        key = f"return_{horizon}d_pct"
        if len(closes) > horizon:
            returns[key] = _calc_pct_change(latest_close, closes[-1 - horizon])
        else:
            returns[key] = None

    cross_signal = "none"
    if len(closes) >= 61:
        prev_ma20 = _moving_average(closes[:-1], 20)
        prev_ma60 = _moving_average(closes[:-1], 60)
        if (
            prev_ma20 is not None
            and prev_ma60 is not None
            and ma20 is not None
            and ma60 is not None
        ):
            if prev_ma20 <= prev_ma60 and ma20 > ma60:
                cross_signal = "golden_cross"
            elif prev_ma20 >= prev_ma60 and ma20 < ma60:
                cross_signal = "dead_cross"

    trend = _classify_equity_trend(
        latest_close=latest_close,
        ma20=ma20,
        ma60=ma60,
        ma120=ma120,
    )
    normalized_country = _infer_equity_country_code(
        explicit_country_code=country_code,
        table_name=table_name,
    )
    earnings_reaction = _build_equity_earnings_reaction_analysis(
        cursor=cursor,
        country_code=normalized_country,
        focus_symbol=focus_symbol,
        bars=bars,
    )

    latest_volume = _safe_int(latest_bar.get("volume"))
    return {
        "status": "ok" if len(closes) >= 120 else "limited",
        "reason": "equity_trend_available",
        "country_code": normalized_country,
        "bars_available": len(closes),
        "lookback_bars": lookback_bars,
        "latest_trade_date": latest_bar["trade_date"].isoformat(),
        "latest_close": round(latest_close, 4),
        "latest_volume": latest_volume,
        "moving_averages": {
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120,
        },
        "trend": {
            "short_term": trend.get("short_term"),
            "long_term": trend.get("long_term"),
            "cross_signal": cross_signal,
        },
        "returns": returns,
        "earnings_reaction": earnings_reaction,
    }


def _resolve_region_scope_label(region_code: Optional[str]) -> str:
    raw = str(region_code or "").strip()
    if not raw:
        return "전국"

    resolved_codes, _, _ = parse_region_input_to_lawd_codes(raw)
    if not resolved_codes:
        return raw

    labels: List[str] = []
    for code in resolved_codes:
        label = LAWD_NAME_BY_CODE.get(code)
        labels.append(label or code)
    if not labels:
        return raw
    if len(labels) <= 3:
        return ", ".join(labels)
    return f"{', '.join(labels[:2])} 외 {len(labels) - 2}개 지역"


def _build_real_estate_trend_analysis(
    *,
    cursor: Any,
    table_name: str,
    columns: List[str],
    date_column: Optional[str],
    region_column: Optional[str],
    region_code: Optional[str],
    request: Any,
) -> Optional[Dict[str, Any]]:
    if table_name != "kr_real_estate_monthly_summary":
        return None
    if not date_column:
        return None

    tx_column = _pick_first_existing(("tx_count", "transaction_count", "deal_count"), columns)
    price_column = _pick_first_existing(("avg_price", "mean_price", "price_avg"), columns)
    if not tx_column and not price_column:
        return None

    select_parts: List[str] = [f"{_quote_identifier(date_column)} AS stat_ym"]
    if tx_column:
        select_parts.append(f"SUM(COALESCE({_quote_identifier(tx_column)}, 0)) AS tx_count")
    else:
        select_parts.append("NULL AS tx_count")

    if price_column and tx_column:
        select_parts.append(
            "CASE WHEN SUM(COALESCE("
            + _quote_identifier(tx_column)
            + ", 0)) > 0 THEN "
            + "SUM(COALESCE("
            + _quote_identifier(price_column)
            + ", 0) * COALESCE("
            + _quote_identifier(tx_column)
            + ", 0)) / SUM(COALESCE("
            + _quote_identifier(tx_column)
            + ", 0)) ELSE NULL END AS weighted_avg_price"
        )
    elif price_column:
        select_parts.append(f"AVG(COALESCE({_quote_identifier(price_column)}, 0)) AS weighted_avg_price")
    else:
        select_parts.append("NULL AS weighted_avg_price")

    where_clauses: List[str] = []
    params: List[Any] = []
    if region_column and region_code:
        region_clause, region_params = _build_region_clause(
            region_column=region_column,
            region_code=region_code,
        )
        if region_clause:
            where_clauses.append(region_clause)
            params.extend(region_params)

    property_type = str(getattr(request, "property_type", "") or "").strip().lower()
    property_column = _pick_first_existing(("property_type",), columns)
    if property_type and property_column:
        where_clauses.append(f"LOWER({_quote_identifier(property_column)}) = %s")
        params.append(property_type)

    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    trend_limit = max(_safe_env_int("GRAPH_RAG_REAL_ESTATE_TREND_LIMIT", 18), 6)
    trend_query = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM {_quote_identifier(table_name)}"
        f"{where_sql} "
        f"GROUP BY {_quote_identifier(date_column)} "
        f"ORDER BY {_quote_identifier(date_column)} DESC "
        f"LIMIT {trend_limit}"
    )
    cursor.execute(trend_query, tuple(params))
    trend_rows_raw = cursor.fetchall() or []

    trend_rows: List[Dict[str, Any]] = []
    for row in trend_rows_raw:
        if not isinstance(row, dict):
            continue
        stat_ym = _normalize_yyyymm(_row_get_ci(row, "stat_ym"))
        if not stat_ym:
            continue
        trend_rows.append(
            {
                "stat_ym": stat_ym,
                "tx_count": _safe_int(_row_get_ci(row, "tx_count")),
                "weighted_avg_price": _safe_float(_row_get_ci(row, "weighted_avg_price")),
            }
        )

    if not trend_rows:
        return {
            "status": "degraded",
            "reason": "real_estate_trend_empty",
            "months_available": 0,
            "scope_label": _resolve_region_scope_label(region_code),
            "query": trend_query,
            "params": list(params),
        }

    trend_rows.sort(key=lambda item: str(item.get("stat_ym") or ""))
    latest = trend_rows[-1]
    earliest = trend_rows[0]
    latest_price = _safe_float(latest.get("weighted_avg_price"))
    earliest_price = _safe_float(earliest.get("weighted_avg_price"))
    latest_tx = _safe_float(latest.get("tx_count"))
    earliest_tx = _safe_float(earliest.get("tx_count"))
    price_pct = _calc_pct_change(latest_price, earliest_price)
    tx_pct = _calc_pct_change(latest_tx, earliest_tx)

    return {
        "status": "ok" if len(trend_rows) >= 6 else "limited",
        "reason": "real_estate_trend_available",
        "scope_label": _resolve_region_scope_label(region_code),
        "months_available": len(trend_rows),
        "earliest_month": str(earliest.get("stat_ym") or ""),
        "latest_month": str(latest.get("stat_ym") or ""),
        "latest_weighted_avg_price": latest_price,
        "latest_tx_count": _safe_int(latest.get("tx_count")),
        "price_change_pct_vs_start": price_pct,
        "tx_change_pct_vs_start": tx_pct,
        "property_type": property_type or None,
        "query": trend_query,
        "params": list(params),
        "rows": trend_rows,
    }


def _extract_focus_symbol(route_decision: Dict[str, Any]) -> Optional[str]:
    symbols = route_decision.get("matched_symbols")
    if not isinstance(symbols, list):
        return None
    for symbol in symbols:
        text = str(symbol or "").strip()
        if text:
            return text
    return None


def _build_region_clause(
    *,
    region_column: str,
    region_code: str,
) -> Tuple[Optional[str], List[Any]]:
    column_expr = _quote_identifier(region_column)
    tokens = [str(item or "").strip() for item in str(region_code or "").split(",") if str(item or "").strip()]
    if not tokens:
        return None, []

    clauses: List[str] = []
    params: List[Any] = []
    for token in tokens:
        upper = token.upper()
        if upper == "SEOUL":
            clauses.append(f"{column_expr} LIKE %s")
            params.append("11%")
            continue
        if upper == "GYEONGGI":
            clauses.append(f"{column_expr} LIKE %s")
            params.append("41%")
            continue

        digits = re.sub(r"[^0-9]", "", token)
        if digits:
            if len(digits) <= 5:
                clauses.append(f"{column_expr} LIKE %s")
                params.append(f"{digits}%")
            else:
                clauses.append(f"{column_expr} = %s")
                params.append(digits)
            continue

        clauses.append(f"{column_expr} = %s")
        params.append(token)

    if not clauses:
        return None, []
    if len(clauses) == 1:
        return clauses[0], params
    return f"({' OR '.join(clauses)})", params


def _build_sql_query(
    *,
    table_name: str,
    columns: List[str],
    date_column: Optional[str],
    select_columns: List[str],
    security_id_column: Optional[str],
    focus_security_id: Optional[str],
    symbol_column: Optional[str],
    focus_symbol: Optional[str],
    region_column: Optional[str],
    region_code: Optional[str],
) -> Tuple[str, Tuple[Any, ...]]:
    selected_projection = ", ".join(_quote_identifier(column) for column in select_columns)
    where_clauses: List[str] = []
    params: List[Any] = []

    if security_id_column and focus_security_id:
        where_clauses.append(f"{_quote_identifier(security_id_column)} = %s")
        params.append(focus_security_id)
    elif symbol_column and focus_symbol:
        where_clauses.append(f"{_quote_identifier(symbol_column)} = %s")
        params.append(focus_symbol)
    if region_column and region_code:
        region_clause, region_params = _build_region_clause(
            region_column=region_column,
            region_code=region_code,
        )
        if region_clause:
            where_clauses.append(region_clause)
            params.extend(region_params)

    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    if date_column:
        order_sql = f" ORDER BY {_quote_identifier(date_column)} DESC"
    else:
        order_sql = ""

    limit = max(_safe_env_int("GRAPH_RAG_AGENT_SQL_TEMPLATE_LIMIT", 5), 1)
    query = f"SELECT {selected_projection} FROM {_quote_identifier(table_name)}{where_sql}{order_sql} LIMIT {limit}"
    return query, tuple(params)


def _execute_sql_template(
    *,
    agent_name: str,
    request: Any,
    route_decision: Dict[str, Any],
) -> Dict[str, Any]:
    global _SQL_FAILURE_AT

    started_at = time.time()
    if _safe_failure_gate(_SQL_FAILURE_AT, "GRAPH_RAG_AGENT_SQL_FAST_FAIL_SEC"):
        return {
            "tool": "sql",
            "status": "degraded",
            "reason": "sql_executor_fast_fail_window",
            "duration_ms": int((time.time() - started_at) * 1000),
        }

    specs = SQL_TEMPLATE_SPECS.get(agent_name) or []
    if not specs:
        return {
            "tool": "sql",
            "status": "degraded",
            "reason": "sql_template_specs_missing",
            "duration_ms": int((time.time() - started_at) * 1000),
        }

    target_tables = [str(spec.get("table") or "").strip() for spec in specs if str(spec.get("table") or "").strip()]
    focus_symbol = _extract_focus_symbol(route_decision)
    focus_identifiers: Dict[str, Optional[str]] = {}
    focus_security_id: Optional[str] = None
    if agent_name == "equity_analyst_agent":
        focus_identifiers = build_equity_focus_identifiers(route_decision, request)
        focus_symbol = str(focus_identifiers.get("focus_symbol") or focus_symbol or "").strip() or None
        focus_security_id = str(focus_identifiers.get("security_id") or "").strip() or None
    region_code = str(getattr(request, "region_code", "") or "").strip() or None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            existing_tables = set(_fetch_existing_tables(cursor, target_tables))
            prioritized_specs = _prioritize_sql_specs(
                specs,
                available_tables=existing_tables,
                preferred_country_code=str(focus_identifiers.get("country_code") or "").strip() or None,
                selected_type=route_decision.get("selected_type"),
                focus_symbol=focus_symbol,
            )
            if not prioritized_specs:
                return {
                    "tool": "sql",
                    "status": "degraded",
                    "reason": "sql_template_table_not_found",
                    "candidate_tables": target_tables,
                    "duration_ms": int((time.time() - started_at) * 1000),
                }

            attempts: List[Dict[str, Any]] = []
            first_degraded_result: Optional[Dict[str, Any]] = None
            last_error_result: Optional[Dict[str, Any]] = None
            preferred_country = str(focus_identifiers.get("country_code") or "").strip() or None

            for selected_spec in prioritized_specs:
                table_name = str(selected_spec.get("table") or "").strip()
                try:
                    columns = _fetch_table_columns(cursor, table_name)
                    if not columns:
                        attempts.append(
                            {
                                "table": table_name,
                                "template_id": str(selected_spec.get("template_id") or ""),
                                "status": "degraded",
                                "reason": "sql_template_columns_missing",
                            }
                        )
                        continue

                    date_column = _pick_first_existing(selected_spec.get("date_candidates") or (), columns)
                    security_id_column = _pick_first_existing(selected_spec.get("security_id_candidates") or (), columns)
                    symbol_column = _pick_first_existing(selected_spec.get("symbol_candidates") or (), columns)
                    region_column = _pick_first_existing(selected_spec.get("region_candidates") or (), columns)
                    select_columns = _pick_select_columns(columns, selected_spec.get("select_candidates") or ())
                    if security_id_column and security_id_column not in select_columns:
                        select_columns = [security_id_column, *select_columns][:8]
                    if date_column and date_column not in select_columns:
                        select_columns = [date_column, *select_columns][:8]

                    query, params = _build_sql_query(
                        table_name=table_name,
                        columns=columns,
                        date_column=date_column,
                        select_columns=select_columns,
                        security_id_column=security_id_column,
                        focus_security_id=focus_security_id,
                        symbol_column=symbol_column,
                        focus_symbol=focus_symbol,
                        region_column=region_column,
                        region_code=region_code,
                    )
                    cursor.execute(query, params)
                    rows = cursor.fetchall() or []
                    trend_analysis = _build_real_estate_trend_analysis(
                        cursor=cursor,
                        table_name=table_name,
                        columns=columns,
                        date_column=date_column,
                        region_column=region_column,
                        region_code=region_code,
                        request=request,
                    )
                    equity_analysis = _build_equity_ohlcv_analysis(
                        cursor=cursor,
                        table_name=table_name,
                        columns=columns,
                        date_column=date_column,
                        security_id_column=security_id_column,
                        focus_security_id=focus_security_id,
                        symbol_column=symbol_column,
                        focus_symbol=focus_symbol,
                        country_code=preferred_country,
                    )

                    status = "ok" if rows else "degraded"
                    reason = "sql_template_executed" if rows else "sql_template_empty_result"
                    result = {
                        "tool": "sql",
                        "status": status,
                        "reason": reason,
                        "template_id": str(selected_spec.get("template_id") or ""),
                        "table": table_name,
                        "date_column": date_column,
                        "security_id_column": security_id_column,
                        "symbol_column": symbol_column,
                        "selected_columns": select_columns,
                        "filters": {
                            "security_id": focus_security_id if security_id_column else None,
                            "symbol": focus_symbol if symbol_column else None,
                            "region_code": region_code if region_column else None,
                        },
                        "identifier": focus_identifiers if focus_identifiers else None,
                        "query": query,
                        "params": list(params),
                        "row_count": len(rows),
                        "rows": rows[:5],
                        "trend_analysis": trend_analysis,
                        "equity_analysis": equity_analysis,
                        "duration_ms": int((time.time() - started_at) * 1000),
                    }

                    attempts.append(
                        {
                            "table": table_name,
                            "template_id": str(selected_spec.get("template_id") or ""),
                            "status": status,
                            "reason": reason,
                            "row_count": len(rows),
                        }
                    )

                    bars_available = int((equity_analysis or {}).get("bars_available") or 0)
                    months_available = int((trend_analysis or {}).get("months_available") or 0)
                    if rows or bars_available > 0 or months_available > 0:
                        result["attempts"] = attempts
                        _SQL_FAILURE_AT = None
                        return result

                    if first_degraded_result is None:
                        first_degraded_result = result

                except Exception as inner_exc:
                    logger.warning(
                        "[GraphRAGAgentLiveExecutor] sql template attempt failed (%s:%s): %s",
                        agent_name,
                        table_name,
                        inner_exc,
                    )
                    attempts.append(
                        {
                            "table": table_name,
                            "template_id": str(selected_spec.get("template_id") or ""),
                            "status": "degraded",
                            "reason": "sql_template_execution_failed",
                            "error_type": type(inner_exc).__name__,
                        }
                    )
                    last_error_result = {
                        "tool": "sql",
                        "status": "degraded",
                        "reason": "sql_template_execution_failed",
                        "template_id": str(selected_spec.get("template_id") or ""),
                        "table": table_name,
                        "identifier": focus_identifiers if focus_identifiers else None,
                        "error_type": type(inner_exc).__name__,
                        "error": str(inner_exc),
                        "duration_ms": int((time.time() - started_at) * 1000),
                    }

            if first_degraded_result is not None:
                first_degraded_result["attempts"] = attempts
                _SQL_FAILURE_AT = None
                return first_degraded_result

            if last_error_result is not None:
                last_error_result["attempts"] = attempts
                _SQL_FAILURE_AT = time.time()
                return last_error_result

            return {
                "tool": "sql",
                "status": "degraded",
                "reason": "sql_template_table_not_found",
                "candidate_tables": target_tables,
                "duration_ms": int((time.time() - started_at) * 1000),
            }
    except Exception as exc:
        _SQL_FAILURE_AT = time.time()
        logger.warning("[GraphRAGAgentLiveExecutor] sql execution failed (%s): %s", agent_name, exc)
        return {
            "tool": "sql",
            "status": "degraded",
            "reason": "sql_template_execution_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "duration_ms": int((time.time() - started_at) * 1000),
        }


def _execute_graph_template(
    *,
    agent_name: str,
    context_meta: Dict[str, Any],
) -> Dict[str, Any]:
    global _GRAPH_FAILURE_AT

    started_at = time.time()
    counts = context_meta.get("counts") if isinstance(context_meta.get("counts"), dict) else {}
    if counts:
        return {
            "tool": "graph",
            "status": "ok",
            "reason": "graph_template_context_counts",
            "template_id": "graph.context.counts.v1",
            "counts": {
                "nodes": int(counts.get("nodes") or 0),
                "links": int(counts.get("links") or 0),
                "events": int(counts.get("events") or 0),
                "documents": int(counts.get("documents") or 0),
                "evidences": int(counts.get("evidences") or 0),
            },
            "duration_ms": int((time.time() - started_at) * 1000),
        }

    if _safe_failure_gate(_GRAPH_FAILURE_AT, "GRAPH_RAG_AGENT_GRAPH_FAST_FAIL_SEC"):
        return {
            "tool": "graph",
            "status": "degraded",
            "reason": "graph_executor_fast_fail_window",
            "duration_ms": int((time.time() - started_at) * 1000),
        }

    spec = GRAPH_TEMPLATE_SPECS.get(agent_name)
    if not isinstance(spec, dict):
        return {
            "tool": "graph",
            "status": "degraded",
            "reason": "graph_template_specs_missing",
            "duration_ms": int((time.time() - started_at) * 1000),
        }

    query = str(spec.get("query") or "").strip()
    metric_key = str(spec.get("metric_key") or "metric_value").strip() or "metric_value"
    if not query:
        return {
            "tool": "graph",
            "status": "degraded",
            "reason": "graph_template_query_missing",
            "duration_ms": int((time.time() - started_at) * 1000),
        }

    try:
        neo4j_client = get_neo4j_client()
        rows = neo4j_client.run_read(query)
        metric_value = 0
        if rows:
            metric_value = int((rows[0] or {}).get("metric_value") or 0)
        _GRAPH_FAILURE_AT = None
        return {
            "tool": "graph",
            "status": "ok" if metric_value > 0 else "degraded",
            "reason": "graph_template_executed" if metric_value > 0 else "graph_template_empty_result",
            "template_id": str(spec.get("template_id") or ""),
            "metric_key": metric_key,
            "metric_value": metric_value,
            "query": query,
            "duration_ms": int((time.time() - started_at) * 1000),
        }
    except Exception as exc:
        _GRAPH_FAILURE_AT = time.time()
        logger.warning("[GraphRAGAgentLiveExecutor] graph execution failed (%s): %s", agent_name, exc)
        return {
            "tool": "graph",
            "status": "degraded",
            "reason": "graph_template_execution_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "duration_ms": int((time.time() - started_at) * 1000),
        }


def execute_live_tool(
    *,
    agent_name: str,
    branch: str,
    request: Any,
    route_decision: Dict[str, Any],
    context_meta: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_branch = str(branch or "").strip().lower()
    if normalized_branch == "sql":
        return _execute_sql_template(agent_name=agent_name, request=request, route_decision=route_decision)
    if normalized_branch == "graph":
        return _execute_graph_template(agent_name=agent_name, context_meta=context_meta)
    return {
        "tool": "llm_direct",
        "status": "ok",
        "reason": "llm_direct_branch",
        "duration_ms": 0,
    }


__all__ = ["execute_live_tool", "SQL_TEMPLATE_SPECS", "GRAPH_TEMPLATE_SPECS"]
