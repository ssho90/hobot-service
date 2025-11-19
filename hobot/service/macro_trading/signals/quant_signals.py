"""
정량 시그널 계산 모듈
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, Optional, Tuple
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
    
    def get_yield_curve_spread(self, days: int = 30) -> Optional[float]:
        """
        공식 1: 장단기 금리차 (DGS10 - DGS2)
        
        Args:
            days: 최근 N일간의 평균값 사용
            
        Returns:
            float: 장단기 금리차 (%) 또는 None (데이터 부족 시)
        """
        try:
            dgs10 = self.fred_collector.get_latest_data("DGS10", days)
            dgs2 = self.fred_collector.get_latest_data("DGS2", days)
            
            if len(dgs10) == 0 or len(dgs2) == 0:
                logger.warning("장단기 금리 데이터가 부족합니다")
                return None
            
            # 최신 값 사용 (또는 평균값)
            latest_dgs10 = dgs10.iloc[-1] if len(dgs10) > 0 else None
            latest_dgs2 = dgs2.iloc[-1] if len(dgs2) > 0 else None
            
            if latest_dgs10 is None or latest_dgs2 is None:
                return None
            
            spread = latest_dgs10 - latest_dgs2
            logger.info(f"장단기 금리차: {spread:.2f}% (DGS10: {latest_dgs10:.2f}%, DGS2: {latest_dgs2:.2f}%)")
            return float(spread)
            
        except Exception as e:
            logger.error(f"장단기 금리차 계산 실패: {e}")
            return None
    
    def get_real_interest_rate(self, days: int = 30) -> Optional[float]:
        """
        공식 2: 실질 금리 (DGS10 - CPI 증가율)
        
        Args:
            days: 최근 N일간의 데이터 사용
            
        Returns:
            float: 실질 금리 (%) 또는 None (데이터 부족 시)
        """
        try:
            # DGS10 (명목 금리)
            dgs10 = self.fred_collector.get_latest_data("DGS10", days)
            if len(dgs10) == 0:
                logger.warning("DGS10 데이터가 부족합니다")
                return None
            
            latest_dgs10 = dgs10.iloc[-1]
            
            # CPI 데이터 (월별 → 일별 보간 필요)
            cpi_data = self.fred_collector.get_latest_data("CPIAUCSL", days=365)  # 1년치 가져오기
            
            if len(cpi_data) < 2:
                logger.warning("CPI 데이터가 부족합니다")
                return None
            
            # CPI 증가율 계산 (전월 대비 연율화)
            # 최신 CPI와 한 달 전 CPI 비교
            cpi_values = cpi_data.sort_index()
            latest_cpi = cpi_values.iloc[-1]
            prev_cpi = cpi_values.iloc[-2] if len(cpi_values) >= 2 else cpi_values.iloc[0]
            
            # 월간 증가율을 연율화 (12배)
            cpi_inflation_rate = ((latest_cpi / prev_cpi) - 1) * 12 * 100
            
            # 실질 금리 = 명목 금리 - 인플레이션율
            real_rate = latest_dgs10 - cpi_inflation_rate
            
            logger.info(
                f"실질 금리: {real_rate:.2f}% "
                f"(명목 금리: {latest_dgs10:.2f}%, CPI 증가율: {cpi_inflation_rate:.2f}%)"
            )
            return float(real_rate)
            
        except Exception as e:
            logger.error(f"실질 금리 계산 실패: {e}")
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
            # FEDFUNDS (현재 연준 금리)
            fedfunds = self.fred_collector.get_latest_data("FEDFUNDS", days)
            if len(fedfunds) == 0:
                logger.warning("FEDFUNDS 데이터가 부족합니다")
                return None
            
            current_fedfunds = fedfunds.iloc[-1]
            
            # PCE 인플레이션율 (월별 데이터)
            pce_data = self.fred_collector.get_latest_data("PCEPI", days=365)
            if len(pce_data) < 2:
                logger.warning("PCE 데이터가 부족합니다")
                return None
            
            # PCE 증가율 계산 (전월 대비 연율화)
            pce_values = pce_data.sort_index()
            latest_pce = pce_values.iloc[-1]
            prev_pce = pce_values.iloc[-2] if len(pce_values) >= 2 else pce_values.iloc[0]
            
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
            "yield_curve_spread": self.get_yield_curve_spread(),
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

