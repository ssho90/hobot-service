"""
메모리 저장소 MySQL 관리 모듈
"""
from datetime import datetime
from typing import List, Dict
from service.database.db import get_db_connection


class MemoryStore:
    def __init__(self):
        self.memory: List[Dict] = self.load()

    def load(self) -> List[Dict]:
        """MySQL에서 메모리 목록 로드"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_store ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def save_to_file(self) -> None:
        """MySQL에 저장 (이미 save에서 처리되므로 빈 함수)"""
        pass

    def save(self, topic: str, summary: str) -> None:
        """메모리 저장"""
        now = datetime.now()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_store (topic, summary, created_at)
                VALUES (%s, %s, %s)
            """, (topic, summary, now))
            conn.commit()
        # 메모리 캐시 업데이트
        self.memory = self.load()

    def recall(self, query: str) -> str:
        """쿼리와 관련된 메모리 검색"""
        for mem in reversed(self.memory):
            if mem["topic"] in query or query in mem["summary"]:
                return mem["summary"]
        return ""

