import json
from datetime import datetime, timedelta, time
from service.database.db import get_db_connection

class TimeProvider:
    @staticmethod
    def get_current_time() -> datetime:
        """현재 시스템 시간 반환 (가상 시간 적용)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_state WHERE `key` = %s", ('virtual_clock',))
                row = cursor.fetchone()
                if row and row['value']:
                    # MySQL JSON type might be returned as dict or string depending on driver
                    data = row['value']
                    if isinstance(data, str):
                        data = json.loads(data)
                        
                    if isinstance(data, dict) and 'current_time' in data:
                        return datetime.fromisoformat(data['current_time'])
        except Exception as e:
            # DB 연결 실패 등 예외 발생 시 실제 시간 반환
            print(f"TimeProvider Error: {e}")
        
        return datetime.now()

    @staticmethod
    def set_virtual_time(dt: datetime) -> None:
        """가상 시간 설정"""
        value_data = {"current_time": dt.isoformat()}
        value_json = json.dumps(value_data)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_state (`key`, `value`) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE `value` = %s
            """, ('virtual_clock', value_json, value_json))

    @staticmethod
    def reset_to_real_time() -> None:
        """실제 시간으로 초기화 (가상 시간 삭제)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM system_state WHERE `key` = %s", ('virtual_clock',))

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
