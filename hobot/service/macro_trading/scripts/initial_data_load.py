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

from service.macro_trading.collectors.fred_collector import get_fred_collector, FRED_INDICATORS
from service.macro_trading.collectors.news_collector import get_news_collector


def initial_data_load(years: int = 5, fill_missing_only: bool = False):
    """
    초기 데이터 적재 함수
    
    Args:
        years: 수집할 과거 데이터 기간 (년, 기본값: 5년)
        fill_missing_only: True이면 DGS10, DGS2의 누락된 날짜만 보간하여 채움
    
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
        if fill_missing_only:
            logger.info("모드: DGS10, DGS2 누락 날짜 보간만 수행")
        logger.info("")
        
        # 누락 날짜 보간만 수행하는 경우
        if fill_missing_only:
            results = {}
            for indicator_code in ["DGS10", "DGS2"]:
                try:
                    logger.info(f"{indicator_code} 누락 날짜 보간 시작...")
                    
                    # 기존 데이터 조회
                    existing_data = collector.get_latest_data(indicator_code, days=years * 365)
                    
                    if len(existing_data) == 0:
                        logger.warning(f"{indicator_code} 기존 데이터가 없습니다. 전체 수집을 먼저 실행하세요.")
                        results[indicator_code] = 0
                        continue
                    
                    # 보간 적용
                    filled_data = collector.fill_missing_dates(
                        existing_data,
                        start_date=start_date,
                        end_date=end_date,
                        method='linear'
                    )
                    
                    # 보간된 데이터만 저장 (기존 데이터는 skip_existing=True로 건너뜀)
                    indicator_info = FRED_INDICATORS.get(indicator_code, {})
                    saved_count = collector.save_to_db(
                        indicator_code,
                        filled_data,
                        indicator_info.get("name", indicator_code),
                        indicator_info.get("unit", ""),
                        fill_missing=False,  # 이미 보간된 데이터이므로 다시 보간하지 않음
                        fill_start_date=None,
                        fill_end_date=None
                    )
                    
                    results[indicator_code] = saved_count
                    logger.info(f"{indicator_code} 보간 완료: {saved_count}개 데이터 추가")
                    
                except Exception as e:
                    logger.error(f"{indicator_code} 보간 실패: {e}", exc_info=True)
                    results[indicator_code] = 0
            
            return results
        
        # 모든 지표 수집 (초기 적재 시 rate limit 준수를 위해 딜레이 적용)
        # 초기 적재는 대량 데이터이므로 약간 더 긴 딜레이 사용 (0.6초)
        # DGS10, DGS2는 자동으로 보간이 적용됨
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


def initial_news_load(hours: int = 24, use_selenium: bool = False):
    """
    초기 뉴스 적재 함수
    
    Args:
        hours: 수집할 시간 범위 (기본값: 24시간)
        use_selenium: Selenium 사용 여부 (JavaScript 렌더링 필요 시)
    
    Returns:
        Tuple[int, int]: (저장된 개수, 건너뛴 개수)
    """
    logger.info("=" * 80)
    logger.info("경제 뉴스 초기 적재 시작")
    logger.info("=" * 80)
    logger.info(f"수집 기간: 최근 {hours}시간")
    if use_selenium:
        logger.info("모드: Selenium 사용 (JavaScript 렌더링)")
    logger.info("")
    
    try:
        collector = get_news_collector()
        
        # 24시간 이내의 뉴스 수집 및 저장
        saved, skipped = collector.collect_recent_news(hours=hours, use_selenium=use_selenium)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("경제 뉴스 초기 적재 완료")
        logger.info("=" * 80)
        logger.info(f"  - 저장된 뉴스: {saved:,}개")
        logger.info(f"  - 건너뛴 뉴스: {skipped:,}개")
        logger.info("=" * 80)
        
        return saved, skipped
        
    except Exception as e:
        logger.error(f"초기 뉴스 적재 중 오류 발생: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FRED 데이터 및 뉴스 초기 적재 스크립트")
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="수집할 과거 데이터 기간 (년, 기본값: 5년)"
    )
    parser.add_argument(
        "--fill-missing-only",
        action="store_true",
        help="DGS10, DGS2의 누락된 날짜만 보간하여 채움 (기존 데이터가 있는 경우)"
    )
    parser.add_argument(
        "--skip-fred",
        action="store_true",
        help="FRED 데이터 수집 건너뛰기 (뉴스만 수집)"
    )
    parser.add_argument(
        "--skip-news",
        action="store_true",
        help="뉴스 수집 건너뛰기 (FRED 데이터만 수집)"
    )
    parser.add_argument(
        "--news-hours",
        type=int,
        default=24,
        help="뉴스 수집 시간 범위 (시간, 기본값: 24시간)"
    )
    parser.add_argument(
        "--use-selenium",
        action="store_true",
        help="뉴스 수집 시 Selenium 사용 (JavaScript 렌더링 필요 시)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("FRED 데이터 및 뉴스 초기 적재 스크립트")
    print("=" * 80)
    
    if not args.skip_fred:
        if args.fill_missing_only:
            print("FRED 모드: 누락 날짜 보간만 수행 (DGS10, DGS2)")
        else:
            print(f"FRED 수집 기간: 최근 {args.years}년")
    else:
        print("FRED 데이터 수집: 건너뜀")
    
    if not args.skip_news:
        print(f"뉴스 수집 기간: 최근 {args.news_hours}시간")
        if args.use_selenium:
            print("뉴스 수집 모드: Selenium 사용")
    else:
        print("뉴스 수집: 건너뜀")
    
    print("=" * 80 + "\n")
    
    try:
        # FRED 데이터 수집
        fred_results = {}
        if not args.skip_fred:
            try:
                fred_results = initial_data_load(years=args.years, fill_missing_only=args.fill_missing_only)
            except Exception as e:
                logger.error(f"FRED 데이터 수집 실패: {e}", exc_info=True)
                print(f"\n⚠️  FRED 데이터 수집 실패: {e}")
                print("  뉴스 수집은 계속 진행합니다...\n")
        
        # 뉴스 수집
        news_saved = 0
        news_skipped = 0
        if not args.skip_news:
            try:
                news_saved, news_skipped = initial_news_load(hours=args.news_hours, use_selenium=args.use_selenium)
            except Exception as e:
                logger.error(f"뉴스 수집 실패: {e}", exc_info=True)
                print(f"\n⚠️  뉴스 수집 실패: {e}")
        
        # 결과 요약
        print("\n" + "=" * 80)
        print("초기 적재 완료 요약")
        print("=" * 80)
        
        if not args.skip_fred:
            if fred_results:
                total_saved = sum(fred_results.values())
                print(f"FRED 데이터: {total_saved:,}개 레코드 저장")
            else:
                print("FRED 데이터: 수집 실패 또는 건너뜀")
        
        if not args.skip_news:
            print(f"경제 뉴스: {news_saved:,}개 저장, {news_skipped:,}개 건너뜀")
        
        print("=" * 80)
        
        if (not args.skip_fred and fred_results) or (not args.skip_news and news_saved > 0):
            print("\n✅ 초기 데이터 적재가 완료되었습니다!")
            print("\n다음 단계:")
            if not args.skip_fred:
                print("  1. 서버를 시작하면 매일 09:00에 자동으로 최신 FRED 데이터가 수집됩니다.")
            if not args.skip_news:
                print("  2. 서버를 시작하면 매 1시간마다 자동으로 최신 뉴스가 수집됩니다.")
            print("  3. 정량 시그널 계산이 정상적으로 작동하는지 확인하세요.")
        else:
            print("\n❌ 초기 데이터 적재에 실패했습니다.")
            if not args.skip_fred:
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

