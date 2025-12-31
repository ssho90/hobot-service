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

### Phase 3: LLM 기반 전략 수립 모듈

#### 3.1 매도 전략 수립 모듈
- **파일**: `hobot/service/macro_trading/rebalancing/sell_strategy_planner.py`
- **역할**: LLM을 활용한 매도 전략 수립
- **사용 모델**: `gemini-3-pro-preview`
- **주요 함수**:
  - `plan_sell_strategy(current_state, target_mp, target_sub_mp, drift_info)`: 매도 전략 수립 (LLM 호출)
  - `build_sell_prompt()`: 매도 전략 수립용 프롬프트 생성
    - "You are a portfolio manager..."
    - "Goal: Generate SELL orders to reduce overweight assets to target."
- **로직**:
  1. Drift < 0 (과비중)인 자산 식별
  2. 현재 보유량, 목표 비중, 편차 정보를 포함한 프롬프트 생성
  3. LLM 호출하여 매도 주문 JSON 생성
- **LLM 출력 형식**: JSON
  - `[{"ticker": "...", "quantity": 10, "reason": "..."}]`

#### 3.2 매수 전략 수립 모듈
- **파일**: `hobot/service/macro_trading/rebalancing/buy_strategy_planner.py`
- **역할**: LLM을 활용한 매수 전략 수립
- **사용 모델**: `gemini-3-pro-preview`
- **주요 함수**:
  - `plan_buy_strategy(current_state, target_mp, target_sub_mp, drift_info, cash_available)`: 매수 전략 수립 (LLM 호출)
  - `build_buy_prompt()`: 매수 전략 수립용 프롬프트 생성
- **로직**:
  1. Drift > 0 (저비중)인 자산 식별
  2. 현재 보유량, 가용 현금, 목표 비중, 편차 정보, 종목별 현재가를 포함한 프롬프트 생성
  3. LLM 호출하여 매수 주문 JSON 생성
- **LLM 출력 형식**: JSON
  - `[{"ticker": "...", "quantity": 10, "reason": "..."}]`

#### 3.3 LLM 통합 및 엔진 연동
- **위치**: `rebalancing_engine.py`
- **변경 사항**:
  - `execute_sell_phase` 및 `execute_buy_phase`에서 위 플래너 호출
  - Phase 2에서 계산된 `drift_info`를 플래너에 전달하여 LLM이 정확한 판단을 내리도록 지원

### Manual Rebalancing Test Feature (User Request)

#### Backend Updates
- **`rebalancing_engine.py`**:
  - Update `execute_rebalancing` to accept `max_phase` (int) argument.
  - Logic:
    - If `max_phase` <= 2: Stop after `check_rebalancing_needed`.
    - If `max_phase` <= 3: Stop after `plan_sell_strategy` / `plan_buy_strategy` (do not execute).
    - Else: Run full execution.
- **`main.py`**:
  - New Endpoint: `POST /api/macro-trading/rebalance/test`
  - Body: `{"max_phase": int}`
  - Returns: Execution result/log up to that phase.

#### Frontend Updates
- **`TradingDashboard.js`**:
  - Add "Rebalancing Test" button.
  - Create `RebalancingTestModal` component.
  - Dropdown options:
    - "Phase 2: Check Drift (Analysis Only)"
    - "Phase 3: Plan Strategy (LLM Plan Only)"
    - "Phase 5: Full Execution (Trade)"
  - Display result JSON in a readable area within the modal.

### Phase 4: 룰 기반 검증 모듈

#### 4.1 매도 전략 검증 모듈
- **파일**: `hobot/service/macro_trading/rebalancing/sell_strategy_validator.py`
- **역할**: LLM이 수립한 매도 전략의 유효성 검증
- **주요 함수**:
  - `validate_sell_strategy()`: 매도 전략 검증
  - `check_sell_drift_reduction()`: 매도 후 편차 감소 확인
- **검증 규칙**:
  1. LLM이 판단한 매도 종목이 목표와 임계값 이상 차이 나는가?
  2. LLM이 판단한 매도 수량만큼 팔았을 때 목표와 1% 안쪽으로 차이가 좁혀지는가?
- **검증 실패 시**: 전략 수립 단계로 재진행 또는 리밸런싱 중단

#### 4.2 매수 전략 검증 모듈
- **파일**: `hobot/service/macro_trading/rebalancing/buy_strategy_validator.py`
- **역할**: LLM이 수립한 매수 전략의 유효성 검증
- **주요 함수**:
  - `validate_buy_strategy()`: 매수 전략 검증
  - `check_buy_drift_reduction()`: 매수 후 편차 감소 확인
- **검증 규칙**:
  1. LLM이 판단한 매수 종목이 목표와 임계값 이상 차이 나는가?
  2. LLM이 판단한 매수 수량만큼 샀을 때 목표와 1% 안쪽으로 차이가 좁혀지는가?
- **검증 실패 시**: 전략 수립 단계로 재진행 또는 리밸런싱 중단

### Phase 5: 매매 실행 모듈

#### 5.1 매도 실행 모듈
- **파일**: `hobot/service/macro_trading/rebalancing/sell_executor.py`
- **역할**: 한국투자증권 API를 통한 실제 매도 주문 실행
- **주요 함수**:
  - `execute_sell_orders()`: 매도 주문 실행
  - `execute_single_sell()`: 단일 종목 매도 실행
- **의존성**: 기존 `kis_api.py`의 `sell_market_order()` 활용
- **에러 처리**:
  - 주문 실패 시 재시도 로직
  - 부분 실행 시 처리

#### 5.2 매수 실행 모듈
- **파일**: `hobot/service/macro_trading/rebalancing/buy_executor.py`
- **역할**: 한국투자증권 API를 통한 실제 매수 주문 실행
- **주요 함수**:
  - `execute_buy_orders()`: 매수 주문 실행
  - `execute_single_buy()`: 단일 종목 매수 실행
- **의존성**: 기존 `kis_api.py`의 `buy_market_order()` 활용
- **에러 처리**:
  - 주문 실패 시 재시도 로직
  - 부분 실행 시 처리

### Phase 6: 이력 저장 및 로깅 모듈

#### 6.1 리밸런싱 이력 저장
- **위치**: `rebalancing_engine.py` 내부 또는 별도 모듈
- **역할**: 리밸런싱 실행 결과를 DB에 저장
- **저장 데이터**:
  - 실행 일시
  - 사용된 임계값
  - 실행 전/후 편차
  - 실행된 거래 내역
  - 총 거래 비용
  - 실행 상태 (SUCCESS, PARTIAL, FAILED)
- **테이블**: `rebalancing_history` (기존 스키마 활용)

#### 6.2 로깅
- **로깅 레벨**: INFO, WARNING, ERROR
- **로깅 내용**:
  - 각 단계별 실행 상태
  - LLM 전략 수립 결과
  - 검증 결과
  - 매매 실행 결과
  - 에러 발생 시 상세 정보

### Phase 7: API 엔드포인트 통합

#### 7.1 기존 API 엔드포인트 수정
- **파일**: `hobot/main.py`
- **엔드포인트**: `/api/macro-trading/rebalance` (POST)
- **수정 내용**:
  - TODO 주석 제거
  - 실제 리밸런싱 엔진 호출
  - 에러 처리 및 응답 형식 정의

#### 7.2 리밸런싱 상태 조회 API (구현 완료 - 2024.12.29)
- **엔드포인트**: `/api/macro-trading/rebalancing-status` (GET)
- **역할**: 현재 리밸런싱 필요 여부 및 편차 정보 조회
- **구현 내용**:
  - MP/Sub-MP 목표 vs 실제 비중 조회
  - 자산군별 가용 현금 정확도 개선 (API 직접 조회)


## 데이터 구조

### 리밸런싱 전략 JSON 형식

#### 매도 전략 JSON
```json
{
  "sell_orders": [
    {
      "ticker": "종목코드",
      "name": "종목명",
      "quantity": 매도수량,
      "reason": "매도 이유"
    }
  ]
}
```

#### 매수 전략 JSON
```json
{
  "buy_orders": [
    {
      "ticker": "종목코드",
      "name": "종목명",
      "quantity": 매수수량,
      "reason": "매수 이유"
    }
  ]
}
```

## 에러 처리 전략

### 단계별 에러 처리
1. **자산 조회 실패**: 리밸런싱 중단, 에러 로그 기록
2. **목표 비중 조회 실패**: 리밸런싱 중단, 에러 로그 기록
3. **리밸런싱 불필요**: 정상 종료, 로그 기록
4. **LLM 전략 수립 실패**: 재시도 (최대 3회), 실패 시 리밸런싱 중단
5. **전략 검증 실패**: 전략 수립 재진행 또는 리밸런싱 중단
6. **매도 실행 실패**: 부분 실행 허용, 실패한 주문은 로그 기록
7. **매수 실행 실패**: 부분 실행 허용, 실패한 주문은 로그 기록

### 트랜잭션 관리
- 매도와 매수는 별도 트랜잭션으로 처리
- 매도 성공 후 매수 실패 시에도 매도는 유지
- 부분 실행 시 상태를 PARTIAL로 기록

## 테스트 계획

### 단위 테스트
- 각 모듈별 단위 테스트 작성
- Mock 객체를 활용한 KIS API 테스트
- LLM 응답 시뮬레이션 테스트

### 통합 테스트
- 전체 리밸런싱 프로세스 통합 테스트
- 실제 KIS API 호출 없이 시뮬레이션 테스트
- 에러 시나리오 테스트

### 수동 테스트
- 모의투자 환경에서 실제 리밸런싱 실행
- 다양한 시나리오 테스트 (편차 크기, 종목 수 등)

## 개발 순서

1. **Phase 1**: 기본 구조 및 데이터 조회 모듈 (1-2주)
2. **Phase 2**: 리밸런싱 필요 여부 판단 모듈 (1주)
3. **Phase 3**: LLM 기반 전략 수립 모듈 (2주)
4. **Phase 4**: 룰 기반 검증 모듈 (1주)
5. **Phase 5**: 매매 실행 모듈 (1-2주)
6. **Phase 6**: 이력 저장 및 로깅 모듈 (1주)
7. **Phase 7**: API 엔드포인트 통합 (1주)

**총 예상 기간**: 8-10주

## 주의사항

1. **실제 거래 실행**: 실제 계좌에 영향을 주므로 신중하게 개발 및 테스트 필요
2. **LLM 응답 검증**: LLM이 잘못된 전략을 수립할 수 있으므로 룰 기반 검증 필수
3. **에러 복구**: 매도 후 매수 실패 시 현금이 남을 수 있으므로 복구 전략 필요
4. **성능**: LLM 호출이 시간이 걸리므로 타임아웃 설정 필요
5. **비용**: 거래 수수료 및 LLM API 비용 고려

## 향후 개선 사항

1. **부분 리밸런싱**: 편차가 큰 자산만 우선 처리
2. **거래 비용 최적화**: 거래 비용을 고려한 리밸런싱 전략
3. **시장 상황 고려**: 시장 변동성이 큰 경우 리밸런싱 지연
4. **다중 계좌 지원**: 여러 계좌에 대한 동시 리밸런싱
5. **백테스팅**: 과거 데이터를 통한 리밸런싱 전략 검증


