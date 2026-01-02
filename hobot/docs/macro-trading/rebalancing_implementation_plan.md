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

### Phase 3: 포트폴리오 최적화 및 전략 수립 (전면 수정)

**기존의 '매도 전략 -> 매수 전략' 분리 방식을 폐기하고, '목표 포트폴리오 산출 -> 트레이딩 전략 수립'으로 변경합니다.**

#### 3.1 Netting 및 수량 산출 모듈 (Python Core)

* **파일**: `hobot/service/macro_trading/rebalancing/portfolio_calculator.py`
* **역할**: 시점의 총 자산과 목표 비중을 기반으로 정확한 매매 수량 계산
* **주요 함수**:
    * `calculate_target_quantities(total_equity, target_weights, current_prices)`:
        * 로직: `(총 자산 * 목표 비중) / 현재가` = 목표 수량
    * `calculate_net_trades(current_holdings, target_quantities)`:
        * 로직: `목표 수량 - 현재 수량` = **Delta (순매매 수량)**
        * **핵심**: 여기서 `+`는 매수, `-`는 매도, `0`은 유지로 확정됨. (불필요한 매도 후 재매수 방지)
    * `apply_minimum_trade_filter(trades, min_amount)`:
        * 너무 소액(예: 1만원 미만)의 리밸런싱은 수수료 낭비이므로 제외

#### 3.2 트레이딩 전략 수립 모듈 (LLM)

* **파일**: `hobot/service/macro_trading/rebalancing/trading_strategy_planner.py`
* **역할**: Python이 계산한 '숙제(매매 리스트)'를 LLM이 '어떻게(How)' 수행할지 결정
* **사용 모델**: `gemini-3-pro-preview`
* **입력(Prompt)**:
    * "시장 상황(VIX, 이슈)을 고려하여 아래 확정된 매매 리스트의 집행 전략을 세워라."
    * Input Data: `[{ticker: "Samsung", action: "SELL", qty: 50}, {ticker: "Bond ETF", action: "BUY", qty: 100}]`
* **출력(JSON)**:
    * 주문 유형(`market` vs `limit`), 호가 전략(`current_price` vs `ask_price`), 분할 매매 여부 등

#### 3.3 엔진 연동

* `rebalancing_engine.py`에서 `calculate_net_trades` 호출 후 `plan_trading_strategy` 호출

---

### Phase 4: 룰 기반 검증 모듈 (수정)

#### 4.1 통합 검증 모듈

* **파일**: `hobot/service/macro_trading/rebalancing/strategy_validator.py`
* **역할**: 산출된 Netting 결과와 LLM 전략의 안전성 검증
* **검증 규칙**:
    1. **현금 흐름 검증**: `(예상 매도 금액 + 현재 예수금) > (예상 매수 금액 * 1.01)` (수수료/슬리피지 버퍼 포함)
    2. **비중 정합성**: 제안된 매매 수행 후의 예상 비중이 목표 비중과 오차 범위(1%) 내에 들어오는가?
    3. **이상 거래 탐지**: 단일 종목 매매액이 총 자산의 50%를 초과하는 등 비정상적 주문 차단

---

### Phase 5: 매매 실행 모듈 (순차 실행 유지)

**계획은 동시에 세웠지만(Phase 3), 실행은 현금 유동성을 위해 매도 후 매수 순서를 유지합니다.**

#### 5.1 주문 실행기

* **파일**: `hobot/service/macro_trading/rebalancing/order_executor.py`
* **주요 함수**:
    * `execute_sell_orders(sell_list)`: 확정된 매도 리스트 실행. (시장가 체결 확인 대기)
    * `execute_buy_orders(buy_list)`: 매도 체결 후 확보된 현금 확인 후 매수 실행.
* **안전 장치**:
    * 매도 후 예상보다 현금이 적게 확보된 경우(급락 등), 매수 리스트의 수량을 비율대로 자동 축소(`adjust_buy_quantities`)하여 미수 발생 방지.

---

### Phase 6: 이력 저장 및 로깅 (유지)

* **테이블**: `rebalancing_history`, `rebalancing_trades`
* **내용**: 시점의 스냅샷 데이터, 목표 비중, 실제 체결 내역 저장

### Phase 7: API 통합 (유지)

* 엔드포인트 및 Dashboard 연동

---

## 데이터 구조 (변경됨)

### 트레이딩 전략 요청/응답 JSON (Phase 3)

#### LLM 입력 (Python 계산 결과)

```json
{
  "portfolio_equity": 100000000,
  "required_trades": [
    { "ticker": "005930", "name": "삼성전자", "action": "SELL", "quantity": 50, "est_amount": 3500000 },
    { "ticker": "123456", "name": "KODEX 채권", "action": "BUY", "quantity": 100, "est_amount": 10000000 }
  ]
}
```

#### LLM 출력 (집행 전략)

```json
{
  "execution_plan": [
    {
      "ticker": "005930",
      "action": "SELL",
      "quantity": 50,
      "order_type": "MARKET",
      "reason": "유동성이 풍부하고 괴리율 해소가 시급하므로 시장가 매도"
    },
    {
      "ticker": "123456",
      "action": "BUY",
      "quantity": 100,
      "order_type": "LIMIT",
      "price_strategy": "CURRENT_BID_1",
      "reason": "변동성이 낮으므로 1호가 아래에 지정가 주문하여 비용 절감"
    }
  ]
}
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
