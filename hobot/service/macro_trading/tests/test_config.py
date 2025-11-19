"""
설정 파일 로더 테스트 스크립트
"""
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from service.macro_trading.config.config_loader import get_config, reload_config, ConfigLoader

def test_config_loading():
    """설정 파일 로드 테스트"""
    print("=" * 50)
    print("설정 파일 로드 테스트")
    print("=" * 50)
    
    try:
        config = get_config()
        print("✅ 설정 파일 로드 성공!")
        print()
        
        print("리밸런싱 설정:")
        print(f"  - 임계값: {config.rebalancing.threshold}%")
        print(f"  - 실행 시간: {config.rebalancing.execution_time}")
        print(f"  - 최소 거래 금액: {config.rebalancing.min_trade_amount:,}원")
        print(f"  - 여유 자금 비율: {config.rebalancing.cash_reserve_ratio * 100}%")
        print()
        
        print("LLM 설정:")
        print(f"  - 모델: {config.llm.model}")
        print(f"  - Temperature: {config.llm.temperature}")
        print(f"  - Max Tokens: {config.llm.max_tokens}")
        print()
        
        print("스케줄 설정:")
        print(f"  - 계좌 조회: {config.schedules.account_check}")
        print(f"  - LLM 분석: {config.schedules.llm_analysis}")
        print(f"  - 리밸런싱: {config.schedules.rebalancing}")
        print()
        
        print("ETF 매핑:")
        for asset_class, mapping in config.etf_mapping.items():
            print(f"  - {asset_class}:")
            for i, ticker in enumerate(mapping.tickers):
                print(f"    * {mapping.names[i]} ({ticker}): {mapping.weights[i] * 100:.1f}%")
        print()
        
        print("안전장치 설정:")
        print(f"  - 일일 최대 손실: {config.safety.max_daily_loss_percent}%")
        print(f"  - 월간 최대 손실: {config.safety.max_monthly_loss_percent}%")
        print(f"  - 수동 승인 필요: {config.safety.manual_approval_required}")
        print(f"  - 드라이런 모드: {config.safety.dry_run_mode}")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ 설정 파일 로드 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_config_loading()
    sys.exit(0 if success else 1)

