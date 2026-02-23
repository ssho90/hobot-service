# [Phase 1] 도메인 특화 자율 분석 파이프라인 구축 (Domain-Specific Refinement)

## 1. 현재 구조 분석 (AS-IS)
현재 코드베이스 (`live_executor.py` 및 `agents` 폴더 내 도우미 스크립트)를 분석한 결과, 각 도메인 에이전트(예: `equity_agent.py`)는 **자체적인 LLM 분석 과정 없이** 단순히 `execute_live_tool()` 결과를 받아 데이터 구조만 약간 매핑한 후(예: primary_store, focus_symbols 등 추가) 상위로 전달하는 "DB/Graph 조회 브로커" 역할에 불과합니다.
LLM 프롬프팅이나 결과 해석을 수행하지 않고 원시 레코드(SQL 검색 결과, Graph 노드/엣지 내용)를 `tool_probe`라는 키 안에 덤프(dump)하여 바로 슈퍼에이전트 단말 파라미터(`StructuredDataContextCompact`)에 주입하고 있습니다.

## 2. 작업 목표 (TO-BE)
도메인 에이전트는 원시 데이터를 스스로 "해석/분석"하여 결론과 명확한 수치/근거를 내놓도록 **강제**해야 합니다.

* **수정 대상 지점:** 
  - `agents/{domain}_agent.py` 내의 `run_{domain}_agent_stub()` 함수들.
  - 현재 단순히 `execute_live_tool()` 결과를 리턴하는 데에서 그치지 않고, 내부적으로 `Domain LLM`(Pydantic/Structured Output parser 결합)을 한 번 더 호출하도록 레이어를 끼워 넣습니다.
* **로직 흐름 변경:**
  1. 기존 `execute_live_tool()` 실행하여 원본 데이터 획득 (AS-IS 부분 유지)
  2. (신규) 획득한 원본 데이터를 해당 도메인 특화 LLM 프롬프트에 주입.
  3. (신규) 도메인 특화 LLM이 이를 분석하여 `DomainInsight` JSON 객체 1개를 생성.
  4. 도메인 에이전트는 원본 데이터 대신 `DomainInsight` JSON을 상위로 반환.

## 3. 도메인별 세부 분석 내용 (LLM Prompting 지침)

### A. Equity Analyst Agent (주식 및 거시경제 분석 전담)
* **LLM 주입 데이터:** `tool_probe` 내부의 OHLCV 시계열, MA(이동평균) 결괏값, 빈티지 단위 거시경제 지표.
* **LLM 판단 목표:** 단순 가격 데이터의 나열이 아니라, "현재 20일 이평선이 60일 이평선을 상향 돌파(Golden Cross) 중이므로 단기 강세(BULL) 국면이다", "FRED 실업률 데이터가 X% 증가하여 거시 투심이 꺾이고 있다" 등 경제 국면(Regime)을 진단하고 지표 가중치를 동적 부여합니다.

### B. Real Estate Agent (부동산 시장 분석 전담)
* **LLM 주입 데이터:** 해당 지역 실거래가 평균, 거래량 변동률 등 쿼리된 부동산 통계와 LTV, 대출 금리 등의 관련 거시 파라미터.
* **LLM 판단 목표:** "송파구 아파트 거래량이 전월비 증가했으나 평균 실거래가는 보합이므로 매수 대기세가 유입 중이다" 혹은 정책 데이터(예: 규제 해제)의 텍스트를 인식하여 미래의 수익률/수급 압력을 시뮬레이션한 입체적 가치 모델링을 도출합니다.

### C. Ontology Master Agent (글로벌 이벤트 및 파급 전담)
* **LLM 주입 데이터:** FIBO 스키마로 조회된 기업 M&A, 임원 리스크, 자연재해 등 그래프 데이터베이스 패스(Path).
* **LLM 판단 목표:** 이벤트와 기업 간의 단순 그래프 텍스트가 아닌, A 이벤트가 하청 공급망 B를 거쳐 최종 시장 C에 미치는 충격 스코어(Impact Score)와 Ripple Effect 크기를 계산해 "이 사건은 C 분야에 8.5/10 만큼의 부정적 연쇄 타격을 줄 것"이라고 추론합니다.

## 4. 진행 현황
- [x] 현재 코드베이스(Agent Stub 파이프라인)의 한계점 확인
- [x] Phase 1: 역할에 따른 도메인 에이전트 수정 계획 확정
- [x] Pydantic 모델을 통한 각 도메인 에이전트 응답 구조 정의 (`Structured Outputs` 도입) - `_build_agent_execution_prompt`에 DomainInsight JSON 스키마 정의 완료
- [x] `live_executor.py` 및 `{domain}_agent.py` 레벨에서 LLM 체인 연동 코드 이식 - `_execute_branch_agents`에서 도메인 LLM 호출 + Retry/Fallback 구현 완료
