# 리밸런싱 알고리즘 구현 계획

## 개요

본 문서는 한국투자증권 API를 활용하여 AI 분석을 통해 결정된 Model Portfolio(MP)와 Sub-MP 비율을 기반으로 자동 리밸런싱 매매를 수행하는 알고리즘의 구현 계획을 설명합니다.

## 알고리즘 개요

리밸런싱은 다음 10단계로 구성됩니다:

1. 한국투자증권 자산 조회
2. MP, Sub-MP 목표 조회
3. Rebalancing 필요 여부 판단
4. Rebalancing 매도 전략 수립 (LLM)
5. 매도 실행 전 Python 룰 기반 체크
6. 매도 실행
7. 한국투자증권 가용 현금 조회
8. Rebalancing 매수 전략 수립 (LLM)
9. 매수 실행 전 Python 룰 기반 체크
10. 매수 실행

## 개발 단계별 계획

### Phase 1: 기본 구조 및 데이터 조회 모듈

#### 1.1 리밸런싱 엔진 메인 모듈 생성
- **파일**: `hobot/service/macro_trading/rebalancing/rebalancing_engine.py`
- **역할**: 리밸런싱 프로세스의 전체 흐름을 관리하는 메인 엔트리 포인트
- **주요 함수**:
  - `execute_rebalancing()`: 전체 리밸런싱 프로세스 실행
  - `check_rebalancing_needed()`: 리밸런싱 필요 여부 판단
  - `execute_sell_phase()`: 매도 단계 실행
  - `execute_buy_phase()`: 매수 단계 실행

#### 1.2 자산 조회 모듈 (구현 완료 - 2024.12.29)
- **파일**: `hobot/service/macro_trading/rebalancing/asset_retriever.py`
- **역할**: 한국투자증권에서 현재 보유 자산 정보 조회
- **구현 현황**:
  - `kis.py`의 `get_balance_info_api()` 함수로 자산 및 현금 조회 구현 완료
  - `rebalancing-status` API에서 활용 중
- **참조 API Spec**: `hobot/service/macro_trading/kis/api_specification/domestic/`
  - `inquire-balance.json`: 주식 잔고 조회
  - `inquire-psbl-order.json`: 주문 가능 현금 조회
- **주요 함수**:
  - `get_current_holdings()`: 현재 보유 종목 및 수량 조회 (완료)
  - `get_current_asset_allocation()`: 현재 자산군별 비중 계산 (완료)
  - `get_available_cash()`: 가용 현금 조회 (완료 - `api.get_buyable_cash()`)

#### 1.3 목표 비중 조회 모듈 (구현 완료 - 2024.12.29)
- **파일**: `hobot/service/macro_trading/rebalancing/target_retriever.py`
- **역할**: MP 및 Sub-MP 목표 비중 조회
- **구현 현황**:
  - `ai_strategist.py` 및 `get_rebalancing_status` API에서 구현 완료
  - `ai_strategy_decisions` 테이블에서 최신 목표 조회
- **주요 함수**:
  - `get_target_mp_allocation()`: 목표 MP 자산군별 비중 조회 (완료)
  - `get_target_sub_mp_allocation()`: 목표 Sub-MP 비중 조회 (완료)

### Phase 2: 리밸런싱 필요 여부 판단 모듈

#### 2.1 편차 계산 모듈
- **파일**: `hobot/service/macro_trading/rebalancing/drift_calculator.py`
- **역할**: 현재 비중과 목표 비중 간의 편차 계산
- **주요 함수**:
  - `calculate_mp_drift()`: MP 자산군별 편차 계산
  - `calculate_sub_mp_drift()`: Sub-MP별 편차 계산
  - `check_threshold_exceeded()`: 임계값 초과 여부 확인 (DB 설정값 사용)
- **임계값 (동적 설정)**:
  - `rebalancing_config` 테이블에서 조회
  - 기본값: MP 3%, Sub-MP 5%
  - Admin 화면에서 설정 가능

#### 2.2 리밸런싱 필요 여부 판단
- **위치**: `rebalancing_engine.py` 내부
- **로직**:
  - MP 자산군별 편차가 설정된 임계값(예: 3%) 이상인 항목이 하나라도 있으면 리밸런싱 필요
  - Sub-MP별 편차가 설정된 임계값(예: 5%) 이상인 항목이 하나라도 있으면 리밸런싱 필요
  - 두 조건 중 하나라도 만족하면 리밸런싱 실행

### Phase 2.5: 리밸런싱 설정 관리 (신규 추가)

#### 2.5.1 DB 스키마 추가
- **테이블**: `rebalancing_config`
- **컬럼**:
  - `id` (PK)
  - `mp_threshold_percent` (MP 임계값, Default 3.0)
  - `sub_mp_threshold_percent` (Sub-MP 임계값, Default 5.0)
  - `updated_at`

#### 2.5.2 설정 API
- **엔드포인트**: 
  - GET `/api/macro-trading/rebalancing/config`: 설정 조회
  - POST `/api/macro-trading/rebalancing/config`: 설정 업데이트

#### 2.5.3 UI 수정 (Admin)
- **위치**: Admin > 리밸런싱 관리 (구 포트폴리오 관리)
- **변경 사항**:
  - 메뉴명 변경: '포트폴리오 관리' -> '리밸런싱 관리'
  - 탭 추가: 'Rebalancing 설정' (MP, Sub-MP 탭 옆에 추가)
  - 기능: MP 임계값, Sub-MP 임계값 입력 및 저장

### Phase 3: 포트폴리오 최적화 및 전략 수립 (Python Algorithmic - 전면 수정)

**Refined Workflow: '목표 수량 산출 -> 매도 전략 수립 -> 매도 실행 -> 매수 전략 수립 -> 매수 실행'의 단계적 접근 적용**

#### 3.1 목표 수량 산출 및 1차 검증 (Step 1, 2)

* **파일**: `hobot/service/macro_trading/rebalancing/portfolio_calculator.py`
* **역할**: 시점의 총 자산과 목표 비중을 기반으로 티커별 매수/매도 목표 수량을 확정합니다.
* **주요 함수**:
    * `calculate_target_quantities(total_equity, target_weights, current_prices)`:
        * 로직: `(총 자산 * 목표 비중) / 현재가` = 목표 수량 (소수점 버림)
    * `calculate_net_trades(current_holdings, target_quantities)`:
        * 로직: `목표 수량 - 현재 수량` = **Delta (순매매 수량)**
    * `verify_strategy_feasibility(trades, current_holdings)`:
        * **1차 검증 (Step 2)**: 산출된 매매 계획이 논리적으로 타당한지 검증 (예: 보유 수량보다 많은 매도 요청 방지)

#### 3.2 매도 전략(JSON) 생성 (Step 3)

* **파일**: `hobot/service/macro_trading/rebalancing/trading_strategy_builder.py` (LLM 대체)
* **역할**: 확정된 매도 수량에 대해 구체적인 주문 정보를 생성합니다.
* **전략 로직**:
    * **매도 가격**: `현재가 - 1 tick` (ETF 기준 -5원)
    * **이유**: 즉각적인 체결 유도 및 불확실성 제거
* **출력 데이터**: `sell_orders` 리스트 (Ticker, Quantity, Price)

#### 3.3 매수 전략(JSON) 생성 (Step 5)

* **파일**: `hobot/service/macro_trading/rebalancing/trading_strategy_builder.py`
* **역할**: (매도 실행 후) 확정된 매수 수량에 대해 구체적인 주문 정보를 생성합니다.
* **전략 로직**:
    * **매수 가격**: `현재가 + 1 tick` (ETF 기준 +5원)
    * **이유**: 즉각적인 체결 유도
* **출력 데이터**: `buy_orders` 리스트 (Ticker, Quantity, Price)

---

### Phase 4: 룰 기반 검증 모듈 (Step 6)

#### 4.1 매수 로직 검증

* **파일**: `hobot/service/macro_trading/rebalancing/strategy_validator.py`
* **역할**: 매수 주문 실행 전, 재정적/비율적 타당성을 최종 검증합니다.
* **검증 항목**:
    1. **가용 현금 검증**: `(매수 예정 금액 + 수수료) <= 현재 예수금`
        * 매도 실행(Phase 5)이 완료된 후의 실제 예수금을 기준으로 해야 함.
    2. **리밸런싱 목표 근접성 검증**:
        * 이번 매수까지 실행되었을 때, 최종 포트폴리오 비중이 목표 비중과 허용 오차 내로 수렴하는지 시뮬레이션.

#### 4.2 실행 로직 연동 (Workflow)

* `rebalancing_engine.py`가 전체 오케스트레이션을 담당:
    * `Step 1~2` (산출) -> `Step 3` (매도계획) -> **`Step 4` (매도 실행 - Phase 5)** -> `Step 5` (매수계획) -> `Step 6` (매수검증) -> **`Step 7` (매수 실행 - Phase 5)** -> `Step 8` (완료체크)

---

### Phase 5: 매매 실행 모듈 (Step 4, 7)

#### 5.1 주문 실행기

* **파일**: `hobot/service/macro_trading/rebalancing/order_executor.py`
* **역할**: 생성된 JSON 전략을 실제 API 주문으로 변환하여 전송.
* **주요 함수**:
    * `execute_sell_phase(sell_orders)`: 매도 주문 전송 및 **체결 완료 대기**(중요).
    * `execute_buy_phase(buy_orders)`: 매수 주문 전송.

---

### Phase 6: 이력 저장 및 로깅 (유지)

* **테이블**: `rebalancing_history`, `rebalancing_trades`
* **내용**: 시점의 스냅샷 데이터, 목표 비중, 실제 체결 내역 저장

### Phase 7: API 통합 (유지)

* 엔드포인트 및 Dashboard 연동

---

## 데이터 구조 (변경됨)

### 트레이딩 전략 JSON 구조 (Phase 3)

LLM을 사용하지 않으므로 복잡한 프롬프트/응답 구조 대신, 내부 처리를 위한 명확한 JSON 구조를 정의합니다.

#### 매도 주문 리스트 (Step 3 Output)

```json
[
  {
    "ticker": "005930",
    "name": "삼성전자",
    "action": "SELL",
    "quantity": 50,
    "limit_price": 75000, 
    "price_logic": "current_price - 1 tick"
  }
]
```

#### 매수 주문 리스트 (Step 5 Output)

```json
[
  {
    "ticker": "123456",
    "name": "KODEX 국고채",
    "action": "BUY",
    "quantity": 100,
    "limit_price": 101050,
    "price_logic": "current_price + 1 tick"
  }
]
```

## 핵심 주의사항 (Revised)

1. **Snapshot Timing**: 자산 조회()와 실제 주문 실행() 사이의 시간차를 최소화해야 합니다. (장중 급변동 시 오차 발생 가능)
2. **현금 버퍼(Cash Buffer)**: 매수 주문 시, 계산된 현금의 98~99%만 사용하도록 설정하여 수수료 미수 발생을 방지해야 합니다.
3. **원자성(Atomicity)**: Python 계산 단계에서 매수/매도 세트가 하나의 트랜잭션처럼 취급되어야 합니다. "팔기만 하고 안 사는" 상황을 막기 위한 예외 처리가 중요합니다.

## 개발 순서 (Revised)

1. **Phase 1**: 기본 구조 및 데이터 조회
2. **Phase 2**: 리밸런싱 판단 및 설정
3. **Phase 3 (핵심)**: **Python Netting 로직 구현** 및 LLM 연동
4. **Phase 4**: 통합 검증 로직 구현
5. **Phase 5**: 순차 실행(Sell -> Wait -> Buy) 구현
6. **Phase 6 & 7**: 로깅 및 API
