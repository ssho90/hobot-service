"""
Macro Knowledge Graph (MKG) - Indicator Loader
Phase A-5: MySQL fred_data → Neo4j IndicatorObservation 동기화
"""
import logging
from datetime import date, timedelta
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
    'BAMLH0A0HYM2', 'VIXCLS', 'STLFSI4'
]


class IndicatorLoader:
    """MySQL fred_data → Neo4j IndicatorObservation 동기화"""
    
    def __init__(self):
        self.neo4j_client = get_neo4j_client()
    
    def _get_mysql_connection(self):
        """MySQL 연결 반환"""
        from service.database.db import get_db_connection
        return get_db_connection()
    
    def fetch_from_mysql(
        self,
        indicator_codes: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """MySQL fred_data에서 지표 데이터 조회"""
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=365)
        
        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()
            
            # IN 절을 위한 placeholder 생성
            placeholders = ', '.join(['%s'] * len(indicator_codes))
            
            query = f"""
                SELECT indicator_code, date, value
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
                observations.append({
                    'indicator_code': row['indicator_code'],
                    'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
                    'value': float(row['value'])
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
            SET o.value = obs.value, o.updated_at = datetime()
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
