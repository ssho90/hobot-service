# 매크로 트레이딩 리밸런싱 워크플로우 (To-Be)

본 문서는 매크로 트레이딩 시스템의 리밸런싱 로직 개선안(2026-01-25)을 반영한 **To-Be 워크플로우**를 정의합니다.

## 1. 개요 (Overview)

*   **목표**: 시장 충격을 최소화하고, AI 신호의 노이즈를 필터링하며, 안정적인 자산 배분을 실행합니다.
*   **핵심 개선**: 5일 분할 진입(Split Entry), 3일 신호 검증(Debouncing), MP/Sub-MP 범위 분리.

## 2. 수집 데이터 (Data Collection)

리밸런싱 판단을 위해 다음과 같은 데이터를 수집합니다.

### 2.1 거시경제 지표 (FRED API)
*   **성장 (Growth)**: Philly Fed 지수 (제조업, 신규주문), GDPNow, 실업률(Unemployment Rate), 비농업 고용(Nonfarm Payroll).
*   **물가 (Inflation)**: Core PCE, Headline CPI, 기대 인플레이션(BEI 10Y).
*   **유동성 (Liquidity)**: 금리 커브(10Y-2Y Spread), 실질 금리, Net Liquidity, 하이일드 스프레드.
*   **심리 (Sentiment)**: VIX, 금융 스트레스 지수(STLFSI4), CNN Fear & Greed Index.
*   **기타**: Taylor Rule Signal, Sahm Rule Signal.

### 2.2 경제 뉴스 (Economic News)
*   **대상 국가/섹터**: 미국(US), 중국(China), 유로존(Euro Area), 원자재(Commodity), 암호화폐(Crypto).
*   **범위**: 최근 **20일** 이내의 주요 헤드라인 및 요약.
*   **전처리**: LLM을 통해 500자 내외로 핵심 경제 흐름 요약 (LangGraph `summarize_news_node`).

### 2.3 계좌 및 시장 데이터 (Market Data)
*   **포트폴리오 상태**: 현재 총 평가액, 보유 종목 및 수량, 현금 잔고 (KIS API).
*   **시장 가격**: 투자 대상 ETF/종목의 실시간 현재가.

---

## 3. 배치 주기 및 스케줄 (Batch Schedule)

매일 아침 장 시작(09:00 KST) 전후로 다음 프로세스가 실행됩니다.

| 시간 (KST) | 단계 | 설명 |
| :--- | :--- | :--- |
| **08:30** | **Step 1: AI 분석 및 신호 검증** | 데이터 수집 및 LLM 분석, 신호 안정성(3-day rule) 체크. |
| **09:40** | **Step 2: 리밸런싱 실행** | 확정된 신호에 따라 매매 실행 (분할 진입 포함). |

---

## 4. 상세 워크플로우 (Phases)

전체 프로세스는 크게 **신호 생성(Generation)** 단계와 **실행(Execution)** 단계로 나뉩니다.

### Phase 1: 데이터 수집 및 AI 분석 (Signal Generation)
*   **주체**: `AI Strategist (LangGraph)`
*   **Flow**:
    1.  `collect_fred_node`: FRED 지표 수집 및 정량 점수(Quant Score) 계산.
    2.  `collect_news_node` -> `summarize_news_node`: 뉴스 수집 및 LLM 요약.
    3.  `analyze_node`:
        *   **MP 분석**: 거시경제 국면 판단 및 MP(MP-1 ~ MP-5) 선택.
        *   **Sub-MP 분석**: 선택된 MP 하에서 자산군별 세부 전략(Eq-A, Bnd-L 등) 결정.
    4.  `save_decision_node`: 1차 결정 저장 (DB: `ai_strategy_decisions`).

### Phase 2: 신호 검증 (Signal Verification)
*   **주체**: `Rebalancing Engine (Verifier)`
*   **로직 (3-Day Rule)**:
    *   오늘 생성된 신호(T)와 과거 신호(T-1, T-2)를 비교합니다.
    *   **Logic**: `Signal(T) == Signal(T-1) == Signal(T-2)`
    *   **결과**:
        *   **일치 (Confirmed)**: 새로운 **Target Portfolio**로 확정 업데이트.
        *   **불일치 (Pending)**: 기존 Target 유지 (노이즈로 간주하고 대기).

### Phase 3: 리밸런싱 계획 수립 (Planning with Split Entry)
*   **주체**: `Rebalancing Engine (Planner)`
*   **시간**: 09:40
*   **로직**:
    1.  **Drift Check**: 현재 포트폴리오(Current) vs 목표 포트폴리오(Target) 괴리율 확인.
    2.  **충돌 처리 (Conflict Handling)**:
        *   *Case A: MP 변경 감지* → 진행 중인 모든 분할 매매 중단, **Global Reset** (1일차부터 재시작).
        *   *Case B: Sub-MP 변경 감지* → 해당 자산군만 멈추고 **Local Switch** (해당 자산군만 1일차 재시작, 나머지는 기존 스케줄 유지).
    3.  **수량 계산 (Sizing)**:
        *   `목표 수량` - `현재 수량` = `Total Delta` 계산.
    4.  **분할 주문 생성 (Split Logic)**:
        *   **Day 1**: `Total Delta`의 **50%** (단, Sub-MP만 변경 시 20~30%로 축소 가능).
        *   **Day 2~5**: `(남은 목표 수량 - 현재 수량) / 남은 일수`.
        *   *보정*: 매일 최신 가격 기준으로 수량을 재계산하여 5일차에 목표에 수렴하도록 함.

### Phase 4: 주문 실행 (Execution)
*   **주체**: `Order Executor`
*   **순서**:
    1.  **매도 (Sell)**: 리밸런싱 매도 주문 전송 -> 체결 확인/대기.
    2.  **현금 정산 (Cash Sim)**: 예상 매도 대금으로 가용 현금 재계산.
    3.  **매수 (Buy)**: 리밸런싱 매수 주문 전송.
*   **후처리**:
    *   DB에 `rebalancing_state` 업데이트 (진행 일수, 남은 수량 등).
    *   알림 발송 (성공/실패 내역).

---

## 5. 데이터 흐름도 (Data Flow Summary)

```mermaid
graph TD
    subgraph "09:10 - AI Analysis"
        A[FRED/Market Data] --> B(Quant Signals)
        C[News Data] --> D(LLM Summary)
        B & D --> E{AI Strategist}
        E --> F[Decision (Daily Signal)]
        F --> G{3-Day Validator}
        G -- Stable (3 days) --> H[Update Target MP/Sub-MP]
        G -- Unstable --> I[Keep Existing Target]
    end

    subgraph "09:40 - Execution"
        H --> J[Drift & Conflict Check]
        I --> J
        J -- Need Rebalancing --> K{Split Logic Calculator}
        
        K -- Day 1 --> L[Exec 50% of Delta]
        K -- Day 2~5 --> M[Exec 1/N of Remaining]
        
        L & M --> N[Order Executor]
        N --> O((Market))
    end
```
