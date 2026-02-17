"""
Macro Knowledge Graph (MKG) - Indicator Loader
Phase A-5: MySQL fred_data → Neo4j IndicatorObservation 동기화
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from .neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)

# 동기화 대상 지표 코드 (Neo4j EconomicIndicator와 동일)
SYNC_INDICATOR_CODES = [
    'DGS10', 'DGS2', 'FEDFUNDS', 'T10Y2Y', 'DFII10',
    'CPIAUCSL', 'PCEPI', 'PCEPILFE', 'T10YIE',
    'GDP', 'GACDFSA066MSFRBPHI', 'NOCDFSA066MSFRBPHI', 'GAFDFSA066MSFRBPHI',
    'UNRATE', 'PAYEMS',
    'WALCL', 'WTREGEN', 'RRPONTSYD', 'NETLIQ',
    'BAMLH0A0HYM2', 'VIXCLS', 'STLFSI4',
    'KR_BASE_RATE', 'KR_CPI', 'KR_UNEMPLOYMENT', 'KR_USDKRW',
    'KR_HOUSE_PRICE_INDEX', 'KR_JEONSE_PRICE_RATIO', 'KR_UNSOLD_HOUSING', 'KR_HOUSING_SUPPLY_APPROVAL'
]


class IndicatorLoader:
    """MySQL fred_data → Neo4j IndicatorObservation 동기화"""

    BASE_COLUMNS = ("indicator_code", "date", "value")
    OPTIONAL_COLUMNS = ("effective_date", "published_at", "as_of_date", "revision_flag", "source")

    def __init__(self):
        self.neo4j_client = get_neo4j_client()

    def _get_mysql_connection(self):
        """MySQL 연결 반환"""
        from service.database.db import get_db_connection
        return get_db_connection()

    @staticmethod
    def _to_iso_date(value: Any, fallback: date) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if value:
            return str(value)[:10]
        return fallback.isoformat()

    @staticmethod
    def _to_iso_datetime(value: Any, fallback_date: str) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return f"{value.isoformat()}T00:00:00"
        if value:
            return str(value)
        return f"{fallback_date}T00:00:00"

    def _get_fred_data_columns(self) -> List[str]:
        """fred_data 컬럼 목록 조회 (배포별 스키마 차이 대응)"""
        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'fred_data'
                """
            )
            return [str(row["COLUMN_NAME"]) for row in cursor.fetchall()]

    def fetch_from_mysql(
        self,
        indicator_codes: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """MySQL fred_data에서 지표 데이터 조회"""
        if not indicator_codes:
            return []

        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=365)

        available_columns = set(self._get_fred_data_columns())
        select_columns = list(self.BASE_COLUMNS)
        for column in self.OPTIONAL_COLUMNS:
            if column in available_columns:
                select_columns.append(column)

        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()

            # IN 절을 위한 placeholder 생성
            placeholders = ', '.join(['%s'] * len(indicator_codes))

            query = f"""
                SELECT {", ".join(select_columns)}
                FROM fred_data
                WHERE indicator_code IN ({placeholders})
                  AND date >= %s
                  AND date <= %s
                ORDER BY indicator_code, date
            """

            params = tuple(indicator_codes) + (start_date, end_date)
            cursor.execute(query, params)

            results = cursor.fetchall()

            # dict 형태로 변환
            observations = []
            for row in results:
                obs_date = self._to_iso_date(row.get("date"), fallback=end_date)
                effective_date = self._to_iso_date(row.get("effective_date"), fallback=row.get("date") or end_date)
                as_of_date = self._to_iso_date(row.get("as_of_date"), fallback=end_date)
                published_at = self._to_iso_datetime(row.get("published_at"), fallback_date=effective_date)
                observations.append({
                    'indicator_code': row['indicator_code'],
                    'date': obs_date,
                    'value': float(row['value']),
                    'effective_date': effective_date,
                    'published_at': published_at,
                    'as_of_date': as_of_date,
                    'revision_flag': bool(row.get("revision_flag", False)),
                    'source': str(row.get("source") or "FRED"),
                })

            logger.info(f"[IndicatorLoader] Fetched {len(observations)} observations from MySQL")
            return observations

    def upsert_to_neo4j(self, observations: List[Dict[str, Any]], batch_size: int = 500) -> Dict[str, int]:
        """Neo4j에 IndicatorObservation MERGE (멱등)"""
        if not observations:
            return {"created": 0, "properties_set": 0}

        total_created = 0
        total_props_set = 0

        # 배치 처리
        for i in range(0, len(observations), batch_size):
            batch = observations[i:i+batch_size]

            query = """
            UNWIND $observations AS obs
            MATCH (i:EconomicIndicator {indicator_code: obs.indicator_code})
            MERGE (o:IndicatorObservation {indicator_code: obs.indicator_code, obs_date: date(obs.date)})
            ON CREATE SET o.created_at = datetime(), o.revision_count = 0
            WITH i, o, obs,
                 CASE
                   WHEN o.value IS NULL THEN false
                   WHEN toFloat(o.value) <> toFloat(obs.value) THEN true
                   ELSE false
                 END AS changed_value
            FOREACH (_ IN CASE WHEN changed_value THEN [1] ELSE [] END |
              CREATE (rev:IndicatorObservationRevision {
                revision_key: obs.indicator_code + ":" + obs.date + ":" + toString(coalesce(o.revision_count, 0) + 1),
                indicator_code: obs.indicator_code,
                obs_date: date(obs.date),
                previous_value: o.value,
                value: obs.value,
                revision_seq: coalesce(o.revision_count, 0) + 1,
                effective_date: date(coalesce(obs.effective_date, obs.date)),
                published_at: datetime(coalesce(obs.published_at, obs.effective_date + "T00:00:00")),
                as_of_date: date(coalesce(obs.as_of_date, obs.date)),
                source: coalesce(obs.source, "FRED"),
                revision_flag: true,
                created_at: datetime()
              })
              MERGE (o)-[:HAS_REVISION]->(rev)
            )
            SET o.value = obs.value,
                o.effective_date = date(coalesce(obs.effective_date, obs.date)),
                o.published_at = datetime(coalesce(obs.published_at, obs.effective_date + "T00:00:00")),
                o.as_of_date = date(coalesce(obs.as_of_date, obs.date)),
                o.source = coalesce(obs.source, "FRED"),
                o.revision_flag = coalesce(obs.revision_flag, false) OR changed_value,
                o.revision_count = CASE
                  WHEN changed_value THEN coalesce(o.revision_count, 0) + 1
                  ELSE coalesce(o.revision_count, 0)
                END,
                o.updated_at = datetime()
            MERGE (i)-[:HAS_OBSERVATION]->(o)
            """

            result = self.neo4j_client.run_write(query, {"observations": batch})
            total_created += result.get("nodes_created", 0)
            total_props_set += result.get("properties_set", 0)

            logger.info(f"[IndicatorLoader] Batch {i//batch_size + 1}: {result}")

        return {"nodes_created": total_created, "properties_set": total_props_set}

    def sync_observations(
        self,
        indicator_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """MySQL fred_data → Neo4j 동기화 실행"""
        if indicator_codes is None:
            indicator_codes = SYNC_INDICATOR_CODES

        logger.info(f"[IndicatorLoader] Starting sync for {len(indicator_codes)} indicators")
        logger.info(f"[IndicatorLoader] Date range: {start_date} ~ {end_date}")

        # 1. MySQL에서 데이터 조회
        observations = self.fetch_from_mysql(indicator_codes, start_date, end_date)

        if not observations:
            logger.warning("[IndicatorLoader] No observations found in MySQL")
            return {"status": "no_data", "observations_synced": 0}

        # 2. Neo4j에 MERGE
        result = self.upsert_to_neo4j(observations)

        logger.info(f"[IndicatorLoader] Sync complete: {result}")

        return {
            "status": "success",
            "observations_synced": len(observations),
            "nodes_created": result["nodes_created"],
            "properties_set": result["properties_set"]
        }

    def verify_sync(self) -> Dict[str, Any]:
        """동기화 결과 검증"""
        query = """
        MATCH (i:EconomicIndicator)-[:HAS_OBSERVATION]->(o:IndicatorObservation)
        RETURN i.indicator_code AS code, count(o) AS obs_count, max(o.obs_date) AS latest_date
        ORDER BY obs_count DESC
        """
        
        results = self.neo4j_client.run_read(query)
        
        logger.info("[IndicatorLoader] Verification results:")
        for row in results:
            logger.info(f"  - {row['code']}: {row['obs_count']} observations (latest: {row['latest_date']})")
        
        return {"indicators": results}


def sync_all_indicators(days: int = 365) -> Dict[str, Any]:
    """모든 지표 동기화 (편의 함수)"""
    loader = IndicatorLoader()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    result = loader.sync_observations(start_date=start_date, end_date=end_date)
    verification = loader.verify_sync()
    
    return {
        "sync_result": result,
        "verification": verification
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from dotenv import load_dotenv
    load_dotenv()
    
    # 최근 1년 데이터 동기화
    result = sync_all_indicators(days=365)
    print("\n=== SYNC RESULT ===")
    print(result)
