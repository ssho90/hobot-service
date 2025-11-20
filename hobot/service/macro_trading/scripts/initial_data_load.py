"""
FRED 데이터 초기 적재 스크립트

이 스크립트는 시스템 최초 실행 시 과거 데이터를 한 번에 수집하여 DB에 저장합니다.
"""
import sys
import os
from pathlib import Path
from datetime import date, timedelta
import logging

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from service.macro_trading.collectors.fred_collector import get_fred_collector


def initial_data_load(years: int = 5):
    """
    초기 데이터 적재 함수
    
    Args:
        years: 수집할 과거 데이터 기간 (년, 기본값: 5년)
    
    Returns:
        Dict[str, int]: 지표별 저장된 레코드 수
    """
    logger.info("=" * 80)
    logger.info("FRED 데이터 초기 적재 시작")
    logger.info("=" * 80)
    
    try:
        collector = get_fred_collector()
        
        # 연결 테스트
        if not collector.test_connection():
            logger.error("FRED API 연결 실패. 환경변수 FRED_API_KEY를 확인하세요.")
            return {}
        
        # 수집 기간 설정
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)
        
        logger.info(f"수집 기간: {start_date} ~ {end_date} ({years}년)")
        logger.info("")
        
        # 모든 지표 수집 (초기 적재 시 rate limit 준수를 위해 딜레이 적용)
        # 초기 적재는 대량 데이터이므로 약간 더 긴 딜레이 사용 (0.6초)
        results = collector.collect_all_indicators(
            start_date=start_date,
            end_date=end_date,
            skip_existing=True,  # 기존 데이터는 건너뛰기
            request_delay=0.6  # 초기 적재 시 약간 더 긴 딜레이
        )
        
        # 결과 요약
        total_saved = sum(results.values())
        successful = sum(1 for v in results.values() if v > 0)
        failed = sum(1 for v in results.values() if v == 0)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("초기 데이터 적재 완료")
        logger.info("=" * 80)
        logger.info(f"  - 총 저장된 레코드: {total_saved:,}개")
        logger.info(f"  - 성공한 지표: {successful}개")
        logger.info(f"  - 실패한 지표: {failed}개")
        logger.info("")
        logger.info("지표별 상세 결과:")
        logger.info("-" * 80)
        
        # 지표별 상세 결과
        for indicator_code, saved_count in sorted(results.items()):
            if saved_count > 0:
                logger.info(f"  ✓ {indicator_code:20s}: {saved_count:6,}개 저장")
            else:
                logger.warning(f"  ✗ {indicator_code:20s}: 수집 실패 또는 데이터 없음")
        
        logger.info("=" * 80)
        
        # 중요 지표 확인
        critical_indicators = ["DGS10", "DGS2"]
        logger.info("")
        logger.info("중요 지표 데이터 확인:")
        logger.info("-" * 80)
        
        for indicator_code in critical_indicators:
            saved_count = results.get(indicator_code, 0)
            if saved_count > 0:
                # 최소 250일 데이터 확인
                latest_data = collector.get_latest_data(indicator_code, days=250)
                if len(latest_data) >= 250:
                    logger.info(f"  ✓ {indicator_code}: {saved_count:,}개 저장, 최근 250일 데이터 있음 (정상)")
                else:
                    logger.warning(
                        f"  ⚠ {indicator_code}: {saved_count:,}개 저장, "
                        f"하지만 최근 250일 데이터 부족 ({len(latest_data)}일)"
                    )
            else:
                logger.error(f"  ✗ {indicator_code}: 데이터 수집 실패")
        
        logger.info("=" * 80)
        
        return results
        
    except Exception as e:
        logger.error(f"초기 데이터 적재 중 오류 발생: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FRED 데이터 초기 적재 스크립트")
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="수집할 과거 데이터 기간 (년, 기본값: 5년)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("FRED 데이터 초기 적재 스크립트")
    print("=" * 80)
    print(f"수집 기간: 최근 {args.years}년")
    print("=" * 80 + "\n")
    
    try:
        results = initial_data_load(years=args.years)
        
        if results:
            print("\n✅ 초기 데이터 적재가 완료되었습니다!")
            print("\n다음 단계:")
            print("  1. 서버를 시작하면 매일 09:00에 자동으로 최신 데이터가 수집됩니다.")
            print("  2. 정량 시그널 계산이 정상적으로 작동하는지 확인하세요.")
        else:
            print("\n❌ 초기 데이터 적재에 실패했습니다.")
            print("  - FRED_API_KEY 환경변수를 확인하세요.")
            print("  - 데이터베이스 연결을 확인하세요.")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 오류 발생: {e}")
        sys.exit(1)

