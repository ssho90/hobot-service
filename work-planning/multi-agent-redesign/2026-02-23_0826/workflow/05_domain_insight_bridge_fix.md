# [Phase 2 보완] DomainInsight 스키마 브릿지 수정 (Structured Output ↔ Supervisor Prompt 연결)

## 1. 문제 진단

### 핵심 이슈: DomainInsight가 슈퍼에이전트에 전달되지 않음
도메인 에이전트(`_execute_branch_agents`)는 Phase 1/2 개선으로 DomainInsight 형식의 payload를 정상 생성하지만,
슈퍼에이전트 프롬프트에 주입하는 중간 함수들이 **구(舊) 필드명**으로 읽고 있어 데이터가 유실됨.

### 영향 범위
- `_build_structured_data_context_for_supervisor` (2534~2572행): payload에서 `summary`, `key_points`, `risks`, `confidence` 로 읽음
  → 새 스키마의 `analytical_summary`, `key_drivers`, `primary_trend`, `confidence_score`, `quantitative_metrics`, `domain_source`를 무시
- `_compact_structured_data_for_prompt` (1986~2001행): agent_insights를 프롬프트용으로 compact할 때 구(舊) 필드 구조 사용
  → 슈퍼에이전트가 `primary_trend`, `domain_source`, `quantitative_metrics` 등을 볼 수 없음
- **결론**: 도메인 에이전트가 아무리 좋은 분석을 해도 슈퍼에이전트는 빈 값만 받음 → 실질적으로 Phase 1~3 개선이 무효화

## 2. 수정 대상

### A. `_build_structured_data_context_for_supervisor` 내부 agent_insights 생성 로직 (2550~2572행)
- **AS-IS**: `payload.get("summary")`, `payload.get("key_points")`, `payload.get("risks")`, `payload.get("confidence")`
- **TO-BE**: `payload.get("analytical_summary")`, `payload.get("key_drivers")`, `payload.get("primary_trend")`, `payload.get("confidence_score")`, `payload.get("quantitative_metrics")`, `payload.get("domain_source")`
- `agent_llm.status == "ok"` 뿐 아니라 `"degraded"` (fallback) 결과도 포함하여 슈퍼에이전트가 "이 도메인은 분석 실패" 상태를 인지

### B. `_compact_structured_data_for_prompt` 내부 agent_insights compact 로직 (1986~2001행)
- **AS-IS**: `{"agent", "summary", "key_points", "risks", "confidence"}` 형식
- **TO-BE**: `{"domain_source", "primary_trend", "confidence_score", "key_drivers", "quantitative_metrics", "analytical_summary"}` 형식

### C. `USE_STRUCTURED_HANDOFF` 런타임 롤백 플래그 추가
- `_execute_branch_agents`의 `agent_llm_enabled` 분기 앞에 환경변수 체크 추가
- `USE_STRUCTURED_HANDOFF=false`이면 DomainInsight 파이프라인을 우회하고 기존 방식으로 동작

## 3. 작업 순서
1. `_build_structured_data_context_for_supervisor` DomainInsight 필드 매핑 수정
2. `_compact_structured_data_for_prompt` DomainInsight compact 형식 수정
3. `USE_STRUCTURED_HANDOFF` 플래그 분기 추가
4. 워크플로우 진행 현황 문서 업데이트
