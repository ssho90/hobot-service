"""
Macro Knowledge Graph (MKG) - Derived Feature Calculator
Phase A-6: IndicatorObservation → DerivedFeature 계산
"""
import logging
from datetime import date
from typing import List, Optional, Dict, Any

import pandas as pd

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

    @staticmethod
    def merge_asof_daily_anchor(
        series_by_indicator: Dict[str, pd.Series],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        다주기 시계열을 daily anchor로 정렬한다.
        - anchor: 일 단위 date range
        - join: pd.merge_asof(direction='backward')
        """
        normalized_frames: Dict[str, pd.DataFrame] = {}
        observed_starts: List[pd.Timestamp] = []
        observed_ends: List[pd.Timestamp] = []

        for indicator_code, series in series_by_indicator.items():
            if series is None or len(series) == 0:
                continue

            ts = pd.Series(series).dropna()
            if ts.empty:
                continue

            index = pd.to_datetime(ts.index).tz_localize(None)
            frame = pd.DataFrame({"date": index, indicator_code: ts.values})
            frame = (
                frame.sort_values("date")
                .drop_duplicates(subset=["date"], keep="last")
                .reset_index(drop=True)
            )
            normalized_frames[indicator_code] = frame
            observed_starts.append(frame["date"].min())
            observed_ends.append(frame["date"].max())

        if not normalized_frames:
            return pd.DataFrame(columns=["date"])

        anchor_start = pd.Timestamp(start_date) if start_date else min(observed_starts)
        anchor_end = pd.Timestamp(end_date) if end_date else max(observed_ends)
        anchor = pd.DataFrame({"date": pd.date_range(anchor_start, anchor_end, freq="D")})

        merged = anchor.sort_values("date").reset_index(drop=True)
        for indicator_code, frame in normalized_frames.items():
            merged = pd.merge_asof(
                merged.sort_values("date"),
                frame.sort_values("date"),
                on="date",
                direction="backward",
                allow_exact_matches=True,
            )

        return merged

    def calculate_delta_1d(
        self,
        indicator_code: str,
        limit: int = 365,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """전일 대비 변화량(delta_1d) 계산 및 저장"""
        as_of_value = (as_of_date or date.today()).isoformat()
        query = """
        MATCH (i:EconomicIndicator {indicator_code: $code})-[:HAS_OBSERVATION]->(o:IndicatorObservation)
        WHERE o.obs_date <= date($as_of_date)
          AND coalesce(o.effective_date, o.obs_date) <= date($as_of_date)
          AND date(coalesce(o.published_at, datetime(toString(o.obs_date) + "T00:00:00"))) <= date($as_of_date)
          AND coalesce(o.as_of_date, o.obs_date) <= date($as_of_date)
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
        SET f.value = delta,
            f.effective_date = coalesce(current.effective_date, current.obs_date),
            f.published_at = coalesce(current.published_at, datetime(toString(current.obs_date) + "T00:00:00")),
            f.as_of_date = coalesce(current.as_of_date, date($as_of_date)),
            f.revision_flag = coalesce(current.revision_flag, false),
            f.updated_at = datetime()
        MERGE (current)-[:HAS_FEATURE]->(f)
        RETURN count(f) AS features_created
        """

        result = self.neo4j_client.run_write(
            query,
            {"code": indicator_code, "limit": limit, "as_of_date": as_of_value},
        )
        logger.info(f"[DerivedFeature] {indicator_code} delta_1d: {result}")
        return result

    def calculate_pct_change_1d(
        self,
        indicator_code: str,
        limit: int = 365,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """전일 대비 변화율(pct_change_1d) 계산 및 저장"""
        as_of_value = (as_of_date or date.today()).isoformat()
        query = """
        MATCH (i:EconomicIndicator {indicator_code: $code})-[:HAS_OBSERVATION]->(o:IndicatorObservation)
        WHERE o.obs_date <= date($as_of_date)
          AND coalesce(o.effective_date, o.obs_date) <= date($as_of_date)
          AND date(coalesce(o.published_at, datetime(toString(o.obs_date) + "T00:00:00"))) <= date($as_of_date)
          AND coalesce(o.as_of_date, o.obs_date) <= date($as_of_date)
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
        SET f.value = pct_change,
            f.effective_date = coalesce(current.effective_date, current.obs_date),
            f.published_at = coalesce(current.published_at, datetime(toString(current.obs_date) + "T00:00:00")),
            f.as_of_date = coalesce(current.as_of_date, date($as_of_date)),
            f.revision_flag = coalesce(current.revision_flag, false),
            f.updated_at = datetime()
        MERGE (current)-[:HAS_FEATURE]->(f)
        RETURN count(f) AS features_created
        """

        result = self.neo4j_client.run_write(
            query,
            {"code": indicator_code, "limit": limit, "as_of_date": as_of_value},
        )
        logger.info(f"[DerivedFeature] {indicator_code} pct_change_1d: {result}")
        return result

    def calculate_all_features(
        self,
        indicator_codes: Optional[List[str]] = None,
        limit: int = 365,
        as_of_date: Optional[date] = None,
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
                delta_result = self.calculate_delta_1d(code, limit, as_of_date=as_of_date)
                pct_result = self.calculate_pct_change_1d(code, limit, as_of_date=as_of_date)
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
