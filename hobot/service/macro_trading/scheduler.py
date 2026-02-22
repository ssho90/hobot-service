"""
FRED 데이터 수집 및 뉴스 수집 자동 스케줄러 모듈
"""
import json
import schedule
import time
import threading
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Sequence
import logging
from functools import wraps

from service.database.db import get_db_connection
from service.macro_trading.collectors.fred_collector import get_fred_collector
from service.macro_trading.collectors.news_collector import get_news_collector
from service.macro_trading.collectors.policy_document_collector import (
    DEFAULT_POLICY_FEED_SOURCES,
    get_policy_document_collector,
)
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
    DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    DEFAULT_KR_TOP50_OHLCV_CONTINUITY_DAYS,
    DEFAULT_KR_TOP50_DAILY_OHLCV_LOOKBACK_DAYS,
    DEFAULT_REQUIRE_EXPECTATION_FEED,
    KR_TOP50_DEFAULT_MARKET,
    KR_TOP50_DEFAULT_SOURCE_URL,
    get_kr_corporate_collector,
)
from service.macro_trading.collectors.us_corporate_collector import (
    DEFAULT_US_FINANCIALS_MAX_PERIODS_PER_STATEMENT,
    DEFAULT_US_FINANCIALS_MAX_SYMBOL_COUNT,
    DEFAULT_US_EARNINGS_LOOKAHEAD_DAYS,
    DEFAULT_US_EARNINGS_LOOKBACK_DAYS,
    DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    DEFAULT_US_TOP50_OHLCV_CONTINUITY_DAYS,
    DEFAULT_US_TOP50_DAILY_OHLCV_LOOKBACK_DAYS,
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
from service.macro_trading.collectors.corporate_event_collector import (
    get_corporate_event_collector,
)
from service.macro_trading.config.config_loader import get_config
from service.macro_trading.ai_strategist import run_ai_analysis
from service.macro_trading.account_service import save_daily_account_snapshot
from service.graph.scheduler import (
    Phase5RegressionRequestConfig,
    run_phase_c_weekly_jobs,
    run_phase5_golden_regression_jobs,
)
from service.graph.news_loader import sync_news_with_extraction_backlog
from service.graph.embedding_loader import sync_document_embeddings

logger = logging.getLogger(__name__)

# 스케줄러 시작 여부를 추적하는 전역 변수
_scheduler_started = False
_scheduler_lock = threading.Lock()

# AI 분석 실행 중 여부를 추적하는 전역 변수 (동시 실행 방지)
_ai_analysis_running = False
_ai_analysis_lock = threading.Lock()

KR_TOP50_EARNINGS_WATCH_JOB_CODE = "KR_TOP50_EARNINGS_WATCH"
US_TOP50_EARNINGS_WATCH_JOB_CODE = "US_TOP50_EARNINGS_WATCH"
TIER1_CORPORATE_EVENT_SYNC_JOB_CODE = "TIER1_CORPORATE_EVENT_SYNC"
GRAPH_NEWS_EXTRACTION_SYNC_JOB_CODE = "GRAPH_NEWS_EXTRACTION_SYNC"
GRAPH_RAG_PHASE5_REGRESSION_JOB_CODE = "GRAPH_RAG_PHASE5_REGRESSION"
GRAPH_RAG_PHASE5_WEEKLY_REPORT_JOB_CODE = "GRAPH_RAG_PHASE5_WEEKLY_REPORT"
EQUITY_GRAPH_PROJECTION_SYNC_JOB_CODE = "EQUITY_GRAPH_PROJECTION_SYNC"

_DETAILS_MERGE_JOB_CODES = {
    GRAPH_RAG_PHASE5_REGRESSION_JOB_CODE,
}
_MAX_FAILED_CASE_DEBUG_ENTRIES = 50


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _merge_counter_dict(
    existing: Optional[Dict[str, Any]],
    incoming: Optional[Dict[str, Any]],
) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for source in (existing, incoming):
        if not isinstance(source, dict):
            continue
        for raw_key, raw_value in source.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            merged[key] = merged.get(key, 0) + max(_safe_int(raw_value), 0)
    return dict(sorted(merged.items()))


def _merge_unique_list(
    existing: Optional[Sequence[Any]],
    incoming: Optional[Sequence[Any]],
    *,
    limit: int = 50,
) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for source in (existing, incoming):
        if not isinstance(source, (list, tuple)):
            continue
        for item in source:
            try:
                token = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            except Exception:
                token = str(item)
            if token in seen:
                continue
            seen.add(token)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def _merge_run_report_details(
    *,
    job_code: str,
    existing: Optional[Dict[str, Any]],
    incoming: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(incoming, dict):
        return incoming
    if str(job_code or "").strip() not in _DETAILS_MERGE_JOB_CODES:
        return incoming

    existing_payload = existing if isinstance(existing, dict) else {}
    merged: Dict[str, Any] = {**existing_payload}
    merged.update(incoming)

    total_cases = max(_safe_int(existing_payload.get("total_cases"), 0), 0) + max(
        _safe_int(incoming.get("total_cases"), 0),
        0,
    )
    passed_cases = max(_safe_int(existing_payload.get("passed_cases"), 0), 0) + max(
        _safe_int(incoming.get("passed_cases"), 0),
        0,
    )
    failed_cases = max(_safe_int(existing_payload.get("failed_cases"), 0), 0) + max(
        _safe_int(incoming.get("failed_cases"), 0),
        0,
    )
    if total_cases <= 0:
        total_cases = passed_cases + failed_cases
    pass_rate_pct = (
        round((passed_cases * 100.0) / total_cases, 2)
        if total_cases > 0
        else _safe_float(incoming.get("pass_rate_pct"), 0.0)
    )
    merged["total_cases"] = total_cases
    merged["passed_cases"] = passed_cases
    merged["failed_cases"] = failed_cases
    merged["pass_rate_pct"] = pass_rate_pct

    merged["failure_counts"] = _merge_counter_dict(
        existing_payload.get("failure_counts"),
        incoming.get("failure_counts"),
    )
    merged["tool_mode_counts"] = _merge_counter_dict(
        existing_payload.get("tool_mode_counts"),
        incoming.get("tool_mode_counts"),
    )
    merged["target_agent_counts"] = _merge_counter_dict(
        existing_payload.get("target_agent_counts"),
        incoming.get("target_agent_counts"),
    )
    merged["freshness_status_counts"] = _merge_counter_dict(
        existing_payload.get("freshness_status_counts"),
        incoming.get("freshness_status_counts"),
    )

    existing_structured = (
        existing_payload.get("structured_citation_stats")
        if isinstance(existing_payload.get("structured_citation_stats"), dict)
        else {}
    )
    incoming_structured = (
        incoming.get("structured_citation_stats")
        if isinstance(incoming.get("structured_citation_stats"), dict)
        else {}
    )
    structured_total_count = max(_safe_int(existing_structured.get("total_count"), 0), 0) + max(
        _safe_int(incoming_structured.get("total_count"), 0),
        0,
    )
    structured_cases = max(
        _safe_int(existing_structured.get("cases_with_structured_citations"), 0),
        0,
    ) + max(_safe_int(incoming_structured.get("cases_with_structured_citations"), 0), 0)
    structured_max_count = max(
        max(_safe_int(existing_structured.get("max_count"), 0), 0),
        max(_safe_int(incoming_structured.get("max_count"), 0), 0),
    )
    structured_avg_count = round(structured_total_count / total_cases, 3) if total_cases > 0 else 0.0
    merged["structured_citation_stats"] = {
        "total_count": structured_total_count,
        "average_count": structured_avg_count,
        "max_count": structured_max_count,
        "cases_with_structured_citations": structured_cases,
    }

    merged["selected_case_ids"] = _merge_unique_list(
        existing_payload.get("selected_case_ids"),
        incoming.get("selected_case_ids"),
        limit=20,
    )

    failed_debug_total = max(_safe_int(existing_payload.get("failed_case_debug_total"), 0), 0) + max(
        _safe_int(incoming.get("failed_case_debug_total"), 0),
        0,
    )
    failed_debug_returned = max(
        _safe_int(existing_payload.get("failed_case_debug_returned"), 0),
        0,
    ) + max(_safe_int(incoming.get("failed_case_debug_returned"), 0), 0)
    merged["failed_case_debug_total"] = failed_debug_total
    merged["failed_case_debug_returned"] = failed_debug_returned
    merged["failed_case_debug_entries"] = _merge_unique_list(
        existing_payload.get("failed_case_debug_entries"),
        incoming.get("failed_case_debug_entries"),
        limit=_MAX_FAILED_CASE_DEBUG_ENTRIES,
    )
    merged["merged_run_count"] = max(_safe_int(existing_payload.get("merged_run_count"), 0), 0) + 1

    if "golden_set_path" in incoming:
        merged["golden_set_path"] = incoming.get("golden_set_path")
    if "request_config" in incoming:
        merged["request_config"] = incoming.get("request_config")

    return merged


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
    status_override: Optional[str] = None,
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

        if status_override:
            candidate_status = str(status_override).strip().lower()
            if candidate_status in {"healthy", "warning", "failed"}:
                last_status = candidate_status
            else:
                last_status = "warning"
        else:
            if not resolved_run_success:
                last_status = "failed"
            elif resolved_failure_count > 0:
                last_status = "warning"
            else:
                last_status = "healthy"

        merged_details: Optional[Dict[str, Any]] = details if isinstance(details, dict) else None

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
            None,  # details_json placeholder
        )
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str(job_code or "").strip() in _DETAILS_MERGE_JOB_CODES:
                cursor.execute(
                    """
                    SELECT details_json
                    FROM macro_collection_run_reports
                    WHERE report_date = %s AND job_code = %s
                    LIMIT 1
                    """,
                    (report_date, str(job_code or "").strip()),
                )
                existing_row = cursor.fetchone()
                existing_details = {}
                if isinstance(existing_row, dict):
                    existing_details = _parse_json_object(existing_row.get("details_json"))
                elif isinstance(existing_row, (list, tuple)) and existing_row:
                    existing_details = _parse_json_object(existing_row[0])
                merged_details = _merge_run_report_details(
                    job_code=str(job_code or "").strip(),
                    existing=existing_details,
                    incoming=merged_details,
                )

            details_json = None
            if isinstance(merged_details, dict) and merged_details:
                details_json = json.dumps(merged_details, ensure_ascii=False, default=str)
            payload_with_details = payload[:-1] + (details_json,)
            cursor.execute(query, payload_with_details)
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
    max_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
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
    limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
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
    limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    graph_sync_enabled: Optional[bool] = None,
    graph_sync_include_daily_bars: bool = False,
    graph_sync_include_earnings_events: bool = False,
    graph_sync_ensure_schema: bool = True,
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
    resolved_graph_sync_enabled = (
        graph_sync_enabled
        if graph_sync_enabled is not None
        else _truthy_env(
            os.getenv("EQUITY_GRAPH_SYNC_ON_MONTHLY_SNAPSHOT_ENABLED", "1"),
            default=True,
        )
    )
    graph_sync_result: Optional[Dict[str, Any]] = None
    if resolved_graph_sync_enabled:
        graph_sync_result = sync_equity_projection_to_graph(
            start_date=today,
            end_date=today,
            country_codes=("KR",),
            include_universe=True,
            include_daily_bars=graph_sync_include_daily_bars,
            include_earnings_events=graph_sync_include_earnings_events,
            ensure_schema=graph_sync_ensure_schema,
        )
    result["graph_sync_enabled"] = bool(resolved_graph_sync_enabled)
    result["graph_sync"] = graph_sync_result
    logger.info(
        "KR Top50 월간 스냅샷 완료: date=%s market=%s saved_rows=%s added=%s removed=%s rank_changed=%s graph_sync=%s",
        today.isoformat(),
        resolved_market,
        (capture_result or {}).get("saved_rows"),
        (diff_result or {}).get("added_count"),
        (diff_result or {}).get("removed_count"),
        (diff_result or {}).get("rank_changed_count"),
        "enabled" if resolved_graph_sync_enabled else "disabled",
    )
    return result


def run_kr_top50_monthly_snapshot_job_from_env() -> Dict[str, Any]:
    target_day_of_month = int(os.getenv("KR_TOP50_SNAPSHOT_DAY_OF_MONTH", "1"))
    market = os.getenv("KR_TOP50_SNAPSHOT_MARKET", "KOSPI")
    source_url = os.getenv(
        "KR_TOP50_SNAPSHOT_SOURCE_URL",
        "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
    )
    limit = int(
        os.getenv(
            "KR_TOP50_SNAPSHOT_LIMIT",
            str(DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT),
        )
    )
    graph_sync_enabled = _truthy_env(
        os.getenv(
            "KR_TOP50_SNAPSHOT_GRAPH_SYNC_ENABLED",
            os.getenv("EQUITY_GRAPH_SYNC_ON_MONTHLY_SNAPSHOT_ENABLED", "1"),
        ),
        default=True,
    )
    graph_sync_include_daily_bars = _truthy_env(
        os.getenv("KR_TOP50_SNAPSHOT_GRAPH_SYNC_INCLUDE_DAILY_BARS", "0"),
        default=False,
    )
    graph_sync_include_earnings_events = _truthy_env(
        os.getenv("KR_TOP50_SNAPSHOT_GRAPH_SYNC_INCLUDE_EARNINGS", "0"),
        default=False,
    )
    graph_sync_ensure_schema = _truthy_env(
        os.getenv("KR_TOP50_SNAPSHOT_GRAPH_SYNC_ENSURE_SCHEMA", "1"),
        default=True,
    )
    return run_kr_top50_monthly_snapshot_job(
        target_day_of_month=target_day_of_month,
        market=market,
        source_url=source_url,
        limit=limit,
        graph_sync_enabled=graph_sync_enabled,
        graph_sync_include_daily_bars=graph_sync_include_daily_bars,
        graph_sync_include_earnings_events=graph_sync_include_earnings_events,
        graph_sync_ensure_schema=graph_sync_ensure_schema,
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
    graph_sync_enabled: Optional[bool] = None,
    graph_sync_include_daily_bars: bool = False,
    graph_sync_include_earnings_events: bool = False,
    graph_sync_ensure_schema: bool = True,
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
    resolved_graph_sync_enabled = (
        graph_sync_enabled
        if graph_sync_enabled is not None
        else _truthy_env(
            os.getenv("EQUITY_GRAPH_SYNC_ON_MONTHLY_SNAPSHOT_ENABLED", "1"),
            default=True,
        )
    )
    graph_sync_result: Optional[Dict[str, Any]] = None
    if resolved_graph_sync_enabled:
        graph_sync_result = sync_equity_projection_to_graph(
            start_date=today,
            end_date=today,
            country_codes=("US",),
            include_universe=True,
            include_daily_bars=graph_sync_include_daily_bars,
            include_earnings_events=graph_sync_include_earnings_events,
            ensure_schema=graph_sync_ensure_schema,
        )
    result["graph_sync_enabled"] = bool(resolved_graph_sync_enabled)
    result["graph_sync"] = graph_sync_result
    logger.info(
        "US Top50 월간 스냅샷 완료: date=%s market=%s saved_rows=%s added=%s removed=%s rank_changed=%s graph_sync=%s",
        today.isoformat(),
        resolved_market,
        (capture_result or {}).get("saved_rows"),
        (diff_result or {}).get("added_count"),
        (diff_result or {}).get("removed_count"),
        (diff_result or {}).get("rank_changed_count"),
        "enabled" if resolved_graph_sync_enabled else "disabled",
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
    graph_sync_enabled = _truthy_env(
        os.getenv(
            "US_TOP50_SNAPSHOT_GRAPH_SYNC_ENABLED",
            os.getenv("EQUITY_GRAPH_SYNC_ON_MONTHLY_SNAPSHOT_ENABLED", "1"),
        ),
        default=True,
    )
    graph_sync_include_daily_bars = _truthy_env(
        os.getenv("US_TOP50_SNAPSHOT_GRAPH_SYNC_INCLUDE_DAILY_BARS", "0"),
        default=False,
    )
    graph_sync_include_earnings_events = _truthy_env(
        os.getenv("US_TOP50_SNAPSHOT_GRAPH_SYNC_INCLUDE_EARNINGS", "0"),
        default=False,
    )
    graph_sync_ensure_schema = _truthy_env(
        os.getenv("US_TOP50_SNAPSHOT_GRAPH_SYNC_ENSURE_SCHEMA", "1"),
        default=True,
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
        graph_sync_enabled=graph_sync_enabled,
        graph_sync_include_daily_bars=graph_sync_include_daily_bars,
        graph_sync_include_earnings_events=graph_sync_include_earnings_events,
        graph_sync_ensure_schema=graph_sync_ensure_schema,
    )


def _parse_env_yyyymm(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%Y%m")
    except ValueError as exc:
        raise ValueError(f"Invalid yyyymm format: {text}. expected YYYYMM") from exc
    return parsed.strftime("%Y%m")


def _shift_month(base_month: date, delta_months: int) -> date:
    month_index = (base_month.year * 12) + (base_month.month - 1) + int(delta_months)
    year, month_zero_based = divmod(month_index, 12)
    return date(year, month_zero_based + 1, 1)


def run_kr_macro_collection_from_env() -> Dict[str, Any]:
    days = max(int(os.getenv("KR_MACRO_COLLECTION_DAYS", "365")), 1)
    indicator_codes_csv = str(os.getenv("KR_MACRO_INDICATOR_CODES", "") or "").strip()
    indicator_codes = [value.strip() for value in indicator_codes_csv.split(",") if value.strip()] or None

    include_real_estate_supplemental = _truthy_env(
        os.getenv("KR_REAL_ESTATE_SUPPLEMENTAL_COLLECTION_ENABLED", "1"),
        default=True,
    )
    supplemental_days = max(
        int(os.getenv("KR_REAL_ESTATE_SUPPLEMENTAL_COLLECTION_DAYS", "365")),
        1,
    )

    macro_result = collect_kr_macro_data(
        indicator_codes=indicator_codes,
        days=days,
    )
    supplemental_result: Optional[Dict[str, Any]] = None
    if include_real_estate_supplemental:
        try:
            supplemental_result = collect_kr_real_estate_supplemental_data(
                days=supplemental_days
            )
        except Exception as exc:
            logger.warning(
                "KR 부동산 보조지표 수집 실패(무시 후 계속): %s",
                exc,
            )
            supplemental_result = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    return {
        "status": "completed",
        "macro": macro_result,
        "real_estate_supplemental_enabled": include_real_estate_supplemental,
        "real_estate_supplemental": supplemental_result,
    }


def run_kr_real_estate_pipeline_from_env() -> Dict[str, Any]:
    end_ym = _parse_env_yyyymm(os.getenv("KR_REAL_ESTATE_COLLECTION_END_YM")) or date.today().strftime("%Y%m")
    start_ym = _parse_env_yyyymm(os.getenv("KR_REAL_ESTATE_COLLECTION_START_YM"))
    rolling_months = max(int(os.getenv("KR_REAL_ESTATE_COLLECTION_ROLLING_MONTHS", "3")), 1)
    if start_ym is None:
        end_month = datetime.strptime(end_ym, "%Y%m").date().replace(day=1)
        start_month = _shift_month(end_month, -(rolling_months - 1))
        start_ym = start_month.strftime("%Y%m")

    scope = str(
        os.getenv("KR_REAL_ESTATE_COLLECTION_SCOPE", DEFAULT_MOLIT_REGION_SCOPE)
        or DEFAULT_MOLIT_REGION_SCOPE
    ).strip()
    lawd_codes_csv = str(os.getenv("KR_REAL_ESTATE_COLLECTION_LAWD_CODES", "") or "").strip()
    lawd_codes = [value.strip() for value in lawd_codes_csv.split(",") if value.strip()] or None
    num_of_rows = max(int(os.getenv("KR_REAL_ESTATE_COLLECTION_NUM_OF_ROWS", "1000")), 1)
    max_pages = max(int(os.getenv("KR_REAL_ESTATE_COLLECTION_MAX_PAGES", "100")), 1)
    progress_log_interval = max(int(os.getenv("KR_REAL_ESTATE_COLLECTION_PROGRESS_LOG_INTERVAL", "100")), 1)

    aggregate_enabled = _truthy_env(
        os.getenv("KR_REAL_ESTATE_AGGREGATION_ENABLED", "1"),
        default=True,
    )
    graph_sync_enabled = _truthy_env(
        os.getenv("KR_REAL_ESTATE_GRAPH_SYNC_ENABLED", "1"),
        default=True,
    )
    property_type = str(os.getenv("KR_REAL_ESTATE_PROPERTY_TYPE", "apartment") or "apartment").strip()
    transaction_type = str(os.getenv("KR_REAL_ESTATE_TRANSACTION_TYPE", "sale") or "sale").strip()

    collect_result = collect_kr_real_estate_data(
        start_ym=start_ym,
        end_ym=end_ym,
        scope=scope,
        lawd_codes=lawd_codes,
        num_of_rows=num_of_rows,
        max_pages=max_pages,
        progress_log_interval=progress_log_interval,
    )

    aggregate_result: Optional[Dict[str, Any]] = None
    graph_sync_result: Optional[Dict[str, Any]] = None
    if aggregate_enabled:
        aggregate_result = aggregate_kr_real_estate_monthly_summary(
            start_ym=start_ym,
            end_ym=end_ym,
            property_type=property_type,
            transaction_type=transaction_type,
        )
        if graph_sync_enabled:
            graph_sync_result = sync_kr_real_estate_summary_to_graph(
                start_ym=start_ym,
                end_ym=end_ym,
                property_type=property_type,
                transaction_type=transaction_type,
            )
    elif graph_sync_enabled:
        logger.warning(
            "KR 부동산 Graph 동기화 요청이 있었지만 집계 비활성화로 스킵합니다(KR_REAL_ESTATE_AGGREGATION_ENABLED=0)"
        )

    return {
        "status": "completed",
        "start_ym": start_ym,
        "end_ym": end_ym,
        "collect": collect_result,
        "aggregation_enabled": aggregate_enabled,
        "aggregate": aggregate_result,
        "graph_sync_enabled": graph_sync_enabled,
        "graph_sync": graph_sync_result,
    }


def _parse_env_date(value: Optional[str]) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid date format: {text}. expected YYYY-MM-DD") from exc


@retry_on_failure(max_retries=2, delay=120)
def run_kr_top50_ohlcv_hotpath(
    stock_codes: Optional[list[str]] = None,
    max_stock_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    market: str = KR_TOP50_DEFAULT_MARKET,
    source_url: str = KR_TOP50_DEFAULT_SOURCE_URL,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    lookback_days: int = DEFAULT_KR_TOP50_DAILY_OHLCV_LOOKBACK_DAYS,
    continuity_days: int = DEFAULT_KR_TOP50_OHLCV_CONTINUITY_DAYS,
    include_sub_mp_universe: bool = True,
    sub_mp_max_stock_count: int = 150,
    graph_sync_enabled: Optional[bool] = None,
    graph_sync_include_universe: bool = True,
    graph_sync_include_earnings_events: bool = True,
    graph_sync_ensure_schema: bool = True,
) -> Dict[str, Any]:
    collector = get_kr_corporate_collector()
    resolved_market = str(market or KR_TOP50_DEFAULT_MARKET).strip().upper() or KR_TOP50_DEFAULT_MARKET
    resolved_end_date = end_date or date.today()
    resolved_sub_mp_max_stock_count = max(int(sub_mp_max_stock_count), 1)
    sub_mp_stock_codes: list[str] = []
    if include_sub_mp_universe:
        sub_mp_stock_codes = _resolve_country_sub_mp_symbols(
            country_code="KR",
            max_symbol_count=resolved_sub_mp_max_stock_count,
        )
    logger.info("=" * 60)
    logger.info(
        "KR Top50 일별 OHLCV 수집 시작: market=%s max_stock_count=%s start=%s end=%s lookback_days=%s continuity_days=%s sub_mp_extra=%s",
        resolved_market,
        max_stock_count,
        start_date.isoformat() if isinstance(start_date, date) else None,
        resolved_end_date.isoformat(),
        lookback_days,
        continuity_days,
        len(sub_mp_stock_codes),
    )
    logger.info("=" * 60)
    result = collector.collect_top50_daily_ohlcv(
        stock_codes=stock_codes,
        extra_stock_codes=sub_mp_stock_codes or None,
        max_stock_count=max_stock_count,
        market=resolved_market,
        source_url=source_url,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        continuity_days=continuity_days,
        as_of_date=date.today(),
    )
    result["sub_mp_universe_enabled"] = bool(include_sub_mp_universe)
    result["sub_mp_extra_stock_count"] = len(sub_mp_stock_codes)
    result["sub_mp_extra_stock_codes"] = sub_mp_stock_codes

    resolved_graph_sync_enabled = (
        graph_sync_enabled
        if graph_sync_enabled is not None
        else _truthy_env(
            os.getenv("EQUITY_GRAPH_SYNC_ON_OHLCV_ENABLED", "1"),
            default=True,
        )
    )
    graph_sync_result: Optional[Dict[str, Any]] = None
    if resolved_graph_sync_enabled:
        graph_sync_start_date = start_date or (
            resolved_end_date - timedelta(days=max(int(lookback_days), 1))
        )
        graph_sync_result = sync_equity_projection_to_graph(
            start_date=graph_sync_start_date,
            end_date=resolved_end_date,
            country_codes=("KR",),
            include_universe=graph_sync_include_universe,
            include_daily_bars=True,
            include_earnings_events=graph_sync_include_earnings_events,
            ensure_schema=graph_sync_ensure_schema,
        )
    result["graph_sync_enabled"] = bool(resolved_graph_sync_enabled)
    result["graph_sync"] = graph_sync_result
    logger.info(
        "KR Top50 일별 OHLCV 수집 완료: target=%s fetched=%s upserted=%s failed=%s sub_mp_extra=%s graph_sync=%s",
        result.get("target_stock_count"),
        result.get("fetched_rows"),
        result.get("upserted_rows"),
        len(result.get("failed_stock_codes") or []),
        len(sub_mp_stock_codes),
        "enabled" if resolved_graph_sync_enabled else "disabled",
    )
    return result


def run_kr_top50_ohlcv_hotpath_from_env() -> Dict[str, Any]:
    stock_codes_csv = str(os.getenv("KR_TOP50_FIXED_STOCK_CODES", "") or "").strip()
    stock_codes = [value.strip() for value in stock_codes_csv.split(",") if value.strip()] or None
    max_stock_count = int(
        os.getenv(
            "KR_TOP50_OHLCV_MAX_STOCK_COUNT",
            str(DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT),
        )
    )
    market = str(os.getenv("KR_TOP50_OHLCV_MARKET", KR_TOP50_DEFAULT_MARKET) or KR_TOP50_DEFAULT_MARKET).strip().upper()
    source_url = str(os.getenv("KR_TOP50_OHLCV_SOURCE_URL", KR_TOP50_DEFAULT_SOURCE_URL) or KR_TOP50_DEFAULT_SOURCE_URL).strip()
    lookback_days = int(
        os.getenv(
            "KR_TOP50_OHLCV_LOOKBACK_DAYS",
            str(DEFAULT_KR_TOP50_DAILY_OHLCV_LOOKBACK_DAYS),
        )
    )
    continuity_days = int(
        os.getenv(
            "KR_TOP50_OHLCV_CONTINUITY_DAYS",
            str(DEFAULT_KR_TOP50_OHLCV_CONTINUITY_DAYS),
        )
    )
    include_sub_mp_universe = _truthy_env(
        os.getenv("KR_TOP50_OHLCV_INCLUDE_SUB_MP_UNIVERSE", "1"),
        default=True,
    )
    sub_mp_max_stock_count = int(
        os.getenv("KR_TOP50_OHLCV_SUB_MP_MAX_STOCK_COUNT", "150")
    )
    graph_sync_enabled = _truthy_env(
        os.getenv(
            "KR_TOP50_OHLCV_GRAPH_SYNC_ENABLED",
            os.getenv("EQUITY_GRAPH_SYNC_ON_OHLCV_ENABLED", "1"),
        ),
        default=True,
    )
    graph_sync_include_universe = _truthy_env(
        os.getenv("KR_TOP50_OHLCV_GRAPH_SYNC_INCLUDE_UNIVERSE", "1"),
        default=True,
    )
    graph_sync_include_earnings_events = _truthy_env(
        os.getenv("KR_TOP50_OHLCV_GRAPH_SYNC_INCLUDE_EARNINGS", "1"),
        default=True,
    )
    graph_sync_ensure_schema = _truthy_env(
        os.getenv("KR_TOP50_OHLCV_GRAPH_SYNC_ENSURE_SCHEMA", "1"),
        default=True,
    )
    start_date = _parse_env_date(os.getenv("KR_TOP50_OHLCV_START_DATE"))
    end_date = _parse_env_date(os.getenv("KR_TOP50_OHLCV_END_DATE"))
    return run_kr_top50_ohlcv_hotpath(
        stock_codes=stock_codes,
        max_stock_count=max_stock_count,
        market=market,
        source_url=source_url,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        continuity_days=continuity_days,
        include_sub_mp_universe=include_sub_mp_universe,
        sub_mp_max_stock_count=sub_mp_max_stock_count,
        graph_sync_enabled=graph_sync_enabled,
        graph_sync_include_universe=graph_sync_include_universe,
        graph_sync_include_earnings_events=graph_sync_include_earnings_events,
        graph_sync_ensure_schema=graph_sync_ensure_schema,
    )


@retry_on_failure(max_retries=2, delay=120)
def run_us_top50_ohlcv_hotpath(
    symbols: Optional[list[str]] = None,
    max_symbol_count: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    market: str = US_TOP50_DEFAULT_MARKET,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    lookback_days: int = DEFAULT_US_TOP50_DAILY_OHLCV_LOOKBACK_DAYS,
    continuity_days: int = DEFAULT_US_TOP50_OHLCV_CONTINUITY_DAYS,
    include_sub_mp_universe: bool = True,
    sub_mp_max_symbol_count: int = 150,
    graph_sync_enabled: Optional[bool] = None,
    graph_sync_include_universe: bool = True,
    graph_sync_include_earnings_events: bool = True,
    graph_sync_ensure_schema: bool = True,
) -> Dict[str, Any]:
    collector = get_us_corporate_collector()
    resolved_market = str(market or US_TOP50_DEFAULT_MARKET).strip().upper() or US_TOP50_DEFAULT_MARKET
    resolved_end_date = end_date or date.today()
    resolved_sub_mp_max_symbol_count = max(int(sub_mp_max_symbol_count), 1)
    sub_mp_symbols: list[str] = []
    if include_sub_mp_universe:
        sub_mp_symbols = _resolve_country_sub_mp_symbols(
            country_code="US",
            max_symbol_count=resolved_sub_mp_max_symbol_count,
        )
    logger.info("=" * 60)
    logger.info(
        "US Top50 일별 OHLCV 수집 시작: market=%s max_symbol_count=%s start=%s end=%s lookback_days=%s continuity_days=%s sub_mp_extra=%s",
        resolved_market,
        max_symbol_count,
        start_date.isoformat() if isinstance(start_date, date) else None,
        resolved_end_date.isoformat(),
        lookback_days,
        continuity_days,
        len(sub_mp_symbols),
    )
    logger.info("=" * 60)
    result = collector.collect_top50_daily_ohlcv(
        symbols=symbols,
        extra_symbols=sub_mp_symbols or None,
        max_symbol_count=max_symbol_count,
        market=resolved_market,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        continuity_days=continuity_days,
        as_of_date=date.today(),
    )
    result["sub_mp_universe_enabled"] = bool(include_sub_mp_universe)
    result["sub_mp_extra_symbol_count"] = len(sub_mp_symbols)
    result["sub_mp_extra_symbols"] = sub_mp_symbols
    resolved_graph_sync_enabled = (
        graph_sync_enabled
        if graph_sync_enabled is not None
        else _truthy_env(
            os.getenv("EQUITY_GRAPH_SYNC_ON_OHLCV_ENABLED", "1"),
            default=True,
        )
    )
    graph_sync_result: Optional[Dict[str, Any]] = None
    if resolved_graph_sync_enabled:
        graph_sync_start_date = start_date or (
            resolved_end_date - timedelta(days=max(int(lookback_days), 1))
        )
        graph_sync_result = sync_equity_projection_to_graph(
            start_date=graph_sync_start_date,
            end_date=resolved_end_date,
            country_codes=("US",),
            include_universe=graph_sync_include_universe,
            include_daily_bars=True,
            include_earnings_events=graph_sync_include_earnings_events,
            ensure_schema=graph_sync_ensure_schema,
        )
    result["graph_sync_enabled"] = bool(resolved_graph_sync_enabled)
    result["graph_sync"] = graph_sync_result
    logger.info(
        "US Top50 일별 OHLCV 수집 완료: target=%s fetched=%s upserted=%s failed=%s sub_mp_extra=%s graph_sync=%s",
        result.get("target_symbol_count"),
        result.get("fetched_rows"),
        result.get("upserted_rows"),
        len(result.get("failed_symbols") or []),
        len(sub_mp_symbols),
        "enabled" if resolved_graph_sync_enabled else "disabled",
    )
    return result


def run_us_top50_ohlcv_hotpath_from_env() -> Dict[str, Any]:
    symbols_csv = str(
        os.getenv(
            "US_TOP50_OHLCV_SYMBOLS",
            os.getenv("US_TOP50_FIXED_SYMBOLS", ""),
        )
        or ""
    ).strip()
    symbols = [value.strip() for value in symbols_csv.split(",") if value.strip()] or None
    max_symbol_count = int(
        os.getenv(
            "US_TOP50_OHLCV_MAX_SYMBOL_COUNT",
            str(DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT),
        )
    )
    market = str(os.getenv("US_TOP50_OHLCV_MARKET", US_TOP50_DEFAULT_MARKET) or US_TOP50_DEFAULT_MARKET).strip().upper()
    lookback_days = int(
        os.getenv(
            "US_TOP50_OHLCV_LOOKBACK_DAYS",
            str(DEFAULT_US_TOP50_DAILY_OHLCV_LOOKBACK_DAYS),
        )
    )
    continuity_days = int(
        os.getenv(
            "US_TOP50_OHLCV_CONTINUITY_DAYS",
            str(DEFAULT_US_TOP50_OHLCV_CONTINUITY_DAYS),
        )
    )
    include_sub_mp_universe = _truthy_env(
        os.getenv("US_TOP50_OHLCV_INCLUDE_SUB_MP_UNIVERSE", "1"),
        default=True,
    )
    sub_mp_max_symbol_count = int(
        os.getenv("US_TOP50_OHLCV_SUB_MP_MAX_SYMBOL_COUNT", "150")
    )
    graph_sync_enabled = _truthy_env(
        os.getenv(
            "US_TOP50_OHLCV_GRAPH_SYNC_ENABLED",
            os.getenv("EQUITY_GRAPH_SYNC_ON_OHLCV_ENABLED", "1"),
        ),
        default=True,
    )
    graph_sync_include_universe = _truthy_env(
        os.getenv("US_TOP50_OHLCV_GRAPH_SYNC_INCLUDE_UNIVERSE", "1"),
        default=True,
    )
    graph_sync_include_earnings_events = _truthy_env(
        os.getenv("US_TOP50_OHLCV_GRAPH_SYNC_INCLUDE_EARNINGS", "1"),
        default=True,
    )
    graph_sync_ensure_schema = _truthy_env(
        os.getenv("US_TOP50_OHLCV_GRAPH_SYNC_ENSURE_SCHEMA", "1"),
        default=True,
    )
    start_date = _parse_env_date(os.getenv("US_TOP50_OHLCV_START_DATE"))
    end_date = _parse_env_date(os.getenv("US_TOP50_OHLCV_END_DATE"))
    return run_us_top50_ohlcv_hotpath(
        symbols=symbols,
        max_symbol_count=max_symbol_count,
        market=market,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        continuity_days=continuity_days,
        include_sub_mp_universe=include_sub_mp_universe,
        sub_mp_max_symbol_count=sub_mp_max_symbol_count,
        graph_sync_enabled=graph_sync_enabled,
        graph_sync_include_universe=graph_sync_include_universe,
        graph_sync_include_earnings_events=graph_sync_include_earnings_events,
        graph_sync_ensure_schema=graph_sync_ensure_schema,
    )


@retry_on_failure(max_retries=2, delay=90)
def validate_kr_top50_corp_code_mapping(
    report_date: Optional[date] = None,
    market: str = "KOSPI",
    top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
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
    top_limit = int(
        os.getenv(
            "KR_CORP_MAPPING_VALIDATION_TOP_LIMIT",
            str(DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT),
        )
    )
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
    top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    lookback_days: int = 30,
    hydrate_disclosures_if_empty: bool = True,
    hydrate_per_corp_max_pages: int = 2,
    hydrate_page_count: int = DEFAULT_DART_DISCLOSURE_PAGE_COUNT,
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
        hydrate_disclosures_if_empty=hydrate_disclosures_if_empty,
        hydrate_per_corp_max_pages=hydrate_per_corp_max_pages,
        hydrate_page_count=hydrate_page_count,
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
    top_limit = int(
        os.getenv(
            "KR_DART_DPLUS1_SLA_TOP_LIMIT",
            str(DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT),
        )
    )
    lookback_days = int(os.getenv("KR_DART_DPLUS1_SLA_LOOKBACK_DAYS", "30"))
    hydrate_disclosures_if_empty = _truthy_env(
        os.getenv("KR_DART_DPLUS1_SLA_HYDRATE_IF_EMPTY", "1"),
        default=True,
    )
    hydrate_per_corp_max_pages = int(os.getenv("KR_DART_DPLUS1_SLA_HYDRATE_PAGES", "2"))
    hydrate_page_count = int(os.getenv("KR_DART_DPLUS1_SLA_HYDRATE_PAGE_COUNT", str(DEFAULT_DART_DISCLOSURE_PAGE_COUNT)))
    persist = _truthy_env(os.getenv("KR_DART_DPLUS1_SLA_PERSIST", "1"), default=True)
    return validate_kr_dart_disclosure_dplus1_sla(
        report_date=date.today(),
        market=market,
        top_limit=top_limit,
        lookback_days=lookback_days,
        hydrate_disclosures_if_empty=hydrate_disclosures_if_empty,
        hydrate_per_corp_max_pages=hydrate_per_corp_max_pages,
        hydrate_page_count=hydrate_page_count,
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
    max_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
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


def _resolve_tier1_event_sync_health_thresholds() -> Dict[str, int]:
    warn_retry_failures = max(_safe_int(os.getenv("TIER1_EVENT_SYNC_WARN_RETRY_FAILURE_COUNT", "1")), 0)
    warn_dlq_count = max(_safe_int(os.getenv("TIER1_EVENT_SYNC_WARN_DLQ_RECORDED_COUNT", "1")), 0)
    degraded_retry_failures = max(
        _safe_int(os.getenv("TIER1_EVENT_SYNC_DEGRADED_RETRY_FAILURE_COUNT", "3")),
        warn_retry_failures,
    )
    degraded_dlq_count = max(
        _safe_int(os.getenv("TIER1_EVENT_SYNC_DEGRADED_DLQ_RECORDED_COUNT", "3")),
        warn_dlq_count,
    )
    return {
        "warn_retry_failures": warn_retry_failures,
        "warn_dlq_count": warn_dlq_count,
        "degraded_retry_failures": degraded_retry_failures,
        "degraded_dlq_count": degraded_dlq_count,
    }


def _evaluate_tier1_event_sync_health_status(result: Dict[str, Any], thresholds: Dict[str, int]) -> str:
    if str(result.get("status") or "").strip().lower() not in {"ok", "healthy", "success"}:
        return "degraded"
    retry_failure_count = max(_safe_int(result.get("retry_failure_count")), 0)
    dlq_recorded_count = max(_safe_int(result.get("dlq_recorded_count")), 0)

    if (
        retry_failure_count >= max(_safe_int(thresholds.get("degraded_retry_failures")), 0)
        or dlq_recorded_count >= max(_safe_int(thresholds.get("degraded_dlq_count")), 0)
    ):
        return "degraded"
    if (
        retry_failure_count >= max(_safe_int(thresholds.get("warn_retry_failures")), 0)
        or dlq_recorded_count >= max(_safe_int(thresholds.get("warn_dlq_count")), 0)
    ):
        return "warn"
    return "healthy"


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


def _load_active_sub_mp_tickers() -> list[str]:
    """
    활성 Sub-MP 구성 종목 티커를 조회합니다.
    조회 실패 시 예외를 상위로 전달하며, 호출부에서 fallback 처리합니다.
    """
    query = """
        SELECT spc.ticker AS ticker
        FROM sub_portfolio_compositions spc
        INNER JOIN sub_portfolio_models spm
            ON spm.id = spc.sub_portfolio_model_id
        WHERE spm.is_active = TRUE
          AND COALESCE(spc.ticker, '') <> ''
        ORDER BY spm.asset_class, spm.display_order, spc.display_order, spc.ticker
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

    tickers: list[str] = []
    for row in rows:
        ticker = str((row or {}).get("ticker") or "").strip()
        if ticker:
            tickers.append(ticker)
    return list(dict.fromkeys(tickers))


def _normalize_kr_stock_code_for_universe(value: Any) -> Optional[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) != 6:
        return None
    return digits


def _normalize_us_symbol_for_universe(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if not text:
        return None
    sanitized = "".join(ch for ch in text if ch.isalnum() or ch in {".", "-"})
    if not sanitized:
        return None
    if not sanitized[0].isalpha():
        return None
    if sanitized in {"CASH", "KRW", "USD"}:
        return None
    if sanitized.isdigit() and len(sanitized) == 6:
        return None
    return sanitized


def _resolve_country_sub_mp_symbols(
    *,
    country_code: str,
    max_symbol_count: int = 150,
) -> list[str]:
    """
    Sub-MP 구성 종목 중 국가별 심볼/종목코드를 정규화하여 반환합니다.
    """
    normalized_country = str(country_code or "").strip().upper()
    if normalized_country not in {"KR", "US"}:
        return []

    try:
        raw_tickers = _load_active_sub_mp_tickers()
    except Exception as exc:
        logger.warning("Sub-MP 구성 종목 조회 실패(country=%s): %s", normalized_country, exc)
        return []

    resolved: list[str] = []
    for raw_ticker in raw_tickers:
        if normalized_country == "KR":
            normalized = _normalize_kr_stock_code_for_universe(raw_ticker)
        else:
            normalized = _normalize_us_symbol_for_universe(raw_ticker)
        if normalized:
            resolved.append(normalized)

    deduped = list(dict.fromkeys(resolved))
    return deduped[: max(int(max_symbol_count), 1)]


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
    max_corp_count: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    per_corp_max_pages: int = 3,
    immediate_fundamentals: bool = True,
    fundamentals_batch_size: int = DEFAULT_DART_BATCH_SIZE,
    use_grace_universe: bool = True,
    grace_lookback_days: int = 365,
    grace_max_symbol_count: int = 150,
    graph_sync_enabled: Optional[bool] = None,
    graph_sync_include_universe: bool = True,
    graph_sync_include_daily_bars: bool = False,
    graph_sync_ensure_schema: bool = True,
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
    resolved_graph_sync_enabled = (
        graph_sync_enabled
        if graph_sync_enabled is not None
        else _truthy_env(
            os.getenv("EQUITY_GRAPH_SYNC_ON_EARNINGS_ENABLED", "1"),
            default=True,
        )
    )

    def _attach_graph_sync(payload: Dict[str, Any]) -> Dict[str, Any]:
        graph_sync_result: Optional[Dict[str, Any]] = None
        if resolved_graph_sync_enabled:
            graph_sync_result = sync_equity_projection_to_graph(
                start_date=resolved_start_date,
                end_date=resolved_end_date,
                country_codes=("KR",),
                include_universe=graph_sync_include_universe,
                include_daily_bars=graph_sync_include_daily_bars,
                include_earnings_events=True,
                ensure_schema=graph_sync_ensure_schema,
            )
        payload["graph_sync_enabled"] = bool(resolved_graph_sync_enabled)
        payload["graph_sync"] = graph_sync_result
        return payload

    if not immediate_fundamentals:
        logger.info("KR Top50 실적 핫패스: 즉시 펀더멘털 배치 비활성화")
        return _attach_graph_sync(result)

    if not grouped_targets:
        logger.info("KR Top50 실적 핫패스: 신규 실적 이벤트 없음 (즉시 배치 스킵)")
        return _attach_graph_sync(result)

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
        "KR Top50 실적 핫패스 완료: new_events=%s trigger_groups=%s graph_sync=%s",
        len(new_earnings_events),
        len(grouped_targets),
        "enabled" if resolved_graph_sync_enabled else "disabled",
    )
    return _attach_graph_sync(result)


def run_kr_top50_earnings_hotpath_from_env() -> Dict[str, Any]:
    """
    환경변수 기반 KR Top50 실적 핫패스 실행 래퍼
    """
    started_at = datetime.now()
    lookback_days = int(os.getenv("KR_TOP50_EARNINGS_WATCH_LOOKBACK_DAYS", "1"))
    max_corp_count = int(
        os.getenv(
            "KR_TOP50_EARNINGS_WATCH_MAX_CORP_COUNT",
            str(DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT),
        )
    )
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
    graph_sync_enabled = _truthy_env(
        os.getenv(
            "KR_TOP50_EARNINGS_GRAPH_SYNC_ENABLED",
            os.getenv("EQUITY_GRAPH_SYNC_ON_EARNINGS_ENABLED", "1"),
        ),
        default=True,
    )
    graph_sync_include_universe = _truthy_env(
        os.getenv("KR_TOP50_EARNINGS_GRAPH_SYNC_INCLUDE_UNIVERSE", "1"),
        default=True,
    )
    graph_sync_include_daily_bars = _truthy_env(
        os.getenv("KR_TOP50_EARNINGS_GRAPH_SYNC_INCLUDE_DAILY_BARS", "0"),
        default=False,
    )
    graph_sync_ensure_schema = _truthy_env(
        os.getenv("KR_TOP50_EARNINGS_GRAPH_SYNC_ENSURE_SCHEMA", "1"),
        default=True,
    )
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
            graph_sync_enabled=graph_sync_enabled,
            graph_sync_include_universe=graph_sync_include_universe,
            graph_sync_include_daily_bars=graph_sync_include_daily_bars,
            graph_sync_ensure_schema=graph_sync_ensure_schema,
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
    graph_sync_enabled: Optional[bool] = None,
    graph_sync_include_universe: bool = True,
    graph_sync_include_daily_bars: bool = False,
    graph_sync_ensure_schema: bool = True,
) -> Dict[str, Any]:
    """
    US Top50 실적 감시 핫패스:
    - expected: yfinance earnings calendar
    - confirmed: SEC submissions(8-K/10-Q/10-K)
    """
    collector = get_us_corporate_collector()
    resolved_today = date.today()
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
        as_of_date=resolved_today,
    )
    result["grace_universe_enabled"] = bool(use_grace_universe)
    result["grace_symbol_count"] = len(grace_symbols)
    result["effective_max_symbol_count"] = resolved_max_symbol_count
    resolved_graph_sync_enabled = (
        graph_sync_enabled
        if graph_sync_enabled is not None
        else _truthy_env(
            os.getenv("EQUITY_GRAPH_SYNC_ON_EARNINGS_ENABLED", "1"),
            default=True,
        )
    )
    graph_sync_result: Optional[Dict[str, Any]] = None
    if resolved_graph_sync_enabled:
        graph_sync_start_date = resolved_today - timedelta(days=max(int(lookback_days), 1))
        graph_sync_end_date = resolved_today + timedelta(days=max(int(lookahead_days), 0))
        graph_sync_result = sync_equity_projection_to_graph(
            start_date=graph_sync_start_date,
            end_date=graph_sync_end_date,
            country_codes=("US",),
            include_universe=graph_sync_include_universe,
            include_daily_bars=graph_sync_include_daily_bars,
            include_earnings_events=True,
            ensure_schema=graph_sync_ensure_schema,
        )
    result["graph_sync_enabled"] = bool(resolved_graph_sync_enabled)
    result["graph_sync"] = graph_sync_result
    logger.info(
        "US Top50 실적 감시 완료: symbols=%s expected=%s confirmed=%s upserted=%s failed=%s graph_sync=%s",
        result.get("target_symbol_count"),
        result.get("expected_rows"),
        result.get("confirmed_rows"),
        result.get("upserted_rows"),
        len(result.get("failed_symbols") or []),
        "enabled" if resolved_graph_sync_enabled else "disabled",
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
    graph_sync_enabled = _truthy_env(
        os.getenv(
            "US_TOP50_EARNINGS_GRAPH_SYNC_ENABLED",
            os.getenv("EQUITY_GRAPH_SYNC_ON_EARNINGS_ENABLED", "1"),
        ),
        default=True,
    )
    graph_sync_include_universe = _truthy_env(
        os.getenv("US_TOP50_EARNINGS_GRAPH_SYNC_INCLUDE_UNIVERSE", "1"),
        default=True,
    )
    graph_sync_include_daily_bars = _truthy_env(
        os.getenv("US_TOP50_EARNINGS_GRAPH_SYNC_INCLUDE_DAILY_BARS", "0"),
        default=False,
    )
    graph_sync_ensure_schema = _truthy_env(
        os.getenv("US_TOP50_EARNINGS_GRAPH_SYNC_ENSURE_SCHEMA", "1"),
        default=True,
    )
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
            graph_sync_enabled=graph_sync_enabled,
            graph_sync_include_universe=graph_sync_include_universe,
            graph_sync_include_daily_bars=graph_sync_include_daily_bars,
            graph_sync_ensure_schema=graph_sync_ensure_schema,
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


@retry_on_failure(max_retries=2, delay=120)
def sync_tier1_corporate_events(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    lookback_days: int = 30,
    kr_market: str = "KOSPI",
    kr_top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    us_market: str = "US",
    us_top_limit: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    include_us_expected: bool = True,
    include_us_news: bool = True,
    include_kr_ir_news: bool = True,
    kr_ir_feed_urls: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    KR/US Tier-1 기업 이벤트를 표준 스키마(corporate_event_feed)로 동기화합니다.
    """
    collector = get_corporate_event_collector()
    resolved_end_date = end_date or date.today()
    resolved_start_date = start_date or (resolved_end_date - timedelta(days=max(int(lookback_days), 1) - 1))

    logger.info("=" * 60)
    logger.info(
        "Tier-1 기업 이벤트 표준 동기화 시작: start=%s end=%s lookback=%s kr=%s/%s us=%s/%s include_us_expected=%s include_us_news=%s include_kr_ir_news=%s",
        resolved_start_date.isoformat(),
        resolved_end_date.isoformat(),
        lookback_days,
        kr_market,
        kr_top_limit,
        us_market,
        us_top_limit,
        include_us_expected,
        include_us_news,
        include_kr_ir_news,
    )
    logger.info("=" * 60)

    result = collector.sync_tier1_events(
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        lookback_days=lookback_days,
        kr_market=kr_market,
        kr_top_limit=kr_top_limit,
        us_market=us_market,
        us_top_limit=us_top_limit,
        include_us_expected=include_us_expected,
        include_us_news=include_us_news,
        include_kr_ir_news=include_kr_ir_news,
        kr_ir_feed_urls=kr_ir_feed_urls,
    )
    logger.info(
        "Tier-1 기업 이벤트 표준 동기화 완료: status=%s kr=%s kr_ir_news=%s us=%s us_news=%s normalized=%s affected=%s",
        result.get("status"),
        result.get("kr_event_count"),
        result.get("kr_ir_news_event_count"),
        result.get("us_event_count"),
        result.get("us_news_event_count"),
        result.get("normalized_rows"),
        result.get("db_affected"),
    )
    return result


def sync_tier1_corporate_events_from_env() -> Dict[str, Any]:
    started_at = datetime.now()
    lookback_days = int(os.getenv("TIER1_EVENT_SYNC_LOOKBACK_DAYS", "30"))
    kr_market = str(os.getenv("TIER1_EVENT_SYNC_KR_MARKET", "KOSPI") or "KOSPI").strip().upper()
    kr_top_limit = int(
        os.getenv(
            "TIER1_EVENT_SYNC_KR_TOP_LIMIT",
            str(DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT),
        )
    )
    us_market = str(os.getenv("TIER1_EVENT_SYNC_US_MARKET", "US") or "US").strip().upper()
    us_top_limit = int(
        os.getenv(
            "TIER1_EVENT_SYNC_US_TOP_LIMIT",
            str(DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT),
        )
    )
    include_us_expected = _truthy_env(
        os.getenv("TIER1_EVENT_SYNC_INCLUDE_US_EXPECTED", "1"),
        default=True,
    )
    include_us_news = _truthy_env(
        os.getenv("TIER1_EVENT_SYNC_INCLUDE_US_NEWS", "1"),
        default=True,
    )
    include_kr_ir_news = _truthy_env(
        os.getenv("TIER1_EVENT_SYNC_INCLUDE_KR_IR_NEWS", "1"),
        default=True,
    )
    kr_ir_feed_urls_csv = str(
        os.getenv("TIER1_EVENT_SYNC_KR_IR_FEED_URLS", os.getenv("KR_TIER1_IR_FEED_URLS", "")) or ""
    ).strip()
    kr_ir_feed_urls = [value.strip() for value in kr_ir_feed_urls_csv.split(",") if value.strip()]
    thresholds = _resolve_tier1_event_sync_health_thresholds()

    try:
        result = sync_tier1_corporate_events(
            start_date=None,
            end_date=date.today(),
            lookback_days=lookback_days,
            kr_market=kr_market,
            kr_top_limit=kr_top_limit,
            us_market=us_market,
            us_top_limit=us_top_limit,
            include_us_expected=include_us_expected,
            include_us_news=include_us_news,
            include_kr_ir_news=include_kr_ir_news,
            kr_ir_feed_urls=kr_ir_feed_urls,
        )
        health_status = _evaluate_tier1_event_sync_health_status(result, thresholds)
        retry_failure_count = max(_safe_int(result.get("retry_failure_count")), 0)
        dlq_recorded_count = max(_safe_int(result.get("dlq_recorded_count")), 0)

        result["health_status"] = health_status
        result["health_thresholds"] = dict(thresholds)

        if health_status == "degraded":
            logger.error(
                "Tier-1 이벤트 동기화 경보(degraded): retry_failures=%s dlq_count=%s thresholds=%s",
                retry_failure_count,
                dlq_recorded_count,
                thresholds,
            )
        elif health_status == "warn":
            logger.warning(
                "Tier-1 이벤트 동기화 경보(warn): retry_failures=%s dlq_count=%s thresholds=%s",
                retry_failure_count,
                dlq_recorded_count,
                thresholds,
            )

        _record_collection_run_report(
            job_code=TIER1_CORPORATE_EVENT_SYNC_JOB_CODE,
            success_count=max(_safe_int(result.get("normalized_rows")), 0),
            failure_count=retry_failure_count + dlq_recorded_count,
            run_success=(health_status != "degraded"),
            started_at=started_at,
            finished_at=datetime.now(),
            status_override=(
                "healthy"
                if health_status == "healthy"
                else ("warning" if health_status == "warn" else "failed")
            ),
            details={
                "health_status": health_status,
                "health_thresholds": thresholds,
                "retry_failure_count": retry_failure_count,
                "dlq_recorded_count": dlq_recorded_count,
                "normalized_rows": max(_safe_int(result.get("normalized_rows")), 0),
                "kr_event_count": max(_safe_int(result.get("kr_event_count")), 0),
                "kr_ir_news_event_count": max(_safe_int(result.get("kr_ir_news_event_count")), 0),
                "us_event_count": max(_safe_int(result.get("us_event_count")), 0),
                "us_news_event_count": max(_safe_int(result.get("us_news_event_count")), 0),
                "db_affected": max(_safe_int(result.get("db_affected")), 0),
            },
        )
        return result
    except Exception as exc:
        _record_collection_run_report(
            job_code=TIER1_CORPORATE_EVENT_SYNC_JOB_CODE,
            success_count=0,
            failure_count=1,
            run_success=False,
            started_at=started_at,
            finished_at=datetime.now(),
            status_override="failed",
            details={
                "error_type": type(exc).__name__,
                "health_thresholds": thresholds,
            },
            error_message=str(exc),
        )
        raise


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


def _coerce_date_like(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_native"):
        try:
            return _coerce_date_like(value.to_native())
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    for parser in (date.fromisoformat, datetime.fromisoformat):
        try:
            parsed = parser(text)
            if isinstance(parsed, datetime):
                return parsed.date()
            if isinstance(parsed, date):
                return parsed
        except Exception:
            continue
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except Exception:
            return None
    return None


def _build_equity_projection_health(
    *,
    result: Dict[str, Any],
    start_date: date,
    end_date: date,
    include_universe: bool,
    include_daily_bars: bool,
    include_earnings_events: bool,
) -> Dict[str, Any]:
    sync_result = (result or {}).get("sync_result") or {}
    verification = ((result or {}).get("verification") or {}).get("summary") or {}
    row_counts = dict(sync_result.get("row_counts") or {})
    sync_status = str(sync_result.get("status") or "").strip().lower()

    max_trade_date = _coerce_date_like(verification.get("max_trade_date"))
    max_event_date = _coerce_date_like(verification.get("max_event_date"))

    candidate_dates: list[date] = []
    if include_daily_bars and max_trade_date:
        candidate_dates.append(max_trade_date)
    if include_earnings_events and max_event_date:
        candidate_dates.append(max_event_date)
    if include_universe and not candidate_dates and sync_status in {"success", "no_data"}:
        candidate_dates.append(end_date)

    latest_graph_date = max(candidate_dates) if candidate_dates else None
    lag_days = None
    lag_hours = None
    if latest_graph_date is not None:
        lag_days = max((end_date - latest_graph_date).days, 0)
        lag_hours = float(lag_days * 24)

    warn_lag_hours = max(_safe_int(os.getenv("EQUITY_GRAPH_PROJECTION_WARN_LAG_HOURS"), 30), 0)
    fail_lag_hours = max(
        _safe_int(os.getenv("EQUITY_GRAPH_PROJECTION_FAIL_LAG_HOURS"), 72),
        warn_lag_hours,
    )

    health_status = "healthy"
    health_reason = "lag_within_threshold"
    if sync_status not in {"success", "no_data"}:
        health_status = "failed"
        health_reason = f"sync_status={sync_status or 'unknown'}"
    elif lag_hours is None:
        health_status = "warning"
        health_reason = "lag_unavailable"
    elif lag_hours >= fail_lag_hours:
        health_status = "failed"
        health_reason = f"lag_hours={lag_hours:.1f}>={fail_lag_hours}"
    elif lag_hours >= warn_lag_hours:
        health_status = "warning"
        health_reason = f"lag_hours={lag_hours:.1f}>={warn_lag_hours}"

    return {
        "status": health_status,
        "reason": health_reason,
        "sync_status": sync_status or None,
        "window_start_date": start_date.isoformat(),
        "window_end_date": end_date.isoformat(),
        "row_counts": row_counts,
        "max_trade_date": max_trade_date.isoformat() if isinstance(max_trade_date, date) else None,
        "max_event_date": max_event_date.isoformat() if isinstance(max_event_date, date) else None,
        "latest_graph_date": latest_graph_date.isoformat() if isinstance(latest_graph_date, date) else None,
        "lag_days": lag_days,
        "lag_hours": lag_hours,
        "warn_lag_hours": warn_lag_hours,
        "fail_lag_hours": fail_lag_hours,
    }


@retry_on_failure(max_retries=2, delay=120)
def sync_equity_projection_to_graph(
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    country_codes: Optional[Sequence[str]] = None,
    include_universe: bool = True,
    include_daily_bars: bool = True,
    include_earnings_events: bool = True,
    ensure_schema: bool = True,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """
    RDB 주식 원천(Top50 universe/ohlcv/earnings)을 Neo4j 주식 도메인으로 동기화합니다.
    """
    from service.graph.equity_loader import sync_equity_projection

    started_at = datetime.now()
    resolved_end_date = end_date or date.today()
    resolved_start_date = start_date or (resolved_end_date - timedelta(days=365))
    if resolved_start_date > resolved_end_date:
        raise ValueError("start_date must be <= end_date")

    resolved_country_codes = [
        str(code or "").strip().upper()
        for code in (country_codes or ("KR", "US"))
        if str(code or "").strip()
    ]
    logger.info("=" * 60)
    logger.info(
        "주식 Projection Graph 동기화 시작: countries=%s start=%s end=%s include_universe=%s include_daily_bars=%s include_earnings=%s ensure_schema=%s",
        resolved_country_codes,
        resolved_start_date.isoformat(),
        resolved_end_date.isoformat(),
        bool(include_universe),
        bool(include_daily_bars),
        bool(include_earnings_events),
        bool(ensure_schema),
    )
    logger.info("=" * 60)
    report_enabled = _truthy_env(
        os.getenv("EQUITY_GRAPH_PROJECTION_SYNC_REPORT_ENABLED", "1"),
        default=True,
    )
    try:
        result = sync_equity_projection(
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            country_codes=resolved_country_codes,
            include_universe=include_universe,
            include_daily_bars=include_daily_bars,
            include_earnings_events=include_earnings_events,
            ensure_schema=ensure_schema,
            batch_size=batch_size,
        )
        projection_health = _build_equity_projection_health(
            result=result,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            include_universe=include_universe,
            include_daily_bars=include_daily_bars,
            include_earnings_events=include_earnings_events,
        )
        result["projection_health"] = projection_health

        if report_enabled:
            row_counts = (
                ((result.get("sync_result") or {}).get("row_counts") or {})
                if isinstance(result, dict)
                else {}
            )
            success_count = sum(max(_safe_int(value), 0) for value in row_counts.values())
            _record_collection_run_report(
                job_code=EQUITY_GRAPH_PROJECTION_SYNC_JOB_CODE,
                success_count=success_count,
                failure_count=0,
                run_success=True,
                started_at=started_at,
                finished_at=datetime.now(),
                status_override=projection_health.get("status"),
                details={
                    "country_codes": resolved_country_codes,
                    "include_universe": bool(include_universe),
                    "include_daily_bars": bool(include_daily_bars),
                    "include_earnings_events": bool(include_earnings_events),
                    "ensure_schema": bool(ensure_schema),
                    "projection_health_status": projection_health.get("status"),
                    "projection_health_reason": projection_health.get("reason"),
                    "lag_hours": projection_health.get("lag_hours"),
                    "lag_days": projection_health.get("lag_days"),
                    "latest_graph_date": projection_health.get("latest_graph_date"),
                    "max_trade_date": projection_health.get("max_trade_date"),
                    "max_event_date": projection_health.get("max_event_date"),
                    "warn_lag_hours": projection_health.get("warn_lag_hours"),
                    "fail_lag_hours": projection_health.get("fail_lag_hours"),
                    "row_counts": projection_health.get("row_counts"),
                    "sync_status": projection_health.get("sync_status"),
                    "window_start_date": projection_health.get("window_start_date"),
                    "window_end_date": projection_health.get("window_end_date"),
                },
            )

        logger.info("주식 Projection Graph 동기화 완료: %s", result)
        return result
    except Exception as exc:
        if report_enabled:
            _record_collection_run_report(
                job_code=EQUITY_GRAPH_PROJECTION_SYNC_JOB_CODE,
                success_count=0,
                failure_count=1,
                run_success=False,
                started_at=started_at,
                finished_at=datetime.now(),
                details={
                    "country_codes": resolved_country_codes,
                    "include_universe": bool(include_universe),
                    "include_daily_bars": bool(include_daily_bars),
                    "include_earnings_events": bool(include_earnings_events),
                    "ensure_schema": bool(ensure_schema),
                },
                error_message=str(exc),
            )
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


@retry_on_failure(max_retries=2, delay=120)
def collect_policy_documents():
    """
    정책기관(Fed/BOK) 공식 문서를 RSS로 수집해 economic_news에 저장합니다.
    """
    try:
        logger.info("=" * 60)
        logger.info("정책기관 공식 문서 수집 시작")
        logger.info("=" * 60)

        hours = max(int(os.getenv("POLICY_DOC_LOOKBACK_HOURS", "72")), 1)
        collector = get_policy_document_collector()
        result = collector.collect_recent_documents(hours=hours)

        logger.info("=" * 60)
        logger.info(
            "정책기관 공식 문서 수집 완료: status=%s normalized_rows=%s db_affected=%s failed_sources=%s",
            result.get("status"),
            result.get("normalized_rows"),
            result.get("db_affected"),
            result.get("failed_source_count"),
        )
        logger.info("=" * 60)
        return result
    except Exception as exc:
        logger.error("정책기관 공식 문서 수집 중 오류 발생: %s", exc, exc_info=True)
        raise


@retry_on_failure(max_retries=2, delay=120)
def collect_kr_housing_policy_documents():
    """
    KR 주택정책 기관(국토부/한국부동산원/주택금융공사) 문서만 수집합니다.
    """
    try:
        logger.info("=" * 60)
        logger.info("KR 주택정책 문서 수집 시작")
        logger.info("=" * 60)

        hours = max(int(os.getenv("KR_HOUSING_POLICY_DOC_LOOKBACK_HOURS", "168")), 1)
        source_keys = {
            "molit_housing_policy",
            "kreb_housing_policy",
            "khf_housing_policy",
        }
        selected_sources = [src for src in DEFAULT_POLICY_FEED_SOURCES if src.key in source_keys]

        collector = get_policy_document_collector()
        result = collector.collect_recent_documents(
            hours=hours,
            sources=selected_sources,
        )

        logger.info("=" * 60)
        logger.info(
            "KR 주택정책 문서 수집 완료: status=%s normalized_rows=%s db_affected=%s failed_sources=%s",
            result.get("status"),
            result.get("normalized_rows"),
            result.get("db_affected"),
            result.get("failed_source_count"),
        )
        logger.info("=" * 60)
        return result
    except Exception as exc:
        logger.error("KR 주택정책 문서 수집 중 오류 발생: %s", exc, exc_info=True)
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


def setup_policy_document_scheduler():
    """
    정책기관 공식 문서 수집 스케줄을 설정합니다.
    기본값은 2시간마다 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("POLICY_DOC_COLLECTION_ENABLED", "1"), default=True)
        interval_minutes = max(int(os.getenv("POLICY_DOC_COLLECTION_INTERVAL_MINUTES", "120")), 1)

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "policy_document_collection" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 정책기관 문서 수집 스케줄 제거: {job}")

        if not enabled:
            logger.info("정책기관 문서 수집 스케줄 비활성화(POLICY_DOC_COLLECTION_ENABLED=0)")
            return

        schedule.every(interval_minutes).minutes.do(
            run_threaded,
            collect_policy_documents,
        ).tag("policy_document_collection")
        logger.info(
            "정책기관 문서 수집 스케줄 등록: 매 %s분마다 실행",
            interval_minutes,
        )
    except Exception as e:
        logger.error(f"정책기관 문서 수집 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_kr_housing_policy_document_scheduler():
    """
    KR 주택정책 기관 문서 수집 스케줄을 설정합니다.
    기본값은 3시간마다 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("KR_HOUSING_POLICY_DOC_COLLECTION_ENABLED", "1"), default=True)
        interval_minutes = max(int(os.getenv("KR_HOUSING_POLICY_DOC_COLLECTION_INTERVAL_MINUTES", "180")), 1)

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_housing_policy_document_collection" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR 주택정책 문서 수집 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR 주택정책 문서 수집 스케줄 비활성화(KR_HOUSING_POLICY_DOC_COLLECTION_ENABLED=0)")
            return

        schedule.every(interval_minutes).minutes.do(
            run_threaded,
            collect_kr_housing_policy_documents,
        ).tag("kr_housing_policy_document_collection")
        logger.info(
            "KR 주택정책 문서 수집 스케줄 등록: 매 %s분마다 실행",
            interval_minutes,
        )
    except Exception as e:
        logger.error(f"KR 주택정책 문서 수집 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_kr_macro_scheduler():
    """
    KR 거시/보조지표 수집 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("KR_MACRO_COLLECTION_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("KR_MACRO_COLLECTION_SCHEDULE_TIME", "06:35") or "06:35"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_macro_collection_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR 거시 수집 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR 거시 수집 스케줄 비활성화(KR_MACRO_COLLECTION_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_kr_macro_collection_from_env,
        ).tag("kr_macro_collection_daily")
        logger.info("KR 거시 수집 스케줄 등록: 매일 %s 실행", schedule_time)
    except Exception as e:
        logger.error(f"KR 거시 수집 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_kr_real_estate_scheduler():
    """
    KR 부동산 수집/집계/그래프동기화 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(
            os.getenv("KR_REAL_ESTATE_COLLECTION_ENABLED", "1"),
            default=True,
        )
        schedule_time = str(
            os.getenv("KR_REAL_ESTATE_COLLECTION_SCHEDULE_TIME", "06:45") or "06:45"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_real_estate_collection_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR 부동산 수집 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR 부동산 수집 스케줄 비활성화(KR_REAL_ESTATE_COLLECTION_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_kr_real_estate_pipeline_from_env,
        ).tag("kr_real_estate_collection_daily")
        logger.info("KR 부동산 수집 스케줄 등록: 매일 %s 실행", schedule_time)
    except Exception as e:
        logger.error(f"KR 부동산 수집 스케줄 설정 실패: {e}", exc_info=True)
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
    started_at = datetime.now()

    sync_limit = int(os.getenv("GRAPH_NEWS_SYNC_LIMIT", "2000"))
    sync_days = int(os.getenv("GRAPH_NEWS_SYNC_DAYS", "30"))
    extraction_batch_size = int(os.getenv("GRAPH_NEWS_EXTRACTION_BATCH_SIZE", "200"))
    max_extraction_batches = int(os.getenv("GRAPH_NEWS_EXTRACTION_MAX_BATCHES", "10"))
    retry_failed_after_minutes = int(os.getenv("GRAPH_NEWS_RETRY_FAILED_AFTER_MINUTES", "180"))
    extraction_progress_log_interval = int(os.getenv("GRAPH_NEWS_EXTRACTION_PROGRESS_LOG_INTERVAL", "25"))
    embedding_enabled = _truthy_env(
        os.getenv("GRAPH_NEWS_EMBEDDING_ENABLED", "1"),
        default=True,
    )
    embedding_limit = int(os.getenv("GRAPH_NEWS_EMBEDDING_LIMIT", "800"))
    embedding_retry_failed_after_minutes = int(
        os.getenv("GRAPH_NEWS_EMBEDDING_RETRY_FAILED_AFTER_MINUTES", "180")
    )

    try:
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
        embedding_result: Dict[str, Any] = {
            "status": "disabled",
            "reason": "embedding_disabled",
        }
        if embedding_enabled:
            try:
                embedding_result = sync_document_embeddings(
                    limit=embedding_limit,
                    retry_failed_after_minutes=embedding_retry_failed_after_minutes,
                )
            except Exception as embedding_exc:
                logger.warning("Macro Graph 문서 임베딩 적재 실패(무시 후 계속): %s", embedding_exc)
                embedding_result = {
                    "status": "failed",
                    "reason": "embedding_sync_error",
                    "error": str(embedding_exc),
                }
        result["embedding"] = embedding_result

        extraction_success_docs = max(_safe_int(extraction_result.get("success_docs")), 0)
        extraction_failed_docs = max(_safe_int(extraction_result.get("failed_docs")), 0)
        embedding_success_docs = max(_safe_int(embedding_result.get("embedded_docs")), 0)
        embedding_failed_docs = max(_safe_int(embedding_result.get("failed_docs")), 0)
        success_count = extraction_success_docs + embedding_success_docs
        failure_count = extraction_failed_docs + embedding_failed_docs
        status_override = "healthy" if failure_count == 0 else "warning"
        _record_collection_run_report(
            job_code=GRAPH_NEWS_EXTRACTION_SYNC_JOB_CODE,
            success_count=success_count,
            failure_count=failure_count,
            run_success=True,
            started_at=started_at,
            finished_at=datetime.now(),
            status_override=status_override,
            details={
                "sync_documents": _safe_int(sync_result.get("documents")),
                "sync_failed": bool(sync_result.get("failed")),
                "extraction_batches": _safe_int(extraction_result.get("batches")),
                "extraction_success_docs": extraction_success_docs,
                "extraction_failed_docs": extraction_failed_docs,
                "extraction_skipped_docs": _safe_int(extraction_result.get("skipped_docs")),
                "extraction_stop_reason": extraction_result.get("stop_reason"),
                "embedding_status": embedding_result.get("status"),
                "embedding_candidate_docs": _safe_int(embedding_result.get("candidate_docs")),
                "embedding_embedded_docs": embedding_success_docs,
                "embedding_failed_docs": embedding_failed_docs,
                "embedding_skipped_docs": _safe_int(embedding_result.get("skipped_docs")),
                "embedding_vector_index_name": embedding_result.get("vector_index_name"),
            },
        )

        logger.info(
            "Macro Graph 뉴스 추출 적재 완료: docs=%s, batches=%s, extracted=%s, failed=%s, skipped=%s, stop_reason=%s, embedding_status=%s, embedded_docs=%s",
            sync_result.get("documents"),
            extraction_result.get("batches"),
            extraction_result.get("success_docs"),
            extraction_result.get("failed_docs"),
            extraction_result.get("skipped_docs"),
            extraction_result.get("stop_reason"),
            embedding_result.get("status"),
            embedding_result.get("embedded_docs"),
        )
        return result
    except Exception as exc:
        _record_collection_run_report(
            job_code=GRAPH_NEWS_EXTRACTION_SYNC_JOB_CODE,
            success_count=0,
            failure_count=1,
            run_success=False,
            started_at=started_at,
            finished_at=datetime.now(),
            details={"error_type": type(exc).__name__},
            error_message=str(exc),
        )
        raise


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


def _resolve_graph_rag_phase5_case_ids_from_env() -> Optional[list[str]]:
    case_ids_csv = str(os.getenv("GRAPH_RAG_PHASE5_CASE_IDS", "") or "").strip()
    if not case_ids_csv:
        return None
    case_ids = [value.strip() for value in case_ids_csv.split(",") if value.strip()]
    return case_ids or None


def _send_phase5_regression_alert(
    *,
    report: Optional[Dict[str, Any]],
    started_at: datetime,
    finished_at: datetime,
    runtime_error: Optional[Exception] = None,
) -> bool:
    """
    Phase 5 회귀 실행 결과를 Slack으로 알립니다.
    - 기본값은 비활성화(env opt-in)
    - Slack 토큰/모듈 문제로 본 스케줄러 실행이 실패하지 않도록 예외는 내부에서 흡수합니다.
    """
    alert_enabled = _truthy_env(
        os.getenv("GRAPH_RAG_PHASE5_ALERT_ENABLED", "0"),
        default=False,
    )
    if not alert_enabled:
        return False

    alert_only_on_warning = _truthy_env(
        os.getenv("GRAPH_RAG_PHASE5_ALERT_ONLY_ON_WARNING", "1"),
        default=True,
    )
    alert_channel = str(
        os.getenv("GRAPH_RAG_PHASE5_ALERT_CHANNEL", "#auto-trading-error") or "#auto-trading-error"
    ).strip()
    alert_case_limit = max(
        _safe_int(os.getenv("GRAPH_RAG_PHASE5_ALERT_CASE_LIMIT", "3"), 3),
        0,
    )
    alert_error_message_limit = max(
        _safe_int(os.getenv("GRAPH_RAG_PHASE5_ALERT_ERROR_MESSAGE_LIMIT", "2"), 2),
        1,
    )

    total_cases = max(_safe_int((report or {}).get("total_cases"), 0), 0)
    passed_cases = max(_safe_int((report or {}).get("passed_cases"), 0), 0)
    failed_cases = max(_safe_int((report or {}).get("failed_cases"), 0), 0)
    pass_rate_pct = float((report or {}).get("pass_rate_pct") or 0.0)

    if runtime_error:
        health_status = "failed"
    elif failed_cases > 0:
        health_status = "warning"
    else:
        health_status = "healthy"

    if alert_only_on_warning and health_status == "healthy":
        return False

    duration_sec = max(int((finished_at - started_at).total_seconds()), 0)
    lines = [
        "[Phase5 Regression Alert]",
        f"- status: {health_status}",
        f"- executed_at: {finished_at.isoformat()}",
        f"- duration_sec: {duration_sec}",
    ]

    if runtime_error is not None:
        lines.append(f"- error_type: {type(runtime_error).__name__}")
        lines.append(f"- error_message: {str(runtime_error)[:300]}")
    else:
        lines.append(
            f"- total_cases: {total_cases}, passed_cases: {passed_cases}, failed_cases: {failed_cases}, pass_rate_pct: {pass_rate_pct:.2f}"
        )
        failure_counts = (report or {}).get("failure_counts")
        if isinstance(failure_counts, dict) and failure_counts:
            lines.append(f"- failure_counts: {json.dumps(failure_counts, ensure_ascii=False)}")

        failure_debug = (report or {}).get("failure_debug")
        debug_entries = []
        if isinstance(failure_debug, dict):
            raw_entries = failure_debug.get("entries")
            if isinstance(raw_entries, list):
                debug_entries = [item for item in raw_entries if isinstance(item, dict)]

        if debug_entries and alert_case_limit > 0:
            lines.append("- failed_cases:")
            for item in debug_entries[:alert_case_limit]:
                case_id = str(item.get("case_id") or "").strip()
                question_id = str(item.get("question_id") or "").strip()
                freshness_status = str(item.get("freshness_status") or "").strip()
                categories = item.get("failure_categories")
                category_text = ""
                if isinstance(categories, list) and categories:
                    category_text = ",".join(
                        str(value).strip() for value in categories if str(value).strip()
                    )
                messages = item.get("failure_messages")
                short_messages: list[str] = []
                if isinstance(messages, list):
                    short_messages = [
                        str(value).strip()
                        for value in messages
                        if str(value).strip()
                    ][:alert_error_message_limit]
                message_text = "; ".join(short_messages)
                lines.append(
                    f"  - {case_id}/{question_id} freshness={freshness_status} categories={category_text} messages={message_text}"
                )

    message = "\n".join(lines)
    try:
        from service.slack_bot import post_message  # pylint: disable=import-outside-toplevel
    except Exception as import_exc:
        logger.warning("Phase 5 회귀 알림 모듈 로드 실패: %s", import_exc)
        return False

    try:
        sent = bool(post_message(message, channel=alert_channel))
        if sent:
            logger.info(
                "Phase 5 회귀 알림 전송 완료(channel=%s, status=%s)",
                alert_channel,
                health_status,
            )
        else:
            logger.warning(
                "Phase 5 회귀 알림 전송 실패(channel=%s, status=%s)",
                alert_channel,
                health_status,
            )
        return sent
    except Exception as alert_exc:
        logger.warning("Phase 5 회귀 알림 전송 중 예외 발생: %s", alert_exc)
        return False


def _build_phase5_failure_debug_entries(
    report: Dict[str, Any],
    *,
    max_cases: int = 10,
    max_messages_per_case: int = 3,
) -> Dict[str, Any]:
    case_results = report.get("case_results")
    if not isinstance(case_results, list):
        return {
            "total_failed_cases": 0,
            "returned_failed_cases": 0,
            "entries": [],
        }

    normalized_limit = max(_safe_int(max_cases, 10), 0)
    normalized_message_limit = max(_safe_int(max_messages_per_case, 3), 1)

    failed_items = [
        item
        for item in case_results
        if isinstance(item, dict) and not bool(item.get("passed"))
    ]
    entries: list[Dict[str, Any]] = []
    for item in failed_items[:normalized_limit]:
        failures = item.get("failures")
        normalized_failures = [
            failure for failure in failures if isinstance(failure, dict)
        ] if isinstance(failures, list) else []
        categories = sorted(
            {
                str(failure.get("category") or "").strip()
                for failure in normalized_failures
                if str(failure.get("category") or "").strip()
            }
        )
        messages = [
            str(failure.get("message") or "").strip()
            for failure in normalized_failures
            if str(failure.get("message") or "").strip()
        ][:normalized_message_limit]
        entries.append(
            {
                "case_id": str(item.get("case_id") or "").strip(),
                "question_id": str(item.get("question_id") or "").strip(),
                "citation_count": max(_safe_int(item.get("citation_count"), 0), 0),
                "structured_citation_count": max(_safe_int(item.get("structured_citation_count"), 0), 0),
                "tool_mode": str(item.get("tool_mode") or "").strip() or None,
                "expected_tool_mode": str(item.get("expected_tool_mode") or "").strip() or None,
                "target_agents": [
                    str(agent).strip()
                    for agent in (item.get("target_agents") if isinstance(item.get("target_agents"), list) else [])
                    if str(agent).strip()
                ],
                "freshness_status": str(item.get("freshness_status") or "").strip() or None,
                "freshness_age_hours": item.get("freshness_age_hours"),
                "latest_evidence_published_at": str(item.get("latest_evidence_published_at") or "").strip() or None,
                "recent_guard_enabled": item.get("recent_guard_enabled"),
                "recent_guard_target_count": item.get("recent_guard_target_count"),
                "recent_guard_max_age_hours": item.get("recent_guard_max_age_hours"),
                "recent_guard_require_focus_match": item.get("recent_guard_require_focus_match"),
                "recent_guard_candidate_recent_evidence_count": item.get("recent_guard_candidate_recent_evidence_count"),
                "recent_guard_selected_recent_citation_count": item.get("recent_guard_selected_recent_citation_count"),
                "recent_guard_added_recent_citation_count": item.get("recent_guard_added_recent_citation_count"),
                "recent_guard_target_satisfied": item.get("recent_guard_target_satisfied"),
                "failure_categories": categories,
                "failure_messages": messages,
                "failure_count": len(normalized_failures),
            }
        )

    return {
        "total_failed_cases": len(failed_items),
        "returned_failed_cases": len(entries),
        "entries": entries,
    }


@retry_on_failure(max_retries=2, delay=120)
def run_graph_rag_phase5_regression() -> Dict[str, Any]:
    """
    Phase 5 GraphRAG 골든셋(Q1~Q6) 회귀를 실행합니다.
    """
    started_at = datetime.now()
    logger.info("=" * 60)
    logger.info("Phase 5 GraphRAG 골든셋 회귀 시작")
    logger.info("=" * 60)

    golden_set_path = str(os.getenv("GRAPH_RAG_PHASE5_GOLDEN_SET_PATH", "") or "").strip()
    if not golden_set_path:
        golden_set_path = None

    time_range = str(os.getenv("GRAPH_RAG_PHASE5_TIME_RANGE", "30d") or "30d").strip()
    as_of_date = _parse_env_date(os.getenv("GRAPH_RAG_PHASE5_AS_OF_DATE")) or date.today()
    model = str(os.getenv("GRAPH_RAG_PHASE5_MODEL", "gemini-3-flash-preview") or "gemini-3-flash-preview").strip()
    timeout_sec = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_TIMEOUT_SEC", "90"), 90), 10)
    max_prompt_evidences = max(
        _safe_int(os.getenv("GRAPH_RAG_PHASE5_MAX_PROMPT_EVIDENCES", "12"), 12),
        3,
    )
    top_k_events = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_TOP_K_EVENTS", "25"), 25), 5)
    top_k_documents = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_TOP_K_DOCUMENTS", "40"), 40), 5)
    top_k_stories = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_TOP_K_STORIES", "20"), 20), 5)
    top_k_evidences = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_TOP_K_EVIDENCES", "40"), 40), 5)
    include_context = _truthy_env(os.getenv("GRAPH_RAG_PHASE5_INCLUDE_CONTEXT", "0"), default=False)
    reuse_cached_run = _truthy_env(os.getenv("GRAPH_RAG_PHASE5_REUSE_CACHED_RUN", "0"), default=False)
    persist_macro_state = _truthy_env(os.getenv("GRAPH_RAG_PHASE5_PERSIST_MACRO_STATE", "0"), default=False)
    persist_analysis_run = _truthy_env(os.getenv("GRAPH_RAG_PHASE5_PERSIST_ANALYSIS_RUN", "0"), default=False)
    case_ids = _resolve_graph_rag_phase5_case_ids_from_env()
    failure_debug_case_limit = max(
        _safe_int(os.getenv("GRAPH_RAG_PHASE5_FAILURE_DEBUG_CASE_LIMIT", "10"), 10),
        0,
    )
    failure_debug_message_limit = max(
        _safe_int(os.getenv("GRAPH_RAG_PHASE5_FAILURE_DEBUG_MESSAGE_LIMIT", "3"), 3),
        1,
    )

    try:
        run_kwargs: Dict[str, Any] = {
            "case_ids": case_ids,
            "request_config": Phase5RegressionRequestConfig(
                model=model,
                time_range=time_range,
                as_of_date=as_of_date,
                timeout_sec=timeout_sec,
                max_prompt_evidences=max_prompt_evidences,
                include_context=include_context,
                reuse_cached_run=reuse_cached_run,
                persist_macro_state=persist_macro_state,
                persist_analysis_run=persist_analysis_run,
                top_k_events=top_k_events,
                top_k_documents=top_k_documents,
                top_k_stories=top_k_stories,
                top_k_evidences=top_k_evidences,
            ),
        }
        if golden_set_path:
            run_kwargs["golden_set_path"] = golden_set_path
        report = run_phase5_golden_regression_jobs(**run_kwargs)

        passed_cases = max(_safe_int(report.get("passed_cases"), 0), 0)
        failed_cases = max(_safe_int(report.get("failed_cases"), 0), 0)
        total_cases = max(_safe_int(report.get("total_cases"), 0), passed_cases + failed_cases)
        failure_debug_payload = _build_phase5_failure_debug_entries(
            report,
            max_cases=failure_debug_case_limit,
            max_messages_per_case=failure_debug_message_limit,
        )
        report["failure_debug"] = failure_debug_payload
        status_override = "healthy" if failed_cases == 0 else "warning"
        finished_at = datetime.now()
        _record_collection_run_report(
            job_code=GRAPH_RAG_PHASE5_REGRESSION_JOB_CODE,
            success_count=passed_cases,
            failure_count=failed_cases,
            run_success=True,
            started_at=started_at,
            finished_at=finished_at,
            status_override=status_override,
            details={
                "total_cases": total_cases,
                "passed_cases": passed_cases,
                "failed_cases": failed_cases,
                "pass_rate_pct": report.get("pass_rate_pct"),
                "failure_counts": report.get("failure_counts"),
                "tool_mode_counts": report.get("tool_mode_counts"),
                "target_agent_counts": report.get("target_agent_counts"),
                "freshness_status_counts": report.get("freshness_status_counts"),
                "structured_citation_stats": report.get("structured_citation_stats"),
                "selected_case_ids": report.get("selected_case_ids"),
                "golden_set_path": report.get("golden_set_path"),
                "request_config": report.get("request_config"),
                "failed_case_debug_total": failure_debug_payload.get("total_failed_cases"),
                "failed_case_debug_returned": failure_debug_payload.get("returned_failed_cases"),
                "failed_case_debug_entries": failure_debug_payload.get("entries"),
            },
        )
        _send_phase5_regression_alert(
            report=report,
            started_at=started_at,
            finished_at=finished_at,
        )
        logger.info(
            "Phase 5 GraphRAG 회귀 완료: total=%s passed=%s failed=%s pass_rate=%.2f%%",
            total_cases,
            passed_cases,
            failed_cases,
            float(report.get("pass_rate_pct") or 0.0),
        )
        return report
    except Exception as exc:
        finished_at = datetime.now()
        _record_collection_run_report(
            job_code=GRAPH_RAG_PHASE5_REGRESSION_JOB_CODE,
            success_count=0,
            failure_count=1,
            run_success=False,
            started_at=started_at,
            finished_at=finished_at,
            details={"error_type": type(exc).__name__},
            error_message=str(exc),
        )
        _send_phase5_regression_alert(
            report=None,
            started_at=started_at,
            finished_at=finished_at,
            runtime_error=exc,
        )
        raise


def setup_graph_rag_phase5_regression_scheduler():
    """
    Phase 5 GraphRAG 골든셋 회귀 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("GRAPH_RAG_PHASE5_REGRESSION_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("GRAPH_RAG_PHASE5_REGRESSION_SCHEDULE_TIME", "08:10") or "08:10"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "graph_rag_phase5_regression_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 Phase 5 GraphRAG 회귀 스케줄 제거: {job}")

        if not enabled:
            logger.info("Phase 5 GraphRAG 회귀 스케줄 비활성화(GRAPH_RAG_PHASE5_REGRESSION_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_graph_rag_phase5_regression,
        ).tag("graph_rag_phase5_regression_daily")
        logger.info("Phase 5 GraphRAG 회귀 스케줄 등록: 매일 %s 실행", schedule_time)
    except Exception as e:
        logger.error(f"Phase 5 GraphRAG 회귀 스케줄 설정 실패: {e}", exc_info=True)
        raise


@retry_on_failure(max_retries=2, delay=120)
def run_graph_rag_phase5_weekly_report(
    *,
    days: int = 7,
) -> Dict[str, Any]:
    """
    최근 N일간 Phase 5 회귀 실행 로그를 집계해 주간 운영 요약을 생성합니다.
    """
    started_at = datetime.now()
    window_days = max(_safe_int(days, 7), 1)
    cutoff = datetime.now() - timedelta(days=window_days)
    cutoff_date = cutoff.date()
    logger.info("=" * 60)
    logger.info(
        "Phase 5 GraphRAG 주간 리포트 집계 시작: window_days=%s cutoff=%s",
        window_days,
        cutoff.isoformat(),
    )
    logger.info("=" * 60)

    min_runs = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_WEEKLY_MIN_RUNS", "3"), 3), 1)
    min_avg_pass_rate = _safe_float(os.getenv("GRAPH_RAG_PHASE5_WEEKLY_MIN_AVG_PASS_RATE", "85"), 85.0)
    max_warning_runs = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_WEEKLY_MAX_WARNING_RUNS", "2"), 2), 0)
    max_routing_mismatch = max(
        _safe_int(os.getenv("GRAPH_RAG_PHASE5_WEEKLY_MAX_ROUTING_MISMATCH", "0"), 0),
        0,
    )
    min_structured_avg = max(
        _safe_float(os.getenv("GRAPH_RAG_PHASE5_WEEKLY_MIN_STRUCTURED_CITATION_AVG", "0.5"), 0.5),
        0.0,
    )

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        run_count,
                        success_run_count,
                        failed_run_count,
                        success_count,
                        failure_count,
                        last_success_rate_pct,
                        last_status,
                        details_json,
                        report_date,
                        updated_at
                    FROM macro_collection_run_reports
                    WHERE job_code = %s AND report_date >= %s
                    ORDER BY report_date DESC, updated_at DESC
                    """,
                    (GRAPH_RAG_PHASE5_REGRESSION_JOB_CODE, cutoff_date),
                )
                rows = cursor.fetchall() or []
    except Exception as exc:
        _record_collection_run_report(
            job_code=GRAPH_RAG_PHASE5_WEEKLY_REPORT_JOB_CODE,
            success_count=0,
            failure_count=1,
            run_success=False,
            started_at=started_at,
            finished_at=datetime.now(),
            details={"window_days": window_days, "error_type": type(exc).__name__},
            error_message=str(exc),
        )
        raise

    total_runs = 0
    success_runs = 0
    warning_runs = 0
    failed_runs = 0
    total_passed_cases = 0
    total_failed_cases = 0
    pass_rate_weighted_sum = 0.0
    pass_rate_weight_total = 0
    effective_pass_rate_values: list[float] = []
    structured_avg_values: list[float] = []
    structured_total_values: list[int] = []
    failure_counts: Dict[str, int] = {}
    tool_mode_counts: Dict[str, int] = {}
    target_agent_counts: Dict[str, int] = {}
    freshness_status_counts: Dict[str, int] = {}
    failed_case_counts: Dict[str, int] = {}
    failed_case_samples: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        run_count_value = max(_safe_int(row.get("run_count"), 1), 0)
        total_runs += run_count_value
        status = str(row.get("last_status") or "").strip().lower()
        success_run_count = max(_safe_int(row.get("success_run_count"), 0), 0)
        failed_run_count = max(_safe_int(row.get("failed_run_count"), 0), 0)
        if success_run_count <= 0 and failed_run_count <= 0 and run_count_value > 0:
            if status == "failed":
                failed_run_count = run_count_value
            else:
                success_run_count = run_count_value
        success_runs += success_run_count
        failed_runs += failed_run_count
        if status == "warning":
            warning_runs += run_count_value

        total_passed_cases += max(_safe_int(row.get("success_count"), 0), 0)
        total_failed_cases += max(_safe_int(row.get("failure_count"), 0), 0)

        pass_rate = _safe_float(row.get("last_success_rate_pct"), -1.0)
        total_case_count = (
            max(_safe_int(row.get("success_count"), 0), 0)
            + max(_safe_int(row.get("failure_count"), 0), 0)
        )
        if total_case_count > 0 and pass_rate <= 0:
            success_case_count = max(_safe_int(row.get("success_count"), 0), 0)
            if success_case_count > 0:
                pass_rate = (success_case_count * 100.0) / total_case_count
        if pass_rate >= 0:
            pass_rate_weighted_sum += pass_rate * max(run_count_value, 1)
            pass_rate_weight_total += max(run_count_value, 1)
            effective_pass_rate_values.append(pass_rate)

        details_payload: Dict[str, Any] = {}
        raw_details = row.get("details_json")
        if raw_details is None:
            raw_details = row.get("details")
        if isinstance(raw_details, dict):
            details_payload = raw_details
        elif isinstance(raw_details, str) and raw_details.strip():
            try:
                parsed = json.loads(raw_details)
                if isinstance(parsed, dict):
                    details_payload = parsed
            except Exception:
                details_payload = {}

        for key, target in (
            ("failure_counts", failure_counts),
            ("tool_mode_counts", tool_mode_counts),
            ("target_agent_counts", target_agent_counts),
            ("freshness_status_counts", freshness_status_counts),
        ):
            source = details_payload.get(key)
            if not isinstance(source, dict):
                continue
            for raw_name, raw_count in source.items():
                name = str(raw_name or "").strip()
                if not name:
                    continue
                target[name] = target.get(name, 0) + max(_safe_int(raw_count), 0)

        structured_stats = details_payload.get("structured_citation_stats")
        if isinstance(structured_stats, dict):
            avg_value = _safe_float(structured_stats.get("average_count"), -1.0)
            if avg_value >= 0:
                structured_avg_values.append(avg_value)
            structured_total_values.append(max(_safe_int(structured_stats.get("total_count"), 0), 0))

        failed_debug_entries = details_payload.get("failed_case_debug_entries")
        if isinstance(failed_debug_entries, list):
            for failed_item in failed_debug_entries:
                if not isinstance(failed_item, dict):
                    continue
                case_id = str(failed_item.get("case_id") or "").strip()
                if not case_id:
                    continue
                failed_case_counts[case_id] = failed_case_counts.get(case_id, 0) + 1
                if case_id not in failed_case_samples:
                    categories = []
                    raw_categories = failed_item.get("failure_categories")
                    if isinstance(raw_categories, list):
                        categories = [
                            str(category).strip()
                            for category in raw_categories
                            if str(category).strip()
                        ]
                    failed_case_samples[case_id] = {
                        "case_id": case_id,
                        "question_id": str(failed_item.get("question_id") or "").strip() or None,
                        "tool_mode": str(failed_item.get("tool_mode") or "").strip() or None,
                        "freshness_status": str(failed_item.get("freshness_status") or "").strip() or None,
                        "failure_categories": categories,
                    }

    if pass_rate_weight_total > 0:
        avg_pass_rate = round(pass_rate_weighted_sum / pass_rate_weight_total, 2)
    elif (total_passed_cases + total_failed_cases) > 0:
        avg_pass_rate = round(
            (total_passed_cases * 100.0) / (total_passed_cases + total_failed_cases),
            2,
        )
    else:
        avg_pass_rate = 0.0
    min_pass_rate = (
        round(min(effective_pass_rate_values), 2)
        if effective_pass_rate_values
        else avg_pass_rate
    )
    max_pass_rate = (
        round(max(effective_pass_rate_values), 2)
        if effective_pass_rate_values
        else avg_pass_rate
    )
    avg_structured_citation_count = (
        round(sum(structured_avg_values) / len(structured_avg_values), 3)
        if structured_avg_values
        else 0.0
    )
    routing_mismatch_count = max(_safe_int(failure_counts.get("routing_mismatch"), 0), 0)
    top_failure_categories = [
        {"category": category, "count": count}
        for category, count in sorted(
            (
                (str(category).strip(), max(_safe_int(count), 0))
                for category, count in failure_counts.items()
                if str(category).strip()
            ),
            key=lambda item: (-item[1], item[0]),
        )
        if count > 0
    ][:5]
    top_failed_cases = []
    for case_id, count in sorted(
        failed_case_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )[:5]:
        sample = failed_case_samples.get(case_id, {})
        top_failed_cases.append(
            {
                "case_id": case_id,
                "question_id": sample.get("question_id"),
                "tool_mode": sample.get("tool_mode"),
                "freshness_status": sample.get("freshness_status"),
                "failure_categories": sample.get("failure_categories") or [],
                "count": count,
            }
        )

    health_status = "healthy"
    health_reason = "weekly_thresholds_passed"
    if total_runs < min_runs:
        health_status = "warning"
        health_reason = f"insufficient_runs:{total_runs}<{min_runs}"
    elif avg_pass_rate < min_avg_pass_rate:
        health_status = "warning"
        health_reason = f"avg_pass_rate:{avg_pass_rate:.2f}<{min_avg_pass_rate:.2f}"
    elif warning_runs > max_warning_runs:
        health_status = "warning"
        health_reason = f"warning_runs:{warning_runs}>{max_warning_runs}"
    elif routing_mismatch_count > max_routing_mismatch:
        health_status = "warning"
        health_reason = f"routing_mismatch:{routing_mismatch_count}>{max_routing_mismatch}"
    elif avg_structured_citation_count < min_structured_avg:
        health_status = "warning"
        health_reason = (
            f"avg_structured_citation_count:{avg_structured_citation_count:.3f}<{min_structured_avg:.3f}"
        )

    summary = {
        "window_days": window_days,
        "cutoff_utc": cutoff.isoformat(),
        "total_runs": total_runs,
        "success_runs": success_runs,
        "warning_runs": warning_runs,
        "failed_runs": failed_runs,
        "total_passed_cases": total_passed_cases,
        "total_failed_cases": total_failed_cases,
        "avg_pass_rate_pct": avg_pass_rate,
        "min_pass_rate_pct": min_pass_rate,
        "max_pass_rate_pct": max_pass_rate,
        "avg_structured_citation_count": avg_structured_citation_count,
        "routing_mismatch_count": routing_mismatch_count,
        "failure_counts": dict(sorted(failure_counts.items())),
        "top_failure_categories": top_failure_categories,
        "top_failed_cases": top_failed_cases,
        "tool_mode_counts": dict(sorted(tool_mode_counts.items())),
        "target_agent_counts": dict(sorted(target_agent_counts.items())),
        "freshness_status_counts": dict(sorted(freshness_status_counts.items())),
        "structured_citation_total": sum(structured_total_values),
        "thresholds": {
            "min_runs": min_runs,
            "min_avg_pass_rate": min_avg_pass_rate,
            "max_warning_runs": max_warning_runs,
            "max_routing_mismatch": max_routing_mismatch,
            "min_structured_citation_avg": min_structured_avg,
        },
        "status": health_status,
        "status_reason": health_reason,
    }

    finished_at = datetime.now()
    _record_collection_run_report(
        job_code=GRAPH_RAG_PHASE5_WEEKLY_REPORT_JOB_CODE,
        success_count=total_passed_cases,
        failure_count=total_failed_cases,
        run_success=True,
        started_at=started_at,
        finished_at=finished_at,
        status_override=health_status,
        details=summary,
    )

    logger.info(
        "Phase 5 GraphRAG 주간 리포트 완료: status=%s reason=%s runs=%s avg_pass_rate=%.2f",
        health_status,
        health_reason,
        total_runs,
        avg_pass_rate,
    )
    return summary


def setup_graph_rag_phase5_weekly_report_scheduler():
    """
    Phase 5 GraphRAG 주간 요약 리포트 스케줄을 설정합니다.
    기본값은 매주 월요일 08:20(KST)입니다.
    """
    try:
        enabled = _truthy_env(
            os.getenv("GRAPH_RAG_PHASE5_WEEKLY_REPORT_ENABLED", "1"),
            default=True,
        )
        schedule_day = str(
            os.getenv("GRAPH_RAG_PHASE5_WEEKLY_REPORT_SCHEDULE_DAY", "monday") or "monday"
        ).strip().lower()
        schedule_time = str(
            os.getenv("GRAPH_RAG_PHASE5_WEEKLY_REPORT_SCHEDULE_TIME", "08:20") or "08:20"
        ).strip()
        report_days = max(_safe_int(os.getenv("GRAPH_RAG_PHASE5_WEEKLY_REPORT_WINDOW_DAYS", "7"), 7), 1)

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "graph_rag_phase5_weekly_report" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 Phase 5 GraphRAG 주간 리포트 스케줄 제거: {job}")

        if not enabled:
            logger.info("Phase 5 GraphRAG 주간 리포트 스케줄 비활성화(GRAPH_RAG_PHASE5_WEEKLY_REPORT_ENABLED=0)")
            return

        weekday_methods = {
            "monday": schedule.every().monday,
            "tuesday": schedule.every().tuesday,
            "wednesday": schedule.every().wednesday,
            "thursday": schedule.every().thursday,
            "friday": schedule.every().friday,
            "saturday": schedule.every().saturday,
            "sunday": schedule.every().sunday,
        }
        job_builder = weekday_methods.get(schedule_day)
        if job_builder is None:
            schedule_day = "monday"
            job_builder = weekday_methods[schedule_day]

        job_builder.at(schedule_time).do(
            run_threaded,
            run_graph_rag_phase5_weekly_report,
            days=report_days,
        ).tag("graph_rag_phase5_weekly_report")
        logger.info(
            "Phase 5 GraphRAG 주간 리포트 스케줄 등록: 매주 %s %s 실행(window_days=%s)",
            schedule_day,
            schedule_time,
            report_days,
        )
    except Exception as e:
        logger.error(f"Phase 5 GraphRAG 주간 리포트 스케줄 설정 실패: {e}", exc_info=True)
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


def setup_kr_top50_ohlcv_scheduler():
    """
    KR Top50 일별 OHLCV 수집 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("KR_TOP50_OHLCV_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("KR_TOP50_OHLCV_SCHEDULE_TIME", "16:20") or "16:20"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "kr_top50_ohlcv_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 KR Top50 OHLCV 스케줄 제거: {job}")

        if not enabled:
            logger.info("KR Top50 OHLCV 스케줄 비활성화(KR_TOP50_OHLCV_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_kr_top50_ohlcv_hotpath_from_env,
        ).tag("kr_top50_ohlcv_daily")
        logger.info(
            "KR Top50 OHLCV 스케줄 등록: 매일 %s 실행",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"KR Top50 OHLCV 스케줄 설정 실패: {e}", exc_info=True)
        raise


def setup_us_top50_ohlcv_scheduler():
    """
    US Top50 일별 OHLCV 수집 스케줄을 설정합니다.
    기본값은 매일 지정 시각 1회 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("US_TOP50_OHLCV_ENABLED", "1"), default=True)
        schedule_time = str(
            os.getenv("US_TOP50_OHLCV_SCHEDULE_TIME", "07:10") or "07:10"
        ).strip()

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "us_top50_ohlcv_daily" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 US Top50 OHLCV 스케줄 제거: {job}")

        if not enabled:
            logger.info("US Top50 OHLCV 스케줄 비활성화(US_TOP50_OHLCV_ENABLED=0)")
            return

        schedule.every().day.at(schedule_time).do(
            run_threaded,
            run_us_top50_ohlcv_hotpath_from_env,
        ).tag("us_top50_ohlcv_daily")
        logger.info(
            "US Top50 OHLCV 스케줄 등록: 매일 %s 실행",
            schedule_time,
        )
    except Exception as e:
        logger.error(f"US Top50 OHLCV 스케줄 설정 실패: {e}", exc_info=True)
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


def setup_tier1_corporate_event_sync_scheduler():
    """
    KR/US Tier-1 이벤트 표준 스키마 동기화 스케줄을 설정합니다.
    기본값은 1시간마다 실행입니다.
    """
    try:
        enabled = _truthy_env(os.getenv("TIER1_EVENT_SYNC_ENABLED", "1"), default=True)
        interval_minutes = max(int(os.getenv("TIER1_EVENT_SYNC_INTERVAL_MINUTES", "60")), 1)

        existing_jobs = schedule.get_jobs()
        for job in existing_jobs:
            if "tier1_corporate_event_sync" in job.tags:
                schedule.cancel_job(job)
                logger.info(f"기존 Tier-1 이벤트 표준 동기화 스케줄 제거: {job}")

        if not enabled:
            logger.info("Tier-1 이벤트 표준 동기화 스케줄 비활성화(TIER1_EVENT_SYNC_ENABLED=0)")
            return

        schedule.every(interval_minutes).minutes.do(
            run_threaded,
            sync_tier1_corporate_events_from_env,
        ).tag("tier1_corporate_event_sync")
        logger.info(
            "Tier-1 이벤트 표준 동기화 스케줄 등록: 매 %s분마다 실행",
            interval_minutes,
        )
    except Exception as e:
        logger.error(f"Tier-1 이벤트 표준 동기화 스케줄 설정 실패: {e}", exc_info=True)
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
    setup_policy_document_scheduler()
    setup_kr_housing_policy_document_scheduler()
    setup_tier1_corporate_event_sync_scheduler()
    setup_graph_news_extraction_scheduler()
    setup_graph_rag_phase5_regression_scheduler()
    setup_graph_rag_phase5_weekly_report_scheduler()
    
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
        setup_policy_document_scheduler()
        logger.info("정책기관 문서 수집 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"정책기관 문서 수집 스케줄 설정 실패: {e}")

    try:
        setup_kr_housing_policy_document_scheduler()
        logger.info("KR 주택정책 문서 수집 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR 주택정책 문서 수집 스케줄 설정 실패: {e}")

    try:
        setup_kr_macro_scheduler()
        logger.info("KR 거시 수집 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR 거시 수집 스케줄 설정 실패: {e}")

    try:
        setup_kr_real_estate_scheduler()
        logger.info("KR 부동산 수집 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR 부동산 수집 스케줄 설정 실패: {e}")

    try:
        setup_graph_news_extraction_scheduler()
        logger.info("Macro Graph 뉴스 추출 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"Macro Graph 뉴스 추출 스케줄 설정 실패: {e}")

    try:
        setup_graph_rag_phase5_regression_scheduler()
        logger.info("Phase 5 GraphRAG 회귀 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"Phase 5 GraphRAG 회귀 스케줄 설정 실패: {e}")

    try:
        setup_graph_rag_phase5_weekly_report_scheduler()
        logger.info("Phase 5 GraphRAG 주간 리포트 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"Phase 5 GraphRAG 주간 리포트 스케줄 설정 실패: {e}")
    
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
        setup_kr_top50_ohlcv_scheduler()
        logger.info("KR Top50 OHLCV 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"KR Top50 OHLCV 스케줄 설정 실패: {e}")

    try:
        setup_us_top50_ohlcv_scheduler()
        logger.info("US Top50 OHLCV 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"US Top50 OHLCV 스케줄 설정 실패: {e}")

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
        setup_tier1_corporate_event_sync_scheduler()
        logger.info("Tier-1 이벤트 표준 동기화 스케줄 설정 완료")
    except Exception as e:
        logger.error(f"Tier-1 이벤트 표준 동기화 스케줄 설정 실패: {e}")

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
