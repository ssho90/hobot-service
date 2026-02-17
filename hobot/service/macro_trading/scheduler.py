"""
FRED 데이터 수집 및 뉴스 수집 자동 스케줄러 모듈
"""
import json
import schedule
import time
import threading
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
import logging
from functools import wraps

from service.database.db import get_db_connection
from service.macro_trading.collectors.fred_collector import get_fred_collector
from service.macro_trading.collectors.news_collector import get_news_collector
from service.macro_trading.collectors.kr_macro_collector import (
    KR_MACRO_INDICATORS,
    KR_REAL_ESTATE_SUPPLEMENTAL_INDICATORS,
    US_KR_COMPARISON_INDICATORS,
    get_kr_macro_collector,
)
from service.macro_trading.collectors.kr_real_estate_collector import (
    DEFAULT_MOLIT_REGION_SCOPE,
    get_kr_real_estate_collector,
)
from service.macro_trading.collectors.kr_corporate_collector import (
    DEFAULT_ALLOW_BASELINE_FALLBACK,
    DEFAULT_DART_BATCH_SIZE,
    DEFAULT_DART_CORPCODE_MAX_AGE_DAYS,
    DEFAULT_DART_DISCLOSURE_PAGE_COUNT,
    DEFAULT_EARNINGS_EXPECTATION_LOOKBACK_YEARS,
    DEFAULT_REQUIRE_EXPECTATION_FEED,
    get_kr_corporate_collector,
)
from service.macro_trading.collectors.us_corporate_collector import (
    DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT,
    DEFAULT_US_FINANCIALS_MAX_SYMBOL_COUNT,
    DEFAULT_US_EARNINGS_LOOKAHEAD_DAYS,
    DEFAULT_US_EARNINGS_LOOKBACK_DAYS,
    DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
    US_TOP50_DEFAULT_MARKET,
    US_TOP50_DEFAULT_SOURCE_URL,
    get_us_corporate_collector,
)
from service.macro_trading.collectors.corporate_tier_collector import (
    DEFAULT_TIER_KR_LIMIT,
    DEFAULT_TIER_US_LIMIT,
    get_corporate_tier_collector,
)
from service.macro_trading.collectors.corporate_entity_collector import (
    DEFAULT_ENTITY_COUNTRIES,
    DEFAULT_ENTITY_SYNC_SOURCE,
    DEFAULT_ENTITY_TIER_LEVEL,
    get_corporate_entity_collector,
)
from service.macro_trading.config.config_loader import get_config
from service.macro_trading.ai_strategist import run_ai_analysis
from service.macro_trading.account_service import save_daily_account_snapshot
from service.graph.scheduler import run_phase_c_weekly_jobs
from service.graph.news_loader import sync_news_with_extraction_backlog

logger = logging.getLogger(__name__)

# 스케줄러 시작 여부를 추적하는 전역 변수
_scheduler_started = False
_scheduler_lock = threading.Lock()

# AI 분석 실행 중 여부를 추적하는 전역 변수 (동시 실행 방지)
_ai_analysis_running = False
_ai_analysis_lock = threading.Lock()

KR_TOP50_EARNINGS_WATCH_JOB_CODE = "KR_TOP50_EARNINGS_WATCH"
US_TOP50_EARNINGS_WATCH_JOB_CODE = "US_TOP50_EARNINGS_WATCH"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ensure_macro_collection_run_reports_table() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS macro_collection_run_reports (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            report_date DATE NOT NULL,
            job_code VARCHAR(64) NOT NULL,
            run_count INT NOT NULL DEFAULT 0,
            success_run_count INT NOT NULL DEFAULT 0,
            failed_run_count INT NOT NULL DEFAULT 0,
            success_count INT NOT NULL DEFAULT 0,
            failure_count INT NOT NULL DEFAULT 0,
            last_success_rate_pct DECIMAL(7,2) NULL,
            last_status VARCHAR(16) NOT NULL DEFAULT 'healthy',
            last_error TEXT NULL,
            last_run_started_at DATETIME NULL,
            last_run_finished_at DATETIME NULL,
            details_json JSON NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_report_date_job (report_date, job_code),
            INDEX idx_job_code_report_date (job_code, report_date),
            INDEX idx_last_status_date (last_status, report_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)


def _record_collection_run_report(
    *,
    job_code: str,
    success_count: int,
    failure_count: int,
    run_success: bool,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> None:
    try:
        _ensure_macro_collection_run_reports_table()
        resolved_started_at = started_at or datetime.now()
        resolved_finished_at = finished_at or datetime.now()
        report_date = resolved_finished_at.date()
        resolved_success_count = max(_safe_int(success_count), 0)
        resolved_failure_count = max(_safe_int(failure_count), 0)
        resolved_run_success = bool(run_success)
        total_count = resolved_success_count + resolved_failure_count
        if total_count > 0:
            last_success_rate_pct: Optional[float] = round(
                (resolved_success_count * 100.0) / total_count,
                2,
            )
        else:
            last_success_rate_pct = 100.0 if resolved_run_success else 0.0

        if not resolved_run_success:
            last_status = "failed"
        elif resolved_failure_count > 0:
            last_status = "warning"
        else:
            last_status = "healthy"

        details_json = None
        if isinstance(details, dict) and details:
            details_json = json.dumps(details, ensure_ascii=False, default=str)

        query = """
            INSERT INTO macro_collection_run_reports (
                report_date,
                job_code,
                run_count,
                success_run_count,
                failed_run_count,
                success_count,
                failure_count,
                last_success_rate_pct,
                last_status,
                last_error,
                last_run_started_at,
                last_run_finished_at,
                details_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                run_count = run_count + VALUES(run_count),
                success_run_count = success_run_count + VALUES(success_run_count),
                failed_run_count = failed_run_count + VALUES(failed_run_count),
                success_count = success_count + VALUES(success_count),
                failure_count = failure_count + VALUES(failure_count),
                last_success_rate_pct = VALUES(last_success_rate_pct),
                last_status = VALUES(last_status),
                last_error = VALUES(last_error),
                last_run_started_at = VALUES(last_run_started_at),
                last_run_finished_at = VALUES(last_run_finished_at),
                details_json = VALUES(details_json),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = (
            report_date,
            str(job_code or "").strip(),
            1,
            1 if resolved_run_success else 0,
            0 if resolved_run_success else 1,
            resolved_success_count,
            resolved_failure_count,
            last_success_rate_pct,
            last_status,
            (str(error_message).strip()[:1000] if error_message else None),
            resolved_started_at,
            resolved_finished_at,
            details_json,
        )
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, payload)
    except Exception as exc:
        logger.warning("수집 실행 리포트 기록 실패(job_code=%s): %s", job_code, exc)


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


@retry_on_failure(max_retries=2, delay=90)
def collect_kr_macro_data(
    indicator_codes: Optional[list[str]] = None,
    days: int = 365,
):
    """
    KR macro/liquidity 지표를 수집하고 canonical row로 저장합니다.
    """
    logger.info("=" * 60)
    logger.info("KR 거시 지표 수집 시작")
    logger.info("=" * 60)
    collector = get_kr_macro_collector()
    end_date = date.today()
    start_date = end_date - timedelta(days=max(int(days), 1))
    result = collector.collect_indicators(
        indicator_codes=indicator_codes or list(KR_MACRO_INDICATORS.keys()),
        start_date=start_date,
        end_date=end_date,
        as_of_date=end_date,
    )
    logger.info(
        "KR 거시 지표 수집 완료: success=%s failed=%s",
        result.get("total_success"),
        result.get("total_failed"),
    )
    return result


@retry_on_failure(max_retries=2, delay=90)
def collect_kr_real_estate_supplemental_data(days: int = 3650) -> Dict[str, Any]:
    """
    KR 부동산 보조지표(REB/KOSIS)를 수집하고 canonical row로 저장합니다.
    기본값은 10년 백필(3650일)입니다.
    """
    return collect_kr_macro_data(
        indicator_codes=list(KR_REAL_ESTATE_SUPPLEMENTAL_INDICATORS),
        days=days,
    )


@retry_on_failure(max_retries=2, delay=90)
def collect_kr_corporate_fundamentals(
    bsns_year: Optional[str] = None,
    reprt_code: str = "11011",
    corp_codes: Optional[list[str]] = None,
    stock_codes: Optional[list[str]] = None,
    max_corp_count: int = 50,
    refresh_corp_codes: bool = True,
    corp_code_max_age_days: int = DEFAULT_DART_CORPCODE_MAX_AGE_DAYS,
    batch_size: int = DEFAULT_DART_BATCH_SIZE,
) -> Dict[str, Any]:
    """
    KR 기업 펀더멘털(Open DART 주요계정) 수집/적재.
    기본은 사업보고서(11011) + 대상 50개 기업 수집.
    """
    resolved_year = bsns_year or str(date.today().year - 1)
    collector = get_kr_corporate_collector()
    logger.info("=" * 60)
    logger.info(
        "KR 기업 펀더멘털 수집 시작: bsns_year=%s reprt_code=%s max_corp_count=%s",
        resolved_year,
        reprt_code,
        max_corp_count,
    )
    logger.info("=" * 60)
    result = collector.collect_major_accounts(
        bsns_year=str(resolved_year),
        reprt_code=reprt_code,
        corp_codes=corp_codes,
        stock_codes=stock_codes,
        max_corp_count=max_corp_count,
        refresh_corp_codes=refresh_corp_codes,
        corp_code_max_age_days=corp_code_max_age_days,
        batch_size=batch_size,
        as_of_date=date.today(),
    )
    logger.info("KR 기업 펀더멘털 수집 완료: %s", result)
    return result


@retry_on_failure(max_retries=2, delay=90)
def capture_kr_top50_snapshot(
    snapshot_date: Optional[date] = None,
    market: str = "KOSPI",
    source_url: str = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
    limit: int = 50,
) -> Dict[str, Any]:
    """
    KR Top50 스냅샷을 테이블(`kr_top50_universe_snapshot`)에 저장합니다.
    같은 snapshot_date + market에 대해서는 UPSERT로 갱신됩니다.
    """
    resolved_snapshot_date = snapshot_date or date.today()
    collector = get_kr_corporate_collector()
    logger.info("=" * 60)
    logger.info(
        "KR Top50 스냅샷 수집 시작: snapshot_date=%s market=%s limit=%s",
        resolved_snapshot_date.isoformat(),
        market,
        limit,
    )
    logger.info("=" * 60)
    result = collector.capture_top50_snapshot_from_naver(
        snapshot_date=resolved_snapshot_date,
        market=market,
        source_url=source_url,
        limit=limit,
    )
    logger.info("KR Top50 스냅샷 수집 완료: %s", result)
    return result


@retry_on_failure(max_retries=2, delay=90)
def run_kr_top50_monthly_snapshot_job(
    target_day_of_month: int = 1,
    market: str = "KOSPI",
    source_url: str = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
    limit: int = 50,
    run_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    KR Top50 월간 스냅샷 배치:
    - 지정한 day-of-month에만 스냅샷을 생성
    - 직전 스냅샷과 diff(편입/편출/순위변동) 요약을 생성
    """
    resolved_day = max(min(int(target_day_of_month), 31), 1)
    today = run_date or date.today()
    resolved_market = str(market or "KOSPI").strip().upper() or "KOSPI"
    resolved_limit = max(int(limit), 1)

    if today.day != resolved_day:
        result = {
            "status": "skipped",
            "reason": f"today.day({today.day}) != target_day_of_month({resolved_day})",
            "run_date": today.isoformat(),
            "target_day_of_month": resolved_day,
            "market": resolved_market,
        }
        logger.info("KR Top50 월간 스냅샷 배치 스킵: %s", result["reason"])
        return result

    capture_result = capture_kr_top50_snapshot(
        snapshot_date=today,
        market=resolved_market,
        source_url=source_url,
        limit=resolved_limit,
    )
    collector = get_kr_corporate_collector()
    diff_result = collector.build_top50_snapshot_diff(
        market=resolved_market,
        latest_snapshot_date=today,
        limit=resolved_limit,
    )
    result = {
        "status": "completed",
        "run_date": today.isoformat(),
        "target_day_of_month": resolved_day,
        "market": resolved_market,
        "capture": capture_result,
        "diff": diff_result,
    }
    logger.info(
        "KR Top50 월간 스냅샷 완료: date=%s market=%s saved_rows=%s added=%s removed=%s rank_changed=%s",
        today.isoformat(),
        resolved_market,
        (capture_result or {}).get("saved_rows"),
        (diff_result or {}).get("added_count"),
        (diff_result or {}).get("removed_count"),
        (diff_result or {}).get("rank_changed_count"),
    )
    return result


def run_kr_top50_monthly_snapshot_job_from_env() -> Dict[str, Any]:
    target_day_of_month = int(os.getenv("KR_TOP50_SNAPSHOT_DAY_OF_MONTH", "1"))
    market = os.getenv("KR_TOP50_SNAPSHOT_MARKET", "KOSPI")
    source_url = os.getenv(
        "KR_TOP50_SNAPSHOT_SOURCE_URL",
        "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
    )
    limit = int(os.getenv("KR_TOP50_SNAPSHOT_LIMIT", "50"))
    return run_kr_top50_monthly_snapshot_job(
        target_day_of_month=target_day_of_month,
        market=market,
        source_url=source_url,
        limit=limit,
    )


@retry_on_failure(max_retries=2, delay=90)
def capture_us_top50_snapshot(
    snapshot_date: Optional[date] = None,
    market: str = US_TOP50_DEFAULT_MARKET,
    source_url: str = US_TOP50_DEFAULT_SOURCE_URL,
    max_symbol_count: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    symbols: Optional[list[str]] = None,
    rebalance_candidates: Optional[list[str]] = None,
    rank_by_market_cap: bool = True,
    refresh_sec_mapping: bool = True,
    sec_mapping_max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
) -> Dict[str, Any]:
    """
    US Top50 스냅샷을 테이블(`us_top50_universe_snapshot`)에 저장합니다.
    같은 snapshot_date + market에 대해서는 UPSERT로 갱신됩니다.
    """
    resolved_snapshot_date = snapshot_date or date.today()
    collector = get_us_corporate_collector()
    logger.info("=" * 60)
    logger.info(
        "US Top50 스냅샷 수집 시작: snapshot_date=%s market=%s max_symbol_count=%s candidates=%s",
        resolved_snapshot_date.isoformat(),
        market,
        max_symbol_count,
        len(rebalance_candidates or symbols or []),
    )
    logger.info("=" * 60)
    result = collector.capture_top50_snapshot(
        snapshot_date=resolved_snapshot_date,
        symbols=symbols,
        rebalance_candidates=rebalance_candidates,
        max_symbol_count=max_symbol_count,
        market=market,
        source_url=source_url,
        rank_by_market_cap=rank_by_market_cap,
        refresh_sec_mapping=refresh_sec_mapping,
        sec_mapping_max_age_days=sec_mapping_max_age_days,
    )
    logger.info("US Top50 스냅샷 수집 완료: %s", result)
    return result


@retry_on_failure(max_retries=2, delay=90)
def run_us_top50_monthly_snapshot_job(
    target_day_of_month: int = 1,
    market: str = US_TOP50_DEFAULT_MARKET,
    source_url: str = US_TOP50_DEFAULT_SOURCE_URL,
    max_symbol_count: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    symbols: Optional[list[str]] = None,
    rebalance_candidates: Optional[list[str]] = None,
    rank_by_market_cap: bool = True,
    refresh_sec_mapping: bool = True,
    sec_mapping_max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
    run_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    US Top50 월간 스냅샷 배치:
    - 지정한 day-of-month에만 스냅샷을 생성
    - 직전 스냅샷과 diff(편입/편출/순위변동) 요약을 생성
    """
    resolved_day = max(min(int(target_day_of_month), 31), 1)
    today = run_date or date.today()
    resolved_market = str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET
    resolved_limit = max(int(max_symbol_count), 1)

    if today.day != resolved_day:
        result = {
            "status": "skipped",
            "reason": f"today.day({today.day}) != target_day_of_month({resolved_day})",
            "run_date": today.isoformat(),
            "target_day_of_month": resolved_day,
            "market": resolved_market,
        }
        logger.info("US Top50 월간 스냅샷 배치 스킵: %s", result["reason"])
        return result

    capture_result = capture_us_top50_snapshot(
        snapshot_date=today,
        market=resolved_market,
        source_url=source_url,
        max_symbol_count=resolved_limit,
        symbols=symbols,
        rebalance_candidates=rebalance_candidates,
        rank_by_market_cap=rank_by_market_cap,
        refresh_sec_mapping=refresh_sec_mapping,
        sec_mapping_max_age_days=sec_mapping_max_age_days,
    )
    collector = get_us_corporate_collector()
    diff_result = collector.build_top50_snapshot_diff(
        market=resolved_market,
        latest_snapshot_date=today,
        limit=resolved_limit,
    )
    result = {
        "status": "completed",
        "run_date": today.isoformat(),
        "target_day_of_month": resolved_day,
        "market": resolved_market,
        "capture": capture_result,
        "diff": diff_result,
    }
    logger.info(
        "US Top50 월간 스냅샷 완료: date=%s market=%s saved_rows=%s added=%s removed=%s rank_changed=%s",
        today.isoformat(),
        resolved_market,
        (capture_result or {}).get("saved_rows"),
        (diff_result or {}).get("added_count"),
        (diff_result or {}).get("removed_count"),
        (diff_result or {}).get("rank_changed_count"),
    )
    return result


def run_us_top50_monthly_snapshot_job_from_env() -> Dict[str, Any]:
    target_day_of_month = int(os.getenv("US_TOP50_SNAPSHOT_DAY_OF_MONTH", "1"))
    market = os.getenv("US_TOP50_SNAPSHOT_MARKET", US_TOP50_DEFAULT_MARKET)
    source_url = os.getenv("US_TOP50_SNAPSHOT_SOURCE_URL", US_TOP50_DEFAULT_SOURCE_URL)
    max_symbol_count = int(
        os.getenv("US_TOP50_SNAPSHOT_LIMIT", str(DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT))
    )
    symbols_csv = str(os.getenv("US_TOP50_FIXED_SYMBOLS", "") or "").strip()
    symbols = [value.strip() for value in symbols_csv.split(",") if value.strip()] or None
    candidate_csv = str(os.getenv("US_TOP50_REBALANCE_CANDIDATES", "") or "").strip()
    rebalance_candidates = [value.strip() for value in candidate_csv.split(",") if value.strip()] or None
    rank_by_market_cap = _truthy_env(
        os.getenv("US_TOP50_SNAPSHOT_RANK_BY_MARKET_CAP", "1"),
        default=True,
    )
    refresh_sec_mapping = _truthy_env(
        os.getenv("US_TOP50_SNAPSHOT_REFRESH_SEC_MAPPING", "1"),
        default=True,
    )
    sec_mapping_max_age_days = int(
        os.getenv("US_SEC_MAPPING_MAX_AGE_DAYS", str(DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS))
    )
    return run_us_top50_monthly_snapshot_job(
        target_day_of_month=target_day_of_month,
        market=market,
        source_url=source_url,
        max_symbol_count=max_symbol_count,
        symbols=symbols,
        rebalance_candidates=rebalance_candidates,
        rank_by_market_cap=rank_by_market_cap,
        refresh_sec_mapping=refresh_sec_mapping,
        sec_mapping_max_age_days=sec_mapping_max_age_days,
    )


@retry_on_failure(max_retries=2, delay=90)
def validate_kr_top50_corp_code_mapping(
    report_date: Optional[date] = None,
    market: str = "KOSPI",
    top_limit: int = 50,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    KR Top50 스냅샷과 DART corp_code 매핑 일관성을 검증합니다.
    """
    collector = get_kr_corporate_collector()
    resolved_report_date = report_date or date.today()
    logger.info("=" * 60)
    logger.info(
        "KR corp_code 매핑 검증 시작: report_date=%s market=%s top_limit=%s",
        resolved_report_date.isoformat(),
        market,
        top_limit,
    )
    logger.info("=" * 60)
    result = collector.validate_top50_corp_code_mapping(
        report_date=resolved_report_date,
        market=market,
        top_limit=top_limit,
        persist=persist,
    )
    logger.info(
        "KR corp_code 매핑 검증 완료: status=%s snapshot_rows=%s missing_corp=%s missing_in_dart=%s mismatches=%s duplicates=%s",
        result.get("status"),
        result.get("snapshot_row_count"),
        result.get("snapshot_missing_corp_count"),
        result.get("snapshot_missing_in_dart_count"),
        result.get("snapshot_corp_code_mismatch_count"),
        result.get("dart_duplicate_stock_count"),
    )
    return result


def validate_kr_top50_corp_code_mapping_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 KR corp_code 매핑 검증 실행 래퍼.
    """
    market = str(os.getenv("KR_CORP_MAPPING_VALIDATION_MARKET", "KOSPI") or "KOSPI").strip().upper()
    top_limit = int(os.getenv("KR_CORP_MAPPING_VALIDATION_TOP_LIMIT", "50"))
    persist = _truthy_env(os.getenv("KR_CORP_MAPPING_VALIDATION_PERSIST", "1"), default=True)
    return validate_kr_top50_corp_code_mapping(
        report_date=date.today(),
        market=market,
        top_limit=top_limit,
        persist=persist,
    )


@retry_on_failure(max_retries=2, delay=90)
def validate_kr_dart_disclosure_dplus1_sla(
    report_date: Optional[date] = None,
    market: str = "KOSPI",
    top_limit: int = 50,
    lookback_days: int = 30,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    KR DART 실적 공시 대비 재무 반영 지연(D+1) SLA 준수 여부를 점검합니다.
    """
    collector = get_kr_corporate_collector()
    resolved_report_date = report_date or date.today()
    logger.info("=" * 60)
    logger.info(
        "KR DART D+1 SLA 점검 시작: report_date=%s market=%s top_limit=%s lookback_days=%s",
        resolved_report_date.isoformat(),
        market,
        top_limit,
        lookback_days,
    )
    logger.info("=" * 60)
    result = collector.validate_dart_disclosure_dplus1_sla(
        report_date=resolved_report_date,
        market=market,
        top_limit=top_limit,
        lookback_days=lookback_days,
        persist=persist,
    )
    logger.info(
        "KR DART D+1 SLA 점검 완료: status=%s checked=%s met=%s violated=%s missing=%s late=%s",
        result.get("status"),
        result.get("checked_event_count"),
        result.get("met_sla_count"),
        result.get("violated_sla_count"),
        result.get("missing_financial_count"),
        result.get("late_financial_count"),
    )
    return result


def validate_kr_dart_disclosure_dplus1_sla_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 KR DART D+1 SLA 점검 실행 래퍼.
    """
    market = str(os.getenv("KR_DART_DPLUS1_SLA_MARKET", "KOSPI") or "KOSPI").strip().upper()
    top_limit = int(os.getenv("KR_DART_DPLUS1_SLA_TOP_LIMIT", "50"))
    lookback_days = int(os.getenv("KR_DART_DPLUS1_SLA_LOOKBACK_DAYS", "30"))
    persist = _truthy_env(os.getenv("KR_DART_DPLUS1_SLA_PERSIST", "1"), default=True)
    return validate_kr_dart_disclosure_dplus1_sla(
        report_date=date.today(),
        market=market,
        top_limit=top_limit,
        lookback_days=lookback_days,
        persist=persist,
    )


@retry_on_failure(max_retries=2, delay=90)
def collect_kr_corporate_disclosure_events(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    corp_codes: Optional[list[str]] = None,
    stock_codes: Optional[list[str]] = None,
    expectation_rows: Optional[list[Dict[str, Any]]] = None,
    auto_expectations: bool = True,
    expectation_feed_url: Optional[str] = None,
    require_feed_expectations: bool = DEFAULT_REQUIRE_EXPECTATION_FEED,
    allow_baseline_fallback: bool = DEFAULT_ALLOW_BASELINE_FALLBACK,
    baseline_lookback_years: int = DEFAULT_EARNINGS_EXPECTATION_LOOKBACK_YEARS,
    max_corp_count: int = 50,
    refresh_corp_codes: bool = False,
    corp_code_max_age_days: int = DEFAULT_DART_CORPCODE_MAX_AGE_DAYS,
    page_count: int = DEFAULT_DART_DISCLOSURE_PAGE_COUNT,
    per_corp_max_pages: int = 3,
    only_earnings: bool = True,
) -> Dict[str, Any]:
    """
    KR 기업 공시 이벤트(Open DART list)를 수집하고,
    실적 이벤트에 대해서는 actual/expected/surprise 메타를 함께 저장합니다.
    """
    resolved_end_date = end_date or date.today()
    resolved_start_date = start_date or (resolved_end_date - timedelta(days=30))

    collector = get_kr_corporate_collector()
    logger.info("=" * 60)
    logger.info(
        "KR 기업 공시 이벤트 수집 시작: start=%s end=%s only_earnings=%s max_corp_count=%s",
        resolved_start_date.isoformat(),
        resolved_end_date.isoformat(),
        only_earnings,
        max_corp_count,
    )
    logger.info("=" * 60)
    result = collector.collect_disclosure_events(
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        corp_codes=corp_codes,
        stock_codes=stock_codes,
        expectation_rows=expectation_rows,
        auto_expectations=auto_expectations,
        expectation_feed_url=expectation_feed_url,
        require_feed_expectations=require_feed_expectations,
        allow_baseline_fallback=allow_baseline_fallback,
        baseline_lookback_years=baseline_lookback_years,
        max_corp_count=max_corp_count,
        refresh_corp_codes=refresh_corp_codes,
        corp_code_max_age_days=corp_code_max_age_days,
        page_count=page_count,
        per_corp_max_pages=per_corp_max_pages,
        only_earnings=only_earnings,
        as_of_date=date.today(),
    )
    logger.info(
        "KR 기업 공시 이벤트 수집 완료: normalized=%s inserted=%s updated=%s new_earnings=%s failed_requests=%s",
        result.get("normalized_rows"),
        result.get("inserted_rows"),
        result.get("updated_rows"),
        result.get("new_earnings_event_count"),
        result.get("failed_requests"),
    )
    return result


def _truthy_env(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _resolve_country_tier_symbols_with_grace(
    *,
    country_code: str,
    as_of_date: Optional[date] = None,
    lookback_days: int = 365,
    max_symbol_count: int = 150,
) -> list[str]:
    """
    Tier 이력 기반 grace window 심볼 목록을 조회합니다.
    조회 실패 시 빈 목록을 반환합니다.
    """
    try:
        tier_collector = get_corporate_tier_collector()
        return tier_collector.load_recent_country_symbols(
            country_code=country_code,
            as_of_date=as_of_date,
            tier_level=1,
            lookback_days=max(int(lookback_days), 1),
            max_symbol_count=max(int(max_symbol_count), 1),
        )
    except Exception as exc:
        logger.warning(
            "Tier grace 심볼 조회 실패(country=%s): %s",
            country_code,
            exc,
        )
        return []


def _resolve_kr_corp_codes_from_tier_with_grace(
    *,
    as_of_date: Optional[date] = None,
    lookback_days: int = 365,
    max_symbol_count: int = 150,
) -> list[str]:
    """
    KR Tier grace 심볼을 corp_code 목록으로 변환합니다.
    """
    symbols = _resolve_country_tier_symbols_with_grace(
        country_code="KR",
        as_of_date=as_of_date,
        lookback_days=lookback_days,
        max_symbol_count=max_symbol_count,
    )
    if not symbols:
        return []
    try:
        kr_collector = get_kr_corporate_collector()
        corp_codes = kr_collector.resolve_corp_codes_from_stock_codes(symbols)
        return [code for code in corp_codes if code]
    except Exception as exc:
        logger.warning("KR tier grace corp_code 변환 실패: %s", exc)
        return []


def _merge_symbol_universe(
    explicit_symbols: Optional[list[str]],
    grace_symbols: list[str],
    *,
    max_symbol_count: int,
) -> Optional[list[str]]:
    base = [value.strip().upper() for value in (explicit_symbols or []) if str(value or "").strip()]
    merged = list(dict.fromkeys(base + grace_symbols))
    if not merged:
        return None
    return merged[: max(int(max_symbol_count), 1)]


def _resolve_kr_top50_earnings_targets(
    events: list[Dict[str, Any]],
) -> Dict[tuple[str, str], list[str]]:
    """
    신규 실적 공시 이벤트 목록에서 (사업연도, reprt_code) -> corp_code 목록을 구성합니다.
    """
    collector = get_kr_corporate_collector()
    grouped: Dict[tuple[str, str], set[str]] = {}

    for event in events:
        corp_code = "".join(ch for ch in str(event.get("corp_code") or "") if ch.isdigit())
        period_year = str(event.get("period_year") or "").strip()
        fiscal_quarter_raw = event.get("fiscal_quarter")
        try:
            fiscal_quarter = int(fiscal_quarter_raw)
        except (TypeError, ValueError):
            fiscal_quarter = 0

        if len(corp_code) != 8:
            continue
        if len(period_year) != 4 or not period_year.isdigit():
            continue
        reprt_code = collector.quarter_to_reprt_code(fiscal_quarter)
        if not reprt_code:
            continue

        key = (period_year, reprt_code)
        grouped.setdefault(key, set()).add(corp_code)

    return {
        key: sorted(values)
        for key, values in grouped.items()
        if values
    }


@retry_on_failure(max_retries=2, delay=120)
def run_kr_top50_earnings_hotpath(
    lookback_days: int = 1,
    max_corp_count: int = 50,
    per_corp_max_pages: int = 3,
    immediate_fundamentals: bool = True,
    fundamentals_batch_size: int = DEFAULT_DART_BATCH_SIZE,
    use_grace_universe: bool = True,
    grace_lookback_days: int = 365,
    grace_max_symbol_count: int = 150,
) -> Dict[str, Any]:
    """
    Top50 실적 공시 감시 핫패스:
    1) 공시(실적 이벤트) 수집
    2) 신규 실적 이벤트 감지 시, 해당 기업/분기에 대해 펀더멘털 배치를 즉시 실행
    """
    resolved_lookback_days = max(int(lookback_days), 1)
    resolved_end_date = date.today()
    resolved_start_date = resolved_end_date - timedelta(days=resolved_lookback_days - 1)
    resolved_per_corp_pages = max(int(per_corp_max_pages), 1)
    resolved_max_corp_count = max(int(max_corp_count), 1)
    resolved_batch_size = max(int(fundamentals_batch_size), 1)
    resolved_grace_lookback_days = max(int(grace_lookback_days), 1)
    resolved_grace_max_symbol_count = max(int(grace_max_symbol_count), 1)
    grace_corp_codes: list[str] = []
    if use_grace_universe:
        grace_corp_codes = _resolve_kr_corp_codes_from_tier_with_grace(
            as_of_date=resolved_end_date,
            lookback_days=resolved_grace_lookback_days,
            max_symbol_count=resolved_grace_max_symbol_count,
        )

    logger.info("=" * 60)
    logger.info(
        "KR Top50 실적 감시 시작: lookback_days=%s max_corp_count=%s grace_codes=%s",
        resolved_lookback_days,
        resolved_max_corp_count,
        len(grace_corp_codes),
    )
    logger.info("=" * 60)

    disclosure_summary = collect_kr_corporate_disclosure_events(
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        corp_codes=grace_corp_codes or None,
        max_corp_count=len(grace_corp_codes) if grace_corp_codes else resolved_max_corp_count,
        refresh_corp_codes=False,
        per_corp_max_pages=resolved_per_corp_pages,
        only_earnings=True,
    )
    new_earnings_events = list(disclosure_summary.get("new_earnings_events") or [])
    grouped_targets = _resolve_kr_top50_earnings_targets(new_earnings_events)

    result: Dict[str, Any] = {
        "watch_window": {
            "start_date": resolved_start_date.isoformat(),
            "end_date": resolved_end_date.isoformat(),
            "lookback_days": resolved_lookback_days,
        },
        "disclosure": disclosure_summary,
        "new_earnings_event_count": len(new_earnings_events),
        "grace_universe_enabled": bool(use_grace_universe),
        "grace_corp_code_count": len(grace_corp_codes),
        "grace_lookback_days": resolved_grace_lookback_days if use_grace_universe else 0,
        "immediate_fundamentals_enabled": bool(immediate_fundamentals),
        "fundamentals_triggered": False,
        "fundamentals_trigger_groups": len(grouped_targets),
        "fundamentals_batches": [],
    }

    if not immediate_fundamentals:
        logger.info("KR Top50 실적 핫패스: 즉시 펀더멘털 배치 비활성화")
        return result

    if not grouped_targets:
        logger.info("KR Top50 실적 핫패스: 신규 실적 이벤트 없음 (즉시 배치 스킵)")
        return result

    fundamentals_batches: list[Dict[str, Any]] = []
    for (period_year, reprt_code), corp_codes in sorted(grouped_targets.items()):
        batch_result = collect_kr_corporate_fundamentals(
            bsns_year=period_year,
            reprt_code=reprt_code,
            corp_codes=corp_codes,
            max_corp_count=len(corp_codes),
            refresh_corp_codes=False,
            batch_size=resolved_batch_size,
        )
        fundamentals_batches.append(
            {
                "bsns_year": period_year,
                "reprt_code": reprt_code,
                "corp_count": len(corp_codes),
                "corp_codes": corp_codes,
                "result": batch_result,
            }
        )

    result["fundamentals_triggered"] = True
    result["fundamentals_batches"] = fundamentals_batches
    result["fundamentals_total_db_affected"] = sum(
        int((item.get("result") or {}).get("db_affected") or 0)
        for item in fundamentals_batches
    )
    logger.info(
        "KR Top50 실적 핫패스 완료: new_events=%s trigger_groups=%s",
        len(new_earnings_events),
        len(grouped_targets),
    )
    return result


def run_kr_top50_earnings_hotpath_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 KR Top50 실적 핫패스 실행 래퍼
    """
    started_at = datetime.now()
    lookback_days = int(os.getenv("KR_TOP50_EARNINGS_WATCH_LOOKBACK_DAYS", "1"))
    max_corp_count = int(os.getenv("KR_TOP50_EARNINGS_WATCH_MAX_CORP_COUNT", "50"))
    per_corp_max_pages = int(os.getenv("KR_TOP50_EARNINGS_WATCH_PER_CORP_MAX_PAGES", "3"))
    immediate_fundamentals = _truthy_env(
        os.getenv("KR_TOP50_EARNINGS_IMMEDIATE_FUNDAMENTALS", "1"),
        default=True,
    )
    fundamentals_batch_size = int(
        os.getenv("KR_TOP50_EARNINGS_FUNDAMENTALS_BATCH_SIZE", str(DEFAULT_DART_BATCH_SIZE))
    )
    use_grace_universe = _truthy_env(
        os.getenv("KR_TOP50_UNIVERSE_GRACE_ENABLED", "1"),
        default=True,
    )
    grace_lookback_days = int(os.getenv("KR_TOP50_UNIVERSE_GRACE_DAYS", "365"))
    grace_max_symbol_count = int(os.getenv("KR_TOP50_UNIVERSE_GRACE_MAX_SYMBOL_COUNT", "150"))
    try:
        result = run_kr_top50_earnings_hotpath(
            lookback_days=lookback_days,
            max_corp_count=max_corp_count,
            per_corp_max_pages=per_corp_max_pages,
            immediate_fundamentals=immediate_fundamentals,
            fundamentals_batch_size=fundamentals_batch_size,
            use_grace_universe=use_grace_universe,
            grace_lookback_days=grace_lookback_days,
            grace_max_symbol_count=grace_max_symbol_count,
        )
        disclosure = result.get("disclosure") or {}
        api_requests = max(_safe_int(disclosure.get("api_requests")), 0)
        failed_requests = max(_safe_int(disclosure.get("failed_requests")), 0)
        success_count = max(api_requests - failed_requests, 0)
        _record_collection_run_report(
            job_code=KR_TOP50_EARNINGS_WATCH_JOB_CODE,
            success_count=success_count,
            failure_count=failed_requests,
            run_success=True,
            started_at=started_at,
            finished_at=datetime.now(),
            details={
                "api_requests": api_requests,
                "failed_requests": failed_requests,
                "new_earnings_event_count": _safe_int(result.get("new_earnings_event_count")),
                "fundamentals_triggered": bool(result.get("fundamentals_triggered")),
                "fundamentals_trigger_groups": _safe_int(result.get("fundamentals_trigger_groups")),
            },
        )
        return result
    except Exception as exc:
        _record_collection_run_report(
            job_code=KR_TOP50_EARNINGS_WATCH_JOB_CODE,
            success_count=0,
            failure_count=1,
            run_success=False,
            started_at=started_at,
            finished_at=datetime.now(),
            details={"error_type": type(exc).__name__},
            error_message=str(exc),
        )
        raise


@retry_on_failure(max_retries=2, delay=120)
def run_us_top50_financials_hotpath(
    symbols: Optional[list[str]] = None,
    max_symbol_count: int = DEFAULT_US_FINANCIALS_MAX_SYMBOL_COUNT,
    refresh_sec_mapping: bool = True,
    sec_mapping_max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
    max_periods_per_statement: int = DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT,
    use_grace_universe: bool = True,
    grace_lookback_days: int = 365,
    grace_max_symbol_count: int = 150,
) -> Dict[str, Any]:
    """
    US Top50 재무제표 수집 핫패스.
    yfinance의 annual/quarterly 재무제표(손익/재무상태/현금흐름)를 canonical row로 적재합니다.
    """
    collector = get_us_corporate_collector()
    resolved_symbols = symbols
    resolved_max_symbol_count = max(int(max_symbol_count), 1)
    grace_symbols: list[str] = []
    if use_grace_universe:
        grace_symbols = _resolve_country_tier_symbols_with_grace(
            country_code="US",
            as_of_date=date.today(),
            lookback_days=max(int(grace_lookback_days), 1),
            max_symbol_count=max(int(grace_max_symbol_count), 1),
        )
        if grace_symbols:
            resolved_max_symbol_count = max(
                resolved_max_symbol_count,
                max(int(grace_max_symbol_count), 1),
            )
        resolved_symbols = _merge_symbol_universe(
            symbols,
            grace_symbols,
            max_symbol_count=resolved_max_symbol_count,
        )

    logger.info("=" * 60)
    logger.info(
        "US Top50 재무제표 수집 시작: max_symbol_count=%s effective_max_symbol_count=%s grace_symbols=%s max_periods=%s target_symbols=%s",
        max_symbol_count,
        resolved_max_symbol_count,
        len(grace_symbols),
        max_periods_per_statement,
        len(resolved_symbols or []),
    )
    logger.info("=" * 60)
    result = collector.collect_financials(
        symbols=resolved_symbols,
        max_symbol_count=resolved_max_symbol_count,
        refresh_sec_mapping=refresh_sec_mapping,
        sec_mapping_max_age_days=sec_mapping_max_age_days,
        max_periods_per_statement=max_periods_per_statement,
        as_of_date=date.today(),
    )
    result["grace_universe_enabled"] = bool(use_grace_universe)
    result["grace_symbol_count"] = len(grace_symbols)
    result["effective_max_symbol_count"] = resolved_max_symbol_count
    logger.info(
        "US Top50 재무제표 수집 완료: fetched=%s upserted=%s failed_symbols=%s",
        result.get("fetched_rows"),
        result.get("upserted_rows"),
        len(result.get("failed_symbols") or []),
    )
    return result


def run_us_top50_financials_hotpath_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 US Top50 재무제표 수집 실행 래퍼.
    """
    symbols_csv = str(os.getenv("US_TOP50_FIXED_SYMBOLS", "") or "").strip()
    symbols = [value.strip() for value in symbols_csv.split(",") if value.strip()] or None
    max_symbol_count = int(
        os.getenv(
            "US_TOP50_FINANCIALS_MAX_SYMBOL_COUNT",
            str(DEFAULT_US_FINANCIALS_MAX_SYMBOL_COUNT),
        )
    )
    refresh_sec_mapping = _truthy_env(
        os.getenv("US_SEC_MAPPING_REFRESH", "1"),
        default=True,
    )
    sec_mapping_max_age_days = int(
        os.getenv("US_SEC_MAPPING_MAX_AGE_DAYS", str(DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS))
    )
    max_periods_per_statement = int(
        os.getenv(
            "US_TOP50_FINANCIALS_MAX_PERIODS_PER_STATEMENT",
            str(DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT),
        )
    )
    use_grace_universe = _truthy_env(
        os.getenv("US_TOP50_UNIVERSE_GRACE_ENABLED", "1"),
        default=True,
    )
    grace_lookback_days = int(os.getenv("US_TOP50_UNIVERSE_GRACE_DAYS", "365"))
    grace_max_symbol_count = int(os.getenv("US_TOP50_UNIVERSE_GRACE_MAX_SYMBOL_COUNT", "150"))
    return run_us_top50_financials_hotpath(
        symbols=symbols,
        max_symbol_count=max_symbol_count,
        refresh_sec_mapping=refresh_sec_mapping,
        sec_mapping_max_age_days=sec_mapping_max_age_days,
        max_periods_per_statement=max_periods_per_statement,
        use_grace_universe=use_grace_universe,
        grace_lookback_days=grace_lookback_days,
        grace_max_symbol_count=grace_max_symbol_count,
    )


@retry_on_failure(max_retries=2, delay=120)
def run_us_top50_earnings_hotpath(
    symbols: Optional[list[str]] = None,
    max_symbol_count: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    refresh_sec_mapping: bool = True,
    sec_mapping_max_age_days: int = DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS,
    include_expected: bool = True,
    include_confirmed: bool = True,
    lookback_days: int = DEFAULT_US_EARNINGS_LOOKBACK_DAYS,
    lookahead_days: int = DEFAULT_US_EARNINGS_LOOKAHEAD_DAYS,
    use_grace_universe: bool = True,
    grace_lookback_days: int = 365,
    grace_max_symbol_count: int = 150,
) -> Dict[str, Any]:
    """
    US Top50 실적 감시 핫패스:
    - expected: yfinance earnings calendar
    - confirmed: SEC submissions(8-K/10-Q/10-K)
    """
    collector = get_us_corporate_collector()
    resolved_symbols = symbols
    resolved_max_symbol_count = max(int(max_symbol_count), 1)
    grace_symbols: list[str] = []
    if use_grace_universe:
        grace_symbols = _resolve_country_tier_symbols_with_grace(
            country_code="US",
            as_of_date=date.today(),
            lookback_days=max(int(grace_lookback_days), 1),
            max_symbol_count=max(int(grace_max_symbol_count), 1),
        )
        if grace_symbols:
            resolved_max_symbol_count = max(
                resolved_max_symbol_count,
                max(int(grace_max_symbol_count), 1),
            )
        resolved_symbols = _merge_symbol_universe(
            symbols,
            grace_symbols,
            max_symbol_count=resolved_max_symbol_count,
        )

    logger.info("=" * 60)
    logger.info(
        "US Top50 실적 감시 시작: max_symbol_count=%s effective_max_symbol_count=%s grace_symbols=%s include_expected=%s include_confirmed=%s target_symbols=%s",
        max_symbol_count,
        resolved_max_symbol_count,
        len(grace_symbols),
        include_expected,
        include_confirmed,
        len(resolved_symbols or []),
    )
    logger.info("=" * 60)
    result = collector.collect_earnings_events(
        symbols=resolved_symbols,
        max_symbol_count=resolved_max_symbol_count,
        refresh_sec_mapping=refresh_sec_mapping,
        sec_mapping_max_age_days=sec_mapping_max_age_days,
        include_expected=include_expected,
        include_confirmed=include_confirmed,
        lookback_days=lookback_days,
        lookahead_days=lookahead_days,
        as_of_date=date.today(),
    )
    result["grace_universe_enabled"] = bool(use_grace_universe)
    result["grace_symbol_count"] = len(grace_symbols)
    result["effective_max_symbol_count"] = resolved_max_symbol_count
    logger.info(
        "US Top50 실적 감시 완료: symbols=%s expected=%s confirmed=%s upserted=%s failed=%s",
        result.get("target_symbol_count"),
        result.get("expected_rows"),
        result.get("confirmed_rows"),
        result.get("upserted_rows"),
        len(result.get("failed_symbols") or []),
    )
    return result


def run_us_top50_earnings_hotpath_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 US Top50 실적 감시 실행 래퍼
    """
    started_at = datetime.now()
    symbols_csv = str(os.getenv("US_TOP50_FIXED_SYMBOLS", "") or "").strip()
    symbols = [value.strip() for value in symbols_csv.split(",") if value.strip()] or None
    max_symbol_count = int(
        os.getenv(
            "US_TOP50_EARNINGS_WATCH_MAX_SYMBOL_COUNT",
            str(DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT),
        )
    )
    refresh_sec_mapping = _truthy_env(
        os.getenv("US_SEC_MAPPING_REFRESH", "1"),
        default=True,
    )
    sec_mapping_max_age_days = int(
        os.getenv("US_SEC_MAPPING_MAX_AGE_DAYS", str(DEFAULT_US_SEC_MAPPING_MAX_AGE_DAYS))
    )
    include_expected = _truthy_env(
        os.getenv("US_TOP50_EARNINGS_INCLUDE_EXPECTED", "1"),
        default=True,
    )
    include_confirmed = _truthy_env(
        os.getenv("US_TOP50_EARNINGS_INCLUDE_CONFIRMED", "1"),
        default=True,
    )
    lookback_days = int(
        os.getenv("US_TOP50_EARNINGS_WATCH_LOOKBACK_DAYS", str(DEFAULT_US_EARNINGS_LOOKBACK_DAYS))
    )
    lookahead_days = int(
        os.getenv(
            "US_TOP50_EARNINGS_WATCH_LOOKAHEAD_DAYS",
            str(DEFAULT_US_EARNINGS_LOOKAHEAD_DAYS),
        )
    )
    use_grace_universe = _truthy_env(
        os.getenv("US_TOP50_UNIVERSE_GRACE_ENABLED", "1"),
        default=True,
    )
    grace_lookback_days = int(os.getenv("US_TOP50_UNIVERSE_GRACE_DAYS", "365"))
    grace_max_symbol_count = int(os.getenv("US_TOP50_UNIVERSE_GRACE_MAX_SYMBOL_COUNT", "150"))
    try:
        result = run_us_top50_earnings_hotpath(
            symbols=symbols,
            max_symbol_count=max_symbol_count,
            refresh_sec_mapping=refresh_sec_mapping,
            sec_mapping_max_age_days=sec_mapping_max_age_days,
            include_expected=include_expected,
            include_confirmed=include_confirmed,
            lookback_days=lookback_days,
            lookahead_days=lookahead_days,
            use_grace_universe=use_grace_universe,
            grace_lookback_days=grace_lookback_days,
            grace_max_symbol_count=grace_max_symbol_count,
        )
        failed_symbols = list(result.get("failed_symbols") or [])
        failed_count = len(failed_symbols)
        target_symbol_count = max(_safe_int(result.get("target_symbol_count")), 0)
        success_count = max(target_symbol_count - failed_count, 0)
        _record_collection_run_report(
            job_code=US_TOP50_EARNINGS_WATCH_JOB_CODE,
            success_count=success_count,
            failure_count=failed_count,
            run_success=True,
            started_at=started_at,
            finished_at=datetime.now(),
            details={
                "target_symbol_count": target_symbol_count,
                "failed_symbol_count": failed_count,
                "api_requests": _safe_int(result.get("api_requests")),
                "expected_rows": _safe_int(result.get("expected_rows")),
                "confirmed_rows": _safe_int(result.get("confirmed_rows")),
            },
        )
        return result
    except Exception as exc:
        _record_collection_run_report(
            job_code=US_TOP50_EARNINGS_WATCH_JOB_CODE,
            success_count=0,
            failure_count=1,
            run_success=False,
            started_at=started_at,
            finished_at=datetime.now(),
            details={"error_type": type(exc).__name__},
            error_message=str(exc),
        )
        raise


@retry_on_failure(max_retries=2, delay=120)
def sync_uskr_tier_state(
    as_of_date: Optional[date] = None,
    kr_market: str = "KOSPI",
    kr_limit: int = DEFAULT_TIER_KR_LIMIT,
    us_symbols: Optional[list[str]] = None,
    us_limit: int = DEFAULT_TIER_US_LIMIT,
) -> Dict[str, Any]:
    """
    US/KR Tier-1 상태를 동기화합니다.
    - KR: 최신 Top50 snapshot
    - US: 고정 Top50 symbol 라인업
    """
    collector = get_corporate_tier_collector()
    logger.info("=" * 60)
    logger.info(
        "US/KR Tier 상태 동기화 시작: as_of_date=%s kr_market=%s kr_limit=%s us_limit=%s",
        as_of_date.isoformat() if as_of_date else date.today().isoformat(),
        kr_market,
        kr_limit,
        us_limit,
    )
    logger.info("=" * 60)
    result = collector.sync_tier1_state(
        as_of_date=as_of_date,
        kr_market=kr_market,
        kr_limit=kr_limit,
        us_symbols=us_symbols,
        us_limit=us_limit,
    )
    logger.info(
        "US/KR Tier 상태 동기화 완료: kr=%s us=%s total_db_affected=%s",
        result.get("kr_source_count"),
        result.get("us_source_count"),
        result.get("db_affected_total"),
    )
    return result


def sync_uskr_tier_state_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 US/KR Tier 상태 동기화 실행 래퍼.
    """
    kr_market = str(os.getenv("USKR_TIER_STATE_KR_MARKET", "KOSPI") or "KOSPI").strip().upper()
    kr_limit = int(os.getenv("USKR_TIER_STATE_KR_LIMIT", str(DEFAULT_TIER_KR_LIMIT)))
    us_limit = int(os.getenv("USKR_TIER_STATE_US_LIMIT", str(DEFAULT_TIER_US_LIMIT)))
    symbols_csv = str(os.getenv("US_TOP50_FIXED_SYMBOLS", "") or "").strip()
    us_symbols = [value.strip() for value in symbols_csv.split(",") if value.strip()] or None
    return sync_uskr_tier_state(
        as_of_date=date.today(),
        kr_market=kr_market,
        kr_limit=kr_limit,
        us_symbols=us_symbols,
        us_limit=us_limit,
    )


@retry_on_failure(max_retries=2, delay=120)
def sync_uskr_corporate_entity_registry(
    as_of_date: Optional[date] = None,
    countries: Optional[list[str]] = None,
    tier_level: int = DEFAULT_ENTITY_TIER_LEVEL,
    source: str = DEFAULT_ENTITY_SYNC_SOURCE,
) -> Dict[str, Any]:
    """
    Tier-1 소스 기반 기업 canonical registry/alias를 동기화합니다.
    Company PK는 (country_code, symbol) 기준으로 유지합니다.
    """
    collector = get_corporate_entity_collector()
    resolved_countries = countries or list(DEFAULT_ENTITY_COUNTRIES)
    logger.info("=" * 60)
    logger.info(
        "US/KR 기업 레지스트리 동기화 시작: as_of_date=%s countries=%s tier_level=%s source=%s",
        as_of_date.isoformat() if as_of_date else "latest",
        resolved_countries,
        tier_level,
        source,
    )
    logger.info("=" * 60)
    result = collector.sync_from_tier1(
        as_of_date=as_of_date,
        countries=resolved_countries,
        tier_level=tier_level,
        source=source,
    )
    logger.info(
        "US/KR 기업 레지스트리 동기화 완료: source_rows=%s registry_upsert=%s alias_upsert=%s",
        result.get("source_row_count"),
        result.get("registry_upsert_affected"),
        result.get("alias_upsert_affected"),
    )
    return result


def sync_uskr_corporate_entity_registry_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 기업 canonical registry/alias 동기화 실행 래퍼.
    """
    countries_csv = str(os.getenv("USKR_ENTITY_REGISTRY_COUNTRIES", "KR,US") or "").strip()
    countries = [value.strip().upper() for value in countries_csv.split(",") if value.strip()]
    tier_level = int(os.getenv("USKR_ENTITY_REGISTRY_TIER_LEVEL", str(DEFAULT_ENTITY_TIER_LEVEL)))
    source = str(os.getenv("USKR_ENTITY_REGISTRY_SOURCE", DEFAULT_ENTITY_SYNC_SOURCE) or DEFAULT_ENTITY_SYNC_SOURCE).strip()
    return sync_uskr_corporate_entity_registry(
        as_of_date=date.today(),
        countries=countries or list(DEFAULT_ENTITY_COUNTRIES),
        tier_level=tier_level,
        source=source,
    )


@retry_on_failure(max_retries=2, delay=90)
def collect_uskr_comparison_data(days: int = 365) -> Dict[str, Any]:
    """
    US/KR 공통 비교 라인업을 수집합니다.
    - KR_USDKRW: KR macro collector
    - DGS2/DGS10: FRED collector
    """
    logger.info("=" * 60)
    logger.info("US/KR 비교 지표 수집 시작")
    logger.info("=" * 60)
    end_date = date.today()
    start_date = end_date - timedelta(days=max(int(days), 1))

    kr_result = collect_kr_macro_data(indicator_codes=["KR_USDKRW"], days=days)

    fred_result: Dict[str, int] = {}
    fred_collector = get_fred_collector()
    for code in ("DGS2", "DGS10"):
        try:
            series = fred_collector.fetch_indicator(code, start_date=start_date, end_date=end_date)
            if len(series) == 0:
                fred_result[code] = 0
                continue
            saved = fred_collector.save_to_db(
                code,
                series,
                indicator_name=code,
                unit="%",
                fill_missing=(code in {"DGS2", "DGS10"}),
                fill_start_date=start_date,
                fill_end_date=end_date,
            )
            fred_result[code] = int(saved)
        except Exception as exc:
            logger.warning("US 비교 지표 수집 실패(%s): %s", code, exc)
            fred_result[code] = 0

    summary = {
        "comparison_lineup": list(US_KR_COMPARISON_INDICATORS),
        "kr_macro": kr_result,
        "us_fred_saved_rows": fred_result,
    }
    logger.info("US/KR 비교 지표 수집 완료: %s", summary)
    return summary


@retry_on_failure(max_retries=2, delay=120)
def collect_kr_real_estate_data(
    start_ym: Optional[str] = None,
    end_ym: Optional[str] = None,
    scope: Optional[str] = None,
    lawd_codes: Optional[list[str]] = None,
    num_of_rows: int = 1000,
    max_pages: int = 100,
    progress_file: Optional[str] = None,
    progress_log_interval: int = 100,
) -> Dict[str, Any]:
    """
    KR 아파트 실거래(MOLIT) 수집/적재를 수행합니다.

    기본 범위:
    - 서울 전 지역
    - 경기 전 지역
    - 지방 주요 도시
    """
    collector = get_kr_real_estate_collector()
    today = date.today()
    resolved_end_ym = end_ym or today.strftime("%Y%m")
    if start_ym:
        resolved_start_ym = start_ym
    else:
        one_year_ago = (today - timedelta(days=365)).replace(day=1)
        resolved_start_ym = one_year_ago.strftime("%Y%m")

    resolved_scope = scope or DEFAULT_MOLIT_REGION_SCOPE
    logger.info("=" * 60)
    logger.info(
        "KR 부동산 수집 시작: start_ym=%s end_ym=%s scope=%s",
        resolved_start_ym,
        resolved_end_ym,
        resolved_scope,
    )
    logger.info("=" * 60)
    result = collector.collect_molit_apartment_trades(
        start_ym=resolved_start_ym,
        end_ym=resolved_end_ym,
        scope=resolved_scope,
        lawd_codes=lawd_codes,
        num_of_rows=num_of_rows,
        max_pages=max_pages,
        progress_file=progress_file,
        progress_log_interval=progress_log_interval,
    )
    logger.info("KR 부동산 수집 완료: %s", result)
    return result


@retry_on_failure(max_retries=2, delay=120)
def aggregate_kr_real_estate_monthly_summary(
    start_ym: str,
    end_ym: str,
    property_type: str = "apartment",
    transaction_type: str = "sale",
) -> Dict[str, Any]:
    """
    KR 실거래 row를 월×지역(5자리 LAWD_CD) 요약으로 집계합니다.
    """
    collector = get_kr_real_estate_collector()
    logger.info("=" * 60)
    logger.info(
        "KR 부동산 월별 집계 시작: start_ym=%s end_ym=%s type=%s/%s",
        start_ym,
        end_ym,
        property_type,
        transaction_type,
    )
    logger.info("=" * 60)
    result = collector.aggregate_monthly_region_summary(
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=property_type,
        transaction_type=transaction_type,
    )
    logger.info("KR 부동산 월별 집계 완료: %s", result)
    return result


@retry_on_failure(max_retries=2, delay=120)
def sync_kr_real_estate_summary_to_graph(
    start_ym: str,
    end_ym: str,
    property_type: str = "apartment",
    transaction_type: str = "sale",
) -> Dict[str, Any]:
    """
    RDB 월×지역 집계를 Neo4j Graph로 동기화합니다.
    """
    from service.graph.real_estate_loader import sync_kr_real_estate_monthly_summary

    logger.info("=" * 60)
    logger.info(
        "KR 부동산 Graph 동기화 시작: start_ym=%s end_ym=%s type=%s/%s",
        start_ym,
        end_ym,
        property_type,
        transaction_type,
    )
    logger.info("=" * 60)
    result = sync_kr_real_estate_monthly_summary(
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=property_type,
        transaction_type=transaction_type,
    )
    logger.info("KR 부동산 Graph 동기화 완료: %s", result)
    return result


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


@retry_on_failure(max_retries=2, delay=120)
def run_graph_news_extraction_sync():
    """
    Macro Graph 뉴스 동기화 + LLM 추출 적재를 실행합니다.
    미처리/실패(쿨다운 경과) 문서를 배치로 재처리하여 Event/Fact/Claim/Evidence/AFFECTS를 업데이트합니다.
    """
    logger.info("=" * 60)
    logger.info("Macro Graph 뉴스 추출 적재 시작")
    logger.info("=" * 60)

    sync_limit = int(os.getenv("GRAPH_NEWS_SYNC_LIMIT", "2000"))
    sync_days = int(os.getenv("GRAPH_NEWS_SYNC_DAYS", "30"))
    extraction_batch_size = int(os.getenv("GRAPH_NEWS_EXTRACTION_BATCH_SIZE", "200"))
    max_extraction_batches = int(os.getenv("GRAPH_NEWS_EXTRACTION_MAX_BATCHES", "10"))
    retry_failed_after_minutes = int(os.getenv("GRAPH_NEWS_RETRY_FAILED_AFTER_MINUTES", "180"))
    extraction_progress_log_interval = int(os.getenv("GRAPH_NEWS_EXTRACTION_PROGRESS_LOG_INTERVAL", "25"))

    result = sync_news_with_extraction_backlog(
        sync_limit=sync_limit,
        sync_days=sync_days,
        extraction_batch_size=extraction_batch_size,
        max_extraction_batches=max_extraction_batches,
        retry_failed_after_minutes=retry_failed_after_minutes,
        extraction_progress_log_interval=extraction_progress_log_interval,
    )
    sync_result = result.get("sync_result", {})
    extraction_result = result.get("extraction", {})
    logger.info(
        "Macro Graph 뉴스 추출 적재 완료: docs=%s, batches=%s, extracted=%s, failed=%s, skipped=%s, stop_reason=%s",
        sync_result.get("documents"),
        extraction_result.get("batches"),
        extraction_result.get("success_docs"),
        extraction_result.get("failed_docs"),
        extraction_result.get("skipped_docs"),
        extraction_result.get("stop_reason"),
    )
    return result


def setup_graph_news_extraction_scheduler():
    """
    Macro Graph 뉴스 추출 적재 스케줄을 설정합니다.
    매 2시간마다 실행되도록 등록합니다.
    """
    try:
        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "graph_news_extraction" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 Macro Graph 뉴스 추출 스케줄 제거: {job}")

        schedule.every(2).hours.do(
            run_threaded, run_graph_news_extraction_sync
        ).tag("graph_news_extraction")
        logger.info("Macro Graph 뉴스 추출 스케줄 등록: 매 2시간마다 실행")
    except Exception as e:
        logger.error(f"Macro Graph 뉴스 추출 스케줄 설정 실패: {e}", exc_info=True)
        raise


@retry_on_failure(max_retries=2, delay=120)
def run_phase_c_weekly_batch():
    """
    Phase C 배치를 실행합니다.
    Event impact / 가중치 재계산 / 상관 엣지 / Story 클러스터링을 수행합니다.
    """
    logger.info("=" * 60)
    logger.info("Phase C 주간 배치 시작")
    logger.info("=" * 60)
    result = run_phase_c_weekly_jobs()
    logger.info(
        "Phase C 배치 완료: corr=%s, leads=%s, stories=%s",
        result.get("correlation", {}).get("correlation_edges"),
        result.get("correlation", {}).get("lead_edges"),
        result.get("story_cluster", {}).get("stories_created"),
    )
    return result


def setup_phase_c_weekly_scheduler():
    """
    Phase C 주간 배치 스케줄을 설정합니다.
    매주 일요일 03:30(KST)에 실행되도록 등록합니다.
    """
    try:
        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "phase_c_weekly" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 Phase C 주간 배치 스케줄 제거: {job}")

        schedule.every().sunday.at("03:30").do(
            run_threaded, run_phase_c_weekly_batch
        ).tag("phase_c_weekly")
        logger.info("Phase C 주간 배치 스케줄 등록: 매주 일요일 03:30 KST")
    except Exception as e:
        logger.error(f"Phase C 주간 배치 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_kr_top50_earnings_scheduler():
    """
    KR Top50 실적발표 감시 스케줄을 설정합니다.
    기본값으로 활성화되며, 주기/옵션은 환경변수로 제어합니다.
    """
    try:
        enabled = _truthy_env(os.getenv("KR_TOP50_EARNINGS_WATCH_ENABLED", "1"), default=True)
        interval_minutes = max(int(os.getenv("KR_TOP50_EARNINGS_WATCH_INTERVAL_MINUTES", "5")), 1)

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_top50_earnings_watch" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR Top50 실적 감시 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR Top50 실적 감시 스케줄 비활성화(KR_TOP50_EARNINGS_WATCH_ENABLED=0)")
            return

        schedule.every(interval_minutes).minutes.do(
            run_threaded,
            run_kr_top50_earnings_hotpath_from_env,
        ).tag("kr_top50_earnings_watch")
        logger.info(
            "KR Top50 실적 감시 스케줄 등록: 매 %s분마다 실행",
            interval_minutes,
        )
    except Exception as e:
        logger.error(f"KR Top50 실적 감시 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_us_top50_financials_scheduler():
    """
    US Top50 재무제표 수집 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("US_TOP50_FINANCIALS_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("US_TOP50_FINANCIALS_SCHEDULE_TIME", "06:40") or "06:40"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "us_top50_financials_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 US Top50 재무제표 스케줄 제거: {job}")

        if not enabled:
            logger.info("US Top50 재무제표 스케줄 비활성화(US_TOP50_FINANCIALS_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_us_top50_financials_hotpath_from_env,
        ).tag("us_top50_financials_daily")
        logger.info(
            "US Top50 재무제표 스케줄 등록: 매일 %s 실행",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"US Top50 재무제표 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_uskr_tier_state_scheduler():
    """
    US/KR Tier 상태 동기화 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("USKR_TIER_STATE_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("USKR_TIER_STATE_SCHEDULE_TIME", "06:50") or "06:50"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "uskr_tier_state_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 US/KR Tier 상태 스케줄 제거: {job}")

        if not enabled:
            logger.info("US/KR Tier 상태 스케줄 비활성화(USKR_TIER_STATE_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            sync_uskr_tier_state_from_env,
        ).tag("uskr_tier_state_daily")
        logger.info(
            "US/KR Tier 상태 스케줄 등록: 매일 %s 실행",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"US/KR Tier 상태 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_uskr_entity_registry_scheduler():
    """
    Tier-1 기반 기업 canonical registry 동기화 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("USKR_ENTITY_REGISTRY_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("USKR_ENTITY_REGISTRY_SCHEDULE_TIME", "06:55") or "06:55"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "uskr_entity_registry_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 US/KR 기업 레지스트리 스케줄 제거: {job}")

        if not enabled:
            logger.info("US/KR 기업 레지스트리 스케줄 비활성화(USKR_ENTITY_REGISTRY_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            sync_uskr_corporate_entity_registry_from_env,
        ).tag("uskr_entity_registry_daily")
        logger.info(
            "US/KR 기업 레지스트리 스케줄 등록: 매일 %s 실행",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"US/KR 기업 레지스트리 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_us_top50_earnings_scheduler():
    """
    US Top50 실적발표 감시 스케줄을 설정합니다.
    기본값으로 활성화되며, 주기/옵션은 환경변수로 제어합니다.
    """
    try:
        enabled = _truthy_env(os.getenv("US_TOP50_EARNINGS_WATCH_ENABLED", "1"), default=True)
        interval_minutes = max(int(os.getenv("US_TOP50_EARNINGS_WATCH_INTERVAL_MINUTES", "5")), 1)

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "us_top50_earnings_watch" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 US Top50 실적 감시 스케줄 제거: {job}")

        if not enabled:
            logger.info("US Top50 실적 감시 스케줄 비활성화(US_TOP50_EARNINGS_WATCH_ENABLED=0)")
            return

        schedule.every(interval_minutes).minutes.do(
            run_threaded,
            run_us_top50_earnings_hotpath_from_env,
        ).tag("us_top50_earnings_watch")
        logger.info(
            "US Top50 실적 감시 스케줄 등록: 매 %s분마다 실행",
            interval_minutes,
        )
    except Exception as e:
        logger.error(f"US Top50 실적 감시 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_us_top50_snapshot_scheduler():
    """
    US Top50 월간 스냅샷 스케줄을 설정합니다.
    - 매일 지정 시각에 실행되며, target day-of-month가 아니면 스킵합니다.
    """
    try:
        enabled = _truthy_env(os.getenv("US_TOP50_SNAPSHOT_ENABLED", "1"), default=True)
        schedule_time = str(os.getenv("US_TOP50_SNAPSHOT_SCHEDULE_TIME", "06:20") or "06:20").strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "us_top50_snapshot" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 US Top50 스냅샷 스케줄 제거: {job}")

        if not enabled:
            logger.info("US Top50 스냅샷 스케줄 비활성화(US_TOP50_SNAPSHOT_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_us_top50_monthly_snapshot_job_from_env,
        ).tag("us_top50_snapshot")
        logger.info(
            "US Top50 스냅샷 스케줄 등록: 매일 %s 실행 (target day-of-month는 env에서 제어)",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"US Top50 스냅샷 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_kr_top50_snapshot_scheduler():
    """
    KR Top50 월간 스냅샷 스케줄을 설정합니다.
    - 매일 지정 시각에 실행되며, target day-of-month가 아니면 스킵합니다.
    """
    try:
        enabled = _truthy_env(os.getenv("KR_TOP50_SNAPSHOT_ENABLED", "1"), default=True)
        schedule_time = str(os.getenv("KR_TOP50_SNAPSHOT_SCHEDULE_TIME", "06:10") or "06:10").strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_top50_snapshot" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR Top50 스냅샷 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR Top50 스냅샷 스케줄 비활성화(KR_TOP50_SNAPSHOT_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_kr_top50_monthly_snapshot_job_from_env,
        ).tag("kr_top50_snapshot")
        logger.info(
            "KR Top50 스냅샷 스케줄 등록: 매일 %s 실행 (target day-of-month는 env에서 제어)",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"KR Top50 스냅샷 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_kr_corp_code_mapping_validation_scheduler():
    """
    KR Top50 corp_code 매핑 검증 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("KR_CORP_MAPPING_VALIDATION_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("KR_CORP_MAPPING_VALIDATION_SCHEDULE_TIME", "06:15") or "06:15"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_corp_mapping_validation_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR corp_code 매핑 검증 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR corp_code 매핑 검증 스케줄 비활성화(KR_CORP_MAPPING_VALIDATION_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            validate_kr_top50_corp_code_mapping_from_env,
        ).tag("kr_corp_mapping_validation_daily")
        logger.info(
            "KR corp_code 매핑 검증 스케줄 등록: 매일 %s 실행",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"KR corp_code 매핑 검증 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_kr_dart_dplus1_sla_scheduler():
    """
    KR DART D+1 SLA 점검 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("KR_DART_DPLUS1_SLA_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("KR_DART_DPLUS1_SLA_SCHEDULE_TIME", "06:25") or "06:25"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_dart_dplus1_sla_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR DART D+1 SLA 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR DART D+1 SLA 스케줄 비활성화(KR_DART_DPLUS1_SLA_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            validate_kr_dart_disclosure_dplus1_sla_from_env,
        ).tag("kr_dart_dplus1_sla_daily")
        logger.info(
            "KR DART D+1 SLA 스케줄 등록: 매일 %s 실행",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"KR DART D+1 SLA 스케줄 설정 실패: {e}", exc_info=True)
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


@retry_on_failure(max_retries=2, delay=120)
def run_extraction_cache_cleanup():
    """
    뉴스 추출 캐시(extraction_cache)에서 90일을 초과한 데이터를 정리합니다.
    """
    from service.database.db import cleanup_old_extraction_cache

    deleted_rows = cleanup_old_extraction_cache(days=90)
    logger.info(
        "뉴스 추출 캐시 정리 완료: 보존기간=90일, 삭제=%s건",
        deleted_rows,
    )
    return deleted_rows


def setup_extraction_cache_cleanup_scheduler():
    """
    뉴스 추출 캐시 정리 스케줄을 설정합니다.
    매일 04:20(KST)에 실행되도록 등록합니다.
    """
    try:
        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "extraction_cache_cleanup" in job.tags:
                schedule.cancel_job(job)
                logger.debug(f"기존 추출 캐시 정리 스케줄 제거: {job}")

        schedule.every().day.at("04:20").do(
            run_threaded, run_extraction_cache_cleanup
        ).tag("extraction_cache_cleanup")
        logger.info("뉴스 추출 캐시 정리 스케줄 등록: 매일 04:20 KST (90일 보존)")
    except Exception as e:
        logger.error(f"뉴스 추출 캐시 정리 스케줄 설정 실패: {e}", exc_info=True)
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
    (뉴스 수집 + Macro Graph 뉴스 추출 적재)
    
    Returns:
        threading.Thread: 스케줄러 스레드
    """
    # 스케줄 설정
    setup_news_scheduler()
    setup_graph_news_extraction_scheduler()
    
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
        setup_graph_news_extraction_scheduler()
        logger.info("Macro Graph 뉴스 추출 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"Macro Graph 뉴스 추출 스케줄 설정 실패: {e}")
    
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

    try:
        setup_extraction_cache_cleanup_scheduler()
        logger.info("뉴스 추출 캐시 정리 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"뉴스 추출 캐시 정리 스케줄 설정 실패: {e}")

    try:
        setup_phase_c_weekly_scheduler()
        logger.info("Phase C 주간 배치 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"Phase C 주간 배치 스케줄 설정 실패: {e}")

    try:
        setup_us_top50_snapshot_scheduler()
        logger.info("US Top50 스냅샷 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"US Top50 스냅샷 스케줄 설정 실패: {e}")

    try:
        setup_kr_top50_snapshot_scheduler()
        logger.info("KR Top50 스냅샷 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR Top50 스냅샷 스케줄 설정 실패: {e}")

    try:
        setup_kr_corp_code_mapping_validation_scheduler()
        logger.info("KR corp_code 매핑 검증 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR corp_code 매핑 검증 스케줄 설정 실패: {e}")

    try:
        setup_kr_dart_dplus1_sla_scheduler()
        logger.info("KR DART D+1 SLA 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR DART D+1 SLA 스케줄 설정 실패: {e}")

    try:
        setup_kr_top50_earnings_scheduler()
        logger.info("KR Top50 실적 감시 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR Top50 실적 감시 스케줄 설정 실패: {e}")

    try:
        setup_us_top50_financials_scheduler()
        logger.info("US Top50 재무제표 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"US Top50 재무제표 스케줄 설정 실패: {e}")

    try:
        setup_uskr_tier_state_scheduler()
        logger.info("US/KR Tier 상태 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"US/KR Tier 상태 스케줄 설정 실패: {e}")

    try:
        setup_uskr_entity_registry_scheduler()
        logger.info("US/KR 기업 레지스트리 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"US/KR 기업 레지스트리 스케줄 설정 실패: {e}")

    try:
        setup_us_top50_earnings_scheduler()
        logger.info("US Top50 실적 감시 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"US Top50 실적 감시 스케줄 설정 실패: {e}")
    
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
