import json
from datetime import date, datetime, timedelta, time
from typing import Any, Optional
from service.database.db import get_db_connection

class TimeProvider:
    VIRTUAL_CLOCK_KEY = "virtual_clock"
    VIRTUAL_BUSINESS_DATE_KEY = "virtual_business_date"
    ACTIVE_TEST_SESSION_KEY = "active_rebalancing_test_session"

    @staticmethod
    def get_current_time() -> datetime:
        """현재 시스템 시간 반환 (가상 시간 적용)"""
        try:
            data = TimeProvider._load_state(TimeProvider.VIRTUAL_CLOCK_KEY)
            if isinstance(data, dict) and 'current_time' in data:
                return datetime.fromisoformat(data['current_time'])
        except Exception as e:
            # DB 연결 실패 등 예외 발생 시 실제 시간 반환
            print(f"TimeProvider Error: {e}")
        
        return datetime.now()

    @staticmethod
    def set_virtual_time(dt: datetime) -> None:
        """가상 시간 설정"""
        TimeProvider._upsert_state(
            TimeProvider.VIRTUAL_CLOCK_KEY,
            {"current_time": dt.isoformat()},
        )
        TimeProvider._upsert_state(
            TimeProvider.VIRTUAL_BUSINESS_DATE_KEY,
            {"business_date": dt.date().isoformat()},
        )

    @staticmethod
    def reset_to_real_time(clear_active_session: bool = False) -> None:
        """실제 시간으로 초기화 (가상 시간 삭제)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM system_state WHERE `key` IN (%s, %s)",
                (
                    TimeProvider.VIRTUAL_CLOCK_KEY,
                    TimeProvider.VIRTUAL_BUSINESS_DATE_KEY,
                ),
            )
            if clear_active_session:
                cursor.execute(
                    "DELETE FROM system_state WHERE `key` = %s",
                    (TimeProvider.ACTIVE_TEST_SESSION_KEY,),
                )

    @staticmethod
    def add_days(days: int, default_time: str = "08:00") -> datetime:
        """현재(또는 가상) 날짜에서 N일 이동 후 특정 시간으로 설정"""
        current = TimeProvider.get_current_time()
        target_date = current.date() + timedelta(days=days)
        
        # Parse default_time (HH:MM)
        try:
            h, m = map(int, default_time.split(':'))
        except ValueError:
            h, m = 8, 0 # Default fallback
            
        target_dt = datetime.combine(target_date, time(hour=h, minute=m))
        
        TimeProvider.set_virtual_time(target_dt)
        return target_dt

    @staticmethod
    def get_virtual_business_date() -> date:
        """현재 가상 거래일 반환. 없으면 현재 시각의 날짜를 사용한다."""
        try:
            data = TimeProvider._load_state(TimeProvider.VIRTUAL_BUSINESS_DATE_KEY)
            if isinstance(data, dict) and data.get("business_date"):
                return datetime.fromisoformat(data["business_date"]).date()
        except Exception as e:
            print(f"TimeProvider BusinessDate Error: {e}")
        return TimeProvider.get_current_time().date()

    @staticmethod
    def set_virtual_business_date(target_date: Any, default_time: str = "08:00") -> datetime:
        """가상 거래일을 지정하고 해당 날짜 기준 가상 시각도 함께 맞춘다."""
        business_date = TimeProvider._coerce_date(target_date)
        default_clock = TimeProvider._parse_time(default_time)
        target_dt = datetime.combine(business_date, default_clock)
        TimeProvider.set_virtual_time(target_dt)
        return target_dt

    @staticmethod
    def get_next_business_day(target_date: Any) -> date:
        """주말을 제외한 다음 거래일을 반환한다."""
        return TimeProvider._shift_business_day(target_date, step=1)

    @staticmethod
    def add_business_days(days: int = 1, default_time: str = "08:00") -> datetime:
        """현재 가상 거래일 기준 N개 거래일 이동한다."""
        current_date = TimeProvider.get_virtual_business_date()
        if days == 0:
            return TimeProvider.set_virtual_business_date(current_date, default_time=default_time)

        step = 1 if days > 0 else -1
        target_date = current_date
        for _ in range(abs(days)):
            target_date = TimeProvider._shift_business_day(target_date, step=step)
        return TimeProvider.set_virtual_business_date(target_date, default_time=default_time)

    @staticmethod
    def set_active_test_session(session_id: str) -> None:
        TimeProvider._upsert_state(
            TimeProvider.ACTIVE_TEST_SESSION_KEY,
            {"session_id": str(session_id or "").strip()},
        )

    @staticmethod
    def get_active_test_session_id() -> Optional[str]:
        data = TimeProvider._load_state(TimeProvider.ACTIVE_TEST_SESSION_KEY)
        if isinstance(data, dict):
            session_id = str(data.get("session_id") or "").strip()
            return session_id or None
        return None

    @staticmethod
    def clear_active_test_session() -> None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM system_state WHERE `key` = %s",
                (TimeProvider.ACTIVE_TEST_SESSION_KEY,),
            )

    @staticmethod
    def _load_state(key: str) -> Optional[Any]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_state WHERE `key` = %s", (key,))
            row = cursor.fetchone()
            if not row or row.get("value") is None:
                return None
            data = row["value"]
            if isinstance(data, str):
                data = json.loads(data)
            return data

    @staticmethod
    def _upsert_state(key: str, value: Any) -> None:
        value_json = json.dumps(value, ensure_ascii=False)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO system_state (`key`, `value`)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)
                """,
                (key, value_json),
            )

    @staticmethod
    def _shift_business_day(target_date: Any, step: int) -> date:
        current_date = TimeProvider._coerce_date(target_date)
        direction = 1 if step >= 0 else -1
        shifted = current_date
        while True:
            shifted = shifted + timedelta(days=direction)
            if shifted.weekday() < 5:
                return shifted

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        raise ValueError(f"Unsupported date type: {type(value)}")

    @staticmethod
    def _parse_time(value: str) -> time:
        try:
            hour, minute = map(int, value.split(":"))
            return time(hour=hour, minute=minute)
        except ValueError:
            return time(hour=8, minute=0)
