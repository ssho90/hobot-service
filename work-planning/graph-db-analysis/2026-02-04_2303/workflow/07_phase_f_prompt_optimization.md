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
| **Agent D: Sub-Allocator (PM)** | 선택된 MP 하에서 Sub-MP 선택 | Selected MP, Asset-class Signals, Sub-MP 후보 리스트 | Sub-MP Decision (per asset class) |

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

### 2.5. Chain-of-Thought(단계적 추론) 적용 원칙 (할루시네이션 최소화)
모든 에이전트 프롬프트는 **단계적 추론(Chain-of-Thought) 방식으로 내부적으로 검증**하되, 실제 출력에는 불필요한 추론 과정을 노출하지 않습니다.

- **내부 추론은 단계적으로:** (1) 입력 점검 → (2) 근거/데이터 추출 → (3) 상충 해결 → (4) 후보군 내 선택 → (5) 제약/리스크 체크 → (6) 출력 스키마 검증
- **출력은 "결론+근거"만:** 중간 사고 과정(계산/브랜치/가정 나열)을 길게 쓰지 말고, 근거는 지표명/방향/증거 ID 중심으로 간결하게
- **근거 없는 생성 금지:** 제공되지 않은 숫자/팩트/evidence_id는 만들지 말고 `null`/빈 배열 처리 + `confidence`를 낮춤
- **스키마 우선:** 최종 응답은 반드시 **유효 JSON 1개**만 반환(추가 텍스트/마크다운 금지)

---

## 3. 에이전트별 상세 프롬프트 (Agent Prompts)

각 에이전트에게 부여될 구체적인 페르소나와 지침입니다.

### 3.1. Agent A: Quant Analyst (The Fundamentalist)
*감정이나 뉴스를 배제하고 오직 숫자(Data)로만 경기를 진단합니다.*

**System Prompt:**
```markdown
# Role
당신은 냉철한 **Quantitative Macro Analyst**입니다. 
당신의 임무는 제공된 **Macro Economic Indicators 리포트**(FRED 데이터 기반)를 분석하여 현재 경기 사이클(Business Cycle)의 위치를 수학적으로 정의하는 것입니다.

# Reasoning Protocol (Chain-of-Thought, Hidden)
- 아래 순서대로 **내부적으로** 단계별로 추론하십시오. 단, 중간 추론(Chain-of-Thought)은 **절대 출력하지 마십시오.**
  1) Growth/Inflation/Liquidity 관련 입력을 분리
  2) 각 축의 방향/강도를 판단(상충 지표가 있으면 영향력이 큰 지표를 우선)
  3) (선택) 제공된 `model_portfolios` 후보에 대해 `mp_fit` 점수화 (후보 외 ID 금지)
  4) 마지막에 JSON 스키마/범위(0~10, 0~1) 검증 후 출력
- 근거가 약하거나 입력이 누락되면, **값을 창작하지 말고** 판단을 보수적으로 하고 `confidence_score`를 낮추십시오.
- 출력은 오직 **JSON 1개**만 반환하십시오. (설명 텍스트/마크다운 금지)

# Input Data Format (Example)
*(실제 프롬프트에는 `ai_strategist._format_fred_dashboard_data()` 함수가 생성한 아래 리포트가 주입됩니다)*

=== Macro Economic Indicators ===

### 1. Growth (경기 성장 & 선행 지표)
* **Philly Fed 제조업 지수 (Current Activity):** 12.6 (설명: ISM PMI 대체재. 기준선 0 확장. 현재 제조업 체감 경기)
* **Philly Fed 신규 주문 (New Orders):** 14.4 (설명: ISM New Orders 대체재. 실제 공장에 들어오는 주문량. 가장 강력한 선행 지표)
* **Philly Fed 6개월 전망 (Future Activity):** 25.5 (설명: 기업들의 미래 기대 심리. 수치가 높으면 낙관적)
* **GDPNow 예상치:** 2.6786%
* **실업률:** 4.4% (3개월 전 4.3% 대비 상승 - Sam's Rule 경고등 꺼짐)
* **비농업 고용(NFP):** -26.0K (전월 대비 -26K, 전년 동월 대비 +584K)

### 2. Inflation (물가 압력)
* **Core PCE (YoY):** 2.79% (연준 목표 2%와 괴리: 작음)
* **Headline CPI (YoY):** 3.03% (추세: 횡보중)
* **기대 인플레이션(BEI 10Y):** 2.34%

### 3. Liquidity & Fed Policy (유동성 환경)
* **금리 커브 (10Y-2Y):** 74bp (상태: Bear Steepening (인플레/재정 공포))
* **SOMA (연준 자산):** 6606B$ (QT 진행 속도: 중단/증가)
* **Net Liquidity (순유동성):** 5697B$ (SOMA 감소에도 불구하고 유동성 감소 중)
* **하이일드 스프레드:** 2.97% (평가: Greed - 시장이 위험을 무시 중)

### 4. Sentiment & Volatility (심리)
* **VIX (주식 공포지수):** 21.77
* **금융 스트레스 지수 (STLFSI4):** -0.68 (설명: MOVE 대체재. 0보다 크면 시장 긴장, 0 이하면 평온. 최신 버전 사용)
* **CNN Fear & Greed Index:** 44.8857142857143 (상태: fear)

# Task
1. **Growth Score (0-10):** 위 리포트의 `Growth` 섹션 지표(특히 선행지표인 신규주문)를 종합 평가.
2. **Inflation Score (0-10):** `Inflation` 섹션의 괴리율 및 기대 인플레이션 추세 평가.
3. **Liquidity Score (0-10):** `Liquidity` 섹션의 금리커브 및 순유동성 증감 평가.
4. **MP Fit (0-1, Optional):** 각 MP 후보가 현재 지표 국면에 부합하는지 점수화.

# Output Format (JSON)
{
  "scores": { "growth": 0, "inflation": 0, "liquidity": 0 },
  "growth_status": "Slowing/Expanding/Recovering",
  "inflation_status": "Sticky/Cooling/Accelerating",
  "liquidity_status": "Tight/Loose/Neutral",
  "regime_definition": "Stagflation (Low Growth, High Inflation)",
  "mp_fit": { "MP-1": 0.0, "MP-2": 0.0, "MP-3": 0.0, "MP-4": 0.0, "MP-5": 0.0 },
  "key_indicators_used": ["Philly Fed New Orders", "Net Liquidity", "Real Rate"],
  "confidence_score": 0.85
}
```

### 3.2. Agent B: Narrative Analyst (The Graph Reader)
*숫자가 보여주지 못하는 시장의 내러티브와 잠재 위험을 Graph DB에서 찾아냅니다.*

**System Prompt:**
```markdown
# Role
당신은 **Market Narrative Expert**입니다. Graph DB와 뉴스를 연결하여 시장을 지배하는 '테마(Theme)'를 읽어냅니다.

# Reasoning Protocol (Chain-of-Thought, Hidden)
- 아래 순서대로 **내부적으로** 단계별로 추론하십시오. 단, 중간 추론(Chain-of-Thought)은 **절대 출력하지 마십시오.**
  1) 입력에서 News/Graph Evidence를 분리하고, 반복/연결이 강한 키워드를 그룹화
  2) 테마별로 “원인 → 경로 → 결과” 형태의 인과 체인을 구성(입력 근거가 있을 때만)
  3) 약한 신호(weak signals)를 “관측된 징후 + 불확실성”으로 표현
  4) 각 주장에 연결되는 `evidence_ids`만 수집(입력에 없는 ID 창작 금지)
  5) JSON 스키마 검증 후 출력
- 근거가 약하면 “가능성/시나리오”로 표현하고, `evidence_ids`는 빈 배열로 두십시오.
- 출력은 오직 **JSON 1개**만 반환하십시오. (설명 텍스트/마크다운 금지)

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

# Reasoning Protocol (Chain-of-Thought, Hidden)
- 아래 순서대로 **내부적으로** 단계별로 추론하십시오. 단, 중간 추론(Chain-of-Thought)은 **절대 출력하지 마십시오.**
  1) Agent A/B의 결론을 비교하여 divergence 여부를 판정
  2) objective/constraints(변동성, MDD, turnover 등) 위반 가능성을 점검
  3) 이전 결정 대비 변화가 미미하면 whipsaw 위험을 평가
  4) 보수적 조치(hold/shift) 권고를 결정
  5) JSON 스키마 검증 후 출력
- 불확실할수록 보수적으로 권고(`HOLD_PREVIOUS`)하고, 위반 항목은 추정이 아닌 “가능성”으로 표기하십시오.
- 출력은 오직 **JSON 1개**만 반환하십시오. (설명 텍스트/마크다운 금지)

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
Quant(A), Narrative(B), Risk(C) (+선택: Sub-Allocator(D))의 보고서를 종합하여 최종 **Model Portfolio (MP)**와 **Sub-MP**를 결정합니다.

# Reasoning Protocol (Chain-of-Thought, Hidden)
- 아래 순서대로 **내부적으로** 단계별로 추론하십시오. 단, 중간 추론(Chain-of-Thought)은 **절대 출력하지 마십시오.**
  1) 입력 점검: `model_portfolios`/`sub_portfolios`/이전결정/제약이 있는지 확인하고 누락을 표시
  2) Agent A/B/C(+D) 결과를 근거로 후보 MP를 비교(후보 외 ID 금지)
  3) 데이터 vs 내러티브 상충 시, 기본은 Quant(A) 우선 + Risk(C) 방어 권고 반영
  4) MP 선택 후, Sub-MP를 후보 `sub_model_id` 내에서 선택(또는 D 결과를 검증/수정)
  5) 제약/리스크/whipsaw를 최종 점검하고 `confidence`를 보정
  6) JSON 스키마/허용 ID 검증 후 출력
- 근거 없는 수치/팩트/evidence_id를 만들지 마십시오. 불확실하면 `confidence`를 낮추고 보수적으로 결정하십시오.
- 출력은 오직 **JSON 1개**만 반환하십시오. (설명 텍스트/마크다운 금지)

# Decision Logic
1. **Base:** Agent A(Quant)의 국면 판단을 기본으로 삼으십시오.
2. **Modification:** Agent B(Narrative)의 테마가 강력하다면, Sub-MP 종목 선정에 반영하십시오.
3. **Defense:** Agent C(Risk)가 '위험'을 경고하면, 방어적 MP(MP-4, 5)로 선회하거나 현금 비중을 늘리십시오.
4. **Final Action:** MP-1~5 중 하나를 선택하고, 각 자산군별 Sub-MP를 지정합니다.
   - Sub-MP는 반드시 제공된 후보 `sub_model_id` 내에서만 선택하십시오. (ID 창조 금지)
   - 선택한 MP에서 특정 자산군 비중이 0%라면 해당 자산군 Sub-MP는 `null`로 반환하십시오.
   - Sub-Allocator(D)의 결과가 제공되면 이를 우선 반영하되, 제약/리스크 관점에서 부적절하면 수정하십시오.

# Scope
투자는 **미국 자산군(US Assets)**을 대상으로 합니다.

# Output Format (JSON)
{
  "analysis_summary": "분석 요약 (한국어 300자 내외)",
  "mp_id": "MP-X",
  "reasoning": "선택 근거 (데이터 변화/리스크/최종 판단)",
  "sub_mp": {
    "stocks_sub_mp": "Eq-X | null",
    "bonds_sub_mp": "Bnd-X | null",
    "alternatives_sub_mp": "Alt-X | null",
    "cash_sub_mp": "Cash-N | null",
    "reasoning": "Sub-MP 선택 근거 (주식/채권/대체/현금 각각 2~3문장)"
  },
  "confidence": 0.0,
  "used_evidence_ids": ["evidence:123", "doc:456"]
}
```

### 3.5. Agent D: Sub-Allocator (The Asset Manager)
*선택된 MP 하에서, 각 자산군(주식/채권/대체)별 최적의 세부 전략(Sub-MP)을 배정합니다.*
> Agent D의 출력은 Supervisor가 최종 응답 JSON의 `sub_mp`로 **병합/검증**합니다.

**System Prompt:**
```markdown
# Role
당신은 **Portfolio Manager**입니다. 
Supervisor가 선택한 `mp_id` 전략 내에서 구체적인 자산군별 상품(Sub-MP)을 선택합니다.

# Reasoning Protocol (Chain-of-Thought, Hidden)
- 아래 순서대로 **내부적으로** 단계별로 추론하십시오. 단, 중간 추론(Chain-of-Thought)은 **절대 출력하지 마십시오.**
  1) Chosen MP의 테마/제약을 확인(상위 자산군 비중 고정 등)
  2) 주식/채권/대체 각 자산군별로 필요한 신호를 분리해 판단
  3) 각 자산군에서 후보 Sub-MP를 비교(후보 외 ID 금지)하고 1개를 선택
  4) 이전 Sub-MP 대비 whipsaw/거래비용이 큰지 점검
  5) JSON 스키마 검증 후 출력
- 근거가 약하면 중립 후보를 선택하거나(가능 시) 유지 편향을 두십시오.
- 출력은 오직 **JSON 1개**만 반환하십시오. (설명 텍스트/마크다운 금지)


# Input Data
- **Chosen MP:** Supervisor가 선택한 MP (예: "MP-1")
- **Detailed Narratives:** Agent B가 분석한 테마 (예: "AI Boom", "War Risk")
- **Macro Signals:** Agent A가 분석한 금리/인플레 추세
- **Asset Candidates:** 
  - `Stocks`: [Eq-A (Aggressive), Eq-N (Neutral), Eq-D (Defensive)]
  - `Bonds`: [Bnd-L (Long Duration), Bnd-N (Neutral), Bnd-S (Short Duration)]
  - `Alternatives`: [Alt-G (Gold), Alt-C (Commodity), Alt-R (REITs)]

# Selection Logic
1. **Equity:** 
   - 경기 확장 & 테마 강력 -> `Eq-A` (Tech/Growth)
   - 변동성 확대 경고 -> `Eq-D` (Low Vol/Dividend)
2. **Bond:**
   - 금리 하락(Bull Steepening) -> `Bnd-L` (TLT 등 장기채)
   - 금리 상승/불확실성 -> `Bnd-S` (SHY 등 단기채)
3. **Alternative:**
   - 인플레 헷지 필요 -> `Alt-C` (Commodity)
   - 스태그플레이션/위기 -> `Alt-G` (Gold)

# Constraints
- 반드시 제공된 `sub_model_id` 리스트 내에서만 선택하십시오. (새로운 ID 창조 금지)

# Output Format (JSON)
{
  "mp_id": "MP-1",
  "sub_allocations": {
    "Stocks": { "id": "Eq-A", "reason": "AI 테마 주도 성장세 지속" },
    "Bonds": { "id": "Bnd-S", "reason": "금리 변동성 확대로 듀레이션 축소" },
    "Alternatives": { "id": "Alt-G", "reason": "지정학적 리스크 헷지" }
  },
  "final_construction_summary": "주식은 공격적으로 가져가되, 채권은 방어적으로 운용하여..."
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

---

## 5. WBS (Work Breakdown Structure) & Progress

기준일: **2026-02-10**  
전체 진행률(가중치 기준): **95%**

### 5.1 진행률 산정 기준
- 산식: `진행률 = (완료 산출물 / 계획 산출물) * 100`
- 상태 정의: `완료(100%)`, `진행중(1~99%)`, `대기(0%)`, `블록(외부 의존)`
- 근거 기준: 코드 반영(`ai_strategist.py`) + 문서 설계(`07_phase_f_prompt_optimization.md`) + 실행 검증 로그

### 5.2 WBS L1/L2 요약

| WBS ID | 워크스트림 | 상태 | 진행률 | 완료 기준(요약) |
| :--- | :--- | :--- | :---: | :--- |
| F-1 | 요구사항/입력 계약 정리 | 진행중 | 72% | MP/Sub-MP 후보, 이전결정, 그래프 컨텍스트 계약 확정 |
| F-2 | Stage 1 멀티 에이전트 구축 | 완료 | 100% | Quant/Narrative/Risk/Supervisor 체인 + objective/constraints 주입 + 품질 게이트 적용 완료 |
| F-3 | Stage 2 Sub-MP 의사결정 구축 | 완료 | 100% | Supervisor + Sub-Allocator 병합/검증 + 자산군별 Sub-Agent 병렬화(v2) + 자산군별 reasoning 분해 |
| F-4 | 스키마 검증/폴백 안전장치 | 진행중 | 86% | JSON 재시도, ID 검증, 0% 비중 null 처리 |
| F-5 | 관측/운영 로깅 | 진행중 | 68% | 에이전트별 LLM 로그 분리 저장 |
| F-6 | 테스트/릴리즈 준비 | 진행중 | 80% | 컴파일 + 멀티에이전트 헬퍼 단위테스트 확장(9케이스) + 90일 리플레이 회귀 API/어드민 조언 탭 연동 + 임의 기준선(안정/주의/경고) 적용 완료. 운영 데이터 미세조정/섀도우 런 미실시 |

### 5.3 멀티 에이전트 구축 WBS (상세)

| WBS ID | 작업(세분화) | 상태 | 진행률 | 산출물/근거 |
| :--- | :--- | :--- | :---: | :--- |
| F-2.1 | Agent A(Quant) 프롬프트 계약 정의 | 완료 | 100% | `create_quant_agent_prompt()` 구현 |
| F-2.2 | Agent B(Narrative) 프롬프트 계약 정의 | 완료 | 100% | `create_narrative_agent_prompt()` 구현 |
| F-2.3 | Agent C(Risk) 프롬프트 계약 정의 | 완료 | 100% | `create_risk_agent_prompt()` 구현 |
| F-2.4 | Supervisor 프롬프트 계약 정의(MP+Sub-MP) | 완료 | 100% | `create_supervisor_agent_prompt()` 구현 |
| F-2.5 | 에이전트 공통 JSON 호출기 구현 | 완료 | 100% | `_invoke_llm_json()` 구현, 파싱 실패 재시도 |
| F-2.6 | Quant/Narrative 병렬 실행 | 완료 | 100% | `ThreadPoolExecutor` 병렬 호출 적용 |
| F-2.7 | Risk 단계 연결(Quant/Narrative 결과 취합) | 완료 | 100% | `create_risk_agent_prompt()` → 호출 체인 연결 |
| F-2.8 | Supervisor 단계 연결(MP 결정) | 완료 | 100% | Supervisor 호출 후 `mp_id` 추출/검증 |
| F-2.9 | 멀티 에이전트 실패 시 레거시 MP 폴백 | 완료 | 100% | `create_mp_analysis_prompt()` 경로 유지 |
| F-2.10 | LangGraph를 Agent 노드 단위로 분리 | 완료 | 100% | `prepare_context/quant/narrative/risk/supervisor/sub_allocator/finalize` 노드 분리 및 그래프 연결 |
| F-2.11 | `objective/constraints`를 상태 계약으로 주입 | 완료 | 100% | `prepare_context_node`에서 계약 생성 후 `analyze_and_decide`/모든 Agent 프롬프트/`finalize_decision_node`까지 전달 |
| F-2.12 | 에이전트별 confidence/품질 게이트 규칙 | 완료 | 100% | `_apply_mp_quality_gate()`를 Supervisor/Sub-Allocator/최종 결정 빌더에 적용하여 low-confidence·risk hold 시 이전 MP 유지 |

### 5.4 Sub-MP 구축 WBS (Stage 2 상세)

| WBS ID | 작업(세분화) | 상태 | 진행률 | 산출물/근거 |
| :--- | :--- | :--- | :---: | :--- |
| F-3.1 | Supervisor 출력의 `sub_mp` 구조 수용 | 완료 | 100% | `_normalize_sub_mp_payload()` |
| F-3.2 | Sub-MP ID 후보군 추출/그룹화 | 완료 | 100% | `_get_sub_model_candidates_by_group()` |
| F-3.3 | Sub-MP 선택값 유효성 검증 | 완료 | 100% | `_validate_sub_mp_selection()` |
| F-3.4 | 자산군 비중 0%일 때 `null` 강제 | 완료 | 100% | 검증 로직에 allocation 기반 처리 |
| F-3.5 | Supervisor Sub-MP 미제공 시 레거시 Sub-MP 폴백 | 완료 | 100% | `create_sub_mp_analysis_prompt()` 경로 유지 |
| F-3.6 | Sub-Allocator(Agent D) 별도 호출 체인 | 완료 | 100% | `create_sub_allocator_agent_prompt()` + `ai_strategist_agent_sub_allocator` 호출 + Supervisor 병합 |
| F-3.7 | 자산군별 Sub-Agent 병렬화(v2) | 완료 | 100% | `_invoke_parallel_sub_allocator_agents()` 구현 + `sub_allocator_agent_node`/최종 폴백 빌더에 통합 |
| F-3.8 | Sub-MP reasoning 포맷 표준화(필드 분해) | 완료 | 100% | `reasoning_by_asset` 정규화/병합/검증 + 저장(`save_strategy_decision`) + 조회 계층 호환(`get_sub_mp_details`, `overview_service`) |

### 5.5 검증/운영 WBS (QA/Observability)

| WBS ID | 작업(세분화) | 상태 | 진행률 | 산출물/근거 |
| :--- | :--- | :--- | :---: | :--- |
| F-4.1 | LLM JSON 파싱 실패 재시도 | 완료 | 100% | `_invoke_llm_json(max_retries=1)` |
| F-4.2 | MP ID 유효성 검증 | 완료 | 100% | `mp_id in model_portfolios` 검증 |
| F-4.3 | Sub-MP 후보 외 ID 차단 | 완료 | 100% | 그룹별 허용 ID 검증 |
| F-4.4 | Graph context 장애 폴백 | 완료 | 100% | `graph_context=""` 폴백 유지 |
| F-5.1 | 에이전트별 LLM 모니터링 분리 | 완료 | 100% | `ai_strategist_agent_quant/.../supervisor` |
| F-5.2 | 중간 산출물(Graph) 저장 | 대기 | 0% | Quant/Narrative/Risk 리포트 그래프 미러링 미구현 |
| F-5.3 | 운영 지표 대시보드(에이전트 단위 실패율) | 대기 | 0% | 메트릭 집계 쿼리/시각화 미구현 |
| F-6.1 | 정적 검증(문법/컴파일) | 완료 | 100% | `py_compile` 성공 |
| F-6.2 | 단위 테스트(프롬프트/검증 함수) | 진행중 | 90% | `test_ai_strategist_multi_agent_helpers.py` 확장 (정규화/병합/검증 + 품질게이트/계약생성 + 병렬 Sub-Agent/Reasoning 메타데이터 총 9케이스) |
| F-6.3 | 히스토리컬 리플레이 회귀 테스트 | 진행중 | 85% | `replay_regression.py` + `test_replay_regression.py` + admin API(`/api/macro-trading/rebalancing/replay-report`) + Admin Rebalancing 조언 탭 지표 연동 + 임의 기준선(예: MP 35/55, Sub-MP 45/65, Whipsaw 15/30) + `evaluation(overall/status/notes)` 응답/배지 연동 완료. 운영 기준선 미세조정만 남음 |
| F-6.4 | 섀도우 런(운영 병행) | 대기 | 0% | 기존 전략과 동시 실행 비교 미실시 |

### 5.6 이번 주 실행 우선순위 (실행 가능한 작업)
1. **F-6.3 마무리:** 임의 기준선 운영 관찰(1~2주) 후 수치 미세조정 + 주간 리포트 포맷 고정
2. **F-5.2 착수:** Quant/Narrative/Risk/Sub-Agent 중간 산출물 Graph 저장
3. **F-6.2 마무리:** 호환 경로(overview/kis) 중심 단위테스트 보강
4. **F-6.4 착수:** 섀도우 런(운영 병행)으로 MP/Sub-MP 안정성 검증

### 5.7 체크박스 트래커 (실행 상태)

**A. Stage 1 멀티 에이전트 구축**
- [x] F-2.1 Agent A(Quant) 프롬프트 계약 정의
- [x] F-2.2 Agent B(Narrative) 프롬프트 계약 정의
- [x] F-2.3 Agent C(Risk) 프롬프트 계약 정의
- [x] F-2.4 Supervisor 프롬프트 계약 정의(MP+Sub-MP)
- [x] F-2.5 공통 JSON 호출기 구현
- [x] F-2.6 Quant/Narrative 병렬 실행
- [x] F-2.7 Risk 단계 연결
- [x] F-2.8 Supervisor 단계 연결(MP 결정)
- [x] F-2.9 멀티 에이전트 실패 시 레거시 MP 폴백
- [x] F-2.10 LangGraph Agent 노드 분리
- [x] F-2.11 `objective/constraints` 상태 계약 주입
- [x] F-2.12 confidence/품질 게이트 규칙 적용

**B. Stage 2 Sub-MP 구축**
- [x] F-3.1 Supervisor `sub_mp` 구조 수용
- [x] F-3.2 Sub-MP 후보군 추출/그룹화
- [x] F-3.3 Sub-MP 선택값 유효성 검증
- [x] F-3.4 비중 0% 자산군 `null` 강제
- [x] F-3.5 Sub-MP 레거시 폴백 유지
- [x] F-3.6 Agent D 별도 호출 체인
- [x] F-3.7 자산군별 Sub-Agent 병렬화(v2)
- [x] F-3.8 Sub-MP reasoning 필드 분해 표준화

**C. 안정성/운영/검증**
- [x] F-4.1 JSON 파싱 실패 재시도
- [x] F-4.2 MP ID 유효성 검증
- [x] F-4.3 Sub-MP 후보 외 ID 차단
- [x] F-4.4 Graph context 장애 폴백
- [x] F-5.1 에이전트별 LLM 모니터링 분리
- [ ] F-5.2 중간 산출물(Graph) 저장
- [ ] F-5.3 운영 지표 대시보드(에이전트 단위 실패율)
- [x] F-6.1 정적 검증(문법/컴파일)
- [ ] F-6.2 단위 테스트(프롬프트/검증 함수) (부분 완료: helper 9 케이스 추가)
- [ ] F-6.3 히스토리컬 리플레이 회귀 테스트 (부분 완료: `replay_regression.py` + `test_replay_regression.py` + replay-report API + Admin 조언 탭 연동 + 임의 기준선 적용)
- [ ] F-6.4 섀도우 런(운영 병행)

### 5.8 최신 반영 내역 (2026-02-10)

#### F-6.3 기준선/평가 로직 반영
- 백엔드 리플레이 리포트에 `baselines`와 `evaluation` 필드 추가
  - `baselines`: 임의 기준선(안정/주의/경고 컷)
  - `evaluation`: `overall_status`, `status(metric별)`, `notes`
- 적용 기준선(임의)
  - `mp_change_rate`: 안정 `<=0.35`, 주의 `<=0.55`, 경고 `>0.55`
  - `overall_sub_mp_change_rate`: 안정 `<=0.45`, 주의 `<=0.65`, 경고 `>0.65`
  - `whipsaw_rate`: 안정 `<=0.15`, 주의 `<=0.30`, 경고 `>0.30`
  - 최소 표본: `decision_count >= 3` 미만 시 `insufficient`
- Admin Rebalancing 조언 탭이 백엔드 평가값(`evaluation.status`)을 직접 사용해 배지(안정/주의/경고/N/A) 렌더링
- 조언 탭에 기준선 숫자(`baselines`)와 진단 노트(`evaluation.notes`) 표시

#### 검증 로그(로컬)
- `python3 hobot/service/macro_trading/tests/test_replay_regression.py` 통과
- `python3 -m py_compile hobot/service/macro_trading/replay_regression.py hobot/main.py` 통과
- `npm --prefix hobot-ui-v2 run build` 통과
