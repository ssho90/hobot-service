"""
FRED 데이터 수집 및 뉴스 수집 자동 스케줄러 모듈
"""
import schedule
import time
import threading
from datetime import date, timedelta
from typing import Optional
import logging
from functools import wraps

from service.macro_trading.collectors.fred_collector import get_fred_collector
from service.macro_trading.collectors.news_collector import get_news_collector
from service.macro_trading.config.config_loader import get_config
from service.macro_trading.config.config_loader import get_config
from service.macro_trading.ai_strategist import run_ai_analysis
from service.macro_trading.account_service import save_daily_account_snapshot

logger = logging.getLogger(__name__)

# 스케줄러 시작 여부를 추적하는 전역 변수
_scheduler_started = False
_scheduler_lock = threading.Lock()

# AI 분석 실행 중 여부를 추적하는 전역 변수 (동시 실행 방지)
_ai_analysis_running = False
_ai_analysis_lock = threading.Lock()


def retry_on_failure(max_retries: int = 3, delay: int = 60):
    """
    재시도 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        delay: 재시도 간격 (초)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"{func.__name__} 실패 (시도 {attempt + 1}/{max_retries}): {e}. "
                            f"{delay}초 후 재시도합니다."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} 최종 실패 (시도 {attempt + 1}/{max_retries}): {e}"
                        )
            
            # 모든 재시도 실패 시 예외 발생
            raise last_exception
        
        return wrapper
    return decorator


@retry_on_failure(max_retries=3, delay=60)
def collect_all_fred_data(request_delay: Optional[float] = None):
    """
    모든 FRED 지표 데이터를 수집하고 DB에 저장합니다.
    
    Returns:
        Dict[str, int]: 지표별 저장된 레코드 수
    """
    try:
        logger.info("=" * 60)
        logger.info("FRED 데이터 수집 시작")
        logger.info("=" * 60)
        
        collector = get_fred_collector()
        
        # 최근 1년 데이터 수집 (또는 마지막 수집일 이후 데이터)
        end_date = date.today()
        start_date = end_date - timedelta(days=365)
        
        logger.info(f"수집 기간: {start_date} ~ {end_date}")
        
        # 모든 지표 수집 (rate limit 준수를 위해 딜레이 적용)
        # request_delay가 None이면 자동으로 rate limit 기준으로 계산됨
        results = collector.collect_all_indicators(
            start_date=start_date,
            end_date=end_date,
            skip_existing=True,
            request_delay=request_delay
        )
        
        # 결과 요약
        total_saved = sum(results.values())
        successful = sum(1 for v in results.values() if v > 0)
        failed = sum(1 for v in results.values() if v == 0)
        
        logger.info("=" * 60)
        logger.info("FRED 데이터 수집 완료")
        logger.info(f"  - 총 저장된 레코드: {total_saved}개")
        logger.info(f"  - 성공한 지표: {successful}개")
        logger.info(f"  - 실패한 지표: {failed}개")
        logger.info("=" * 60)
        
        # 지표별 상세 결과
        for indicator_code, saved_count in results.items():
            if saved_count > 0:
                logger.info(f"  ✓ {indicator_code}: {saved_count}개 저장")
            else:
                logger.warning(f"  ✗ {indicator_code}: 수집 실패 또는 데이터 없음")
        
        # DGS10, DGS2의 누락된 날짜 보간 처리
        logger.info("")
        logger.info("DGS10, DGS2 누락 날짜 보간 처리 시작...")
        for indicator_code in ["DGS10", "DGS2"]:
            try:
                # 기존 데이터 조회 (최근 1년)
                existing_data = collector.get_latest_data(indicator_code, days=365)
                
                if len(existing_data) == 0:
                    logger.debug(f"{indicator_code}: 기존 데이터가 없어 보간을 건너뜁니다.")
                    continue
                
                # 보간 적용
                filled_data = collector.fill_missing_dates(
                    existing_data,
                    start_date=start_date,
                    end_date=end_date,
                    method='linear'
                )
                
                # 보간된 데이터만 저장 (기존 데이터는 skip_existing=True로 건너뜀)
                from service.macro_trading.collectors.fred_collector import FRED_INDICATORS
                indicator_info = FRED_INDICATORS.get(indicator_code, {})
                
                interpolated_count = collector.save_to_db(
                    indicator_code,
                    filled_data,
                    indicator_info.get("name", indicator_code),
                    indicator_info.get("unit", ""),
                    fill_missing=False,  # 이미 보간된 데이터이므로 다시 보간하지 않음
                    fill_start_date=None,
                    fill_end_date=None
                )
                
                if interpolated_count > 0:
                    logger.info(f"  ✓ {indicator_code}: {interpolated_count}개 보간 데이터 추가")
                else:
                    logger.debug(f"  - {indicator_code}: 누락된 날짜 없음 (이미 완전함)")
                    
            except Exception as e:
                # 예외 발생 시 상세 정보는 debug 레벨로, 요약만 warning으로
                logger.warning(f"{indicator_code} 보간 처리 중 오류: {type(e).__name__}: {str(e)}")
                logger.debug(f"{indicator_code} 보간 처리 상세 오류:", exc_info=True)
                continue
        
        logger.info("=" * 60)
        
        return results
        
    except Exception as e:
        logger.error(f"FRED 데이터 수집 중 오류 발생: {e}", exc_info=True)
        raise


@retry_on_failure(max_retries=3, delay=60)
def collect_recent_news():
    """
    TradingEconomics 스트림에서 최근 2시간 이내의 뉴스를 수집하고 DB에 저장합니다.
    
    Returns:
        Tuple[int, int]: (저장된 개수, 건너뛴 개수)
    """
    try:
        logger.info("=" * 60)
        logger.info("경제 뉴스 수집 시작")
        logger.info("=" * 60)
        
        collector = get_news_collector()
        
        # 2시간 이내의 뉴스 수집
        saved, skipped = collector.collect_recent_news(hours=2)
        
        logger.info("=" * 60)
        logger.info("경제 뉴스 수집 완료")
        logger.info(f"  - 저장된 뉴스: {saved}개")
        logger.info(f"  - 건너뛴 뉴스: {skipped}개")
        logger.info("=" * 60)
        
        return saved, skipped
        
    except Exception as e:
        logger.error(f"뉴스 수집 중 오류 발생: {e}", exc_info=True)
        raise


def run_threaded(job_func):
    """
    작업을 별도 스레드에서 실행하는 래퍼 함수
    스케줄러의 블로킹을 방지합니다.
    """
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


def setup_fred_scheduler():
    """
    FRED 데이터 수집 스케줄을 설정합니다.
    
    설정 파일에서 스케줄 시간을 읽어와서 등록합니다.
    """
    try:
        config = get_config()
        schedule_times = config.schedules.fred_data_collection
        
        if not schedule_times:
            logger.warning("FRED 데이터 수집 스케줄이 설정되지 않았습니다.")
            return
        
        # 기존 'fred_data_collection' 태그가 있는 스케줄 제거
        # schedule 라이브러리는 태그로 필터링하여 제거하는 기능이 없으므로,
        # 모든 스케줄을 클리어하고 다시 등록하는 방식 사용
        # (다른 스케줄이 있다면 영향을 받을 수 있음)
        # 대안: 태그를 사용하지 않고 직접 관리하거나, 첫 실행 시에만 등록
        
        # 각 시간에 스케줄 등록
        registered_count = 0
        for time_str in schedule_times:
            try:
                hour, minute = time_str.split(':')
                schedule.every().day.at(f"{hour}:{minute}").do(run_threaded, collect_all_fred_data).tag('fred_data_collection')
                logger.info(f"FRED 데이터 수집 스케줄 등록: 매일 {time_str} KST")
                registered_count += 1
            except Exception as e:
                logger.error(f"스케줄 등록 실패 ({time_str}): {e}")
        
        logger.info(f"총 {registered_count}개의 FRED 데이터 수집 스케줄이 등록되었습니다.")
        
    except Exception as e:
        logger.error(f"FRED 스케줄 설정 실패: {e}", exc_info=True)
        raise


def run_scheduler():
    """
    스케줄러를 실행합니다. (무한 루프)
    이 함수는 별도 스레드에서 실행되어야 합니다.
    모든 등록된 스케줄(FRED, 뉴스 등)을 실행합니다.
    """
    thread_name = threading.current_thread().name
    logger.info(f"스케줄러 시작: {thread_name}")
    
    # 등록된 스케줄 확인
    jobs = schedule.get_jobs()
    logger.info(f"등록된 스케줄: {len(jobs)}개")
    for job in jobs:
        logger.info(f"  - {job}")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크
        except Exception as e:
            logger.error(f"스케줄러 실행 중 오류: {e}", exc_info=True)
            time.sleep(60)


def setup_news_scheduler():
    """
    뉴스 수집 스케줄을 설정합니다.
    1시간마다 실행되도록 등록합니다.
    """
    try:
        # 1시간마다 실행
        schedule.every().hour.do(run_threaded, collect_recent_news).tag('news_collection')
        logger.info("뉴스 수집 스케줄 등록: 매 1시간마다 실행")
        
    except Exception as e:
        logger.error(f"뉴스 스케줄 설정 실패: {e}", exc_info=True)
        raise


@retry_on_failure(max_retries=3, delay=60)
def run_ai_strategy_analysis():
    """
    AI 전략 분석을 실행합니다.
    매일 08:30에 실행되도록 스케줄에 등록됩니다.
    
    동시 실행 방지: 이미 실행 중인 경우 건너뜁니다.
    """
    global _ai_analysis_running
    
    # 동시 실행 방지
    with _ai_analysis_lock:
        if _ai_analysis_running:
            logger.warning("AI 전략 분석이 이미 실행 중입니다. 중복 실행을 방지합니다.")
            return False
        
        _ai_analysis_running = True
    
    try:
        logger.info("AI 전략 분석 실행 시작")
        success = run_ai_analysis()
        if success:
            logger.info("AI 전략 분석 완료")
        else:
            logger.error("AI 전략 분석 실패")
        return success
    except Exception as e:
        logger.error(f"AI 전략 분석 중 오류 발생: {e}", exc_info=True)
        raise
    finally:
        # 실행 완료 후 플래그 해제
        with _ai_analysis_lock:
            _ai_analysis_running = False


def setup_ai_analysis_scheduler():
    """
    AI 전략 분석 스케줄을 설정합니다.
    매일 08:30에 실행되도록 등록합니다.
    """
    try:
        # 기존 'ai_analysis' 태그가 있는 스케줄 제거 (중복 등록 방지)
        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if 'ai_analysis' in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 AI 분석 스케줄 제거: {job}")
        
        # 매일 08:30에 실행
        schedule.every().day.at("08:30").do(run_threaded, run_ai_strategy_analysis).tag('ai_analysis')
        logger.info("AI 전략 분석 스케줄 등록: 매일 08:30 KST")
        
    except Exception as e:
        logger.error(f"AI 전략 분석 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_account_snapshot_scheduler():
    """
    계좌 상태 스냅샷 스케줄을 설정합니다.
    매일 15:30(KST)에 실행되도록 등록합니다.
    """
    try:
        # 기존 'account_snapshot' 태그가 있는 스케줄 제거
        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if 'account_snapshot' in job.tags:
                schedule.cancel_job(job)
                logger.debug(f"기존 계좌 스냅샷 스케줄 제거: {job}")
        
        # 매일 15:30 실행
        schedule.every().day.at("15:30").do(run_threaded, save_daily_account_snapshot).tag('account_snapshot')
        logger.info("계좌 스냅샷 스케줄 등록: 매일 15:30 KST")
        
    except Exception as e:
        logger.error(f"계좌 스냅샷 스케줄 설정 실패: {e}", exc_info=True)
        raise


def start_fred_scheduler_thread():
    """
    FRED 데이터 수집 스케줄러를 별도 스레드에서 시작합니다.
    
    Returns:
        threading.Thread: 스케줄러 스레드
    """
    # 스케줄 설정
    setup_fred_scheduler()
    
    # 스케줄러 스레드 생성 및 시작
    scheduler_thread = threading.Thread(
        target=run_scheduler,
        name="FREDDataCollectionScheduler",
        daemon=True
    )
    scheduler_thread.start()
    
    logger.info("FRED 데이터 수집 스케줄러 스레드가 시작되었습니다.")
    
    return scheduler_thread


def start_news_scheduler_thread():
    """
    뉴스 수집 스케줄러를 별도 스레드에서 시작합니다.
    
    Returns:
        threading.Thread: 스케줄러 스레드
    """
    # 스케줄 설정
    setup_news_scheduler()
    
    # 스케줄러 스레드 생성 및 시작
    scheduler_thread = threading.Thread(
        target=run_scheduler,
        name="NewsCollectionScheduler",
        daemon=True
    )
    scheduler_thread.start()
    
    logger.info("뉴스 수집 스케줄러 스레드가 시작되었습니다.")
    
    return scheduler_thread


def start_all_schedulers():
    """
    모든 스케줄러를 시작합니다.
    
    주의: schedule 라이브러리는 전역 상태를 사용하므로,
    모든 스케줄을 하나의 스레드에서 실행하는 것이 더 효율적입니다.
    
    중복 호출 방지: 이미 시작된 경우 다시 시작하지 않습니다.
    
    Returns:
        List[threading.Thread]: 스케줄러 스레드 리스트
    """
    global _scheduler_started
    
    with _scheduler_lock:
        if _scheduler_started:
            logger.warning("스케줄러가 이미 시작되었습니다. 중복 시작을 방지합니다.")
            return []
        
        _scheduler_started = True
    
    threads = []
    
    # 먼저 모든 스케줄을 설정
    try:
        setup_fred_scheduler()
        logger.info("FRED 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"FRED 스케줄 설정 실패: {e}")
    
    try:
        setup_news_scheduler()
        logger.info("뉴스 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"뉴스 스케줄 설정 실패: {e}")
    
    try:
        setup_ai_analysis_scheduler()
        logger.info("AI 전략 분석 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"AI 전략 분석 스케줄 설정 실패: {e}")
    
    try:
        setup_account_snapshot_scheduler()
        logger.info("계좌 스냅샷 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"계좌 스냅샷 스케줄 설정 실패: {e}")
    
    # 하나의 통합 스케줄러 스레드에서 모든 스케줄 실행
    try:
        scheduler_thread = threading.Thread(
            target=run_scheduler,
            name="UnifiedScheduler",
            daemon=True
        )
        scheduler_thread.start()
        threads.append(scheduler_thread)
        logger.info("통합 스케줄러 스레드가 시작되었습니다.")
    except Exception as e:
        logger.error(f"스케줄러 스레드 시작 실패: {e}")
    
    return threads


if __name__ == "__main__":
    # 테스트용: 직접 실행 시 즉시 수집 실행
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("FRED 데이터 수집 테스트 실행...")
    try:
        results = collect_all_fred_data()
        print("\n수집 결과:")
        for indicator, count in results.items():
            print(f"  {indicator}: {count}개")
    except Exception as e:
        print(f"오류 발생: {e}")
