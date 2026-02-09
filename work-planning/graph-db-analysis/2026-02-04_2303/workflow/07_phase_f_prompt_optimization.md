# Phase F: Multi-Agent Strategy Design for Active Portfolio Management

## 1. 아키텍처 개요 (Architecture Overview)

기존의 단일 프롬프트 방식(Single-Prompt)에서 벗어나, 각 영역별 전문성을 극대화하고 상호 검증을 수행하는 **멀티 에이전트 시스템(Multi-Agent System)**으로 전환합니다. 이를 위해 LangGraph 기반의 **Orchestrator-Workers 패턴**을 적용합니다.

### 1.1. 시스템 구성 (Agent Roles)

| 에이전트 (Role) | 주요 임무 (Responsibility) | 입력 데이터 (Input) | 출력 (Output) |
| :--- | :--- | :--- | :--- |
| **Supervisor (Orchestrator)** | 전체 흐름 제어, 최종 의사결정(MP 선택), 사용자 보고 | 각 에이전트의 분석 결과 | Final Decision (MP/Sub-MP) |
| **Agent A: Quant Analyst** | 정량 데이터 기반의 거시경제 국면(Regime) 정의 | FRED 지표 (Growth, Inflation, Liquidity) | Regime(3축)+신뢰도, MP Fit 점수 |
| **Agent B: Narrative Analyst** | 비정형 데이터 기반의 시장 서사(Narrative) 및 리스크 발굴 | News Summary, **Graph Evidence** | Dominant Themes, Weak/Strong Signals, Evidence IDs |
| **Agent C: Risk Manager** | A/B 괴리(Divergence) 분석, 제약/리스크 점검, Whipsaw 방지 | A/B 출력, 이전 결정, 제약조건 | Divergence Report, Risk Guardrail Advice |
| (선택) **Agent D: Sub-Allocator (PM)** | 선택된 MP 하에서 Sub-MP 선택 | Selected MP, Asset-class Signals, Sub-MP 후보 리스트 | Sub-MP Decision (per asset class) |

---

## 2. 상세 구현 전략 (Implementation Strategy)

### 2.1. 적용 범위 (Two-Stage Pipeline)

멀티 에이전트는 "거시경제 분석(국면 정의)"의 신뢰도를 올리기 위해 Stage 1에 우선 적용하고, Stage 2는 비용/복잡도에 따라 선택합니다.

- **Stage 0 (Context Build):** FRED 시그널 + 뉴스 요약 + Graph Evidence 블록 + 후보 포트폴리오( MP / Sub-MP ) 로드 + 이전 결정 로드
- **Stage 1 (MP Selection):** `Quant` + `Narrative` 병렬 분석 → `Risk` 취합/검증 → `Supervisor`가 MP 1개 선택
- **Stage 2 (Sub-MP Selection):** (v1) 단일 PM 프롬프트로 Sub-MP 선택 / (v2) 자산군별 Sub-Agent 병렬 후 통합

> 핵심은 **"후보 리스트를 프롬프트에 넣고 그 중에서만 고르게"** 하여, LLM이 포트폴리오 정의를 창작/왜곡하지 않도록 하는 것입니다.

### 2.2. LangGraph State Definition (Input Contract 포함)
각 에이전트가 공유할 상태(State)를 정의합니다.

```python
class AgentState(TypedDict):
    # Meta
    as_of: str
    objective: Dict[str, Any]          # 예: {"primary":"maximize_sharpe","max_drawdown":-0.2,"turnover_penalty":"high"}
    constraints: Dict[str, Any]        # 예: {"rebalance":"monthly","no_leverage":True,"max_single_asset":0.35}

    # Inputs (Context Build output)
    fred_signals: Dict[str, Any]
    news_summary: str
    graph_context: str
    model_portfolios: Dict[str, Any]   # DB에서 로드된 MP 후보 (mp_id -> 정의)
    sub_portfolios: Dict[str, Any]     # DB에서 로드된 Sub-MP 후보 (sub_model_id -> 정의)
    previous_decision: Dict[str, Any]  # 예: {"mp_id":"MP-3","sub_mp":{...},"decision_date":"..."}
    
    # Intermediate Outputs (Agent Thoughts)
    quant_report: Optional[Dict[str, Any]]        # Agent A Output
    narrative_report: Optional[Dict[str, Any]]    # Agent B Output
    risk_report: Optional[Dict[str, Any]]         # Agent C Output

    # Stage Decisions
    mp_decision: Optional[Dict[str, Any]]         # Supervisor Stage 1 output
    sub_mp_decision: Optional[Dict[str, Any]]     # (옵션) Agent D or Supervisor Stage 2 output
    
    # Final Output
    final_decision: Optional[Dict[str, Any]]
```

### 2.3. Workflow (Execution Flow)
0. **Context Build:** `collect_fred_signals()` + `summarize_news()` + `build_strategy_graph_context()` + 후보 포트폴리오 로드 + 이전 결정 로드
1. **Parallel (Stage 1):** `Quant Analyst`와 `Narrative Analyst`가 동시에 독립적으로 분석 (서로의 결과/이전 포트폴리오를 보지 않게 구성 권장)
2. **Risk (Stage 1):** `Risk Manager`가 A/B 결과를 취합하여 `divergence`, `constraint violations`, `whipsaw`를 판단
3. **Supervisor (Stage 1):** Risk 보고서를 반영하여 **후보 MP 중 1개**를 선택 (필수: `mp_id`는 `model_portfolios` 내에서만)
4. **Stage 2 (선택):**
   - v1: 단일 `Sub-Allocator`가 자산군별 Sub-MP를 선택
   - v2: Equity/Bond/Alt Sub-Agent 병렬 → Risk 체크 → Supervisor 최종 확정
5. **Persist & Trace:** 최종 결정 저장(MySQL) + Graph 미러링 + LLM 호출 로그(에이전트별)

### 2.4. Validation & Fallback (필수)
- **JSON Schema 검증:** 각 에이전트 출력은 파싱/검증 실패 시 1회 자동 재시도(“유효 JSON만 반환”) → 그래도 실패하면 해당 에이전트 결과를 `None` 처리하고 보수적 폴백
- **Graph 장애 폴백:** `graph_context=""`로 진행(Phase E 정책 유지)
- **불확실성 폴백:** `divergence=true` 또는 `confidence 낮음`이면 `previous_decision` 유지 또는 Neutral/Defensive bias
- **환각 방지:** “후보 리스트 외 mp_id/sub_mp_id 생성 금지”, “근거 없는 수치 생성 금지(모르면 null)”

---

## 3. 에이전트별 상세 프롬프트 (Agent Prompts)

각 에이전트에게 부여될 구체적인 페르소나와 지침입니다.

### 3.1. Agent A: Quant Analyst (The Fundamentalist)
*감정이나 뉴스를 배제하고 오직 숫자(Data)로만 경기를 진단합니다.*

**System Prompt:**
```markdown
# Role
당신은 냉철한 **Quantitative Macro Analyst**입니다. 
당신의 임무는 제공된 FRED 데이터를 분석하여 현재 경기 사이클(Business Cycle)의 위치를 수학적으로 정의하는 것입니다.

# Task
1. **Growth Score (0-10):** GDPNow, PMI, 생산지표를 통해 경기 확장 강도를 평가.
2. **Inflation Score (0-10):** CPI/PCE 추세와 괴리율을 평가. (높을수록 물가 불안)
3. **Liquidity Score (0-10):** 실질금리, 연준 자산, 금융여건지수를 종합 평가. (높을수록 긴축)
4. **MP Fit (0-1, Optional):** 제공된 `model_portfolios` 후보 각각이 현재 Regime에 얼마나 부합하는지 점수화하십시오. (후보 외 ID 생성 금지)

# Output Format (JSON)
{
  "scores": { "growth": 0, "inflation": 0, "liquidity": 0 },
  "growth_status": "Slowing/Expanding/Recovering",
  "inflation_status": "Sticky/Cooling/Accelerating",
  "liquidity_status": "Tight/Loose/Neutral",
  "regime_definition": "Stagflation (Low Growth, High Inflation)",
  "mp_fit": { "MP-1": 0.0, "MP-2": 0.0, "MP-3": 0.0, "MP-4": 0.0, "MP-5": 0.0 },
  "key_indicators_used": ["PMI", "PCE", "2Y10Y", "HY Spread"],
  "confidence_score": 0.85
}
```

### 3.2. Agent B: Narrative Analyst (The Graph Reader)
*숫자가 보여주지 못하는 시장의 내러티브와 잠재 위험을 Graph DB에서 찾아냅니다.*

**System Prompt:**
```markdown
# Role
당신은 **Market Narrative Expert**입니다. Graph DB와 뉴스를 연결하여 시장을 지배하는 '테마(Theme)'를 읽어냅니다.

# Task (Active Graph Utilization)
1. **Dominant Theme Extraction:** Graph Evidence에서 가장 빈번하게 연결되는 키워드 클러스터(예: AI, War, Debt)를 찾으시오.
2. **Causal Chain Simulation:** 주요 사건(Node)이 어떤 경로(Edge)를 통해 경제에 충격을 줄지 연쇄 반응을 시뮬레이션 하십시오.
   - 예: [Oil Spike] -> [Inflation Expectation] -> [Rate Hike Fear]
3. **Hidden Risk Detection:** 현재 데이터에는 없지만 Graph에서 감지되는 '약한 신호(Weak Signal)'를 보고하시오.

# Output Format (JSON)
{
  "dominant_themes": ["AI Capex", "Geopolitical Tension"],
  "narrative_sentiment": "Fear/Greed/Neutral",
  "causal_risks": ["Supply Chain Disruption -> Inflation Rebound"],
  "weak_signals": ["..."],
  "graph_evidence_summary": "...",
  "evidence_ids": ["evidence:123", "doc:456"]
}
```

### 3.3. Agent C: Risk Manager (The Skeptic)
*Agent A와 B의 의견 차이를 분석하고, 포트폴리오를 방어적으로 조정합니다.*

**System Prompt:**
```markdown
# Role
당신은 **Risk Manager**입니다. Quant(A)와 Narrative(B)의 분석이 상충할 때, 보수적인 관점에서 의사결정을 가이드합니다.

# Task
1. **Divergence Check:** 
   - A는 '경기 확장'이라고 하는데 B는 '경기 침체 공포'를 말하는가? (괴리 발생)
   - 괴리가 발생하면 "시장 가격과 심리의 괴리"로 정의하고 **변동성 확대**에 대비하도록 경고하시오.
2. **Constraint Validation:**
   - 제안된 전략이 허용된 리스크 한도(변동성, MDD)를 초과할 가능성이 있는지 점검하시오.
3. **Whipsaw Protection:**
   - 지표의 변화가 미미하다면 '이전 포트폴리오 유지'를 권고하시오.

# Output Format (JSON)
{
  "divergence_detected": true/false,
  "risk_level": "High/Medium/Low",
  "constraint_violations": ["max_drawdown 위험", "turnover 과다 추정"],
  "adjustment_advice": "Equity 비중 10% 축소 권고 (심리적 불안정)",
  "whipsaw_warning": false,
  "recommended_action": "HOLD_PREVIOUS/SHIFT_NEUTRAL/SHIFT_DEFENSIVE"
}
```

### 3.4. Supervisor (The PM)
*모든 보고서를 종합하여 최종 MP를 선택합니다.*

**System Prompt:**
```markdown
# Role
당신은 **Chief Investment Officer (CIO)**입니다. 
Quant(A), Narrative(B), Risk(C)의 보고서를 종합하여 최종 **Model Portfolio (MP)**와 **Sub-MP**를 결정합니다.

# Decision Logic
1. **Base:** Agent A(Quant)의 국면 판단을 기본으로 삼으십시오.
2. **Modification:** Agent B(Narrative)의 테마가 강력하다면, Sub-MP 종목 선정에 반영하십시오.
3. **Defense:** Agent C(Risk)가 '위험'을 경고하면, 방어적 MP(MP-4, 5)로 선회하거나 현금 비중을 늘리십시오.
4. **Final Action:** MP-1~5 중 하나를 선택하고, 각 자산군별 Sub-MP를 지정합니다.

# Scope
투자는 **미국 자산군(US Assets)**을 대상으로 합니다.

# Output Format (JSON)
{
  "analysis_summary": "분석 요약 (한국어 300자 내외)",
  "mp_id": "MP-X",
  "reasoning": "선택 근거 (데이터 변화/리스크/최종 판단)",
  "confidence": 0.0,
  "used_evidence_ids": ["evidence:123", "doc:456"],
  "next_stage": "RUN_SUB_MP/HOLD_ONLY"
}
```

---

## 4. 실행 계획 (Execution Roadmap)

이 시스템을 구현하기 위해 다음 단계로 진행합니다.

1.  **Graph/DB 입력 계약 정리:** `model_portfolios`, `sub_portfolios`, `previous_decision`, `objective/constraints`를 State에 주입
2.  **LangGraph 노드 구현:** `node_quant`, `node_narrative` 병렬 → `node_risk` → `node_supervisor_mp` (Stage 1)
3.  **Stage 2 전략 결정:** (v1) 기존 Sub-MP 프롬프트 유지 / (v2) 자산군별 Sub-Agent 병렬화
4.  **Schema/폴백 추가:** JSON 검증/재시도/보수적 폴백(이전 포트폴리오 유지)
5.  **관측/저장:** `track_llm_call`을 에이전트별로 분리 기록 + (선택) Graph에 중간 산출물도 저장
6.  **Integration Test:** 과거 데이터(Historical Data) 주입 + divergence 케이스(“데이터 vs 내러티브 상충”) 회귀 테스트
