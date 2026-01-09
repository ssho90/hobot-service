"""
FRED API를 통한 거시경제 지표 수집 모듈
"""
import os
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
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


class RateLimitError(Exception):
    """FRED API rate limit 초과 오류"""
    pass


class FREDAPIError(Exception):
    """FRED API 일반 오류"""
    pass


class DataInsufficientError(Exception):
    """데이터 부족 오류"""
    pass


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
        "frequency": "monthly"
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
    },
    "DFII10": {
        "code": "DFII10",
        "name": "10-Year Treasury Inflation-Indexed Security, Constant Maturity",
        "unit": "%",
        "frequency": "daily"
    },
    # 추가 매크로 지표 (Growth, Inflation, Liquidity, Sentiment)
    "NAPM": {
        "code": "NAPM",
        "name": "ISM Manufacturing PMI",
        "unit": "Index",
        "frequency": "monthly"
    },
    "NAPMNO": {
        "code": "NAPMNO",
        "name": "ISM Manufacturing New Orders Index",
        "unit": "Index",
        "frequency": "monthly"
    },
    "GDPNOW": {
        "code": "GDPNOW",
        "name": "GDPNow",
        "unit": "%",
        "frequency": "quarterly"  # 실제로는 불규칙하지만 편의상
    },
    "PCEPILFE": {
        "code": "PCEPILFE",
        "name": "Core PCE Price Index",
        "unit": "Index",
        "frequency": "monthly"
    },
    "T10YIE": {
        "code": "T10YIE",
        "name": "10-Year Breakeven Inflation Rate",
        "unit": "%",
        "frequency": "daily"
    },
    "VIXCLS": {
        "code": "VIXCLS",
        "name": "CBOE Volatility Index: VIX",
        "unit": "Index",
        "frequency": "daily"
    },
    "M04154USM223NNBR": {
        "code": "M04154USM223NNBR",
        "name": "Merrill Lynch Option Volatility Estimate (MOVE Index)",
        "unit": "Index",
        "frequency": "monthly" # 데이터 가용성에 따라 조정 필요할 수 있음
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
        
        # FRED API Rate Limit 설정
        # - 분당 120회 요청 제한
        # - 요청당 최대 100,000개 관측치 제한
        self.requests_per_minute = 120
        self.min_request_interval = 60.0 / self.requests_per_minute  # 약 0.5초
        self.max_observations_per_request = 100000
        self._last_request_time = 0.0
    
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
    
    def _rate_limit_delay(self):
        """
        FRED API rate limit을 준수하기 위한 딜레이 처리
        
        분당 120회 요청 제한을 준수하기 위해 요청 간 최소 간격을 유지합니다.
        """
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def fetch_indicator(
        self,
        indicator_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_rate_limit: bool = True
    ) -> pd.Series:
        """
        특정 지표 데이터를 FRED API에서 가져옵니다.
        
        Args:
            indicator_code: 지표 코드 (예: "DGS10")
            start_date: 시작 날짜 (None이면 최근 1년)
            end_date: 종료 날짜 (None이면 오늘)
            use_rate_limit: Rate limit 딜레이 사용 여부 (기본값: True)
            
        Returns:
            pd.Series: 날짜를 인덱스로 하는 시계열 데이터
        """
        if end_date is None:
            end_date = date.today()
        
        if start_date is None:
            start_date = end_date - timedelta(days=365)
        
        # 100,000개 관측치 제한 확인
        # 일별 데이터의 경우 약 274년치가 100,000개에 해당
        # 월별 데이터의 경우 약 8,333년치가 100,000개에 해당
        # 실제로는 문제가 없지만, 매우 긴 기간의 경우 분할 수집 필요
        days_diff = (end_date - start_date).days
        if days_diff > 100000:
            logger.warning(
                f"{indicator_code}: 요청 기간이 매우 깁니다 ({days_diff}일). "
                f"100,000개 관측치 제한을 고려하여 분할 수집이 필요할 수 있습니다."
            )
        
        try:
            # Rate limit 딜레이 적용
            if use_rate_limit:
                self._rate_limit_delay()
            
            logger.info(f"FRED API에서 {indicator_code} 데이터 수집 중... ({start_date} ~ {end_date})")
            data = self.fred.get_series(
                indicator_code,
                observation_start=start_date,
                observation_end=end_date
            )
            
            if data is None or len(data) == 0:
                logger.warning(f"{indicator_code} 데이터가 없습니다")
                return pd.Series(dtype=float)
            
            # 100,000개 제한 확인
            if len(data) >= self.max_observations_per_request:
                logger.warning(
                    f"{indicator_code}: 수집된 데이터가 {len(data)}개로 "
                    f"100,000개 제한에 근접합니다. 일부 데이터가 누락되었을 수 있습니다."
                )
            
            # NaN 값 제거
            data = data.dropna()
            
            logger.info(f"{indicator_code} 데이터 수집 완료: {len(data)}개 데이터 포인트")
            return data
            
        except Exception as e:
            error_msg = str(e).lower()
            # Rate limit 오류 감지
            if 'rate limit' in error_msg or '429' in error_msg or 'too many requests' in error_msg:
                logger.error(
                    f"{indicator_code} 데이터 수집 실패: FRED API rate limit 초과. "
                    f"잠시 후 재시도하거나 요청 간격을 늘려주세요."
                )
                raise RateLimitError(f"FRED API rate limit 초과: {e}") from e
            elif '401' in error_msg or 'unauthorized' in error_msg or 'invalid' in error_msg:
                logger.error(f"{indicator_code} 데이터 수집 실패: FRED API 인증 오류. API 키를 확인하세요.")
                raise FREDAPIError(f"FRED API 인증 실패: {e}") from e
            elif '404' in error_msg or 'not found' in error_msg:
                logger.error(f"{indicator_code} 데이터 수집 실패: 지표를 찾을 수 없습니다.")
                raise FREDAPIError(f"FRED API 지표를 찾을 수 없음: {e}") from e
            else:
                logger.error(f"{indicator_code} 데이터 수집 실패: {e}")
                raise FREDAPIError(f"FRED API 오류: {e}") from e
    
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
    
    def fill_missing_dates(
        self,
        data: pd.Series,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        method: str = 'linear'
    ) -> pd.Series:
        """
        누락된 날짜를 보간으로 채웁니다.
        
        Args:
            data: 시계열 데이터 (pd.Series, 인덱스는 날짜)
            start_date: 시작 날짜 (None이면 데이터의 첫 날짜)
            end_date: 종료 날짜 (None이면 데이터의 마지막 날짜)
            method: 보간 방법 ('linear', 'forward', 'backward')
            
        Returns:
            pd.Series: 보간된 데이터
        """
        if len(data) == 0:
            return data
        
        # 날짜 범위 설정
        if start_date is None:
            start_date = data.index.min()
            if isinstance(start_date, pd.Timestamp):
                start_date = start_date.date()
            elif not isinstance(start_date, date):
                start_date = pd.to_datetime(start_date).date()
        
        if end_date is None:
            end_date = data.index.max()
            if isinstance(end_date, pd.Timestamp):
                end_date = end_date.date()
            elif not isinstance(end_date, date):
                end_date = pd.to_datetime(end_date).date()
        
        # 전체 날짜 범위 생성 (일별)
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # 기존 데이터를 새로운 인덱스에 재인덱싱
        data_reindexed = data.reindex(date_range)
        
        # 보간 적용
        if method == 'linear':
            data_filled = data_reindexed.interpolate(method='linear', limit_direction='both')
        elif method == 'forward':
            data_filled = data_reindexed.ffill()
        elif method == 'backward':
            data_filled = data_reindexed.bfill()
        else:
            data_filled = data_reindexed.interpolate(method='linear', limit_direction='both')
        
        # 원본 데이터가 있던 날짜는 원본 값 유지, 보간된 날짜만 추가
        return data_filled
    
    def save_to_db(
        self,
        indicator_code: str,
        data: pd.Series,
        indicator_name: Optional[str] = None,
        unit: Optional[str] = None,
        fill_missing: bool = False,
        fill_start_date: Optional[date] = None,
        fill_end_date: Optional[date] = None
    ) -> int:
        """
        FRED 데이터를 DB에 저장합니다. 중복 데이터는 건너뜁니다.
        
        Args:
            indicator_code: 지표 코드
            data: 시계열 데이터 (pd.Series, 인덱스는 날짜)
            indicator_name: 지표 이름 (None이면 FRED_INDICATORS에서 가져옴)
            unit: 단위 (None이면 FRED_INDICATORS에서 가져옴)
            fill_missing: 누락된 날짜를 보간으로 채울지 여부
            fill_start_date: 보간 시작 날짜 (None이면 데이터의 첫 날짜)
            fill_end_date: 보간 종료 날짜 (None이면 데이터의 마지막 날짜)
            
        Returns:
            int: 저장된 레코드 수
        """
        if indicator_name is None or unit is None:
            indicator_info = FRED_INDICATORS.get(indicator_code, {})
            indicator_name = indicator_name or indicator_info.get("name", indicator_code)
            unit = unit or indicator_info.get("unit", "")
        
        # 누락된 날짜 보간
        if fill_missing:
            data = self.fill_missing_dates(data, fill_start_date, fill_end_date, method='linear')
            logger.info(f"{indicator_code}: 누락된 날짜를 보간으로 채웠습니다. (총 {len(data)}개 데이터 포인트)")
        
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
        skip_existing: bool = True,
        request_delay: Optional[float] = None
    ) -> Dict[str, int]:
        """
        모든 주요 지표를 수집하고 저장합니다.
        
        Args:
            start_date: 시작 날짜
            end_date: 종료 날짜
            skip_existing: 기존 데이터 건너뛰기 여부
            request_delay: 요청 간 추가 딜레이 (초, None이면 자동 계산)
            
        Returns:
            Dict[str, int]: 지표별 저장된 레코드 수
        """
        results = {}
        total_indicators = len(FRED_INDICATORS)
        
        # 요청 간 딜레이 설정 (기본값: rate limit 기준)
        if request_delay is None:
            request_delay = self.min_request_interval
        
        logger.info(f"총 {total_indicators}개 지표 수집 시작 (요청 간 딜레이: {request_delay:.2f}초)")
        
        for idx, (indicator_code, indicator_info) in enumerate(FRED_INDICATORS.items(), 1):
            try:
                logger.info(
                    f"[{idx}/{total_indicators}] {indicator_code} ({indicator_info['name']}) 수집 시작..."
                )
                
                # 데이터 수집 (rate limit 딜레이 자동 적용)
                data = self.fetch_indicator(indicator_code, start_date, end_date, use_rate_limit=True)
                
                if len(data) == 0:
                    logger.warning(f"{indicator_code} 데이터가 없습니다")
                    results[indicator_code] = 0
                    # 다음 요청 전 딜레이
                    if idx < total_indicators:
                        time.sleep(request_delay)
                    continue
                
                # DGS10, DGS2는 누락된 날짜를 보간으로 채움
                fill_missing = indicator_code in ["DGS10", "DGS2"]
                
                # DB 저장
                saved_count = self.save_to_db(
                    indicator_code,
                    data,
                    indicator_info["name"],
                    indicator_info["unit"],
                    fill_missing=fill_missing,
                    fill_start_date=start_date,
                    fill_end_date=end_date
                )
                
                results[indicator_code] = saved_count
                
                # 다음 요청 전 딜레이 (마지막 지표가 아니면)
                if idx < total_indicators:
                    time.sleep(request_delay)
                
            except RateLimitError as e:
                logger.error(f"{indicator_code} 수집 실패: Rate limit 초과. 60초 대기 후 재시도...")
                time.sleep(60)  # Rate limit 오류 시 60초 대기
                # 재시도
                try:
                    data = self.fetch_indicator(indicator_code, start_date, end_date, use_rate_limit=True)
                    if len(data) > 0:
                        # DGS10, DGS2는 누락된 날짜를 보간으로 채움
                        fill_missing = indicator_code in ["DGS10", "DGS2"]
                        saved_count = self.save_to_db(
                            indicator_code,
                            data,
                            indicator_info["name"],
                            indicator_info["unit"],
                            fill_missing=fill_missing,
                            fill_start_date=start_date,
                            fill_end_date=end_date
                        )
                        results[indicator_code] = saved_count
                    else:
                        results[indicator_code] = 0
                except Exception as retry_e:
                    logger.error(f"{indicator_code} 재시도 실패: {retry_e}")
                    results[indicator_code] = 0
                    
            except Exception as e:
                logger.error(f"{indicator_code} 수집 실패: {e}")
                results[indicator_code] = 0
                # 오류 발생 시에도 다음 요청 전 딜레이
                if idx < total_indicators:
                    time.sleep(request_delay)
        
        return results
    
    def collect_yield_curve_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, int]:
        """
        장단기 금리 데이터(DGS10, DGS2)를 수집하고 DB에 저장합니다.
        
        Args:
            start_date: 시작 날짜 (None이면 최근 1년)
            end_date: 종료 날짜 (None이면 오늘)
            
        Returns:
            Dict[str, int]: 지표별 저장된 레코드 수
        """
        if end_date is None:
            end_date = date.today()
        
        if start_date is None:
            start_date = end_date - timedelta(days=365)
        
        results = {}
        yield_indicators = ["DGS10", "DGS2"]
        
        for indicator_code in yield_indicators:
            try:
                indicator_info = FRED_INDICATORS.get(indicator_code)
                if not indicator_info:
                    logger.warning(f"{indicator_code} 지표 정보를 찾을 수 없습니다")
                    results[indicator_code] = 0
                    continue
                
                logger.info(f"{indicator_code} ({indicator_info['name']}) 수집 시작...")
                
                # 데이터 수집
                data = self.fetch_indicator(indicator_code, start_date, end_date)
                
                if len(data) == 0:
                    logger.warning(f"{indicator_code} 데이터가 없습니다")
                    results[indicator_code] = 0
                    continue
                
                # DGS10, DGS2는 누락된 날짜를 보간으로 채움
                # DB 저장
                saved_count = self.save_to_db(
                    indicator_code,
                    data,
                    indicator_info["name"],
                    indicator_info["unit"],
                    fill_missing=True,  # DGS10, DGS2는 항상 보간 적용
                    fill_start_date=start_date,
                    fill_end_date=end_date
                )
                
                results[indicator_code] = saved_count
                
            except Exception as e:
                logger.error(f"{indicator_code} 수집 실패: {e}")
                results[indicator_code] = 0
        
        return results
    
    def get_latest_data(self, indicator_code: str, days: int = 30, min_data_points: Optional[int] = None) -> pd.Series:
        """
        최근 N일간의 데이터를 DB에서 가져옵니다.
        
        Args:
            indicator_code: 지표 코드
            days: 가져올 일수
            min_data_points: 최소 데이터 포인트 수 (None이면 검사 안 함)
            
        Returns:
            pd.Series: 날짜를 인덱스로 하는 시계열 데이터
            
        Raises:
            DataInsufficientError: 데이터가 부족한 경우
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
                    if min_data_points is not None and min_data_points > 0:
                        raise DataInsufficientError(
                            f"{indicator_code}: 요청한 기간({days}일) 동안 데이터가 없습니다."
                        )
                    return pd.Series(dtype=float)
                
                # DataFrame으로 변환
                df = pd.DataFrame(results)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                # decimal.Decimal 타입을 float로 변환
                data = df['value'].apply(lambda x: float(x) if isinstance(x, Decimal) else float(x))
                
                # 최소 데이터 포인트 검사
                if min_data_points is not None and len(data) < min_data_points:
                    raise DataInsufficientError(
                        f"{indicator_code}: 데이터가 부족합니다. "
                        f"요청: {min_data_points}개, 실제: {len(data)}개"
                    )
                
                return data
                
        except DataInsufficientError:
            raise
        except Exception as e:
            logger.error(f"{indicator_code} 최신 데이터 조회 실패: {e}")
            raise FREDAPIError(f"데이터 조회 실패: {e}") from e


def get_fred_collector() -> FREDCollector:
    """FRED 수집기 인스턴스를 반환합니다."""
    return FREDCollector()

