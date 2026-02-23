# [Phase 3 & 4] 슈퍼에이전트 오케스트레이션 개편 및 안정화 (Fallback/Retry)

## 1. 운영 안정성 (Fallback & Retry) 구현 내역
도메인 에이전트의 구조화된 결괏값을 슈퍼에이전트가 안전하게 파싱 및 취합할 수 있게, 아래의 방어 로직을 `response_generator.py`의 `_execute_branch_agents` 및 관련 함수에 구현합니다.

* **최대 1회 재시도 (Retry):**
    * 도메인 LLM API를 호출(`agent_llm.invoke()`)했을 때 타임아웃 오류(Timeout)나 `agent_raw_json` 형식이 파싱 불가능한 깨진 상태인 경우, 예외를 던지지 않고 즉시 동일한 프롬프트로 1회 재시도하도록 `try-except` 블록을 구성합니다.
* **Safe Fallback (Empty JSON 리턴):**
    * 재시도마저 실패하거나 알 수 없는 이유로 에러가 발생했을 때, `run_result["agent_llm"]`의 상태를 `fallback`으로 남기고, `_normalize_agent_execution_payload`에 의해 규격화된 "텅 빈(또는 중립적인) DomainInsight" 구조체를 반환하도록 합니다.
    * 이로써 한 도메인 에이전트(`equity`)가 에러가 났더라도 다른 성공한 도메인(`macro`)의 분석 결과를 살려내 시스템 치명타(Crash)를 막습니다.

## 2. 슈퍼에이전트 (Supervisor Agent) 합성(Synthesis) 로직 개편
이전에 도메인 에이전트들이 뱉어낸 `StructuredDataContextCompact`가 거대해지면서 슈퍼에이전트의 프롬프트에서 `truncation(자르기)`이 일어났던 현상을 해결합니다.

* **[AS-IS] `_make_prompt()`**:
    * 원본 텍스트(News Evidences), SQL 결과물의 로우 데이터(Datasets), 그래프 노드(GraphContextCompact) 등이 무분별하게 들어감.
* **[TO-BE] `_make_prompt()`**:
    * 도메인 에이전트 성공 여부를 체크하여 `domain_source`, `confidence_score`, `primary_trend`, `key_drivers`, `analytical_summary` 로 이루어진 `[DomainInsights]`를 핵심 판별 파라미터로 격상.
    * 슈퍼에이전트의 프롬프트 룰에 **"서호환되거나 상충(Conflict)되는 도메인 에이전트 간의 primary_trend(BULL vs BEAR)를 분석하고 조율(Reflective Reasoning)하여 최종 일관된 견해를 제시하라"**는 명시적 비평가(Critic) 역할을 부여함.
    * 불필요한 원시 데이터(truncation 유발 요소) 제거 및 다이어트 완료.

## 3. 진행 현황
- [x] Phase 3 & 4 목표 및 예외 전략 설정 완료
- [ ] `_execute_branch_agents` 내에 Retry/Fallback 블록 구현
- [ ] `_make_prompt` 슈퍼에이전트 프롬프트에 도메인 인사이트 합성 지침 및 충돌해결 (Debate) 로직 부여
