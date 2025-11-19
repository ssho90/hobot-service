"""
FRED API 연동 테스트 스크립트
"""
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (hobot 디렉토리)
# test_fred.py -> tests -> macro_trading -> service -> hobot
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import logging
from datetime import date, timedelta
from service.macro_trading.collectors.fred_collector import FREDCollector, get_fred_collector

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_fred_connection():
    """FRED API 연결 테스트"""
    print("=" * 50)
    print("FRED API 연결 테스트")
    print("=" * 50)
    
    try:
        collector = get_fred_collector()
        success = collector.test_connection()
        
        if success:
            print("✅ FRED API 연결 성공!")
            return True
        else:
            print("❌ FRED API 연결 실패")
            return False
    except Exception as e:
        print(f"❌ FRED API 연결 오류: {e}")
        return False


def test_data_collection():
    """데이터 수집 테스트"""
    print("\n" + "=" * 50)
    print("데이터 수집 테스트")
    print("=" * 50)
    
    try:
        collector = get_fred_collector()
        
        # 최근 30일 데이터 수집
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        print(f"수집 기간: {start_date} ~ {end_date}")
        
        # DGS10 데이터 수집 테스트
        print("\n[DGS10] 미국 10년 국채 금리 수집 중...")
        dgs10_data = collector.fetch_indicator("DGS10", start_date, end_date)
        print(f"  수집된 데이터 포인트: {len(dgs10_data)}개")
        if len(dgs10_data) > 0:
            print(f"  최신 값: {dgs10_data.iloc[-1]:.2f}% (날짜: {dgs10_data.index[-1].date()})")
            print(f"  첫 값: {dgs10_data.iloc[0]:.2f}% (날짜: {dgs10_data.index[0].date()})")
        
        # DGS2 데이터 수집 테스트
        print("\n[DGS2] 미국 2년 국채 금리 수집 중...")
        dgs2_data = collector.fetch_indicator("DGS2", start_date, end_date)
        print(f"  수집된 데이터 포인트: {len(dgs2_data)}개")
        if len(dgs2_data) > 0:
            print(f"  최신 값: {dgs2_data.iloc[-1]:.2f}% (날짜: {dgs2_data.index[-1].date()})")
        
        return True
        
    except Exception as e:
        print(f"❌ 데이터 수집 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_quant_signals():
    """정량 시그널 계산 테스트 (DB 없이 메모리에서 계산)"""
    print("\n" + "=" * 50)
    print("정량 시그널 계산 테스트")
    print("=" * 50)
    print("⚠️  주의: DB 저장 없이 메모리에서만 계산합니다")
    
    try:
        collector = get_fred_collector()
        
        # 최근 데이터 수집 (메모리에서만)
        print("\n[데이터 수집] 최근 90일 데이터 수집 중...")
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        
        dgs10_data = collector.fetch_indicator("DGS10", start_date, end_date)
        dgs2_data = collector.fetch_indicator("DGS2", start_date, end_date)
        fedfunds_data = collector.fetch_indicator("FEDFUNDS", start_date, end_date)
        cpi_data = collector.fetch_indicator("CPIAUCSL", start_date=end_date - timedelta(days=365), end_date=end_date)
        pce_data = collector.fetch_indicator("PCEPI", start_date=end_date - timedelta(days=365), end_date=end_date)
        
        print(f"  DGS10: {len(dgs10_data)}개 데이터 포인트")
        print(f"  DGS2: {len(dgs2_data)}개 데이터 포인트")
        print(f"  FEDFUNDS: {len(fedfunds_data)}개 데이터 포인트")
        print(f"  CPI: {len(cpi_data)}개 데이터 포인트")
        print(f"  PCE: {len(pce_data)}개 데이터 포인트")
        
        # 장단기 금리차 계산
        print("\n[장단기 금리차] 계산 중...")
        if len(dgs10_data) > 0 and len(dgs2_data) > 0:
            latest_dgs10 = dgs10_data.iloc[-1]
            latest_dgs2 = dgs2_data.iloc[-1]
            spread = latest_dgs10 - latest_dgs2
            print(f"  장단기 금리차: {spread:.2f}% (DGS10: {latest_dgs10:.2f}%, DGS2: {latest_dgs2:.2f}%)")
        else:
            print("  데이터 부족")
        
        # 실질 금리 계산
        print("\n[실질 금리] 계산 중...")
        if len(dgs10_data) > 0 and len(cpi_data) >= 2:
            latest_dgs10 = dgs10_data.iloc[-1]
            cpi_values = cpi_data.sort_index()
            latest_cpi = cpi_values.iloc[-1]
            prev_cpi = cpi_values.iloc[-2] if len(cpi_values) >= 2 else cpi_values.iloc[0]
            cpi_inflation_rate = ((latest_cpi / prev_cpi) - 1) * 12 * 100
            real_rate = latest_dgs10 - cpi_inflation_rate
            print(f"  실질 금리: {real_rate:.2f}% (명목 금리: {latest_dgs10:.2f}%, CPI 증가율: {cpi_inflation_rate:.2f}%)")
        else:
            print("  데이터 부족")
        
        # 테일러 준칙 계산
        print("\n[테일러 준칙] 계산 중...")
        if len(fedfunds_data) > 0 and len(pce_data) >= 2:
            current_fedfunds = fedfunds_data.iloc[-1]
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
            print(f"  테일러 준칙 신호: {signal:.2f}% (목표 금리: {target_rate:.2f}%, 현재 금리: {current_fedfunds:.2f}%)")
        else:
            print("  데이터 부족")
        
        return True
        
    except Exception as e:
        print(f"❌ 정량 시그널 계산 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("FRED API 모듈 테스트 시작\n")
    
    # 1. 연결 테스트
    connection_ok = test_fred_connection()
    if not connection_ok:
        print("\n❌ 연결 테스트 실패. FRED_API_KEY 환경변수를 확인하세요.")
        sys.exit(1)
    
    # 2. 데이터 수집 테스트
    collection_ok = test_data_collection()
    if not collection_ok:
        print("\n⚠️  데이터 수집 테스트 실패")
    
    # 3. 정량 시그널 계산 테스트
    signals_ok = test_quant_signals()
    if not signals_ok:
        print("\n⚠️  정량 시그널 계산 테스트 실패")
    
    print("\n" + "=" * 50)
    if connection_ok and collection_ok and signals_ok:
        print("✅ 모든 테스트 통과!")
        sys.exit(0)
    else:
        print("⚠️  일부 테스트 실패")
        sys.exit(1)

