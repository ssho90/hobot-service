"""
DFII10 (실질 금리) 데이터 초기 적재 스크립트

이 스크립트는 DFII10 데이터를 1년치 수집하여 DB에 저장합니다.
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

from service.macro_trading.collectors.fred_collector import get_fred_collector, FRED_INDICATORS


def load_dfii10_data(years: int = 1):
    """
    DFII10 데이터 수집 및 저장
    
    Args:
        years: 수집할 과거 데이터 기간 (년, 기본값: 1년)
    
    Returns:
        int: 저장된 레코드 수
    """
    logger.info("=" * 80)
    logger.info("DFII10 (실질 금리) 데이터 초기 적재 시작")
    logger.info("=" * 80)
    
    try:
        collector = get_fred_collector()
        
        # 연결 테스트
        if not collector.test_connection():
            logger.error("FRED API 연결 실패. 환경변수 FRED_API_KEY를 확인하세요.")
            return 0
        
        # 수집 기간 설정
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)
        
        logger.info(f"수집 기간: {start_date} ~ {end_date} ({years}년)")
        logger.info("")
        
        # DFII10 지표 정보 확인
        indicator_info = FRED_INDICATORS.get("DFII10")
        if not indicator_info:
            logger.error("DFII10 지표 정보를 찾을 수 없습니다. FRED_INDICATORS에 DFII10이 정의되어 있는지 확인하세요.")
            return 0
        
        logger.info(f"지표 코드: DFII10")
        logger.info(f"지표 이름: {indicator_info['name']}")
        logger.info(f"단위: {indicator_info['unit']}")
        logger.info(f"주기: {indicator_info['frequency']}")
        logger.info("")
        
        # DFII10 데이터 수집
        logger.info("DFII10 데이터 수집 중...")
        data = collector.fetch_indicator(
            "DFII10",
            start_date=start_date,
            end_date=end_date,
            use_rate_limit=True
        )
        
        if len(data) == 0:
            logger.warning("DFII10 데이터가 없습니다")
            return 0
        
        logger.info(f"수집된 데이터: {len(data)}개 데이터 포인트")
        logger.info("")
        
        # DB 저장 (누락된 날짜 보간 포함)
        logger.info("DB에 저장 중...")
        saved_count = collector.save_to_db(
            "DFII10",
            data,
            indicator_info["name"],
            indicator_info["unit"],
            fill_missing=True,  # 누락된 날짜 보간 적용
            fill_start_date=start_date,
            fill_end_date=end_date
        )
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("DFII10 데이터 초기 적재 완료")
        logger.info("=" * 80)
        logger.info(f"  - 저장된 레코드: {saved_count:,}개")
        logger.info("=" * 80)
        
        return saved_count
        
    except Exception as e:
        logger.error(f"DFII10 데이터 적재 중 오류 발생: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DFII10 (실질 금리) 데이터 초기 적재 스크립트")
    parser.add_argument(
        "--years",
        type=int,
        default=1,
        help="수집할 과거 데이터 기간 (년, 기본값: 1년)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("DFII10 (실질 금리) 데이터 초기 적재 스크립트")
    print("=" * 80)
    print(f"수집 기간: 최근 {args.years}년")
    print("=" * 80 + "\n")
    
    try:
        saved_count = load_dfii10_data(years=args.years)
        
        if saved_count > 0:
            print(f"\n✅ DFII10 데이터 {saved_count:,}개가 성공적으로 저장되었습니다!")
        else:
            print("\n❌ DFII10 데이터 수집에 실패했습니다.")
            print("  - FRED_API_KEY 환경변수를 확인하세요.")
            print("  - 데이터베이스 연결을 확인하세요.")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

