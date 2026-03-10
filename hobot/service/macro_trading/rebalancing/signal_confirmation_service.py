import json
import logging
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from service.database.db import get_db_connection
from service.macro_trading.rebalancing.signal_tracker import (
    DEFAULT_STRATEGY_PROFILE_ID,
    normalize_target_payload,
    track_signal_observation,
)


logger = logging.getLogger(__name__)


DEFAULT_SIGNAL_CONFIRMATION_TIME = time(hour=8, minute=35)


def register_strategy_decision_signal(
    cursor: Any,
    strategy_profile_id: Optional[str],
    decision_id: int,
    decision_date: Any,
    target_payload: Any,
) -> Dict[str, Any]:
    """
    이미 저장된 전략 결정을 signal observation/candidate/effective target 경로에 반영한다.
    운영 AI 분석 저장과 테스트 fixture 저장이 동일한 판정 로직을 타도록 하는 공통 진입점이다.
    """
    resolved_strategy_profile_id = (
        str(strategy_profile_id or DEFAULT_STRATEGY_PROFILE_ID).strip() or DEFAULT_STRATEGY_PROFILE_ID
    )
    decision_timestamp = _coerce_datetime(decision_date)
    normalized_target_payload = normalize_target_payload(target_payload)
    _ensure_sub_mp_details_snapshot(normalized_target_payload)

    signal_result = track_signal_observation(
        cursor=cursor,
        strategy_profile_id=resolved_strategy_profile_id,
        decision_id=decision_id,
        decision_date=decision_timestamp,
        target_payload=normalized_target_payload,
    )
    return {
        "status": "SUCCESS",
        "strategy_profile_id": resolved_strategy_profile_id,
        "decision_id": decision_id,
        "decision_date": decision_timestamp.isoformat(),
        **signal_result,
    }


def extract_signal_confirmation_fixture(fixture_payload: Optional[Any]) -> Optional[Dict[str, Any]]:
    """fixture payload에서 signal confirmation 입력 블록을 추출한다."""
    if not fixture_payload:
        return None

    payload = fixture_payload
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        return None

    signal_confirmation = payload.get("signal_confirmation")
    if isinstance(signal_confirmation, dict):
        return signal_confirmation

    if isinstance(payload.get("target_payload"), dict):
        return {"target_payload": payload["target_payload"]}

    if "mp_id" in payload and "target_allocation" in payload:
        return {"target_payload": payload}

    return None


def build_signal_confirmation_assertions(
    session_id: str,
    business_date: Any,
    result: Dict[str, Any],
    fixture_payload: Optional[Any],
) -> List[Dict[str, Any]]:
    """fixture의 expected 블록을 기준으로 assertion payload를 만든다."""
    if not fixture_payload:
        return []

    payload = fixture_payload
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        return []

    expected_root = payload.get("expected")
    if not isinstance(expected_root, dict):
        return []

    expected_signal = expected_root.get("signal_confirmation")
    if not isinstance(expected_signal, dict):
        return []

    assertions: List[Dict[str, Any]] = []
    for field in ("candidate_status", "consecutive_days", "promoted", "effective_target_signature"):
        if field not in expected_signal:
            continue
        expected_value = expected_signal.get(field)
        actual_value = result.get(field)
        passed = expected_value == actual_value
        assertions.append(
            {
                "session_id": session_id,
                "business_date": business_date,
                "assertion_key": f"signal_confirmation.{field}",
                "status": "PASSED" if passed else "FAILED",
                "expected": expected_value,
                "actual": actual_value,
                "message": None if passed else f"expected={expected_value}, actual={actual_value}",
            }
        )
    return assertions


def run_fixture_signal_confirmation(
    strategy_profile_id: str,
    business_date: Any,
    fixture_payload: Optional[Any],
    session_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    fixture 기반 synthetic decision을 저장하고 Phase 1 observation/effective target 로직을 실행한다.
    """
    try:
        signal_fixture = extract_signal_confirmation_fixture(fixture_payload)
        if not signal_fixture:
            return {
                "status": "SKIPPED_NO_SIGNAL_FIXTURE",
                "message": "fixture에 signal_confirmation 또는 target_payload가 없습니다.",
            }

        normalized_date = _coerce_date(business_date)
        decision_timestamp = datetime.combine(normalized_date, DEFAULT_SIGNAL_CONFIRMATION_TIME)
        normalized_target_payload = normalize_target_payload(signal_fixture.get("target_payload") or signal_fixture)
        _ensure_sub_mp_details_snapshot(normalized_target_payload)
        _apply_fixture_decision_meta(normalized_target_payload, signal_fixture, session_context, normalized_date)

        analysis_summary = str(signal_fixture.get("analysis_summary") or "").strip()
        if not analysis_summary:
            analysis_summary = f"[PAPER_TIME_TRAVEL] fixture signal for {normalized_date.isoformat()}"

        recommended_stocks = signal_fixture.get("recommended_stocks")
        quant_signals = signal_fixture.get("quant_signals")
        account_pnl = signal_fixture.get("account_pnl")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ai_strategy_decisions (
                    strategy_profile_id,
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    recommended_stocks,
                    quant_signals,
                    account_pnl
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    strategy_profile_id or DEFAULT_STRATEGY_PROFILE_ID,
                    decision_timestamp,
                    analysis_summary,
                    json.dumps(normalized_target_payload, ensure_ascii=False),
                    json.dumps(recommended_stocks, ensure_ascii=False) if recommended_stocks is not None else None,
                    json.dumps(quant_signals, ensure_ascii=False) if quant_signals is not None else None,
                    json.dumps(account_pnl, ensure_ascii=False) if account_pnl is not None else None,
                ),
            )
            decision_id = cursor.lastrowid
            signal_result = register_strategy_decision_signal(
                cursor=cursor,
                strategy_profile_id=strategy_profile_id or DEFAULT_STRATEGY_PROFILE_ID,
                decision_id=decision_id,
                decision_date=decision_timestamp,
                target_payload=normalized_target_payload,
            )

        return {
            "status": "SUCCESS",
            "decision_id": decision_id,
            "decision_date": decision_timestamp.isoformat(),
            "business_date": normalized_date.isoformat(),
            "analysis_summary": analysis_summary,
            **signal_result,
        }
    except Exception as exc:
        logger.error("Fixture signal confirmation failed: %s", exc, exc_info=True)
        return {
            "status": "ERROR",
            "message": str(exc),
            "business_date": _coerce_date(business_date).isoformat(),
        }


def _ensure_sub_mp_details_snapshot(target_payload: Dict[str, Any]) -> None:
    if target_payload.get("sub_mp_details_snapshot"):
        return

    sub_mp_payload = target_payload.get("sub_mp")
    if not sub_mp_payload:
        return

    try:
        from service.macro_trading.ai_strategist import get_sub_mp_details

        sub_mp_details_snapshot = get_sub_mp_details(sub_mp_payload)
        if sub_mp_details_snapshot:
            target_payload["sub_mp_details_snapshot"] = sub_mp_details_snapshot
    except Exception as exc:
        logger.warning("Failed to build sub_mp_details_snapshot from fixture: %s", exc)


def _apply_fixture_decision_meta(
    target_payload: Dict[str, Any],
    signal_fixture: Dict[str, Any],
    session_context: Optional[Dict[str, Any]],
    business_date: date,
) -> None:
    decision_meta = dict(target_payload.get("decision_meta") or {})
    decision_meta["source"] = "paper_time_travel_fixture"
    decision_meta["business_date"] = business_date.isoformat()

    if session_context:
        session_id = str(session_context.get("session_id") or "").strip()
        if session_id:
            decision_meta["test_session_id"] = session_id
        fixture_name = str(session_context.get("fixture_name") or "").strip()
        if fixture_name:
            decision_meta["fixture_name"] = fixture_name
        advanced_by = str(session_context.get("advanced_by") or "").strip()
        if advanced_by:
            decision_meta["advanced_by"] = advanced_by

    signal_label = str(signal_fixture.get("signal_label") or "").strip()
    if signal_label:
        decision_meta["signal_label"] = signal_label

    target_payload["decision_meta"] = decision_meta


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    raise ValueError(f"Unsupported business_date type: {type(value)}")


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, DEFAULT_SIGNAL_CONFIRMATION_TIME)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if isinstance(parsed, datetime):
            return parsed
    raise ValueError(f"Unsupported decision_date type: {type(value)}")
