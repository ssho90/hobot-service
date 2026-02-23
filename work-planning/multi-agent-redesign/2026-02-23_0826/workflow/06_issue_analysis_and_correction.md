# [Phase 6 분석] Multi-Agent 아키텍처 결함 진단 및 개선 방안 (2026-02-23)

## 🚨 1. 문제 상황 (What went wrong)

사용자가 지적한 도메인 에이전트(`equity_analyst_agent`) 및 슈퍼 에이전트(`supervisor_agent`)의 Request/Response 프롬프트 덤프를 기반으로 현재 아키텍처의 중대한 설계적/구현적 결함을 확인했습니다. 

### 1.1. 도메인 에이전트 결함: 데이터 기아 상태에 따른 환각 (Data Starvation & Hallucination)
- **목표 (Plan.md L18-L19)**: 주식/거시 에이전트는 OHLCV 기반 기술적 지표, FRED 거시 지표, 재무제표 KPI, 실적 발표 등 **실제 정량적 데이터와 비정형 데이터 원문**을 해석하여 팩트 기반의 결론(DomainInsights)을 도출해야 함.
- **현실 (AS-IS)**: 에이전트의 Request Prompt 내 `[ToolProbe]` 및 `[ContextCounts]` 섹션에 `{ "nodes": 34, "links": 50, "evidences": 10 }` 와 같은 **가공(단순 집계)된 건수 수준의 메타데이터밖에 전달되지 않음**.
- **결과**: `[Rules]`에서는 "OHLCV, FRED 지표를 기반으로 해석하라"고 명령하지만, **볼 수 있는 수치나 데이터 내용이 사실상 존재하지 않습니다**. 이로 인해 LLM은 사전 훈련된 일반적 시장 상식(예: "골든크로스", "CPI 안정화")을 조합하여 그럴싸한(하지만 근거 없는) 하찮은 분석 결과를 **환각(Hallucinate)** 해내는 심각한 오류가 발생했습니다.

### 1.2. 슈퍼 에이전트 결함: 미위임에 따른 정보 과부하 (Context Overload & Lack of Delegation)
- **목표 (Plan.md)**: Supervisor는 Graph DB의 방대한 원시 데이터를 직접 읽는 대신, 각 도메인 에이전트들이 분석 및 정제하여 넘긴 구조화된 `DomainInsights` JSON 데이터만을 취합하고, 그 사이의 상충(Conflict)을 조율(Critic)해야 함.
- **현실 (AS-IS)**: Supervisor Request Prompt를 보면, 최상단 `[GraphContextCompact]` 하위에 `events`, `indicators`, `themes`, `stories`, `evidences`(raw text 포함) 등 그래프 DB의 **무거운 원시 데이터 덩어리가 필터링 없이 그대로 모두 노출**되어 있음.
- **결과**: 결국 Supervisor는 도메인 에이전트의 요약본(`DomainInsights`)만 보고 종합 판단을 내리는 것이 아니라, 예전 단일 프롬프트 방식처럼 원본 데이터를 다시 훑어보게 되므로 **의사결정 프로세스의 분리로 인한 토큰 효율성 및 레이턴시 단축이라는 본래의 Multi-Agent 아키텍처 도입(다이어트) 목표를 전혀 달성하지 못하고 있습니다**.

---

## 🛠 2. 개선 방안 (How to fix)

현재 문제는 "파이프라인의 구조"는 만들었으나, 정작 **핵심 알맹이(Data Payload)의 흐름(Flow)이 끊어지거나 뒤섞인 상태**입니다. 이를 바로잡기 위해 다음과 같은 수정이 필요합니다.

### 2.1. 도메인 에이전트에 실제 Context Data(원문/수치) 주입 
도메인 에이전트가 "빈 껍데기만 보고 일반론을 지어내는 현상"을 막기 위해 프롬프트 뼈대를 수정합니다.

- **작업 계획**: `_build_agent_execution_prompt()` 내부에서, 도메인 에이전트에게 보내는 프롬프트에 `[GraphDataExtract]` (또는 SQL/Graph의 실질적인 Context 내용) 섹션을 추가합니다.
- **주입 대상**: 
  - Graph Request일 경우: `GraphRagContextResponse` 내에 존재하는 실제 `indicators`(금리/지표 데이터), 주요 `evidences`(뉴스 문장), `events` 등의 세부 내용 일부를 전달하여 해석의 "재료(Raw Material)"를 제공.
  - SQL Request일 경우: OHLCV 테이블에서 추출된 `trend_analysis`, `moving_averages`, `returns` 같은 정량적 집계 수치(Dataset Trend)를 전달. 

### 2.2. Supervisor 프롬프트의 극단적 다이어트 (Strict Context Delegation)
Supervisor가 도메인 에이전트의 통찰력에만 강제적으로 의존하도록 만들어야 합니다.

- **작업 계획**: `_make_prompt()` 에서 Supervisor에게 건네는 `compact_context` (즉 `[GraphContextCompact]`)에서 **방대한 원문 데이터(`evidences.text`, `stories.title`, 원시 `events` 등)를 완전히 제거(Drop)하거나 극단적으로 축소**합니다.
- **유지 대상**: Supervisor는 `[RoutingDecisionCompact]`, `[DomainInsights]` 만 보고, 필요시 인용 목적을 위해 `evidence_id`, `indicator_code` 목록 정도의 메타데이터만 참조하도록 프롬프트 직렬화 로직(`_build_compact_graph_context_for_prompt` 하위 등)을 쳐냅니다.

---

## 🚀 3. 다음 작업(Action Item)

1. `hobot/service/graph/rag/response_generator.py`의 `_build_agent_execution_prompt` 수정 (도메인 에이전트를 위한 Context Data Payload 주입)
2. `hobot/service/graph/rag/response_generator.py`의 `_build_compact_graph_context_for_prompt` 또는 `_make_prompt` 호출부 수정 (Supervisor를 위한 데이터 블라인드 처리)
3. 해당 로직 변경 후 다시 API를 호출하여 프롬프트 덤프를 재확인하고, LLM 답변 퀄리티 비교.
