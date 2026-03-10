import json
import logging
import math
import uuid
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from service.database.db import get_db_connection
from service.macro_trading.rebalancing.signal_tracker import DEFAULT_STRATEGY_PROFILE_ID


logger = logging.getLogger(__name__)


DEFAULT_EXECUTION_DAYS = 5

RUN_STATUS_ACTIVE = "ACTIVE"
RUN_STATUS_PAUSED = "PAUSED"
RUN_STATUS_COMPLETED = "COMPLETED"
RUN_STATUS_CANCELLED = "CANCELLED"
RUN_STATUS_SUPERSEDED = "SUPERSEDED"
RUN_STATUS_FAILED = "FAILED"
OPEN_RUN_STATUSES = (RUN_STATUS_ACTIVE, RUN_STATUS_PAUSED)

SNAPSHOT_TYPE_PLANNING = "PLANNING"
SNAPSHOT_TYPE_EXECUTION_RESULT = "EXECUTION_RESULT"
SNAPSHOT_TYPE_STATE_TRANSITION = "STATE_TRANSITION"


def calculate_today_slice_quantity(quantity: Any, remaining_execution_days: Any) -> int:
    normalized_quantity = max(int(quantity or 0), 0)
    normalized_days = max(int(remaining_execution_days or 1), 1)
    if normalized_quantity <= 0:
        return 0
    return max(1, math.ceil(normalized_quantity / normalized_days))


def build_daily_sliced_trades(
    trades: Iterable[Dict[str, Any]],
    remaining_execution_days: Any,
) -> List[Dict[str, Any]]:
    normalized_days = max(int(remaining_execution_days or 1), 1)
    sliced_trades: List[Dict[str, Any]] = []
    for trade in trades or []:
        quantity = max(int((trade or {}).get("quantity") or 0), 0)
        if quantity <= 0:
            continue

        today_quantity = min(quantity, calculate_today_slice_quantity(quantity, normalized_days))
        action = str((trade or {}).get("action") or "").upper()
        if action not in {"BUY", "SELL"}:
            continue

        sliced_trade = dict(trade)
        sliced_trade["quantity"] = today_quantity
        sliced_trade["diff"] = today_quantity if action == "BUY" else -today_quantity
        sliced_trade["planned_total_quantity"] = quantity
        sliced_trade["remaining_execution_days"] = normalized_days
        sliced_trade["slice_rule"] = "ceil(remaining_qty / remaining_execution_days)"
        sliced_trades.append(sliced_trade)
    return sliced_trades


class RebalancingRunRepository:
    def get_open_run(
        self,
        user_id: str,
        strategy_profile_id: str = DEFAULT_STRATEGY_PROFILE_ID,
    ) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            return self._fetch_open_run(cursor, user_id, strategy_profile_id)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            return self._fetch_run(cursor, run_id)

    def list_run_snapshots(self, run_id: str) -> List[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM rebalancing_run_snapshots
                WHERE run_id = %s
                ORDER BY business_date ASC, id ASC
                """,
                (run_id,),
            )
            rows = cursor.fetchall() or []
        return [self._normalize_snapshot_row(row) for row in rows]

    def ensure_run_for_target(
        self,
        user_id: str,
        strategy_profile_id: str,
        business_date: Any,
        target_signature: str,
        target_payload: Any,
        planned_execution_days: int = DEFAULT_EXECUTION_DAYS,
    ) -> Dict[str, Any]:
        normalized_profile_id = str(strategy_profile_id or DEFAULT_STRATEGY_PROFILE_ID).strip() or DEFAULT_STRATEGY_PROFILE_ID
        normalized_target_signature = str(target_signature or "").strip()
        if not normalized_target_signature:
            raise ValueError("target_signature is required")

        normalized_business_date = _coerce_date(business_date)
        normalized_target_payload = _normalize_json_value(target_payload)
        normalized_planned_days = max(int(planned_execution_days or DEFAULT_EXECUTION_DAYS), 1)
        now = datetime.now()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            open_run = self._fetch_open_run(cursor, user_id, normalized_profile_id)
            if open_run and open_run["target_signature"] == normalized_target_signature:
                if open_run["status"] == RUN_STATUS_PAUSED:
                    cursor.execute(
                        """
                        UPDATE rebalancing_runs
                        SET status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE run_id = %s
                        """,
                        (RUN_STATUS_ACTIVE, open_run["run_id"]),
                    )
                    self._upsert_snapshot(
                        cursor=cursor,
                        run_id=open_run["run_id"],
                        business_date=normalized_business_date,
                        snapshot_type=SNAPSHOT_TYPE_STATE_TRANSITION,
                        metadata={
                            "reason": "RESUMED_FOR_MATCHING_TARGET",
                            "target_signature": normalized_target_signature,
                        },
                    )
                return self._fetch_run(cursor, open_run["run_id"])

            parent_run_id = None
            new_run_id = uuid.uuid4().hex
            if open_run:
                parent_run_id = open_run["run_id"]
                cursor.execute(
                    """
                    UPDATE rebalancing_runs
                    SET status = %s,
                        superseded_by_run_id = %s,
                        completed_at = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE run_id = %s
                    """,
                    (RUN_STATUS_SUPERSEDED, new_run_id, now, parent_run_id),
                )
                self._upsert_snapshot(
                    cursor=cursor,
                    run_id=parent_run_id,
                    business_date=normalized_business_date,
                    snapshot_type=SNAPSHOT_TYPE_STATE_TRANSITION,
                    metadata={
                        "reason": "SUPERSEDED_BY_NEW_TARGET",
                        "superseded_by_run_id": new_run_id,
                        "previous_target_signature": open_run["target_signature"],
                        "new_target_signature": normalized_target_signature,
                    },
                )

            cursor.execute(
                """
                INSERT INTO rebalancing_runs (
                    run_id,
                    user_id,
                    strategy_profile_id,
                    target_signature,
                    status,
                    parent_run_id,
                    planned_execution_days,
                    executed_days,
                    remaining_execution_days,
                    start_business_date,
                    target_payload_json,
                    notes_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s)
                """,
                (
                    new_run_id,
                    user_id,
                    normalized_profile_id,
                    normalized_target_signature,
                    RUN_STATUS_ACTIVE,
                    parent_run_id,
                    normalized_planned_days,
                    normalized_planned_days,
                    normalized_business_date,
                    _dump_json(normalized_target_payload),
                    _dump_json(
                        {
                            "created_reason": "NEW_TARGET_RUN" if not parent_run_id else "SUPERSEDE_PREVIOUS_RUN",
                        }
                    ),
                ),
            )
            self._upsert_snapshot(
                cursor=cursor,
                run_id=new_run_id,
                business_date=normalized_business_date,
                snapshot_type=SNAPSHOT_TYPE_STATE_TRANSITION,
                metadata={
                    "reason": "CREATED",
                    "target_signature": normalized_target_signature,
                    "parent_run_id": parent_run_id,
                },
            )
            return self._fetch_run(cursor, new_run_id)

    def save_planning_snapshot(
        self,
        run_id: str,
        business_date: Any,
        *,
        current_state: Optional[Dict[str, Any]] = None,
        full_trades: Optional[List[Dict[str, Any]]] = None,
        sliced_trades: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_business_date = _coerce_date(business_date)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            run_row = self._fetch_run(cursor, run_id)
            if not run_row:
                return None
            self._upsert_snapshot(
                cursor=cursor,
                run_id=run_id,
                business_date=normalized_business_date,
                snapshot_type=SNAPSHOT_TYPE_PLANNING,
                current_state=current_state,
                full_trade_plan=full_trades,
                sliced_trade_plan=sliced_trades,
                metadata=metadata,
            )
            return self._fetch_run(cursor, run_id)

    def record_execution_result(
        self,
        run_id: str,
        business_date: Any,
        execution_result: Dict[str, Any],
        *,
        current_state: Optional[Dict[str, Any]] = None,
        full_trades: Optional[List[Dict[str, Any]]] = None,
        sliced_trades: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_business_date = _coerce_date(business_date)
        normalized_execution_result = _normalize_json_value(execution_result)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            run_row = self._fetch_run(cursor, run_id)
            if not run_row:
                return None

            cursor.execute(
                """
                SELECT id
                FROM rebalancing_run_snapshots
                WHERE run_id = %s
                  AND business_date = %s
                  AND snapshot_type = %s
                LIMIT 1
                """,
                (run_id, normalized_business_date, SNAPSHOT_TYPE_EXECUTION_RESULT),
            )
            existing_snapshot = cursor.fetchone()
            current_executed_days = max(int(run_row.get("executed_days") or 0), 0)
            planned_execution_days = max(int(run_row.get("planned_execution_days") or DEFAULT_EXECUTION_DAYS), 1)
            executed_days = current_executed_days if existing_snapshot else current_executed_days + 1
            remaining_execution_days = max(planned_execution_days - executed_days, 0)

            result_status = str(normalized_execution_result.get("status") or "").lower()
            new_status = RUN_STATUS_COMPLETED if remaining_execution_days <= 0 else RUN_STATUS_ACTIVE

            cursor.execute(
                """
                UPDATE rebalancing_runs
                SET status = %s,
                    executed_days = %s,
                    remaining_execution_days = %s,
                    last_executed_business_date = %s,
                    last_error = %s,
                    completed_at = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = %s
                """,
                (
                    new_status,
                    executed_days,
                    remaining_execution_days,
                    normalized_business_date,
                    None if result_status in {"success", "stopped"} else str(normalized_execution_result.get("message") or ""),
                    datetime.now() if new_status == RUN_STATUS_COMPLETED else None,
                    run_id,
                ),
            )
            execution_metadata = dict(metadata or {})
            execution_metadata["executed_days"] = executed_days
            execution_metadata["remaining_execution_days"] = remaining_execution_days
            execution_metadata["run_status"] = new_status
            self._upsert_snapshot(
                cursor=cursor,
                run_id=run_id,
                business_date=normalized_business_date,
                snapshot_type=SNAPSHOT_TYPE_EXECUTION_RESULT,
                current_state=current_state,
                full_trade_plan=full_trades,
                sliced_trade_plan=sliced_trades,
                execution_result=normalized_execution_result,
                metadata=execution_metadata,
            )
            return self._fetch_run(cursor, run_id)

    def complete_run(
        self,
        run_id: str,
        business_date: Any,
        completion_reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_business_date = _coerce_date(business_date)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            run_row = self._fetch_run(cursor, run_id)
            if not run_row:
                return None
            if run_row["status"] == RUN_STATUS_COMPLETED:
                return run_row
            cursor.execute(
                """
                UPDATE rebalancing_runs
                SET status = %s,
                    remaining_execution_days = 0,
                    completed_at = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = %s
                """,
                (RUN_STATUS_COMPLETED, datetime.now(), run_id),
            )
            self._upsert_snapshot(
                cursor=cursor,
                run_id=run_id,
                business_date=normalized_business_date,
                snapshot_type=SNAPSHOT_TYPE_STATE_TRANSITION,
                metadata={
                    "reason": completion_reason,
                    "details": _normalize_json_value(details),
                },
            )
            return self._fetch_run(cursor, run_id)

    def pause_run(
        self,
        run_id: str,
        business_date: Any,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._transition_run_status(
            run_id=run_id,
            business_date=business_date,
            status=RUN_STATUS_PAUSED,
            reason=reason,
            details=details,
        )

    def resume_run(
        self,
        run_id: str,
        business_date: Any,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._transition_run_status(
            run_id=run_id,
            business_date=business_date,
            status=RUN_STATUS_ACTIVE,
            reason=reason,
            details=details,
        )

    def _transition_run_status(
        self,
        *,
        run_id: str,
        business_date: Any,
        status: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_business_date = _coerce_date(business_date)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            run_row = self._fetch_run(cursor, run_id)
            if not run_row:
                return None
            cursor.execute(
                """
                UPDATE rebalancing_runs
                SET status = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = %s
                """,
                (status, run_id),
            )
            self._upsert_snapshot(
                cursor=cursor,
                run_id=run_id,
                business_date=normalized_business_date,
                snapshot_type=SNAPSHOT_TYPE_STATE_TRANSITION,
                metadata={
                    "reason": reason,
                    "details": _normalize_json_value(details),
                    "status": status,
                },
            )
            return self._fetch_run(cursor, run_id)

    def _fetch_open_run(
        self,
        cursor: Any,
        user_id: str,
        strategy_profile_id: str,
    ) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT *
            FROM rebalancing_runs
            WHERE user_id = %s
              AND strategy_profile_id = %s
              AND status IN (%s, %s)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (user_id, strategy_profile_id, RUN_STATUS_ACTIVE, RUN_STATUS_PAUSED),
        )
        row = cursor.fetchone()
        return self._normalize_run_row(row) if row else None

    def _fetch_run(self, cursor: Any, run_id: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT *
            FROM rebalancing_runs
            WHERE run_id = %s
            LIMIT 1
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        return self._normalize_run_row(row) if row else None

    def _upsert_snapshot(
        self,
        *,
        cursor: Any,
        run_id: str,
        business_date: date,
        snapshot_type: str,
        current_state: Optional[Dict[str, Any]] = None,
        full_trade_plan: Optional[List[Dict[str, Any]]] = None,
        sliced_trade_plan: Optional[List[Dict[str, Any]]] = None,
        execution_result: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO rebalancing_run_snapshots (
                run_id,
                business_date,
                snapshot_type,
                current_state_json,
                full_trade_plan_json,
                sliced_trade_plan_json,
                execution_result_json,
                metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                current_state_json = VALUES(current_state_json),
                full_trade_plan_json = VALUES(full_trade_plan_json),
                sliced_trade_plan_json = VALUES(sliced_trade_plan_json),
                execution_result_json = VALUES(execution_result_json),
                metadata_json = VALUES(metadata_json)
            """,
            (
                run_id,
                business_date,
                snapshot_type,
                _dump_json(_normalize_json_value(current_state)) if current_state is not None else None,
                _dump_json(_normalize_json_value(full_trade_plan)) if full_trade_plan is not None else None,
                _dump_json(_normalize_json_value(sliced_trade_plan)) if sliced_trade_plan is not None else None,
                _dump_json(_normalize_json_value(execution_result)) if execution_result is not None else None,
                _dump_json(_normalize_json_value(metadata)) if metadata is not None else None,
            ),
        )

    def _normalize_run_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        for field in ("target_payload_json", "notes_json"):
            normalized[field] = _load_json_field(normalized.get(field))
        if normalized.get("start_business_date"):
            normalized["start_business_date"] = normalized["start_business_date"].isoformat()
        if normalized.get("last_executed_business_date"):
            normalized["last_executed_business_date"] = normalized["last_executed_business_date"].isoformat()
        if normalized.get("completed_at"):
            normalized["completed_at"] = normalized["completed_at"].isoformat()
        if normalized.get("created_at"):
            normalized["created_at"] = normalized["created_at"].isoformat()
        if normalized.get("updated_at"):
            normalized["updated_at"] = normalized["updated_at"].isoformat()
        return normalized

    def _normalize_snapshot_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        for field in (
            "current_state_json",
            "full_trade_plan_json",
            "sliced_trade_plan_json",
            "execution_result_json",
            "metadata_json",
        ):
            normalized[field] = _load_json_field(normalized.get(field))
        if normalized.get("business_date"):
            normalized["business_date"] = normalized["business_date"].isoformat()
        if normalized.get("created_at"):
            normalized["created_at"] = normalized["created_at"].isoformat()
        return normalized


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    raise ValueError(f"Unsupported business_date type: {type(value)}")


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalize_json_value(item)
            for key, item in value.items()
        }
    return str(value)


def _load_json_field(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return value
    return value
