# 진단 및 수정 로그

## 원인
- 증상: `Earnings expectation feed fetch failed: (1038, Out of sort memory)`
- 1차 원인: `kr_corporate_earnings_expectations` 내부피드 조회 SQL이 `ORDER BY expected_as_of_date DESC, updated_at DESC`를 강제하여 filesort 발생
- 2차 리스크: Top corp fallback의 revenue 정렬 SQL도 대용량 환경에서 동일한 sort 메모리 위험

## 수정
1. 내부피드 조회 정렬 제거
- 파일: `hobot/service/macro_trading/collectors/kr_corporate_collector.py`
- 변경: expectation 조회 SQL에서 `ORDER BY` 제거

2. 애플리케이션 최신값 dedupe로 대체
- 키: `(corp_code, period_year, fiscal_quarter, metric_key, expected_source)`
- 우선순위: `(expected_as_of_date, updated_at)` 최대값 선택
- 효과: DB sort 의존 제거 + 기존 최신값 선택 의미 유지

3. 인덱스 자동 보강
- 테이블: `kr_corporate_earnings_expectations`
- 인덱스: `idx_expectation_feed_lookup (corp_code, expected_source, period_year, fiscal_quarter, expected_as_of_date, updated_at)`
- `ensure_tables()`에서 없는 환경에 자동 생성

4. fallback 내구성 강화
- revenue 정렬 SQL 실패 시 예외를 로깅하고 `kr_dart_corp_codes ORDER BY stock_code` fallback으로 계속 진행

## 검증
- 실행: `cd hobot && PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_kr_corporate_collector -v`
- 결과: `Ran 26 tests ... OK`
- 신규 테스트:
  - `test_fetch_expectation_rows_from_internal_feed_prefers_latest_row_without_sql_order`
  - `test_resolve_top_corp_codes_for_expectation_feed_fallback_on_revenue_sort_error`
