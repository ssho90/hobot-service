"""
Macro Knowledge Graph (MKG) - Derived Feature Calculator
Phase A-6: IndicatorObservation → DerivedFeature 계산
"""
import logging
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from .neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class DerivedFeatureCalculator:
    """IndicatorObservation에서 파생 피처 계산"""
    
    # 계산할 피처 정의
    FEATURES = [
        {'name': 'delta_1d', 'description': '전일 대비 변화량'},
        {'name': 'pct_change_1d', 'description': '전일 대비 변화율(%)'},
    ]
    
    def __init__(self):
        self.neo4j_client = get_neo4j_client()
    
    def calculate_delta_1d(self, indicator_code: str, limit: int = 365) -> Dict[str, Any]:
        """전일 대비 변화량(delta_1d) 계산 및 저장"""
        query = """
        MATCH (i:EconomicIndicator {indicator_code: $code})-[:HAS_OBSERVATION]->(o:IndicatorObservation)
        WITH o ORDER BY o.obs_date DESC LIMIT $limit
        WITH collect(o) AS observations
        UNWIND range(0, size(observations)-2) AS idx
        WITH observations[idx] AS current, observations[idx+1] AS prev
        WHERE current.value IS NOT NULL AND prev.value IS NOT NULL
        WITH current, prev, current.value - prev.value AS delta
        MERGE (f:DerivedFeature {
            indicator_code: $code,
            feature_name: 'delta_1d',
            obs_date: current.obs_date
        })
        SET f.value = delta, f.updated_at = datetime()
        MERGE (current)-[:HAS_FEATURE]->(f)
        RETURN count(f) AS features_created
        """
        
        result = self.neo4j_client.run_write(query, {"code": indicator_code, "limit": limit})
        logger.info(f"[DerivedFeature] {indicator_code} delta_1d: {result}")
        return result
    
    def calculate_pct_change_1d(self, indicator_code: str, limit: int = 365) -> Dict[str, Any]:
        """전일 대비 변화율(pct_change_1d) 계산 및 저장"""
        query = """
        MATCH (i:EconomicIndicator {indicator_code: $code})-[:HAS_OBSERVATION]->(o:IndicatorObservation)
        WITH o ORDER BY o.obs_date DESC LIMIT $limit
        WITH collect(o) AS observations
        UNWIND range(0, size(observations)-2) AS idx
        WITH observations[idx] AS current, observations[idx+1] AS prev
        WHERE current.value IS NOT NULL AND prev.value IS NOT NULL AND prev.value <> 0
        WITH current, prev, ((current.value - prev.value) / abs(prev.value)) * 100 AS pct_change
        MERGE (f:DerivedFeature {
            indicator_code: $code,
            feature_name: 'pct_change_1d',
            obs_date: current.obs_date
        })
        SET f.value = pct_change, f.updated_at = datetime()
        MERGE (current)-[:HAS_FEATURE]->(f)
        RETURN count(f) AS features_created
        """
        
        result = self.neo4j_client.run_write(query, {"code": indicator_code, "limit": limit})
        logger.info(f"[DerivedFeature] {indicator_code} pct_change_1d: {result}")
        return result
    
    def calculate_all_features(
        self,
        indicator_codes: Optional[List[str]] = None,
        limit: int = 365
    ) -> Dict[str, Any]:
        """모든 지표에 대해 파생 피처 계산"""
        if indicator_codes is None:
            # Neo4j에서 EconomicIndicator 목록 조회
            query = "MATCH (i:EconomicIndicator) RETURN i.indicator_code AS code"
            indicator_codes = [row['code'] for row in self.neo4j_client.run_read(query)]
        
        results = {}
        for code in indicator_codes:
            logger.info(f"[DerivedFeature] Calculating features for {code}...")
            try:
                delta_result = self.calculate_delta_1d(code, limit)
                pct_result = self.calculate_pct_change_1d(code, limit)
                results[code] = {
                    "delta_1d": delta_result,
                    "pct_change_1d": pct_result
                }
            except Exception as e:
                logger.error(f"[DerivedFeature] {code} failed: {e}")
                results[code] = {"error": str(e)}
        
        return results
    
    def verify_features(self) -> Dict[str, Any]:
        """파생 피처 검증"""
        query = """
        MATCH (f:DerivedFeature)
        RETURN f.feature_name AS feature, f.indicator_code AS code, count(f) AS count
        ORDER BY feature, code
        """
        
        results = self.neo4j_client.run_read(query)
        
        logger.info("[DerivedFeature] Verification:")
        for row in results:
            logger.info(f"  - {row['code']}/{row['feature']}: {row['count']} features")
        
        return {"features": results}


def calculate_all_derived_features(limit: int = 365) -> Dict[str, Any]:
    """모든 파생 피처 계산 (편의 함수)"""
    calc = DerivedFeatureCalculator()
    results = calc.calculate_all_features(limit=limit)
    verification = calc.verify_features()
    return {"calculation": results, "verification": verification}


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from dotenv import load_dotenv
    load_dotenv()
    
    result = calculate_all_derived_features(limit=365)
    print("\n=== RESULT ===")
    print(result.get("verification", {}))
