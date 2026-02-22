# 실행 로그

## 1) 현황 진단
- `supervisor_agent` 프롬프트에 `RoutingDecision`, `GraphContext`, `StructuredDataContext` 원본이 과다 주입되는 구간 확인.
- `real_estate_detail` 라우트가 기본적으로 SQL+Graph 병렬 전략을 타는 경로 확인.
- `graph_need=false`여도 컨텍스트 조회량이 기본 top-k를 그대로 사용하는 경로 확인.

## 2) 구현 예정
- 프롬프트 축약 헬퍼 추가
- 프롬프트 예산 초과 시 자동 축소 가드 추가
- `real_estate_detail` 조건부 병렬 전략 보수화
- context top-k 동적 축소 반영

## 3) 구현 완료
- `GraphRagAnswerRequest.to_context_request()`에 `graph_need=false`일 때 top-k 자동 축소 로직 반영.
- `_derive_conditional_parallel_strategy()`에서 `real_estate_detail` 기본 전략을 `sql_need=true, graph_need=false`로 변경.
- `_make_prompt()`를 경량화 구조로 개편:
  - `RoutingDecisionCompact`, `GraphContextCompact`, `StructuredDataContextCompact` 블록으로 축약
  - evidence 텍스트 길이 제한, 링크 기본 비포함
  - `agent_insights` 존재 시 insight-first로 컨텍스트 축소
  - 프롬프트 토큰 추정 기반 단계적 축소 가드(링크 제거→evidence 축소→섹션 축소)
- 프롬프트 보조 헬퍼 추가:
  - `_compact_route_for_prompt`
  - `_compact_structured_data_for_prompt`
  - `_build_compact_graph_context_for_prompt`
  - `_truncate_prompt_text`, `_estimate_prompt_tokens`
- 기존 테스트 기대치 반영:
  - `test_make_prompt_includes_structured_data_context`의 섹션 라벨을 `StructuredDataContextCompact`로 업데이트.

## 4) 검증 결과
- 문법 검사: `py_compile` 통과
- 단위 테스트: `test_phase_d_response_generator.py` 54건 통과 (`skipped=2`)
  - 테스트 환경 제약으로 MySQL 연결 경고 로그는 다수 출력되었으나 테스트 결과는 PASS.

## 5) 실측 리포트 생성
- `llm_usage_logs`에서 개선 시점(`2026-02-22 09:54:00`) 기준 전/후 질의 로그를 비교 집계.
- 대상 질의 3개:
  - 한국 부동산 가격 전망
  - 팔란티어 주가
  - 미국 금리/물가가 경기 전망에 미친 영향
- 리포트 파일:
  - `work-planning/supervisor-load-optimization/2026-02-22_0954/workflow/02_prompt_latency_before_after_report.md`
