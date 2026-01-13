"""
정량 시그널 계산 모듈
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, Optional, Tuple, Any
import logging

from service.macro_trading.collectors.fred_collector import FREDCollector, get_fred_collector
from service.macro_trading.config.config_loader import get_config
from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


class QuantSignalCalculator:
    """정량 시그널 계산 클래스"""
    
    def __init__(self, fred_collector: Optional[FREDCollector] = None):
        """
        Args:
            fred_collector: FRED 수집기 인스턴스 (None이면 새로 생성)
        """
        self.fred_collector = fred_collector or get_fred_collector()
    
    def get_yield_curve_spread_trend_following(
        self,
        ma_fast: int = 20,
        ma_slow: int = 120,
        ma_filter: int = 200,
        min_days: int = 250
    ) -> Optional[Dict]:
        """
        공식 1 (개선): 장단기 금리차 장기 추세 추종 전략
        
        노이즈를 제거하고 거시경제의 큰 사이클을 타기 위해 기간을 길게 잡습니다.
        
        Args:
            ma_fast: 단기 추세선 기간 (일, 기본값: 20일)
            ma_slow: 장기 기준선 기간 (일, 기본값: 120일)
            ma_filter: 대세 판단용 이동평균 기간 (일, 기본값: 200일)
            min_days: 최소 필요한 데이터 일수 (기본값: 250일)
            
        Returns:
            Dict: {
                "spread": 현재 스프레드 값 (%),
                "spread_fast": Spread의 단기 이동평균 (%),
                "spread_slow": Spread의 장기 이동평균 (%),
                "yield_trend": DGS10의 200일 이동평균 (%),
                "current_dgs10": 현재 DGS10 값 (%),
                "current_dgs2": 현재 DGS2 값 (%),
                "spread_trend": "Steepening" 또는 "Flattening",
                "spread_trend_kr": 스프레드 추세 한글명,
                "yield_regime": "Rising" 또는 "Falling",
                "yield_regime_kr": 금리 대세 한글명,
                "regime": "Bull Steepening" | "Bear Steepening" | "Bull Flattening" | "Bear Flattening",
                "regime_kr": 국면 한글명
            } 또는 None (데이터 부족 시)
        """
        try:
            # 충분한 일별 데이터 조회 (최소 250일, 여유를 두고)
            dgs10 = self.fred_collector.get_latest_data("DGS10", min_days)
            dgs2 = self.fred_collector.get_latest_data("DGS2", min_days)
            
            if len(dgs10) == 0 or len(dgs2) == 0:
                logger.warning("장단기 금리 데이터가 부족합니다")
                return None
            
            # 최소 데이터 요구사항 확인 (ma_filter보다 충분히 많아야 함)
            if len(dgs10) < ma_filter or len(dgs2) < ma_filter:
                logger.warning(
                    f"데이터가 부족합니다. 필요: {ma_filter}일, 현재: DGS10={len(dgs10)}일, DGS2={len(dgs2)}일"
                )
                return None
            
            # 날짜 기준으로 정렬 및 병합
            df = pd.DataFrame({
                "DGS10": dgs10,
                "DGS2": dgs2
            })
            df = df.sort_index()
            
            # 결측치 처리 (forward fill)
            df = df.ffill().dropna()
            
            if len(df) < ma_filter:
                logger.warning(f"결측치 제거 후 데이터가 부족합니다: {len(df)}일")
                return None
            
            # 1. Spread 계산: DGS10 - DGS2
            df["Spread"] = df["DGS10"] - df["DGS2"]
            
            # 2. Spread_Fast: Spread의 단기 이동평균
            df["Spread_Fast"] = df["Spread"].rolling(window=ma_fast).mean()
            
            # 3. Spread_Slow: Spread의 장기 이동평균
            df["Spread_Slow"] = df["Spread"].rolling(window=ma_slow).mean()
            
            # 4. Yield_Trend: DGS10의 200일 이동평균
            df["Yield_Trend"] = df["DGS10"].rolling(window=ma_filter).mean()
            
            # 최신 값 추출
            latest = df.iloc[-1]
            current_spread = latest["Spread"]
            spread_fast = latest["Spread_Fast"]
            spread_slow = latest["Spread_Slow"]
            yield_trend = latest["Yield_Trend"]
            current_dgs10 = latest["DGS10"]
            current_dgs2 = latest["DGS2"]
            
            # Condition A: 스프레드 추세 판단
            if spread_fast > spread_slow:
                spread_trend = "Steepening"
                spread_trend_kr = "확대"
            else:
                spread_trend = "Flattening"
                spread_trend_kr = "축소"
            
            # Condition B: 금리 대세 판단
            if current_dgs10 > yield_trend:
                yield_regime = "Rising"
                yield_regime_kr = "금리 상승 추세"
            else:
                yield_regime = "Falling"
                yield_regime_kr = "금리 하락 추세"
            
            # 4가지 국면 판단
            if spread_trend == "Steepening" and yield_regime == "Falling":
                regime = "Bull Steepening"
                regime_kr = "Bull Steepening (경기 부양 기대)"
            elif spread_trend == "Steepening" and yield_regime == "Rising":
                regime = "Bear Steepening"
                regime_kr = "Bear Steepening (인플레/재정 공포)"
            elif spread_trend == "Flattening" and yield_regime == "Falling":
                regime = "Bull Flattening"
                regime_kr = "Bull Flattening (경기 둔화 초기)"
            else:  # Flattening + Rising
                regime = "Bear Flattening"
                regime_kr = "Bear Flattening (강력한 긴축)"
            
            logger.info(
                f"장단기 금리차 추세 추종 전략: {regime_kr}\n"
                f"  - 스프레드: {current_spread:.2f}% (단기 MA: {spread_fast:.2f}%, 장기 MA: {spread_slow:.2f}%)\n"
                f"  - 금리 대세: {yield_regime_kr} (DGS10: {current_dgs10:.2f}%, 200일 MA: {yield_trend:.2f}%)"
            )
            
            return {
                "spread": float(current_spread),
                "spread_fast": float(spread_fast),
                "spread_slow": float(spread_slow),
                "yield_trend": float(yield_trend),
                "current_dgs10": float(current_dgs10),
                "current_dgs2": float(current_dgs2),
                "spread_trend": spread_trend,
                "spread_trend_kr": spread_trend_kr,
                "yield_regime": yield_regime,
                "yield_regime_kr": yield_regime_kr,
                "regime": regime,
                "regime_kr": regime_kr
            }
            
        except Exception as e:
            logger.error(f"장단기 금리차 추세 추종 전략 계산 실패: {e}", exc_info=True)
            return None
    
    def get_real_interest_rate(self, days: int = 30) -> Optional[float]:
        """
        실질 금리 (DFII10 - FRED에서 직접 조회)
        
        Args:
            days: 최근 N일간의 데이터 사용
            
        Returns:
            float: 실질 금리 (%) 또는 None (데이터 부족 시)
        """
        try:
            # DFII10 (10-Year Treasury Inflation-Indexed Security, Constant Maturity)
            dfii10 = self.fred_collector.get_latest_data("DFII10", days)
            if len(dfii10) == 0:
                logger.warning("DFII10 데이터가 부족합니다")
                return None
            
            latest_rate = dfii10.iloc[-1]
            
            logger.info(f"실질 금리 (DFII10): {latest_rate:.2f}%")
            return float(latest_rate)
            
        except Exception as e:
            logger.error(f"실질 금리 조회 실패: {e}")
            return None
    
    def get_taylor_rule_signal(
        self,
        natural_rate: float = 2.0,
        target_inflation: float = 2.0,
        days: int = 30
    ) -> Optional[float]:
        """
        공식 3: 테일러 준칙 (Target_Rate - FEDFUNDS)
        
        테일러 준칙 공식:
        Target_Rate = r* + π + 0.5(π - π*) + 0.5(y - y*)
        
        여기서:
        - r*: 자연 이자율 (기본값 2%)
        - π: 현재 인플레이션율 (PCE 사용)
        - π*: 목표 인플레이션율 (기본값 2%)
        - y: 실제 GDP 성장률
        - y*: 잠재 GDP 성장률 (추정 필요)
        
        Args:
            natural_rate: 자연 이자율 r* (%)
            target_inflation: 목표 인플레이션율 π* (%)
            days: 최근 N일간의 데이터 사용
            
        Returns:
            float: 테일러 준칙 신호 (Target_Rate - FEDFUNDS) 또는 None
        """
        try:
            # FEDFUNDS (현재 연준 금리 - 월별 데이터)
            # 월별 데이터이므로 최신 값만 필요, 안전하게 최근 90일(약 3개월) 조회
            fedfunds = self.fred_collector.get_latest_data("FEDFUNDS", days=90)
            if len(fedfunds) == 0:
                logger.warning("FEDFUNDS 데이터가 부족합니다.")
                return None
            
            current_fedfunds = fedfunds.iloc[-1]
            
            # PCE 인플레이션율 (월별 데이터)
            # PCEPI는 최신 데이터가 3개월 전 것일 수 있으므로 충분한 기간 조회 필요
            # 최소 6개월(180일) 데이터 조회하여 최소 2개월치 데이터 확보
            pce_data = self.fred_collector.get_latest_data("PCEPI", days=180)
            if len(pce_data) < 2:
                logger.warning("PCE 데이터가 부족합니다 (최소 2개월치 필요)")
                return None
            
            # PCE 증가율 계산 (전월 대비 연율화)
            # 월별 데이터이므로 날짜 기준으로 정렬하여 최신 2개월치 사용
            pce_values = pce_data.sort_index()
            latest_pce = pce_values.iloc[-1]
            latest_pce_date = pce_values.index[-1]
            prev_pce = pce_values.iloc[-2] if len(pce_values) >= 2 else pce_values.iloc[0]
            
            # 최신 데이터의 날짜 확인 (3개월 이상 오래된 경우 경고)
            today = date.today()
            if isinstance(latest_pce_date, pd.Timestamp):
                latest_pce_date_only = latest_pce_date.date()
            else:
                latest_pce_date_only = latest_pce_date
            
            days_old = (today - latest_pce_date_only).days
            if days_old > 90:
                logger.warning(
                    f"PCEPI 최신 데이터가 {days_old}일 전 것입니다 "
                    f"(날짜: {latest_pce_date_only}). "
                    f"3개월 이상 지연된 데이터를 사용합니다."
                )
            
            current_inflation = ((latest_pce / prev_pce) - 1) * 12 * 100
            
            # GDP 갭 추정 (간단히 0으로 가정, 추후 개선 가능)
            gdp_gap = 0.0
            
            # 테일러 준칙 계산
            # Target_Rate = r* + π + 0.5(π - π*) + 0.5(y - y*)
            target_rate = (
                natural_rate +
                current_inflation +
                0.5 * (current_inflation - target_inflation) +
                0.5 * gdp_gap
            )
            
            # 신호 = 목표 금리 - 현재 금리
            signal = target_rate - current_fedfunds
            
            logger.info(
                f"테일러 준칙 신호: {signal:.2f}% "
                f"(목표 금리: {target_rate:.2f}%, 현재 금리: {current_fedfunds:.2f}%)"
            )
            return float(signal)
            
        except Exception as e:
            logger.error(f"테일러 준칙 계산 실패: {e}")
            return None
    
    def get_net_liquidity(
        self,
        ma_weeks: int = 4,
        days: int = 60
    ) -> Optional[Dict[str, float]]:
        """
        공식 4: 연준 순유동성 (Fed Net Liquidity)
        
        공식: Net Liquidity = WALCL - WTREGEN - RRPONTSYD
        
        Args:
            ma_weeks: 이동평균 기간 (주)
            days: 최근 N일간의 데이터 사용
            
        Returns:
            Dict[str, float]: {
                "net_liquidity": 순유동성 값 (Millions of Dollars),
                "ma_trend": 이동평균 추세 (1: 상승, -1: 하락, 0: 보합),
                "ma_value": 이동평균 값
            } 또는 None (데이터 부족 시)
        """
        try:
            # 각 지표 데이터 수집
            walcl = self.fred_collector.get_latest_data("WALCL", days)
            tga = self.fred_collector.get_latest_data("WTREGEN", days)
            rrp = self.fred_collector.get_latest_data("RRPONTSYD", days)
            
            if len(walcl) == 0 or len(tga) == 0 or len(rrp) == 0:
                logger.warning("유동성 지표 데이터가 부족합니다")
                return None
            
            # 날짜 기준으로 정렬 및 병합
            df = pd.DataFrame({
                "WALCL": walcl,
                "TGA": tga,
                "RRP": rrp
            })
            df = df.sort_index()
            
            # 결측치 처리 (forward fill)
            df = df.ffill().dropna()
            
            if len(df) == 0:
                logger.warning("유동성 지표 데이터 병합 실패")
                return None
            
            # 순유동성 계산
            df["net_liquidity"] = df["WALCL"] - df["TGA"] - df["RRP"]
            
            # 이동평균 계산 (주 단위로 변환)
            ma_period = ma_weeks * 7  # 일 단위로 변환
            if len(df) >= ma_period:
                df["ma"] = df["net_liquidity"].rolling(window=ma_period).mean()
                
                # 최신 값과 이동평균 추세
                latest_net = df["net_liquidity"].iloc[-1]
                latest_ma = df["ma"].iloc[-1]
                prev_ma = df["ma"].iloc[-2] if len(df) >= 2 else latest_ma
                
                # 추세 판단 (1: 상승, -1: 하락, 0: 보합)
                if latest_ma > prev_ma:
                    trend = 1
                elif latest_ma < prev_ma:
                    trend = -1
                else:
                    trend = 0
                
                logger.info(
                    f"연준 순유동성: {latest_net:.0f}M (이동평균: {latest_ma:.0f}M, "
                    f"추세: {'상승' if trend == 1 else '하락' if trend == -1 else '보합'})"
                )
                
                return {
                    "net_liquidity": float(latest_net),
                    "ma_trend": float(trend),
                    "ma_value": float(latest_ma)
                }
            else:
                logger.warning(f"이동평균 계산을 위한 데이터가 부족합니다 (필요: {ma_period}일, 현재: {len(df)}일)")
                return {
                    "net_liquidity": float(df["net_liquidity"].iloc[-1]),
                    "ma_trend": None,
                    "ma_value": None
                }
                
        except Exception as e:
            logger.error(f"연준 순유동성 계산 실패: {e}")
            return None
    
    def get_high_yield_spread_signal(
        self,
        days: int = 30
    ) -> Optional[Dict[str, float]]:
        """
        공식 5: 하이일드 스프레드 (High Yield Spread) 평가
        
        평가 기준:
        - 3.5% 미만: 유동성 매우 풍부 (Greed) → 주식 적극 매수
        - 5.0% 이상: 유동성 경색 시작 (Fear) → 주식 비중 축소
        - 10.0% 이상: 금융 위기 (Panic) → 전량 현금/달러/국채
        
        Args:
            days: 최근 N일간의 데이터 사용
            
        Returns:
            Dict[str, float]: {
                "spread": 스프레드 값 (%),
                "signal": 신호 (-1: Panic, 0: Fear, 1: Greed),
                "signal_name": 신호 이름,
                "week_change": 전주 대비 변화율 (%)
            } 또는 None (데이터 부족 시)
        """
        try:
            # 하이일드 스프레드 데이터 수집
            spread_data = self.fred_collector.get_latest_data("BAMLH0A0HYM2", days)
            
            if len(spread_data) == 0:
                logger.warning("하이일드 스프레드 데이터가 부족합니다")
                return None
            
            # 최신 값
            latest_spread = spread_data.iloc[-1]
            
            # 전주 대비 변화율 계산 (7일 전 값과 비교)
            if len(spread_data) >= 7:
                week_ago_spread = spread_data.iloc[-7]
                week_change = ((latest_spread / week_ago_spread) - 1) * 100
            else:
                week_change = None
            
            # 신호 판단 (설정 파일에서 임계값 가져오기)
            try:
                config = get_config()
                thresholds = config.liquidity.high_yield_spread_thresholds if config.liquidity else {
                    "greed": 3.5, "fear": 5.0, "panic": 10.0
                }
            except Exception:
                # 설정 파일 로드 실패 시 기본값 사용
                thresholds = {"greed": 3.5, "fear": 5.0, "panic": 10.0}
            
            if latest_spread >= thresholds["panic"]:
                signal = -1  # Panic
                signal_name = "Panic"
            elif latest_spread >= thresholds["fear"]:
                signal = 0  # Fear
                signal_name = "Fear"
            elif latest_spread < thresholds["greed"]:
                signal = 1  # Greed
                signal_name = "Greed"
            else:
                signal = 0  # Neutral
                signal_name = "Neutral"
            
            logger.info(
                f"하이일드 스프레드: {latest_spread:.2f}% ({signal_name})"
                + (f", 전주 대비: {week_change:+.2f}%" if week_change is not None else "")
            )
            
            return {
                "spread": float(latest_spread),
                "signal": float(signal),
                "signal_name": signal_name,
                "week_change": float(week_change) if week_change is not None else None
            }
            
        except Exception as e:
            logger.error(f"하이일드 스프레드 평가 실패: {e}")
            return None
    
    def calculate_all_signals(
        self,
        natural_rate: float = 2.0,
        target_inflation: float = 2.0,
        liquidity_ma_weeks: Optional[int] = None
    ) -> Dict[str, Optional[float]]:
        """
        모든 정량 시그널을 계산합니다.
        
        Args:
            natural_rate: 자연 이자율 (%)
            target_inflation: 목표 인플레이션율 (%)
            liquidity_ma_weeks: 유동성 이동평균 기간 (주, None이면 설정 파일에서 가져옴)
            
        Returns:
            Dict[str, Optional[float]]: 시그널별 값
        """
        # 설정 파일에서 유동성 이동평균 기간 가져오기
        if liquidity_ma_weeks is None:
            try:
                config = get_config()
                liquidity_ma_weeks = config.liquidity.net_liquidity_ma_weeks if config.liquidity else 4
            except Exception:
                liquidity_ma_weeks = 4  # 기본값
        
        signals = {
            "yield_curve_spread_trend": self.get_yield_curve_spread_trend_following(),
            "real_interest_rate": self.get_real_interest_rate(),
            "taylor_rule_signal": self.get_taylor_rule_signal(
                natural_rate=natural_rate,
                target_inflation=target_inflation
            ),
            "net_liquidity": self.get_net_liquidity(ma_weeks=liquidity_ma_weeks),
            "high_yield_spread": self.get_high_yield_spread_signal()
        }
        
        return signals
    
    def get_additional_indicators(self) -> Dict[str, Optional[float]]:
        """
        추가 지표 조회 (VIX, DXY, 실업률, GDP 성장률 등)
        
        Returns:
            Dict[str, Optional[float]]: 지표별 값
        """
        indicators = {}
        
        # 실업률
        try:
            unrate = self.fred_collector.get_latest_data("UNRATE", days=30)
            if len(unrate) > 0:
                indicators["unemployment_rate"] = float(unrate.iloc[-1])
        except Exception as e:
            logger.warning(f"실업률 조회 실패: {e}")
            indicators["unemployment_rate"] = None
        
        # 비농업 고용 지표
        try:
            payems = self.fred_collector.get_latest_data("PAYEMS", days=60)
            if len(payems) >= 2:
                # 전월 대비 증가율
                latest = payems.iloc[-1]
                prev = payems.iloc[-2]
                growth_rate = ((latest / prev) - 1) * 100
                indicators["payroll_growth"] = float(growth_rate)
        except Exception as e:
            logger.warning(f"고용 지표 조회 실패: {e}")
            indicators["payroll_growth"] = None
        
        return indicators
    
    def get_real_interest_rate_series(self, days: int = 365) -> Optional[pd.Series]:
        """
        실질 금리 시계열 데이터 조회 (DFII10 - FRED에서 직접 조회)
        
        Args:
            days: 조회할 일수
            
        Returns:
            pd.Series: 날짜를 인덱스로 하는 실질 금리 시계열 데이터 (%) 또는 None
        """
        try:
            # DFII10 (10-Year Treasury Inflation-Indexed Security, Constant Maturity)
            dfii10 = self.fred_collector.get_latest_data("DFII10", days=days)
            if len(dfii10) == 0:
                logger.warning("DFII10 데이터가 부족합니다")
                return None
            
            logger.info(f"실질 금리 시계열 데이터 조회 완료: {len(dfii10)}개 데이터 포인트")
            return dfii10
            
        except Exception as e:
            logger.error(f"실질 금리 시계열 데이터 조회 실패: {e}", exc_info=True)
            return None
    
    def get_net_liquidity_series(self, days: int = 365) -> Optional[pd.Series]:
        """
        연준 순유동성 시계열 데이터 계산
        
        Args:
            days: 조회할 일수
            
        Returns:
            pd.Series: 날짜를 인덱스로 하는 순유동성 시계열 데이터 (Millions of Dollars) 또는 None
        """
        try:
            # 각 지표 데이터 수집
            walcl = self.fred_collector.get_latest_data("WALCL", days=days)
            tga = self.fred_collector.get_latest_data("WTREGEN", days=days)
            rrp = self.fred_collector.get_latest_data("RRPONTSYD", days=days)
            
            if len(walcl) == 0 or len(tga) == 0 or len(rrp) == 0:
                logger.warning("유동성 지표 데이터가 부족합니다")
                return None
            
            # 날짜 기준으로 정렬 및 병합
            df = pd.DataFrame({
                "WALCL": walcl,
                "TGA": tga,
                "RRP": rrp
            })
            df = df.sort_index()
            
            # 결측치 처리 (forward fill)
            df = df.ffill().dropna()
            
            if len(df) == 0:
                logger.warning("유동성 지표 데이터 병합 실패")
                return None
            
            # 순유동성 계산
            df["net_liquidity"] = df["WALCL"] - df["TGA"] - df["RRP"]
            
            logger.info(f"연준 순유동성 시계열 데이터 계산 완료: {len(df)}개 데이터 포인트")
            return df["net_liquidity"]
            
        except Exception as e:
            logger.error(f"연준 순유동성 시계열 데이터 계산 실패: {e}", exc_info=True)
            return None

    def get_macro_dashboard_indicators(self) -> Dict[str, Any]:
        """
        매크로 대시보드용 종합 지표 수집
        (Growth, Inflation, Liquidity, Sentiment)
        
        Returns:
            Dict[str, Any]: 대시보드 구성을 위한 데이터 딕셔너리
        """
        dashboard_data = {
            "growth": {},
            "inflation": {},
            "liquidity": {},
            "sentiment": {}
        }
        
        # 1. Growth (경기 성장 & 선행 지표)
        # 1. Growth (경기 성장 & 선행 지표)
        try:
            # Philly Fed Current Activity (GACDFSA066MSFRBPHI) - ISM PMI 대체
            philly_curr = self.fred_collector.get_latest_data("GACDFSA066MSFRBPHI", days=90)
            if len(philly_curr) > 0:
                latest_curr = philly_curr.iloc[-1]
                dashboard_data["growth"]["philly_current"] = {
                    "value": float(latest_curr),
                    "status": "확장" if latest_curr > 0 else "위축"
                }

            # Philly Fed New Orders (NOCDFSA066MSFRBPHI) - ISM New Orders 대체
            philly_new = self.fred_collector.get_latest_data("NOCDFSA066MSFRBPHI", days=90)
            if len(philly_new) > 0:
                dashboard_data["growth"]["philly_new_orders"] = float(philly_new.iloc[-1])

            # Philly Fed Future Activity (GAFDFSA066MSFRBPHI)
            philly_future = self.fred_collector.get_latest_data("GAFDFSA066MSFRBPHI", days=90)
            if len(philly_future) > 0:
                dashboard_data["growth"]["philly_future"] = float(philly_future.iloc[-1])
            
            # GDPNow (GDPNOW)
            gdpnow = self.fred_collector.get_latest_data("GDPNOW", days=365)
            if len(gdpnow) > 0:
                dashboard_data["growth"]["gdp_now"] = float(gdpnow.iloc[-1])
                
            # 실업률 (UNRATE)
            unrate = self.fred_collector.get_latest_data("UNRATE", days=365)
            if len(unrate) > 0:
                current_unrate = unrate.iloc[-1]
                # 3개월 전 (대략 3번째 뒤의 값, or 날짜 비교)
                # 월별 데이터이므로 tail(4)에서 맨 처음이 3개월 전
                past_unrate = unrate.iloc[-4] if len(unrate) >= 4 else unrate.iloc[0]
                
                # Sam's Rule 유사 로직 (최근 3개월 이동평균이 지난 12개월 최저치보다 0.5%p 이상 상승 시 침체)
                # 여기서는 단순 급등 여부만 판단
                diff = current_unrate - past_unrate
                sams_rule = "경고등 켜짐" if diff >= 0.5 else "경고등 꺼짐"
                
                dashboard_data["growth"]["unemployment"] = {
                    "current": float(current_unrate),
                    "past_3m": float(past_unrate),
                    "diff_trend": "급등" if diff >= 0.5 else "안정/하락" if diff <= 0 else "상승",
                    "sams_rule": sams_rule
                }
            
            # 비농업 고용 (PAYEMS) - NFP Change
            # 1년 전 데이터 비교를 위해 충분한 기간 수집 (400일)
            payems = self.fred_collector.get_latest_data("PAYEMS", days=400)
            if len(payems) >= 13:
                latest_nfp = payems.iloc[-1]
                prev_nfp = payems.iloc[-2]
                year_ago_nfp = payems.iloc[-13]
                
                nfp_change = (latest_nfp - prev_nfp) # 단위: 천명 (이번달 증가폭)
                nfp_diff_prev = nfp_change # 이번달 증가폭이 곧 전월 대비 차이(Flow 개념이 아니라 Stock의 차이이므로)
                # 요청사항: "1년 전의 지수와의 차이, 직전 지수와의 차이"
                # PAYEMS는 'Total Nonfarm Payrolls' (Total Stock) 임.
                # 직전 지수와의 차이 = 이번달 증감 (NFP Change)
                # 1년 전 지수와의 차이 = YoY Growth (Total Stock의 차이)
                
                nfp_diff_year = latest_nfp - year_ago_nfp
                
                dashboard_data["growth"]["nfp"] = {
                    "value": float(nfp_change),
                    "diff_prev": float(nfp_diff_prev), # == value
                    "diff_year": float(nfp_diff_year),
                    "consensus": 0,
                    "surprise": "N/A"
                }
            elif len(payems) >= 2:
                 # 데이터가 부족한 경우 (최소 전월 대비는 계산)
                latest_nfp = payems.iloc[-1]
                prev_nfp = payems.iloc[-2]
                nfp_change = latest_nfp - prev_nfp
                
                dashboard_data["growth"]["nfp"] = {
                    "value": float(nfp_change),
                    "diff_prev": float(nfp_change),
                    "diff_year": "N/A",
                    "consensus": 0,
                    "surprise": "N/A"
                }

        except Exception as e:
            logger.error(f"Growth 지표 수집 실패: {e}")
            
        # 2. Inflation (물가 압력)
        try:
            # Core PCE (PCEPILFE) - YoY
            pce_core = self.fred_collector.get_latest_data("PCEPILFE", days=730)
            if len(pce_core) >= 13:
                curr = pce_core.iloc[-1]
                year_ago = pce_core.iloc[-13] # 1년 전
                yoy = ((curr / year_ago) - 1) * 100
                dashboard_data["inflation"]["core_pce_yoy"] = {
                    "value": float(yoy),
                    "target_gap": "큼" if abs(yoy - 2.0) > 1.0 else "작음"
                }
            
            # Headline CPI (CPIAUCSL) - YoY
            cpi = self.fred_collector.get_latest_data("CPIAUCSL", days=730)
            if len(cpi) >= 13:
                curr = cpi.iloc[-1]
                year_ago = cpi.iloc[-13]
                yoy = ((curr / year_ago) - 1) * 100
                
                # 추세 (최근 3개월 변화율 추이)
                last_3m_change = cpi.pct_change().tail(3).mean()
                trend = "상승중" if last_3m_change > 0.003 else "횡보중" if last_3m_change > -0.001 else "하락중"
                
                dashboard_data["inflation"]["cpi_yoy"] = {
                    "value": float(yoy),
                    "trend": trend
                }
            
            # 기대 인플레이션 (T10YIE or BEI 10Y)
            bei = self.fred_collector.get_latest_data("T10YIE", days=30)
            if len(bei) > 0:
                dashboard_data["inflation"]["expected_inflation"] = float(bei.iloc[-1])
                
        except Exception as e:
            logger.error(f"Inflation 지표 수집 실패: {e}")
            
        # 3. Liquidity & Fed Policy
        try:
            # 금리 커브 (10Y-2Y)
            dgs10 = self.fred_collector.get_latest_data("DGS10", days=30)
            dgs2 = self.fred_collector.get_latest_data("DGS2", days=30)
            if len(dgs10) > 0 and len(dgs2) > 0:
                spread = dgs10.iloc[-1] - dgs2.iloc[-1]
                # 상태 판단 (단순화)
                status = "Bull Steepening - 경기 침체 대비 금리 인하 기대 반영" # 기본값, 실제로는 로직 필요
                # QuantSignalCalculator의 기존 로직 활용 권장
                yc_signal = self.get_yield_curve_spread_trend_following()
                if yc_signal:
                    status = yc_signal.get("regime_kr", status)
                
                dashboard_data["liquidity"]["yield_curve"] = {
                    "value_bp": float(spread * 100),
                    "status": status
                }
            
            # SOMA (WALCL)
            walcl = self.fred_collector.get_latest_data("WALCL", days=90)
            if len(walcl) > 0:
                latest_walcl = walcl.iloc[-1] / 1000 # B unit
                # QT 속도 (최근 4주 변화)
                if len(walcl) >= 5:
                    change_4w = walcl.iloc[-1] - walcl.iloc[-5]
                    qt_speed = "빠름" if change_4w < -50000 else "느림" if change_4w < 0 else "중단/증가"
                else:
                    qt_speed = "N/A"
                
                dashboard_data["liquidity"]["soma"] = {
                    "value": float(latest_walcl),
                    "qt_speed": qt_speed
                }
            
            # Net Liquidity
            net_liq = self.get_net_liquidity(days=30)
            if net_liq:
                # SOMA 감소에도 유동성 증가 여부 -> TGA/RRP 변화 확인 필요하나 여기서는 단순 추세만
                trend = "증가" if net_liq.get("ma_trend") == 1 else "감소"
                dashboard_data["liquidity"]["net_liquidity"] = {
                    "value": net_liq.get("net_liquidity") / 1000, # B unit
                    "status": f"SOMA 감소에도 불구하고 유동성 {trend} 중" # 텍스트 템플릿용
                }
            
            # HY Spread
            hy = self.get_high_yield_spread_signal()
            if hy:
                dashboard_data["liquidity"]["hy_spread"] = {
                    "value": hy.get("spread"),
                    "evaluation": f"{hy.get('signal_name')} - 시장이 위험을 {'무시' if hy.get('signal_name')=='Greed' else '반영'} 중"
                }
                
        except Exception as e:
            logger.error(f"Liquidity 지표 수집 실패: {e}")
            
        # 4. Sentiment
        try:
            # VIX
            vix = self.fred_collector.get_latest_data("VIXCLS", days=30)
            if len(vix) > 0:
                dashboard_data["sentiment"]["vix"] = float(vix.iloc[-1])
            
            # 금융 스트레스 지수 (STLFSI4) - MOVE 대체
            stlfsi = self.fred_collector.get_latest_data("STLFSI4", days=90)
            if len(stlfsi) > 0:
                latest_stlfsi = stlfsi.iloc[-1]
                dashboard_data["sentiment"]["stlfsi4"] = {
                    "value": float(latest_stlfsi),
                    "status": "긴장" if latest_stlfsi > 0 else "평온"
                }
            else:
                 # 데이터 없으면 N/A 처리
                 dashboard_data["sentiment"]["stlfsi4"] = {
                    "value": "N/A",
                    "status": "N/A"
                }

            # CNN Fear & Greed (데이터 없음 - Placeholder)
            dashboard_data["sentiment"]["cnn_index"] = {
                "value": "N/A",
                "status": "알 수 없음"
            }
            
        except Exception as e:
            logger.error(f"Sentiment 지표 수집 실패: {e}")
            
        return dashboard_data
