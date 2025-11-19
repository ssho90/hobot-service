"""
정량 시그널 계산 테스트 스크립트 (DB 없이 동작)
FRED API에서 직접 데이터를 가져와서 메모리에서만 계산합니다.
"""
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (hobot 디렉토리)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import logging
from datetime import date, timedelta
from typing import Optional, Dict
import pandas as pd

from service.macro_trading.collectors.fred_collector import FREDCollector, get_fred_collector
from service.macro_trading.config.config_loader import get_config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockFREDCollector(FREDCollector):
    """DB 없이 동작하는 Mock FRED Collector"""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        self._cache: Dict[str, pd.Series] = {}
    
    def get_latest_data(self, indicator_code: str, days: int = 30) -> pd.Series:
        """
        DB 대신 메모리 캐시에서 데이터를 가져옵니다.
        캐시에 없으면 FRED API에서 직접 가져옵니다.
        """
        cache_key = f"{indicator_code}_{days}"
        
        if cache_key not in self._cache:
            # FRED API에서 직접 데이터 가져오기
            end_date = date.today()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"[Mock] FRED API에서 {indicator_code} 데이터 수집 중...")
            data = self.fetch_indicator(indicator_code, start_date, end_date)
            
            if len(data) > 0:
                self._cache[cache_key] = data
                logger.info(f"[Mock] {indicator_code} 데이터 캐시에 저장: {len(data)}개 포인트")
            else:
                logger.warning(f"[Mock] {indicator_code} 데이터가 없습니다")
                return pd.Series(dtype=float)
        
        return self._cache[cache_key]


def test_yield_curve_spread(collector: MockFREDCollector):
    """공식 1: 장단기 금리차 테스트"""
    print("\n" + "=" * 60)
    print("공식 1: 장단기 금리차 (DGS10 - DGS2)")
    print("=" * 60)
    
    try:
        dgs10 = collector.get_latest_data("DGS10", days=30)
        dgs2 = collector.get_latest_data("DGS2", days=30)
        
        if len(dgs10) == 0 or len(dgs2) == 0:
            print("❌ 데이터 부족")
            return None
        
        latest_dgs10 = dgs10.iloc[-1]
        latest_dgs2 = dgs2.iloc[-1]
        spread = latest_dgs10 - latest_dgs2
        
        print(f"  DGS10 (10년 국채): {latest_dgs10:.2f}%")
        print(f"  DGS2 (2년 국채): {latest_dgs2:.2f}%")
        print(f"  📊 장단기 금리차: {spread:.2f}%")
        
        if spread < 0:
            print("  ⚠️  금리 역전 (경기 침체 신호)")
        elif spread < 1.0:
            print("  ⚠️  금리차 축소 (경기 둔화 신호)")
        else:
            print("  ✅ 정상적인 금리차")
        
        return spread
    except Exception as e:
        print(f"❌ 계산 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_real_interest_rate(collector: MockFREDCollector):
    """공식 2: 실질 금리 테스트"""
    print("\n" + "=" * 60)
    print("공식 2: 실질 금리 (DGS10 - CPI 증가율)")
    print("=" * 60)
    
    try:
        dgs10 = collector.get_latest_data("DGS10", days=30)
        cpi_data = collector.get_latest_data("CPIAUCSL", days=365)
        
        if len(dgs10) == 0 or len(cpi_data) < 2:
            print("❌ 데이터 부족")
            return None
        
        latest_dgs10 = dgs10.iloc[-1]
        cpi_values = cpi_data.sort_index()
        latest_cpi = cpi_values.iloc[-1]
        prev_cpi = cpi_values.iloc[-2] if len(cpi_values) >= 2 else cpi_values.iloc[0]
        
        cpi_inflation_rate = ((latest_cpi / prev_cpi) - 1) * 12 * 100
        real_rate = latest_dgs10 - cpi_inflation_rate
        
        print(f"  명목 금리 (DGS10): {latest_dgs10:.2f}%")
        print(f"  CPI 증가율 (연율): {cpi_inflation_rate:.2f}%")
        print(f"  📊 실질 금리: {real_rate:.2f}%")
        
        if real_rate < 0:
            print("  ⚠️  음의 실질 금리 (인플레이션 > 명목 금리)")
        elif real_rate < 1.0:
            print("  ⚠️  낮은 실질 금리")
        else:
            print("  ✅ 양의 실질 금리")
        
        return real_rate
    except Exception as e:
        print(f"❌ 계산 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_taylor_rule(collector: MockFREDCollector):
    """공식 3: 테일러 준칙 테스트"""
    print("\n" + "=" * 60)
    print("공식 3: 테일러 준칙 (Target_Rate - FEDFUNDS)")
    print("=" * 60)
    
    try:
        fedfunds = collector.get_latest_data("FEDFUNDS", days=30)
        pce_data = collector.get_latest_data("PCEPI", days=365)
        
        if len(fedfunds) == 0 or len(pce_data) < 2:
            print("❌ 데이터 부족")
            return None
        
        current_fedfunds = fedfunds.iloc[-1]
        pce_values = pce_data.sort_index()
        latest_pce = pce_values.iloc[-1]
        prev_pce = pce_values.iloc[-2] if len(pce_values) >= 2 else pce_values.iloc[0]
        
        current_inflation = ((latest_pce / prev_pce) - 1) * 12 * 100
        
        natural_rate = 2.0
        target_inflation = 2.0
        gdp_gap = 0.0
        
        target_rate = (
            natural_rate +
            current_inflation +
            0.5 * (current_inflation - target_inflation) +
            0.5 * gdp_gap
        )
        
        signal = target_rate - current_fedfunds
        
        print(f"  현재 연준 금리 (FEDFUNDS): {current_fedfunds:.2f}%")
        print(f"  현재 인플레이션율 (PCE): {current_inflation:.2f}%")
        print(f"  목표 금리 (테일러 준칙): {target_rate:.2f}%")
        print(f"  📊 테일러 준칙 신호: {signal:+.2f}%p")
        
        if signal > 0.5:
            print("  📈 금리 인상 필요 (긴축 정책)")
        elif signal < -0.5:
            print("  📉 금리 인하 여지 (완화 정책)")
        else:
            print("  ✅ 적정 금리 수준")
        
        return signal
    except Exception as e:
        print(f"❌ 계산 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_net_liquidity(collector: MockFREDCollector):
    """공식 4: 연준 순유동성 테스트"""
    print("\n" + "=" * 60)
    print("공식 4: 연준 순유동성 (Fed Net Liquidity)")
    print("=" * 60)
    print("공식: Net Liquidity = WALCL - WTREGEN - RRPONTSYD")
    
    try:
        walcl = collector.get_latest_data("WALCL", days=60)
        tga = collector.get_latest_data("WTREGEN", days=60)
        rrp = collector.get_latest_data("RRPONTSYD", days=60)
        
        if len(walcl) == 0 or len(tga) == 0 or len(rrp) == 0:
            print("❌ 데이터 부족")
            return None
        
        # 날짜 기준으로 정렬 및 병합
        df = pd.DataFrame({
            "WALCL": walcl,
            "TGA": tga,
            "RRP": rrp
        })
        df = df.sort_index()
        df = df.ffill().dropna()
        
        if len(df) == 0:
            print("❌ 데이터 병합 실패")
            return None
        
        # 순유동성 계산
        df["net_liquidity"] = df["WALCL"] - df["TGA"] - df["RRP"]
        
        # 이동평균 계산 (4주 = 28일)
        ma_weeks = 4
        ma_period = ma_weeks * 7
        
        if len(df) >= ma_period:
            df["ma"] = df["net_liquidity"].rolling(window=ma_period).mean()
            
            latest_net = df["net_liquidity"].iloc[-1]
            latest_ma = df["ma"].iloc[-1]
            prev_ma = df["ma"].iloc[-2] if len(df) >= 2 else latest_ma
            
            trend = 1 if latest_ma > prev_ma else (-1 if latest_ma < prev_ma else 0)
            
            print(f"  연준 총자산 (WALCL): {df['WALCL'].iloc[-1]:,.0f}M")
            print(f"  재무부 일반 계정 (TGA): {df['TGA'].iloc[-1]:,.0f}M")
            print(f"  역레포 잔고 (RRP): {df['RRP'].iloc[-1]:,.0f}M")
            print(f"  📊 순유동성: {latest_net:,.0f}M")
            print(f"  이동평균 ({ma_weeks}주): {latest_ma:,.0f}M")
            
            if trend == 1:
                print("  📈 추세: 상승 (유동성 공급 확대 → 위험자산 비중 확대)")
            elif trend == -1:
                print("  📉 추세: 하락 (유동성 흡수 → 현금/채권 비중 확대)")
            else:
                print("  ➡️  추세: 보합")
            
            return {
                "net_liquidity": float(latest_net),
                "ma_trend": float(trend),
                "ma_value": float(latest_ma)
            }
        else:
            latest_net = df["net_liquidity"].iloc[-1]
            print(f"  📊 순유동성: {latest_net:,.0f}M (이동평균 계산 불가: 데이터 부족)")
            return {"net_liquidity": float(latest_net), "ma_trend": None, "ma_value": None}
            
    except Exception as e:
        print(f"❌ 계산 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_high_yield_spread(collector: MockFREDCollector):
    """공식 5: 하이일드 스프레드 테스트"""
    print("\n" + "=" * 60)
    print("공식 5: 하이일드 스프레드 (High Yield Spread)")
    print("=" * 60)
    
    try:
        spread_data = collector.get_latest_data("BAMLH0A0HYM2", days=30)
        
        if len(spread_data) == 0:
            print("❌ 데이터 부족")
            return None
        
        latest_spread = spread_data.iloc[-1]
        
        # 전주 대비 변화율
        if len(spread_data) >= 7:
            week_ago_spread = spread_data.iloc[-7]
            week_change = ((latest_spread / week_ago_spread) - 1) * 100
        else:
            week_change = None
        
        # 설정 파일에서 임계값 가져오기
        try:
            config = get_config()
            thresholds = config.liquidity.high_yield_spread_thresholds if config.liquidity else {
                "greed": 3.5, "fear": 5.0, "panic": 10.0
            }
        except Exception:
            thresholds = {"greed": 3.5, "fear": 5.0, "panic": 10.0}
        
        # 신호 판단
        if latest_spread >= thresholds["panic"]:
            signal = -1
            signal_name = "Panic"
            signal_emoji = "🚨"
            signal_desc = "금융 위기 → 전량 현금/달러/국채"
        elif latest_spread >= thresholds["fear"]:
            signal = 0
            signal_name = "Fear"
            signal_emoji = "⚠️"
            signal_desc = "유동성 경색 시작 → 주식 비중 축소"
        elif latest_spread < thresholds["greed"]:
            signal = 1
            signal_name = "Greed"
            signal_emoji = "💰"
            signal_desc = "유동성 매우 풍부 → 주식 적극 매수"
        else:
            signal = 0
            signal_name = "Neutral"
            signal_emoji = "➡️"
            signal_desc = "중립"
        
        print(f"  📊 하이일드 스프레드: {latest_spread:.2f}%")
        if week_change is not None:
            print(f"  전주 대비: {week_change:+.2f}%")
        print(f"  {signal_emoji} 신호: {signal_name}")
        print(f"  💡 판단: {signal_desc}")
        print(f"  임계값: Greed < {thresholds['greed']}%, Fear ≥ {thresholds['fear']}%, Panic ≥ {thresholds['panic']}%")
        
        return {
            "spread": float(latest_spread),
            "signal": float(signal),
            "signal_name": signal_name,
            "week_change": float(week_change) if week_change is not None else None
        }
        
    except Exception as e:
        print(f"❌ 계산 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """메인 테스트 함수"""
    print("=" * 60)
    print("정량 시그널 계산 테스트 (DB 없이 동작)")
    print("=" * 60)
    print("⚠️  주의: DB 저장 없이 메모리에서만 계산합니다.")
    print("⚠️  FRED API 키가 필요합니다 (환경변수 FRED_API_KEY)\n")
    
    try:
        # Mock Collector 생성 (DB 없이 동작)
        collector = MockFREDCollector()
        
        # 연결 테스트
        print("\n[연결 테스트] FRED API 연결 확인 중...")
        if not collector.test_connection():
            print("❌ FRED API 연결 실패. FRED_API_KEY 환경변수를 확인하세요.")
            sys.exit(1)
        print("✅ FRED API 연결 성공!\n")
        
        # 각 시그널 테스트
        results = {}
        
        results["yield_curve_spread"] = test_yield_curve_spread(collector)
        results["real_interest_rate"] = test_real_interest_rate(collector)
        results["taylor_rule"] = test_taylor_rule(collector)
        results["net_liquidity"] = test_net_liquidity(collector)
        results["high_yield_spread"] = test_high_yield_spread(collector)
        
        # 결과 요약
        print("\n" + "=" * 60)
        print("테스트 결과 요약")
        print("=" * 60)
        
        success_count = sum(1 for v in results.values() if v is not None)
        total_count = len(results)
        
        print(f"\n성공: {success_count}/{total_count}")
        
        if results["yield_curve_spread"] is not None:
            print(f"  ✅ 장단기 금리차: {results['yield_curve_spread']:.2f}%")
        if results["real_interest_rate"] is not None:
            print(f"  ✅ 실질 금리: {results['real_interest_rate']:.2f}%")
        if results["taylor_rule"] is not None:
            print(f"  ✅ 테일러 준칙: {results['taylor_rule']:+.2f}%p")
        if results["net_liquidity"] is not None:
            net_liq = results["net_liquidity"]
            if isinstance(net_liq, dict):
                trend_str = "상승" if net_liq["ma_trend"] == 1 else ("하락" if net_liq["ma_trend"] == -1 else "보합")
                print(f"  ✅ 순유동성: {net_liq['net_liquidity']:,.0f}M (추세: {trend_str})")
        if results["high_yield_spread"] is not None:
            hy_spread = results["high_yield_spread"]
            print(f"  ✅ 하이일드 스프레드: {hy_spread['spread']:.2f}% ({hy_spread['signal_name']})")
        
        print("\n" + "=" * 60)
        if success_count == total_count:
            print("✅ 모든 테스트 통과!")
            sys.exit(0)
        else:
            print("⚠️  일부 테스트 실패")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ 테스트 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

