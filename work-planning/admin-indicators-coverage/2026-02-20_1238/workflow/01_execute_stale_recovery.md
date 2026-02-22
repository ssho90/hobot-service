# Workflow Log - Stale Indicators Recovery

## 실행 예정
- `collect_recent_news`
- `sync_tier1_corporate_events_from_env`
- `run_kr_top50_earnings_hotpath_from_env`
- `run_graph_news_extraction_sync`
- `get_macro_indicator_health_snapshot`

## 비고
- 본 작업은 DB/외부 API/Neo4j 접근이 필요하여 권한 상승 실행으로 검증한다.

## 실행 결과
1. 배치 실행
- `collect_recent_news` -> saved 0 / skipped 19
- `sync_tier1_corporate_events_from_env` -> normalized 601 / db_affected 1193 / health_status healthy
- `run_kr_top50_earnings_hotpath_from_env` -> 신규 실적 이벤트 0 (첫 실행에서는 run report warning 상태 잔존)
- `run_graph_news_extraction_sync` -> sync_documents 2000 / extraction_success 2 / embedding_embedded 5

2. 중간 상태
- `healthy 58 / stale 3 / missing 0`
- stale: `ECONOMIC_NEWS_STREAM`, `GRAPH_DOCUMENT_EMBEDDING_COVERAGE`, `TIER1_CORPORATE_EVENT_FEED`

## 🔴 에러 원인
- **지연 계산 타임존 불일치**: `indicator_health._build_health()`가 로컬 시각(`datetime.now`) 기준으로 lag를 계산하는 반면, 여러 테이블(`economic_news`, `corporate_event_feed`, graph timestamps)의 `updated_at`/timestamp 값은 UTC 기준으로 저장되어 약 +9시간 과대 지연으로 판정됨.

## 수정 사항
- `hobot/service/macro_trading/indicator_health.py`
  - `_build_health()` 기본 현재시각을 UTC-naive(`datetime.now(timezone.utc).replace(tzinfo=None)`)로 통일.
  - (이전 단계 반영 포함) `_coerce_reference_timestamp()`의 문자열/Neo4j temporal 파싱 보강.

## 추가 실행
- `run_kr_top50_earnings_hotpath_from_env` 1회 재실행
  - `failed_requests=0`으로 run report `last_status=healthy` 반영.

## 최종 검증
- health snapshot: `healthy 61 / stale 0 / missing 0`
- 국가별:
  - GLOBAL: 5 healthy
  - KR: 25 healthy
  - US: 31 healthy

## 테스트
- `PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_indicator_health -v`
- 결과: 11 tests, 모두 통과.
