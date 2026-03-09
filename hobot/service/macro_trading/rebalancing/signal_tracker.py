import hashlib
import json
import logging
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional


logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_PROFILE_ID = "DEFAULT_US_MACRO_PROFILE"
DEFAULT_STRATEGY_PROFILE_NAME = "Default US Macro Profile"
GLOBAL_SCOPE = "GLOBAL"
GLOBAL_ASSET_CLASS = ""
PENDING_STATUS = "PENDING"
CONFIRMED_STATUS = "CONFIRMED"
CANCELLED_STATUS = "CANCELLED"
APPLIED_STATUS = "APPLIED"
ACTIVE_STATUS = "ACTIVE"
SUPERSEDED_STATUS = "SUPERSEDED"
SUPPORTED_ASSET_CLASSES = ("stocks", "bonds", "alternatives", "cash")


def normalize_alloc(alloc: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """자산 배분 딕셔너리를 표준 형식으로 변환한다."""
    if not alloc:
        return {"stocks": 0.0, "bonds": 0.0, "alternatives": 0.0, "cash": 0.0}
    return {
        "stocks": _to_float(alloc.get("stocks") or alloc.get("Stocks")),
        "bonds": _to_float(alloc.get("bonds") or alloc.get("Bonds")),
        "alternatives": _to_float(alloc.get("alternatives") or alloc.get("Alternatives")),
        "cash": _to_float(alloc.get("cash") or alloc.get("Cash")),
    }


def normalize_sub_mp_payload(sub_mp_payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Sub-MP 선택 payload를 자산군 기준으로 정규화한다."""
    if not isinstance(sub_mp_payload, dict):
        return {}

    field_aliases = {
        "stocks": ("stocks", "stocks_sub_mp"),
        "bonds": ("bonds", "bonds_sub_mp"),
        "alternatives": ("alternatives", "alternatives_sub_mp"),
        "cash": ("cash", "cash_sub_mp"),
    }
    normalized: Dict[str, str] = {}
    for asset_class, aliases in field_aliases.items():
        for alias in aliases:
            value = str(sub_mp_payload.get(alias) or "").strip()
            if value:
                normalized[asset_class] = value
                break
    return normalized


def normalize_sub_mp_details_snapshot(
    snapshot: Optional[Dict[str, Any]],
    normalized_sub_mp: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Sub-MP 상세 스냅샷을 signature 생성용으로 정규화한다."""
    normalized_sub_mp = normalized_sub_mp or {}
    if not isinstance(snapshot, dict):
        snapshot = {}

    normalized_snapshot: Dict[str, Dict[str, Any]] = {}
    for asset_class in SUPPORTED_ASSET_CLASSES:
        sub_mp_id = normalized_sub_mp.get(asset_class)
        asset_snapshot = snapshot.get(asset_class) if isinstance(snapshot.get(asset_class), dict) else {}
        resolved_sub_mp_id = str(asset_snapshot.get("sub_mp_id") or sub_mp_id or "").strip()
        if not resolved_sub_mp_id:
            continue

        normalized_snapshot[asset_class] = {
            "sub_mp_id": resolved_sub_mp_id,
            "sub_mp_name": str(asset_snapshot.get("sub_mp_name") or "").strip(),
            "sub_mp_description": str(asset_snapshot.get("sub_mp_description") or "").strip(),
            "etf_details": normalize_etf_details(asset_snapshot.get("etf_details") or []),
        }
        reasoning = str(asset_snapshot.get("reasoning") or "").strip()
        if reasoning:
            normalized_snapshot[asset_class]["reasoning"] = reasoning

    return normalized_snapshot


def normalize_target_payload(target_payload: Any) -> Dict[str, Any]:
    """target payload를 signature/저장용 공통 포맷으로 정규화한다."""
    raw_payload = target_payload
    if isinstance(raw_payload, str):
        raw_payload = json.loads(raw_payload)
    if not isinstance(raw_payload, dict):
        raw_payload = {}

    normalized_payload = dict(raw_payload)
    normalized_payload["target_allocation"] = normalize_alloc(
        raw_payload.get("target_allocation") if isinstance(raw_payload.get("target_allocation"), dict) else raw_payload
    )

    mp_id = str(raw_payload.get("mp_id") or "").strip()
    if mp_id:
        normalized_payload["mp_id"] = mp_id

    normalized_sub_mp = normalize_sub_mp_payload(raw_payload.get("sub_mp"))
    if normalized_sub_mp:
        normalized_payload["sub_mp"] = normalized_sub_mp

    normalized_snapshot = normalize_sub_mp_details_snapshot(
        raw_payload.get("sub_mp_details_snapshot"),
        normalized_sub_mp,
    )
    if normalized_snapshot:
        normalized_payload["sub_mp_details_snapshot"] = normalized_snapshot

    return normalized_payload


def normalize_etf_details(etf_details: Iterable[Dict[str, Any]]) -> list:
    """ETF 상세 정보를 signature 생성용으로 정규화한다."""
    normalized = []
    for item in etf_details or []:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip()
        if not ticker:
            continue
        normalized.append(
            {
                "ticker": ticker,
                "name": str(item.get("name") or "").strip(),
                "weight": round(_to_float(item.get("weight")), 8),
            }
        )
    normalized.sort(key=lambda item: (item["ticker"], item["name"], item["weight"]))
    return normalized


def build_mp_signature(mp_id: str, allocation: Dict[str, float]) -> str:
    payload = {
        "mp_id": str(mp_id or "").strip(),
        "allocation": normalize_alloc(allocation),
    }
    return _hash_payload(payload)


def build_sub_mp_signatures(
    mp_signature: str,
    sub_mp_payload: Optional[Dict[str, Any]],
    sub_mp_details_snapshot: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    normalized_sub_mp = normalize_sub_mp_payload(sub_mp_payload)
    normalized_snapshot = normalize_sub_mp_details_snapshot(sub_mp_details_snapshot, normalized_sub_mp)

    signatures: Dict[str, str] = {}
    for asset_class in SUPPORTED_ASSET_CLASSES:
        sub_mp_id = normalized_sub_mp.get(asset_class)
        if not sub_mp_id:
            continue
        asset_snapshot = normalized_snapshot.get(asset_class, {})
        payload = {
            "mp_signature": mp_signature,
            "asset_class": asset_class,
            "sub_mp_id": sub_mp_id,
            "etf_details": asset_snapshot.get("etf_details", []),
        }
        signatures[asset_class] = _hash_payload(payload)
    return signatures


def build_effective_target_signature(mp_signature: str, sub_mp_signatures: Dict[str, str]) -> str:
    payload = {
        "mp_signature": mp_signature,
        "sub_mp_signatures": {key: sub_mp_signatures[key] for key in sorted(sub_mp_signatures)},
    }
    return _hash_payload(payload)


def build_signal_bundle(target_payload: Any) -> Dict[str, Any]:
    """target payload에서 MP/Sub-MP signature 묶음을 계산한다."""
    normalized_payload = normalize_target_payload(target_payload)
    mp_signature = build_mp_signature(
        normalized_payload.get("mp_id", ""),
        normalized_payload.get("target_allocation") or {},
    )
    sub_mp_signatures = build_sub_mp_signatures(
        mp_signature=mp_signature,
        sub_mp_payload=normalized_payload.get("sub_mp"),
        sub_mp_details_snapshot=normalized_payload.get("sub_mp_details_snapshot"),
    )
    effective_target_signature = build_effective_target_signature(mp_signature, sub_mp_signatures)
    return {
        "target_payload": normalized_payload,
        "mp_signature": mp_signature,
        "sub_mp_signatures": sub_mp_signatures,
        "effective_target_signature": effective_target_signature,
    }


def calculate_consecutive_observation_days(
    observation_rows: Iterable[Dict[str, Any]],
    candidate_signature: str,
) -> int:
    """최신 관찰값 기준 동일 signature 연속 거래일 수를 계산한다."""
    count = 0
    for row in observation_rows or []:
        if row.get("effective_target_signature_candidate") != candidate_signature:
            break
        count += 1
    return count


def track_signal_observation(
    cursor: Any,
    strategy_profile_id: str,
    decision_id: int,
    decision_date: Any,
    target_payload: Any,
) -> Dict[str, Any]:
    """
    거래일별 공식 관찰값을 저장하고 3거래일 확정 여부를 판정한다.

    같은 거래일에 여러 번 저장되면 마지막 저장값으로 observation이 교체된다.
    """
    strategy_profile_id = str(strategy_profile_id or DEFAULT_STRATEGY_PROFILE_ID).strip() or DEFAULT_STRATEGY_PROFILE_ID
    business_date = _coerce_business_date(decision_date)
    bundle = build_signal_bundle(target_payload)
    normalized_payload_json = _dump_json(bundle["target_payload"])
    sub_mp_signatures_json = _dump_json(bundle["sub_mp_signatures"])

    cursor.execute(
        """
        INSERT INTO rebalancing_signal_observations (
            business_date,
            strategy_profile_id,
            decision_id,
            decision_date,
            mp_signature,
            sub_mp_signatures_json,
            effective_target_signature_candidate,
            target_payload_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            decision_id = VALUES(decision_id),
            decision_date = VALUES(decision_date),
            mp_signature = VALUES(mp_signature),
            sub_mp_signatures_json = VALUES(sub_mp_signatures_json),
            effective_target_signature_candidate = VALUES(effective_target_signature_candidate),
            target_payload_json = VALUES(target_payload_json),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            business_date,
            strategy_profile_id,
            decision_id,
            decision_date,
            bundle["mp_signature"],
            sub_mp_signatures_json,
            bundle["effective_target_signature"],
            normalized_payload_json,
        ),
    )

    cursor.execute(
        """
        SELECT business_date, effective_target_signature_candidate
        FROM rebalancing_signal_observations
        WHERE strategy_profile_id = %s
        ORDER BY business_date DESC, updated_at DESC, id DESC
        LIMIT 10
        """,
        (strategy_profile_id,),
    )
    recent_rows = cursor.fetchall() or []
    consecutive_days = calculate_consecutive_observation_days(
        recent_rows,
        bundle["effective_target_signature"],
    )
    if consecutive_days <= 0:
        consecutive_days = 1
    streak_rows = recent_rows[:consecutive_days]
    first_seen_date = streak_rows[-1]["business_date"] if streak_rows else business_date

    cursor.execute(
        """
        SELECT id, target_signature
        FROM effective_rebalancing_targets
        WHERE strategy_profile_id = %s
          AND status = %s
        ORDER BY effective_from_date DESC, id DESC
        LIMIT 1
        """,
        (strategy_profile_id, ACTIVE_STATUS),
    )
    active_target_row = cursor.fetchone()
    active_target_signature = active_target_row.get("target_signature") if active_target_row else None

    cursor.execute(
        """
        UPDATE rebalancing_signal_candidates
        SET status = %s, updated_at = CURRENT_TIMESTAMP
        WHERE strategy_profile_id = %s
          AND scope_type = %s
          AND asset_class = %s
          AND status = %s
          AND candidate_signature <> %s
        """,
        (
            CANCELLED_STATUS,
            strategy_profile_id,
            GLOBAL_SCOPE,
            GLOBAL_ASSET_CLASS,
            PENDING_STATUS,
            bundle["effective_target_signature"],
        ),
    )

    if active_target_signature == bundle["effective_target_signature"]:
        cursor.execute(
            """
            UPDATE rebalancing_signal_candidates
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE strategy_profile_id = %s
              AND scope_type = %s
              AND asset_class = %s
              AND status = %s
            """,
            (
                CANCELLED_STATUS,
                strategy_profile_id,
                GLOBAL_SCOPE,
                GLOBAL_ASSET_CLASS,
                PENDING_STATUS,
            ),
        )
        return {
            "business_date": business_date,
            "consecutive_days": consecutive_days,
            "candidate_status": CANCELLED_STATUS,
            "effective_target_signature": bundle["effective_target_signature"],
            "promoted": False,
        }

    candidate_status = CONFIRMED_STATUS if consecutive_days >= 3 else PENDING_STATUS
    cursor.execute(
        """
        INSERT INTO rebalancing_signal_candidates (
            scope_type,
            strategy_profile_id,
            asset_class,
            candidate_signature,
            first_seen_date,
            last_seen_date,
            consecutive_days,
            status,
            supersedes_target_signature,
            latest_decision_id,
            target_payload_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            first_seen_date = VALUES(first_seen_date),
            last_seen_date = VALUES(last_seen_date),
            consecutive_days = VALUES(consecutive_days),
            status = VALUES(status),
            supersedes_target_signature = VALUES(supersedes_target_signature),
            latest_decision_id = VALUES(latest_decision_id),
            target_payload_json = VALUES(target_payload_json),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            GLOBAL_SCOPE,
            strategy_profile_id,
            GLOBAL_ASSET_CLASS,
            bundle["effective_target_signature"],
            first_seen_date,
            business_date,
            consecutive_days,
            candidate_status,
            active_target_signature,
            decision_id,
            normalized_payload_json,
        ),
    )

    cursor.execute(
        """
        SELECT id
        FROM rebalancing_signal_candidates
        WHERE strategy_profile_id = %s
          AND scope_type = %s
          AND asset_class = %s
          AND candidate_signature = %s
        LIMIT 1
        """,
        (
            strategy_profile_id,
            GLOBAL_SCOPE,
            GLOBAL_ASSET_CLASS,
            bundle["effective_target_signature"],
        ),
    )
    candidate_row = cursor.fetchone() or {}
    candidate_id = candidate_row.get("id")

    promoted = False
    if candidate_status == CONFIRMED_STATUS:
        cursor.execute(
            """
            UPDATE effective_rebalancing_targets
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE strategy_profile_id = %s
              AND status = %s
            """,
            (
                SUPERSEDED_STATUS,
                strategy_profile_id,
                ACTIVE_STATUS,
            ),
        )
        cursor.execute(
            """
            INSERT INTO effective_rebalancing_targets (
                target_signature,
                strategy_profile_id,
                mp_signature,
                sub_mp_signatures_json,
                source_candidate_id,
                source_decision_id,
                effective_from_date,
                status,
                target_payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                bundle["effective_target_signature"],
                strategy_profile_id,
                bundle["mp_signature"],
                sub_mp_signatures_json,
                candidate_id,
                decision_id,
                business_date,
                ACTIVE_STATUS,
                normalized_payload_json,
            ),
        )
        cursor.execute(
            """
            UPDATE rebalancing_signal_candidates
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                APPLIED_STATUS,
                candidate_id,
            ),
        )
        promoted = True

    return {
        "business_date": business_date,
        "consecutive_days": consecutive_days,
        "candidate_status": APPLIED_STATUS if promoted else candidate_status,
        "effective_target_signature": bundle["effective_target_signature"],
        "promoted": promoted,
    }


def _coerce_business_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    raise ValueError(f"지원하지 않는 decision_date 형식입니다: {type(value)}")


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_payload(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_dump_json(payload).encode("utf-8")).hexdigest()


def _to_float(value: Any) -> float:
    try:
        return round(float(value or 0), 8)
    except (TypeError, ValueError):
        return 0.0
