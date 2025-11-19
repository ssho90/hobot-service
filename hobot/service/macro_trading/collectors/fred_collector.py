"""
FRED API를 통한 거시경제 지표 수집 모듈
"""
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import logging
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

try:
    from fredapi import Fred
except ImportError:
    Fred = None
    logging.warning("fredapi 패키지가 설치되지 않았습니다. pip install fredapi로 설치하세요.")

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


# FRED 지표 코드 정의
FRED_INDICATORS = {
    "DGS10": {
        "code": "DGS10",
        "name": "10-Year Treasury Constant Maturity Rate",
        "unit": "%",
        "frequency": "daily"
    },
    "DGS2": {
        "code": "DGS2",
        "name": "2-Year Treasury Constant Maturity Rate",
        "unit": "%",
        "frequency": "daily"
    },
    "FEDFUNDS": {
        "code": "FEDFUNDS",
        "name": "Effective Federal Funds Rate",
        "unit": "%",
        "frequency": "daily"
    },
    "CPIAUCSL": {
        "code": "CPIAUCSL",
        "name": "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
        "unit": "Index",
        "frequency": "monthly"
    },
    "PCEPI": {
        "code": "PCEPI",
        "name": "Personal Consumption Expenditures: Chain-type Price Index",
        "unit": "Index",
        "frequency": "monthly"
    },
    "GDP": {
        "code": "GDP",
        "name": "Gross Domestic Product",
        "unit": "Billions of Dollars",
        "frequency": "quarterly"
    },
    "UNRATE": {
        "code": "UNRATE",
        "name": "Unemployment Rate",
        "unit": "%",
        "frequency": "monthly"
    },
    "PAYEMS": {
        "code": "PAYEMS",
        "name": "All Employees, Total Nonfarm",
        "unit": "Thousands of Persons",
        "frequency": "monthly"
    },
    # 유동성 지표
    "WALCL": {
        "code": "WALCL",
        "name": "Assets: Total Assets: Total Assets (Less Eliminations from Consolidation): Wednesday Level",
        "unit": "Millions of Dollars",
        "frequency": "weekly"
    },
    "WTREGEN": {
        "code": "WTREGEN",
        "name": "U.S. Treasury General Account (TGA)",
        "unit": "Millions of Dollars",
        "frequency": "daily"
    },
    "RRPONTSYD": {
        "code": "RRPONTSYD",
        "name": "Reverse Repurchase Agreements: Treasury Securities Sold by the Federal Reserve in the Temporary Open Market Operations",
        "unit": "Millions of Dollars",
        "frequency": "daily"
    },
    "BAMLH0A0HYM2": {
        "code": "BAMLH0A0HYM2",
        "name": "ICE BofA US High Yield Index Option-Adjusted Spread",
        "unit": "%",
        "frequency": "daily"
    }
}


class FREDCollector:
    """FRED API 데이터 수집 클래스"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: FRED API 키 (None이면 환경변수에서 로드)
        """
        if api_key is None:
            api_key = os.getenv("FRED_API_KEY")
        
        if not api_key:
            raise ValueError("FRED API 키가 설정되지 않았습니다. 환경변수 FRED_API_KEY를 설정하세요.")
        
        if Fred is None:
            raise ImportError("fredapi 패키지가 설치되지 않았습니다. pip install fredapi로 설치하세요.")
        
        self.fred = Fred(api_key=api_key)
        self.api_key = api_key
    
    def test_connection(self) -> bool:
        """
        FRED API 연결 테스트
        
        Returns:
            bool: 연결 성공 여부
        """
        try:
            # 간단한 데이터 조회로 연결 테스트
            test_data = self.fred.get_series("DGS10", limit=1)
            if test_data is not None and len(test_data) > 0:
                logger.info("FRED API 연결 성공")
                return True
            else:
                logger.warning("FRED API 연결 테스트 실패: 데이터를 가져올 수 없습니다")
                return False
        except Exception as e:
            logger.error(f"FRED API 연결 테스트 실패: {e}")
            return False
    
    def fetch_indicator(
        self,
        indicator_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.Series:
        """
        특정 지표 데이터를 FRED API에서 가져옵니다.
        
        Args:
            indicator_code: 지표 코드 (예: "DGS10")
            start_date: 시작 날짜 (None이면 최근 1년)
            end_date: 종료 날짜 (None이면 오늘)
            
        Returns:
            pd.Series: 날짜를 인덱스로 하는 시계열 데이터
        """
        if end_date is None:
            end_date = date.today()
        
        if start_date is None:
            start_date = end_date - timedelta(days=365)
        
        try:
            logger.info(f"FRED API에서 {indicator_code} 데이터 수집 중... ({start_date} ~ {end_date})")
            data = self.fred.get_series(
                indicator_code,
                observation_start=start_date,
                observation_end=end_date
            )
            
            if data is None or len(data) == 0:
                logger.warning(f"{indicator_code} 데이터가 없습니다")
                return pd.Series(dtype=float)
            
            # NaN 값 제거
            data = data.dropna()
            
            logger.info(f"{indicator_code} 데이터 수집 완료: {len(data)}개 데이터 포인트")
            return data
            
        except Exception as e:
            logger.error(f"{indicator_code} 데이터 수집 실패: {e}")
            raise
    
    def check_data_exists(self, indicator_code: str, target_date: date) -> bool:
        """
        특정 날짜의 데이터가 DB에 이미 존재하는지 확인합니다.
        
        Args:
            indicator_code: 지표 코드
            target_date: 확인할 날짜
            
        Returns:
            bool: 데이터 존재 여부
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM fred_data
                    WHERE indicator_code = %s AND date = %s
                    """,
                    (indicator_code, target_date)
                )
                result = cursor.fetchone()
                return result['count'] > 0 if result else False
        except Exception as e:
            logger.error(f"데이터 존재 확인 실패: {e}")
            return False
    
    def save_to_db(
        self,
        indicator_code: str,
        data: pd.Series,
        indicator_name: Optional[str] = None,
        unit: Optional[str] = None
    ) -> int:
        """
        FRED 데이터를 DB에 저장합니다. 중복 데이터는 건너뜁니다.
        
        Args:
            indicator_code: 지표 코드
            data: 시계열 데이터 (pd.Series, 인덱스는 날짜)
            indicator_name: 지표 이름 (None이면 FRED_INDICATORS에서 가져옴)
            unit: 단위 (None이면 FRED_INDICATORS에서 가져옴)
            
        Returns:
            int: 저장된 레코드 수
        """
        if indicator_name is None or unit is None:
            indicator_info = FRED_INDICATORS.get(indicator_code, {})
            indicator_name = indicator_name or indicator_info.get("name", indicator_code)
            unit = unit or indicator_info.get("unit", "")
        
        saved_count = 0
        skipped_count = 0
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for date_idx, value in data.items():
                    # pandas Timestamp를 date로 변환
                    if isinstance(date_idx, pd.Timestamp):
                        data_date = date_idx.date()
                    elif isinstance(date_idx, date):
                        data_date = date_idx
                    else:
                        data_date = pd.to_datetime(date_idx).date()
                    
                    # 이미 존재하는 데이터는 건너뛰기
                    if self.check_data_exists(indicator_code, data_date):
                        skipped_count += 1
                        continue
                    
                    try:
                        cursor.execute(
                            """
                            INSERT INTO fred_data 
                            (indicator_code, indicator_name, date, value, unit, source)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                indicator_code,
                                indicator_name,
                                data_date,
                                float(value),
                                unit,
                                "FRED"
                            )
                        )
                        saved_count += 1
                    except Exception as e:
                        logger.warning(f"데이터 저장 실패 ({indicator_code}, {data_date}): {e}")
                        continue
                
                conn.commit()
                logger.info(
                    f"{indicator_code} 저장 완료: {saved_count}개 저장, {skipped_count}개 건너뜀"
                )
                return saved_count
                
        except Exception as e:
            logger.error(f"{indicator_code} DB 저장 실패: {e}")
            raise
    
    def collect_all_indicators(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip_existing: bool = True
    ) -> Dict[str, int]:
        """
        모든 주요 지표를 수집하고 저장합니다.
        
        Args:
            start_date: 시작 날짜
            end_date: 종료 날짜
            skip_existing: 기존 데이터 건너뛰기 여부
            
        Returns:
            Dict[str, int]: 지표별 저장된 레코드 수
        """
        results = {}
        
        for indicator_code, indicator_info in FRED_INDICATORS.items():
            try:
                logger.info(f"{indicator_code} ({indicator_info['name']}) 수집 시작...")
                
                # 데이터 수집
                data = self.fetch_indicator(indicator_code, start_date, end_date)
                
                if len(data) == 0:
                    logger.warning(f"{indicator_code} 데이터가 없습니다")
                    results[indicator_code] = 0
                    continue
                
                # DB 저장
                saved_count = self.save_to_db(
                    indicator_code,
                    data,
                    indicator_info["name"],
                    indicator_info["unit"]
                )
                
                results[indicator_code] = saved_count
                
            except Exception as e:
                logger.error(f"{indicator_code} 수집 실패: {e}")
                results[indicator_code] = 0
        
        return results
    
    def get_latest_data(self, indicator_code: str, days: int = 30) -> pd.Series:
        """
        최근 N일간의 데이터를 DB에서 가져옵니다.
        
        Args:
            indicator_code: 지표 코드
            days: 가져올 일수
            
        Returns:
            pd.Series: 날짜를 인덱스로 하는 시계열 데이터
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                end_date = date.today()
                start_date = end_date - timedelta(days=days)
                
                cursor.execute(
                    """
                    SELECT date, value
                    FROM fred_data
                    WHERE indicator_code = %s
                    AND date >= %s
                    AND date <= %s
                    ORDER BY date ASC
                    """,
                    (indicator_code, start_date, end_date)
                )
                
                results = cursor.fetchall()
                
                if not results:
                    return pd.Series(dtype=float)
                
                # DataFrame으로 변환
                df = pd.DataFrame(results)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                return df['value']
                
        except Exception as e:
            logger.error(f"{indicator_code} 최신 데이터 조회 실패: {e}")
            return pd.Series(dtype=float)


def get_fred_collector() -> FREDCollector:
    """FRED 수집기 인스턴스를 반환합니다."""
    return FREDCollector()

