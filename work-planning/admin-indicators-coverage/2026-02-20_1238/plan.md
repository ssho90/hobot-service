# Admin Indicators Stale Recovery Plan

## 목표
- `/admin/indicators`에서 stale로 표시되는 핵심 파이프라인 지표를 즉시 갱신한다.
- 대상: `ECONOMIC_NEWS_STREAM`, `TIER1_CORPORATE_EVENT_FEED`, `KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE`, `GRAPH_DOCUMENT_EMBEDDING_COVERAGE`.

## 실행 전략
1. 경제 뉴스 수집 실행 (`collect_recent_news`).
2. Tier1 기업 이벤트 동기화 실행 (`sync_tier1_corporate_events_from_env`).
3. KR Top50 실적 감시 실행 (`run_kr_top50_earnings_hotpath_from_env`).
4. Graph 뉴스 추출+임베딩 실행 (`run_graph_news_extraction_sync`).
5. health snapshot 재조회로 stale/missing 상태 확인.

## 완료 기준
- 대상 지표가 stale에서 해소되거나, 최소한 최신 실행 시각 및 실패 원인이 명확히 업데이트된다.
