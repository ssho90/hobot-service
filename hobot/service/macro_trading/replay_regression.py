"""Historical replay regression helpers for AI strategy decisions."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

ASSET_KEYS = ("stocks", "bonds", "alternatives", "cash")


def _safe_json_loads(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.warning("target_allocation JSON decode failed. raw=%s", value[:200])
    return {}


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _extract_sub_mp_ids(sub_mp_raw: Any) -> Dict[str, Optional[str]]:
    result: Dict[str, Optional[str]] = {asset: None for asset in ASSET_KEYS}
    if not isinstance(sub_mp_raw, dict):
        return result

    key_aliases = {
        "stocks": ("stocks", "stocks_sub_mp"),
        "bonds": ("bonds", "bonds_sub_mp"),
        "alternatives": ("alternatives", "alternatives_sub_mp"),
        "cash": ("cash", "cash_sub_mp"),
    }

    for asset, aliases in key_aliases.items():
        for key in aliases:
            raw_value = sub_mp_raw.get(key)
            if isinstance(raw_value, dict):
                candidate = raw_value.get("sub_mp_id") or raw_value.get("id")
            else:
                candidate = raw_value
            if isinstance(candidate, str) and candidate.strip():
                result[asset] = candidate.strip()
                break

    return result


def normalize_strategy_history_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize decision rows from DB/API into a deterministic replay shape."""
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        decision_date = _coerce_datetime(row.get("decision_date"))
        if not decision_date:
            continue

        allocation_payload = _safe_json_loads(row.get("target_allocation"))
        mp_id = allocation_payload.get("mp_id")
        sub_mp = _extract_sub_mp_ids(allocation_payload.get("sub_mp"))

        normalized.append(
            {
                "decision_date": decision_date,
                "mp_id": str(mp_id).strip() if isinstance(mp_id, str) and mp_id.strip() else None,
                "sub_mp": sub_mp,
            }
        )

    normalized.sort(key=lambda item: item["decision_date"])
    return normalized


def calculate_replay_regression_metrics(
    normalized_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate MP/Sub-MP switch rates and whipsaw frequency."""
    decision_count = len(normalized_rows)

    mp_change_count = 0
    mp_transition_count = 0

    sub_change_count = {asset: 0 for asset in ASSET_KEYS}
    sub_transition_count = {asset: 0 for asset in ASSET_KEYS}

    for i in range(1, decision_count):
        prev_row = normalized_rows[i - 1]
        curr_row = normalized_rows[i]

        prev_mp = prev_row.get("mp_id")
        curr_mp = curr_row.get("mp_id")
        if prev_mp and curr_mp:
            mp_transition_count += 1
            if prev_mp != curr_mp:
                mp_change_count += 1

        prev_sub = prev_row.get("sub_mp") or {}
        curr_sub = curr_row.get("sub_mp") or {}
        for asset in ASSET_KEYS:
            prev_sub_id = prev_sub.get(asset)
            curr_sub_id = curr_sub.get(asset)
            if prev_sub_id and curr_sub_id:
                sub_transition_count[asset] += 1
                if prev_sub_id != curr_sub_id:
                    sub_change_count[asset] += 1

    whipsaw_count = 0
    whipsaw_triplet_count = 0
    whipsaw_events: List[Dict[str, Any]] = []
    for i in range(2, decision_count):
        mp_a = normalized_rows[i - 2].get("mp_id")
        mp_b = normalized_rows[i - 1].get("mp_id")
        mp_c = normalized_rows[i].get("mp_id")
        if not (mp_a and mp_b and mp_c):
            continue
        whipsaw_triplet_count += 1
        if mp_a == mp_c and mp_a != mp_b:
            whipsaw_count += 1
            whipsaw_events.append(
                {
                    "decision_date": normalized_rows[i]["decision_date"].strftime("%Y-%m-%d %H:%M:%S"),
                    "pattern": [mp_a, mp_b, mp_c],
                }
            )

    sub_change_rate = {
        asset: (
            round(sub_change_count[asset] / sub_transition_count[asset], 4)
            if sub_transition_count[asset]
            else 0.0
        )
        for asset in ASSET_KEYS
    }

    total_sub_changes = sum(sub_change_count.values())
    total_sub_transitions = sum(sub_transition_count.values())

    return {
        "decision_count": decision_count,
        "mp_change_count": mp_change_count,
        "mp_transition_count": mp_transition_count,
        "mp_change_rate": round(mp_change_count / mp_transition_count, 4) if mp_transition_count else 0.0,
        "sub_mp_change_count": sub_change_count,
        "sub_mp_transition_count": sub_transition_count,
        "sub_mp_change_rate": sub_change_rate,
        "overall_sub_mp_change_rate": (
            round(total_sub_changes / total_sub_transitions, 4) if total_sub_transitions else 0.0
        ),
        "whipsaw_count": whipsaw_count,
        "whipsaw_triplet_count": whipsaw_triplet_count,
        "whipsaw_rate": round(whipsaw_count / whipsaw_triplet_count, 4) if whipsaw_triplet_count else 0.0,
        "whipsaw_events": whipsaw_events,
    }


def fetch_strategy_history_rows(
    days: int = 90,
    now: Optional[datetime] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Fetch strategy history rows from DB for replay analysis."""
    reference_now = now or datetime.now()
    cutoff = reference_now - timedelta(days=days)

    try:
        from service.database.db import get_db_connection

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT decision_date, target_allocation
                FROM ai_strategy_decisions
                WHERE decision_date >= %s
                ORDER BY decision_date ASC
                LIMIT %s
                """,
                (cutoff, limit),
            )
            return cursor.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch strategy history rows for replay: %s", exc)
        return []


def generate_historical_replay_report(
    days: int = 90,
    history_rows: Optional[Iterable[Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build a replay report for MP/Sub-MP volatility and whipsaw diagnostics."""
    reference_now = now or datetime.now()
    cutoff = reference_now - timedelta(days=days)

    source_rows = list(history_rows) if history_rows is not None else fetch_strategy_history_rows(days=days, now=reference_now)
    normalized_rows = normalize_strategy_history_rows(source_rows)
    scoped_rows = [row for row in normalized_rows if row["decision_date"] >= cutoff]

    metrics = calculate_replay_regression_metrics(scoped_rows)
    first_decision = scoped_rows[0]["decision_date"].strftime("%Y-%m-%d %H:%M:%S") if scoped_rows else None
    last_decision = scoped_rows[-1]["decision_date"].strftime("%Y-%m-%d %H:%M:%S") if scoped_rows else None

    return {
        "lookback_days": days,
        "reference_now": reference_now.strftime("%Y-%m-%d %H:%M:%S"),
        "period_start": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
        "first_decision_date": first_decision,
        "last_decision_date": last_decision,
        "metrics": metrics,
    }


__all__ = [
    "ASSET_KEYS",
    "calculate_replay_regression_metrics",
    "fetch_strategy_history_rows",
    "generate_historical_replay_report",
    "normalize_strategy_history_rows",
]
