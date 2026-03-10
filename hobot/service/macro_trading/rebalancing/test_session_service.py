import json
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from service.core.time_provider import TimeProvider
from service.database.db import get_db_connection
from service.macro_trading.kis.user_credentials import get_user_kis_credentials
from service.macro_trading.rebalancing.paper_broker_adapter import PaperTradingBrokerAdapter
from service.macro_trading.rebalancing.scenario_fixture_loader import ScenarioFixtureLoader
from service.macro_trading.rebalancing.signal_confirmation_service import (
    build_signal_confirmation_assertions,
    run_fixture_signal_confirmation,
)
from service.macro_trading.rebalancing.signal_tracker import DEFAULT_STRATEGY_PROFILE_ID


logger = logging.getLogger(__name__)


TEST_MODE_PAPER_TIME_TRAVEL = "PAPER_TIME_TRAVEL"
TEST_MODE_PAPER_REALTIME = "PAPER_REALTIME"
TEST_MODE_DUMMY_UNIT = "DUMMY_UNIT"
ACTIVE_STATUS = "ACTIVE"
COMPLETED_STATUS = "COMPLETED"
CANCELLED_STATUS = "CANCELLED"
DAY_STATUS_PLANNED = "PLANNED"
DAY_STATUS_RUNNING = "RUNNING"
DAY_STATUS_COMPLETED = "COMPLETED"
DAY_STATUS_FAILED = "FAILED"
DAY_STATUS_PENDING_MARKET_WINDOW = "PENDING_MARKET_WINDOW"


class TestSessionService:
    @classmethod
    def list_available_fixtures(cls) -> List[str]:
        return ScenarioFixtureLoader.list_available_fixtures()

    @classmethod
    def get_active_session(cls) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM rebalancing_test_sessions
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ACTIVE_STATUS,),
            )
            session_row = cursor.fetchone()
        if not session_row:
            return None
        return cls.get_session_details(session_row["session_id"])

    @classmethod
    def create_session(
        cls,
        name: str,
        user_ids: List[str],
        start_business_date: Any,
        mode: str = TEST_MODE_PAPER_TIME_TRAVEL,
        strategy_profile_id: str = DEFAULT_STRATEGY_PROFILE_ID,
        fixture_name: Optional[str] = None,
        capture_baseline: bool = True,
        auto_execute_enabled: bool = False,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_mode = str(mode or TEST_MODE_PAPER_TIME_TRAVEL).strip().upper()
        if normalized_mode not in {
            TEST_MODE_PAPER_TIME_TRAVEL,
            TEST_MODE_PAPER_REALTIME,
            TEST_MODE_DUMMY_UNIT,
        }:
            raise ValueError(f"Unsupported test mode: {mode}")

        if not user_ids:
            raise ValueError("At least one user_id is required")

        active_session = cls.get_active_session()
        if active_session:
            raise ValueError(f"Active test session already exists: {active_session['session_id']}")

        normalized_start_date = cls._coerce_date(start_business_date)
        session_id = uuid.uuid4().hex
        fixture_payload = ScenarioFixtureLoader.load_fixture(fixture_name) if fixture_name else None
        current_virtual_time = datetime.combine(normalized_start_date, cls._default_session_time())

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO rebalancing_test_sessions (
                    session_id,
                    name,
                    mode,
                    status,
                    strategy_profile_id,
                    fixture_name,
                    fixture_payload_json,
                    start_business_date,
                    current_virtual_business_date,
                    current_virtual_time,
                    auto_execute_enabled,
                    created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    name,
                    normalized_mode,
                    ACTIVE_STATUS,
                    strategy_profile_id,
                    fixture_name,
                    cls._json_dumps(fixture_payload) if fixture_payload else None,
                    normalized_start_date,
                    normalized_start_date,
                    current_virtual_time,
                    bool(auto_execute_enabled),
                    created_by,
                ),
            )

            for user_id in user_ids:
                baseline_data = cls._build_baseline_row(
                    user_id=user_id,
                    capture_baseline=capture_baseline,
                )
                cursor.execute(
                    """
                    INSERT INTO rebalancing_test_session_users (
                        session_id,
                        user_id,
                        is_paper_account,
                        baseline_status,
                        baseline_snapshot_json,
                        baseline_message,
                        baseline_captured_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        baseline_data["user_id"],
                        baseline_data["is_paper_account"],
                        baseline_data["baseline_status"],
                        cls._json_dumps(baseline_data["baseline_snapshot_json"])
                        if baseline_data["baseline_snapshot_json"] is not None else None,
                        baseline_data["baseline_message"],
                        baseline_data["baseline_captured_at"],
                    ),
                )

        TimeProvider.set_virtual_business_date(normalized_start_date, default_time="08:00")
        TimeProvider.set_active_test_session(session_id)
        return cls.get_session_details(session_id)

    @classmethod
    async def advance_business_day(
        cls,
        session_id: str,
        advanced_by: Optional[str] = None,
        run_signal_confirmation: bool = True,
        run_rebalancing_execution: bool = False,
    ) -> Dict[str, Any]:
        session = cls.get_session_details(session_id)
        if not session:
            raise ValueError(f"Test session not found: {session_id}")
        if session["status"] != ACTIVE_STATUS:
            raise ValueError(f"Test session is not active: {session_id}")
        if session["mode"] != TEST_MODE_PAPER_TIME_TRAVEL:
            raise ValueError("advance_business_day is only supported for PAPER_TIME_TRAVEL mode")

        current_business_date = cls._coerce_date(session["current_virtual_business_date"])
        next_business_date = TimeProvider.get_next_business_day(current_business_date)
        current_virtual_time = TimeProvider.set_virtual_business_date(next_business_date, default_time="08:00")
        TimeProvider.set_active_test_session(session_id)

        fixture_payload = ScenarioFixtureLoader.resolve_fixture_for_business_date(
            session.get("fixture_payload_json"),
            next_business_date,
        )
        should_execute_rebalancing = bool(
            run_rebalancing_execution or session.get("auto_execute_enabled", False)
        )
        logs: List[Dict[str, Any]] = []
        user_results: List[Dict[str, Any]] = []
        real_executed_at = None
        market_window_status = "NOT_REQUESTED"
        day_status = DAY_STATUS_PLANNED

        if run_signal_confirmation:
            signal_result = run_fixture_signal_confirmation(
                strategy_profile_id=session["strategy_profile_id"],
                business_date=next_business_date,
                fixture_payload=fixture_payload,
                session_context={
                    "session_id": session_id,
                    "fixture_name": session.get("fixture_name"),
                    "advanced_by": advanced_by,
                },
            )
            logs.append(
                {
                    "step": "signal_confirmation",
                    "status": signal_result.get("status"),
                    "result": signal_result,
                }
            )
            for assertion in build_signal_confirmation_assertions(
                session_id=session_id,
                business_date=next_business_date,
                result=signal_result,
                fixture_payload=fixture_payload,
            ):
                cls.record_assertion(
                    session_id=assertion["session_id"],
                    business_date=assertion["business_date"],
                    assertion_key=assertion["assertion_key"],
                    status=assertion["status"],
                    expected=assertion["expected"],
                    actual=assertion["actual"],
                    message=assertion["message"],
                )
            if signal_result.get("status") == "ERROR":
                day_status = DAY_STATUS_FAILED

        if should_execute_rebalancing:
            if day_status == DAY_STATUS_FAILED:
                logs.append(
                    {
                        "step": "rebalancing_execution",
                        "status": "SKIPPED_SIGNAL_FAILURE",
                        "message": "signal confirmation 실패로 인해 리밸런싱 실행을 건너뜀",
                    }
                )
                should_execute_rebalancing = False
        if should_execute_rebalancing:
            market_window_status = "OPEN" if PaperTradingBrokerAdapter.is_us_market_open() else "CLOSED"
            if market_window_status != "OPEN":
                day_status = DAY_STATUS_PENDING_MARKET_WINDOW
                logs.append(
                    {
                        "step": "rebalancing_execution",
                        "status": "DEFERRED",
                        "message": "실제 모의투자 주문은 미국 정규장 시간에만 실행",
                    }
                )
            else:
                day_status = DAY_STATUS_RUNNING
                real_executed_at = datetime.now()
                for session_user in session.get("users", []):
                    user_id = session_user["user_id"]
                    if not session_user.get("is_paper_account"):
                        user_results.append(
                            {
                                "user_id": user_id,
                                "status": "SKIPPED",
                                "message": "paper trading 계좌가 아님",
                            }
                        )
                        continue

                    try:
                        adapter = PaperTradingBrokerAdapter(user_id)
                        execution_result = await adapter.execute_rebalancing(
                            max_phase=5,
                            strategy_profile_id=session["strategy_profile_id"],
                            business_date=next_business_date,
                        )
                        user_results.append(
                            {
                                "user_id": user_id,
                                "status": execution_result.get("status", "unknown"),
                                "result": execution_result,
                            }
                        )
                    except Exception as exc:
                        logger.error("Paper test execution failed user=%s: %s", user_id, exc, exc_info=True)
                        user_results.append(
                            {
                                "user_id": user_id,
                                "status": "FAILED",
                                "message": str(exc),
                            }
                        )

                if user_results and all(item.get("status") not in {"FAILED", "error"} for item in user_results):
                    day_status = DAY_STATUS_COMPLETED
                else:
                    day_status = DAY_STATUS_FAILED
        else:
            logs.append(
                {
                    "step": "rebalancing_execution",
                    "status": "SKIPPED",
                    "message": "run_rebalancing_execution=false",
                }
            )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE rebalancing_test_sessions
                SET current_virtual_business_date = %s,
                    current_virtual_time = %s,
                    last_advanced_at = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """,
                (
                    next_business_date,
                    current_virtual_time,
                    datetime.now(),
                    session_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO rebalancing_test_day_results (
                    session_id,
                    business_date,
                    status,
                    run_signal_confirmation,
                    run_rebalancing_execution,
                    fixture_payload_json,
                    real_executed_at,
                    market_window_status,
                    user_results_json,
                    logs_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    run_signal_confirmation = VALUES(run_signal_confirmation),
                    run_rebalancing_execution = VALUES(run_rebalancing_execution),
                    fixture_payload_json = VALUES(fixture_payload_json),
                    real_executed_at = VALUES(real_executed_at),
                    market_window_status = VALUES(market_window_status),
                    user_results_json = VALUES(user_results_json),
                    logs_json = VALUES(logs_json),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    session_id,
                    next_business_date,
                    day_status,
                    bool(run_signal_confirmation),
                    should_execute_rebalancing,
                    cls._json_dumps(fixture_payload) if fixture_payload is not None else None,
                    real_executed_at,
                    market_window_status,
                    cls._json_dumps(user_results),
                    cls._json_dumps(logs),
                ),
            )

        return {
            "session": cls.get_session_details(session_id),
            "day_result": cls.get_day_result(session_id, next_business_date),
            "advanced_by": advanced_by,
        }

    @classmethod
    def close_session(
        cls,
        session_id: str,
        closed_by: Optional[str] = None,
        status: str = COMPLETED_STATUS,
    ) -> Dict[str, Any]:
        normalized_status = status if status in {COMPLETED_STATUS, CANCELLED_STATUS} else COMPLETED_STATUS
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE rebalancing_test_sessions
                SET status = %s,
                    closed_by = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """,
                (
                    normalized_status,
                    closed_by,
                    session_id,
                ),
            )
            if not cursor.rowcount:
                raise ValueError(f"Test session not found: {session_id}")
        if TimeProvider.get_active_test_session_id() == session_id:
            TimeProvider.reset_to_real_time(clear_active_session=True)
        return cls.get_session_details(session_id)

    @classmethod
    def get_session_details(cls, session_id: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM rebalancing_test_sessions WHERE session_id = %s",
                (session_id,),
            )
            session_row = cursor.fetchone()
            if not session_row:
                return None

            cursor.execute(
                """
                SELECT *
                FROM rebalancing_test_session_users
                WHERE session_id = %s
                ORDER BY id
                """,
                (session_id,),
            )
            user_rows = cursor.fetchall() or []

            cursor.execute(
                """
                SELECT *
                FROM rebalancing_test_day_results
                WHERE session_id = %s
                ORDER BY business_date DESC, id DESC
                LIMIT 20
                """,
                (session_id,),
            )
            day_rows = cursor.fetchall() or []

        session = cls._normalize_row(session_row)
        session["users"] = [cls._normalize_row(row) for row in user_rows]
        session["day_results"] = [cls._normalize_row(row) for row in day_rows]
        session["active_system_session_id"] = TimeProvider.get_active_test_session_id()
        session["virtual_business_date"] = TimeProvider.get_virtual_business_date().isoformat()
        return session

    @classmethod
    def list_day_results(cls, session_id: str) -> List[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM rebalancing_test_day_results
                WHERE session_id = %s
                ORDER BY business_date DESC, id DESC
                """,
                (session_id,),
            )
            day_rows = cursor.fetchall() or []
        return [cls._normalize_row(row) for row in day_rows]

    @classmethod
    def list_assertions(
        cls,
        session_id: str,
        business_date: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        normalized_business_date = cls._coerce_date(business_date) if business_date else None
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if normalized_business_date:
                cursor.execute(
                    """
                    SELECT *
                    FROM rebalancing_test_assertions
                    WHERE session_id = %s
                      AND business_date = %s
                    ORDER BY created_at DESC, id DESC
                    """,
                    (
                        session_id,
                        normalized_business_date,
                    ),
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                    FROM rebalancing_test_assertions
                    WHERE session_id = %s
                    ORDER BY created_at DESC, id DESC
                    """,
                    (session_id,),
                )
            rows = cursor.fetchall() or []
        return [cls._normalize_row(row) for row in rows]

    @classmethod
    def get_day_result(cls, session_id: str, business_date: Any) -> Optional[Dict[str, Any]]:
        normalized_date = cls._coerce_date(business_date)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM rebalancing_test_day_results
                WHERE session_id = %s
                  AND business_date = %s
                LIMIT 1
                """,
                (
                    session_id,
                    normalized_date,
                ),
            )
            row = cursor.fetchone()
        return cls._normalize_row(row) if row else None

    @classmethod
    def record_assertion(
        cls,
        session_id: str,
        assertion_key: str,
        status: str,
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        message: Optional[str] = None,
        business_date: Optional[Any] = None,
    ) -> None:
        normalized_business_date = cls._coerce_date(business_date) if business_date else None
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO rebalancing_test_assertions (
                    session_id,
                    business_date,
                    assertion_key,
                    status,
                    expected_json,
                    actual_json,
                    message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    normalized_business_date,
                    assertion_key,
                    status,
                    cls._json_dumps(expected) if expected is not None else None,
                    cls._json_dumps(actual) if actual is not None else None,
                    message,
                ),
            )

    @classmethod
    def _build_baseline_row(cls, user_id: str, capture_baseline: bool) -> Dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        credentials = get_user_kis_credentials(normalized_user_id)
        is_paper_account = bool(credentials and credentials.get("is_simulation", False))
        row = {
            "user_id": normalized_user_id,
            "is_paper_account": is_paper_account,
            "baseline_status": "SKIPPED" if not capture_baseline else "PENDING",
            "baseline_snapshot_json": None,
            "baseline_message": None,
            "baseline_captured_at": None,
        }

        if not capture_baseline:
            row["baseline_message"] = "capture_baseline=false"
            return row

        if not is_paper_account:
            row["baseline_status"] = "FAILED"
            row["baseline_message"] = "paper trading 계좌가 필요합니다"
            return row

        try:
            snapshot = PaperTradingBrokerAdapter(normalized_user_id).get_account_snapshot()
            row["baseline_status"] = "CAPTURED"
            row["baseline_snapshot_json"] = snapshot
            row["baseline_captured_at"] = datetime.now()
        except Exception as exc:
            row["baseline_status"] = "FAILED"
            row["baseline_message"] = str(exc)
        return row

    @staticmethod
    def _normalize_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return row
        normalized = dict(row)
        for key, value in list(normalized.items()):
            if isinstance(value, (datetime, date)):
                normalized[key] = value.isoformat()
            elif key.endswith("_json") and value is not None:
                normalized[key] = TestSessionService._json_loads(value)
        return normalized

    @staticmethod
    def _json_loads(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        raise ValueError(f"Unsupported business date type: {type(value)}")

    @staticmethod
    def _default_session_time():
        return datetime.strptime("08:00", "%H:%M").time()
