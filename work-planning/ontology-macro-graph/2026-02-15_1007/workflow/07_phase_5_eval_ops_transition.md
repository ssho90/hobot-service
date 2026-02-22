# Phase 5 상세 계획: 평가/운영 전환

## 1. 목표
- US/KR QA 및 KR 부동산 응답 품질을 골든셋/회귀 테스트로 정량 검증한다.
- 신선도/커버리지/SLA 대시보드를 운영 기준으로 전환한다.
- 장애 대응 플레이북과 운영 절차를 확정해 실서비스 운영 상태로 전환한다.

## 2. 기간
- 권장 기간: 2026-05-18 ~ 2026-05-29 (2주)

## 3. 작업 스트림
### 3.1 골든셋 구축/관리
- [ ] 골든 질의 160개 구성(US 단일/KR 단일/US-KR 비교/KR 부동산)
- [x] 필수 질문 6개(Q1~Q6) 고정 회귀 세트 등록
- [ ] 질문별 기대 근거 타입/최소 근거 수 정의

### 3.2 자동 회귀 테스트 파이프라인
- [ ] JSON 스키마 검증 + 정답 적합도 평가 자동화
- [ ] PR/배포 전 회귀 파이프라인 연결
- [x] 실패 유형 분류(근거 누락/지연/스코프 오류/가드레일 위반) 리포트 자동 생성

예상 대상 테스트
- `hobot/tests/test_phase_d_response_generator.py`
- `hobot/tests/test_phase_d_monitoring.py`
- `hobot/service/macro_trading/tests/test_replay_regression.py`

### 3.3 운영 KPI 대시보드
- [ ] Freshness/커버리지/SLA 대시보드 구성
- [ ] 소스별 일일 성공률, DLQ 적재량, 재처리 시간 시각화
- [ ] KR 부동산 지역 매핑 정확도 및 반영 지연 모니터링

예상 대상 코드
- `hobot/service/graph/monitoring/graphrag_metrics.py`
- `hobot/service/graph/impact/quality_metrics.py`

### 3.4 운영 가이드/장애 대응 플레이북
- [ ] 수집 실패/스키마 드리프트/품질 저하 대응 절차 문서화
- [ ] 온콜 체크리스트(탐지 5분, 복구 2시간 목표) 확정
- [ ] 릴리즈 승인 게이트(KPI 달성 기준) 운영화

예상 산출물
- `hobot/docs/operations/ontology_macro_graph_runbook.md`

## 4. 완료 기준 (Go-Live Gate)
- 골든셋 기준 QA 적합도 80% 이상
- 근거 인용 누락률 2% 이하
- 주요 파이프라인 일일 성공률 99% 이상
- 장애 탐지 5분 이내, 재처리 완료 2시간 이내 기준 충족

## 5. 리스크/대응
- 리스크: 골든셋 편향으로 실제 질의 일반화 실패
- 대응: 운영 로그 기반 샘플링으로 골든셋 월간 갱신
- 리스크: 운영 지표는 양호하나 답변 품질 체감 저하
- 대응: 정량 KPI + 전문가 리뷰(주간) 병행

## 6. 운영 전환 산출물 패키지
- 릴리즈 노트
- KPI 달성 리포트
- 회귀 테스트 결과 요약
- 장애 대응 플레이북

---

## 진행 현황 업데이트 (2026-02-20, 1차)
- [x] Phase 5 골든셋/자동 회귀 착수 구현(초기)
  - 구현 파일:
    - `hobot/service/graph/monitoring/phase5_regression.py`
    - `hobot/service/graph/monitoring/golden_sets/phase5_q1_q6_v1.json`
    - `hobot/tests/test_phase5_golden_regression.py`
  - 반영 항목:
    - 골든셋 파일 로드/검증 유틸
    - 케이스별 자동 판정(필수키/근거수/신선도/스코프/가드레일)
    - 실패 유형 분류 집계 리포트
      - `schema_mismatch`, `citation_missing`, `freshness_stale`, `scope_violation`, `guardrail_violation`, `evaluator_error`
- [x] 테스트 검증
  - `tests/test_phase5_golden_regression.py`: `Ran 4 tests ... OK`
  - `tests/test_phase_d_monitoring.py`: `Ran 3 tests ... OK`

## 진행 현황 업데이트 (2026-02-20, 2차)
- [x] Phase 5 자동 회귀 배치/스케줄 연결(일일 운영 경로)
  - 구현 파일:
    - `hobot/service/graph/scheduler/phase5_regression_batch.py`
    - `hobot/service/graph/scheduler/__init__.py`
    - `hobot/service/graph/__init__.py`
    - `hobot/service/macro_trading/scheduler.py`
  - 반영 항목:
    - GraphRAG 답변 생성기(`generate_graph_rag_answer`)를 evaluator로 연결한 실행기 추가
    - 케이스 필터(`GRAPH_RAG_PHASE5_CASE_IDS`) 및 실행 옵션 env 구성
    - 일일 스케줄 등록 함수 추가
      - `setup_graph_rag_phase5_regression_scheduler`
      - 기본 실행 시각: `08:10` (KST)
    - 수집 실행 리포트 테이블(`macro_collection_run_reports`) 기록 연결
      - job_code: `GRAPH_RAG_PHASE5_REGRESSION`
- [x] 연동 테스트 검증
  - `tests/test_phase5_regression_batch_runner.py`: `Ran 3 tests ... OK`
  - `service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`: `Ran 3 tests ... OK`
  - `service/macro_trading/tests/test_scheduler_graph_news_embedding.py`: `Ran 3 tests ... OK`

## 진행 현황 업데이트 (2026-02-20, 3차)
- [x] 실패 케이스 디버깅 리포트 저장 강화
  - 반영 항목:
    - `macro_collection_run_reports.details_json`에 케이스 단위 실패 디버깅 필드 추가
      - `failed_case_debug_total`, `failed_case_debug_returned`, `failed_case_debug_entries`
      - entry 필드: `case_id`, `question_id`, `citation_count`, `failure_categories`, `failure_messages`, `failure_count`
    - 리포트 payload 제한 env 추가
      - `GRAPH_RAG_PHASE5_FAILURE_DEBUG_CASE_LIMIT` (default: `10`)
      - `GRAPH_RAG_PHASE5_FAILURE_DEBUG_MESSAGE_LIMIT` (default: `3`)
- [x] 검증
  - `service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`: `Ran 3 tests ... OK`

## 진행 현황 업데이트 (2026-02-20, 4차)
- [x] 최신 근거 보강 로직 회귀 오류 수정
  - 🔴 **에러 원인:** `hobot/service/graph/rag/response_generator.py`에서 `timedelta` import 누락으로 `NameError`가 발생해 회귀 테스트 다건이 실패.
  - 조치:
    - `from datetime import ... timedelta ...` 추가로 런타임 오류 제거.
- [x] 재검증 완료
  - `tests/test_phase_d_response_generator.py`: `Ran 29 tests ... OK`
  - `tests/test_phase5_golden_regression.py`: `Ran 4 tests ... OK`
  - `tests/test_phase5_regression_batch_runner.py`: `Ran 3 tests ... OK`
  - `service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`: `Ran 3 tests ... OK`
  - 참고: 샌드박스 환경에서 MySQL 접근 권한 제한으로 경고 로그는 출력되지만, 테스트 판정에는 영향 없음.

## 진행 현황 업데이트 (2026-02-20, 5차)
- [x] 실패 케이스 원인 추적용 최신 근거 가드 디버그 필드 확장
  - 반영 파일:
    - `hobot/service/graph/rag/response_generator.py`
    - `hobot/service/graph/monitoring/phase5_regression.py`
    - `hobot/service/macro_trading/scheduler.py`
  - 반영 항목:
    - `context_meta.recent_citation_guard` 추가
      - `enabled`, `target_count`, `max_age_hours`, `require_focus_match`
      - `candidate_recent_evidence_count`, `selected_recent_citation_count`
      - `added_recent_citation_count`, `target_satisfied`
    - Phase 5 `case_results` 및 `failure_debug.entries`에 동일 필드 전달
    - 라우터 LLM 타임아웃 기본값 상향: `GRAPH_RAG_ROUTER_LLM_TIMEOUT_SEC` default `10`
- [x] 테스트 검증
  - `tests/test_phase5_golden_regression.py`: `Ran 5 tests ... OK`
  - `service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`: `Ran 3 tests ... OK`
  - `tests/test_phase_d_response_generator.py`: `Ran 29 tests ... OK`
- [x] 운영 검증 실행
  - 뉴스 동기화(샘플): `sync_news_with_extraction(limit=300)` 성공
  - Phase 5 전체: `total=6, passed=4, failed=2` (`freshness_stale` 2건)
  - 실패 케이스 축약 재실행(Q1/Q5): `total=2, passed=0, failed=2`
    - 두 케이스 공통: `candidate_recent_evidence_count=0`, `selected_recent_citation_count=0`, `target_satisfied=false`
    - 결론: 가드 로직 문제보다 **최근 근거 자체 부재(데이터 공백)**가 직접 원인임을 확인.

## 진행 현황 업데이트 (2026-02-20, 6차)
- [x] Q1/Q5 실패 원인 재진단 및 retrieval/근거 샘플링 보강
  - 🔴 **에러 원인(Q1):** explicit `question_id` 우선 라우팅 시 `us_single_stock_agent`가 누락되어 종목 focus 심볼이 context 요청으로 전달되지 않음.
  - 🔴 **에러 원인(Q5):** 최신 문서는 context에 포함돼도 `top_k_evidences=40` + 문서당 샘플링 제한으로 상위 점수의 구형 문서 근거만 선택되어 freshness가 stale 처리됨.
  - 반영 파일:
    - `hobot/service/graph/rag/response_generator.py`
    - `hobot/service/graph/rag/context_api.py`
    - `hobot/tests/test_phase_d_response_generator.py`
    - `hobot/tests/test_phase_d_context_api.py`
  - 반영 항목:
    - `us_single_stock_agent`를 explicit `question_id` 경로에서도 병행 실행하도록 수정 (focus symbol/company 보존)
    - stock focus(`focus_symbols`/`focus_companies`)가 있으면 route_type과 무관하게 종목 전용 문서 수집 실행
    - `ABOUT_THEME` 링크 희소 구간 보완을 위해 테마 키워드 fallback 검색(`phase_d_documents_by_theme_keywords`) 추가
    - 근거 문서 우선순위에 최신 문서 버킷을 강제 삽입
      - env: `GRAPH_RAG_RECENT_DOC_PRIORITY_COUNT` (default `8`)
      - retrieval meta: `recent_doc_priority_count`, `theme_keyword_docs`
- [x] 테스트/운영 재검증
  - 단위 테스트:
    - `tests/test_phase_d_context_api.py`: `Ran 16 tests ... OK`
    - `tests/test_phase_d_response_generator.py`: `Ran 30 tests ... OK`
    - 신규 검증:
      - explicit `question_id` + 단일종목 focus 보존 테스트
      - non-us_single_stock route에서도 stock focus 수집 테스트
      - theme keyword fallback 동작 테스트
  - 실데이터 회귀:
    - Q1/Q5 재실행: `total=2, passed=2, failed=0`
      - Q1: `candidate_recent_evidence_count=8`, `target_satisfied=true`
      - Q5: `freshness_status=fresh`, `latest_evidence_published_at=2026-02-17T15:02:25+00:00`
    - 전체 골든셋(6개): `total=6, passed=6, failed=0, pass_rate=100%`

## 진행 현황 업데이트 (2026-02-20, 7차)
- [x] 운영 환경값(.env) 고정 및 재검증
  - 반영 파일:
    - `hobot/.env`
  - 추가/명시 env:
    - `GRAPH_RAG_ROUTER_LLM_TIMEOUT_SEC=10`
    - `GRAPH_RAG_RECENT_DOC_PRIORITY_COUNT=8`
    - `GRAPH_RAG_RECENT_CITATION_TARGET_COUNT=1`
    - `GRAPH_RAG_RECENT_CITATION_MAX_AGE_HOURS=168`
    - `GRAPH_RAG_DATA_FRESHNESS_WARN_HOURS=72`
    - `GRAPH_RAG_DATA_FRESHNESS_FAIL_HOURS=168`
- [x] 검증
  - Q1/Q5 회귀 재실행: `total=2, passed=2, failed=0`
  - 결과 유지:
    - Q1 `warning`(최신 근거 연령 144.9h, fail 기준 168h 이내)
    - Q5 `fresh`(최신 근거 연령 57.0h)

## 진행 현황 업데이트 (2026-02-20, 8차)
- [x] 운영값 고정(.env) 기준 전체 골든셋 재검증
  - 실행: `run_phase5_golden_regression_jobs()` (Q1~Q6 전체)
  - 결과: `total=6, passed=6, failed=0, pass_rate=100%`
  - 케이스별 freshness:
    - Q1: `warning` (`age_hours=144.9`)
    - Q2: `warning` (`age_hours=144.9`)
    - Q3: `warning` (`age_hours=160.9`)
    - Q4: `fresh` (`age_hours=11.7`)
    - Q5: `fresh` (`age_hours=57.0`)
    - Q6: `warning` (`age_hours=161.9`)
- [x] 실행 중 관찰 사항
  - Gemini API `504 DEADLINE_EXCEEDED` 1회 발생 후 자동 재시도로 정상 회복.
  - Neo4j `property key does not exist (url)` 경고 반복 확인.
    - 현재 쿼리에서 `coalesce(d.url, d.link)`를 사용 중이라 기능/판정 영향 없음(경고성).

## 진행 현황 업데이트 (2026-02-20, 9차)
- [x] Phase5 회귀 결과 Slack 알림(옵트인) 추가
  - 반영 파일:
    - `hobot/service/macro_trading/scheduler.py`
    - `hobot/service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`
  - 구현 항목:
    - `_send_phase5_regression_alert(...)` 헬퍼 추가
    - `run_graph_rag_phase5_regression` 성공/예외 경로에서 알림 호출
    - Slack 모듈 import 실패/토큰 누락/전송 실패 시 예외를 전파하지 않고 경고 로그로 처리
  - 신규 env:
    - `GRAPH_RAG_PHASE5_ALERT_ENABLED` (default `0`)
    - `GRAPH_RAG_PHASE5_ALERT_ONLY_ON_WARNING` (default `1`)
    - `GRAPH_RAG_PHASE5_ALERT_CHANNEL` (default `#auto-trading-error`)
    - `GRAPH_RAG_PHASE5_ALERT_CASE_LIMIT` (default `3`)
    - `GRAPH_RAG_PHASE5_ALERT_ERROR_MESSAGE_LIMIT` (default `2`)
- [x] 테스트 검증
  - `service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`: `Ran 3 tests ... OK`
  - `tests/test_phase5_regression_batch_runner.py`: `Ran 3 tests ... OK`
