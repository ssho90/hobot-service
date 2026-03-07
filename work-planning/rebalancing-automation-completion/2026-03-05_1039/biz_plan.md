# 리밸런싱 자동화 완성 실행 계획

## 목표
- 현재 수동 중심 리밸런싱을 자동화로 전환한다.
- 핵심 규칙을 시스템으로 강제한다.
  - `3일 연속 동일 LLM 신호 유지 시 확정`
  - `확정 후 5거래일 분할 매수/매도`
- 운영자가 테스트 화면에서 상태/진행률/예외를 추적 가능하게 만든다.

## 현재 진단 (2026-03-05 기준)
- 수동 실행 엔진은 존재: `POST /api/macro-trading/rebalance/test` -> `execute_rebalancing(max_phase)`
- 자동 상태머신은 부재:
  - 3일 확정 로직 없음
  - 5일 분할 집행 로직 없음
  - 분할 진행 상태 저장/재개 로직 없음
- 스케줄러는 AI 분석(08:30) 중심이며 자동 리밸런싱 실행 스케줄은 없음
- `rebalancing_state` 테이블은 생성만 있고 실사용 업데이트 코드가 없음

## 설계 원칙
1. 신호 확정과 주문 집행을 분리한다.
2. 상태를 JSON blob가 아니라 테이블 단위로 정규화한다.
3. 매일 재계산(가격/보유수량 반영) 가능한 idempotent 실행으로 설계한다.
4. 실패 시 중단이 아니라 재시도 가능한 상태 전이로 설계한다.

## To-Be 아키텍처
- `AI 분석 단계(08:30)`
  - 최신 `ai_strategy_decisions` 생성
  - 신호 비교 후 `signal_confirmation_state` 갱신(연속일 카운트)
  - 3일 확정 시 `rebalance_campaign` 생성(상태 `READY`)
- `리밸런싱 실행 단계(09:40)`
  - `READY/IN_PROGRESS` 캠페인 조회
  - 거래일 기준 1~5일차 tranche 생성/실행
  - 매일 최신 가격 기준으로 남은 수량 재산출
  - 체결 결과 반영 후 캠페인 상태 전이

## Phase별 상세 계획

### Phase 0. 베이스라인 고정
- 범위
  - 현재 수동 엔진/테스트 UI/스케줄 동작을 스냅샷 문서화
  - 운영 DB 백업 및 feature flag 기본값 정의
- 산출물
  - 베이스라인 리포트
  - `.env` 신규 키 목록
- 완료 기준
  - 현재 동작을 재현 가능한 명령/화면 경로 확보

### Phase 1. 상태 스키마 설계 및 마이그레이션
- 범위
  - 신규 테이블 설계
    - `signal_confirmation_state` (mp/sub-mp 해시, 연속일, last_seen_date)
    - `rebalance_campaign` (캠페인 단위 상태, 시작일, 종료일, scope)
    - `rebalance_tranche` (D1~D5 주문 계획/실행 결과)
    - `rebalance_execution_log` (실패 원인, 재시도 이력)
  - 기존 `rebalancing_state`는 읽기 호환용으로 유지하거나 view로 대체
- 구현 포인트
  - unique key로 중복 실행 방지 (`campaign_id + trade_date + tranche_no`)
- 완료 기준
  - 마이그레이션 적용/롤백 스크립트 통과
  - DB 스키마 문서 갱신

### Phase 2. 3일 신호 확정기 구현
- 범위
  - `ai_strategy_decisions` 최신 3건 기준 확정기 구현
  - MP 변경/서브MP 변경 분리 판정
  - 확정/취소/유지 상태 전이 구현
- 구현 포인트
  - 해시 기반 비교(정렬/필드 노이즈 제거)
  - 휴장일 처리(거래일 캘린더 기준)
- 완료 기준
  - 단위 테스트: 연속 3일 확정, 중간 변경 시 카운트 리셋, 동일 신호 유지

### Phase 3. 5일 분할 실행기 구현
- 범위
  - D1~D5 분할 비중 정책 구현
  - 일자별 남은 수량 재산출 로직 구현
  - MP Global reset / Sub-MP Local switch 충돌 처리 구현
- 구현 포인트
  - 기존 `calculate_net_trades` 재사용
  - 주문 실패 시 tranche 상태 `FAILED_RETRYABLE` 저장
- 완료 기준
  - 시뮬레이션 테스트: 5일 종료 시 목표 비중 수렴
  - 충돌 케이스 2종 자동 전이 검증

### Phase 4. 스케줄러 자동화 연결
- 범위
  - `08:30` 확정기 잡
  - `09:40` 실행기 잡
  - 중복 실행 락/동시성 가드 추가
- 구현 포인트
  - 단일 인스턴스 락(DB advisory lock 또는 lock row)
  - 재기동 복구 시 `IN_PROGRESS` 캠페인 이어서 수행
- 완료 기준
  - 스케줄 등록 확인 + 수동 트리거/자동 트리거 동일 결과

### Phase 5. 테스트 화면/운영 모니터링 개선
- 범위
  - 기존 `RebalancingTestModal` 확장
    - 신호 확정 상태(연속일)
    - 캠페인 상태(READY/IN_PROGRESS/COMPLETED)
    - tranche별 실행 결과/오류
  - Admin API 추가
    - 캠페인 목록/상세
    - 강제 재시도/중단
- 완료 기준
  - 운영자가 UI만으로 현재 진행상황과 실패 원인 파악 가능

### Phase 6. 검증/롤아웃
- 범위
  - 단위 테스트 + DB 통합 테스트 + 타임트래블 시나리오 테스트
  - Paper Trading 1주 검증
- Gate
  - 주문 실패율, 재시도 성공률, 목표비중 수렴률 기준치 충족
  - 미충족 시 자동 실행 flag off 후 수동 모드 유지

## 컴포넌트별 작업 분리

### 신호 확정 컴포넌트
- 입력: `ai_strategy_decisions`
- 책임: 3일 확정 여부 판단, 캠페인 생성
- 출력: `signal_confirmation_state`, `rebalance_campaign`

### 실행 컴포넌트
- 입력: `rebalance_campaign`, 계좌/가격 데이터
- 책임: 5일 분할 주문 계산/실행/상태 전이
- 출력: `rebalance_tranche`, `rebalance_execution_log`

### UI/운영 컴포넌트
- 입력: 캠페인/트랜치/로그 테이블
- 책임: 상태 시각화, 수동 개입(재시도/중단)
- 출력: 운영 제어 액션 로그

## 환경변수(초안)
- `REBAL_AUTO_ENABLED=0|1`
- `REBAL_CONFIRMATION_DAYS=3`
- `REBAL_SPLIT_DAYS=5`
- `REBAL_CONFIRM_SCHEDULE=08:30`
- `REBAL_EXEC_SCHEDULE=09:40`
- `REBAL_DRY_RUN=0|1`

## 작업 순서 제안
1. Phase 1 (스키마)
2. Phase 2 (3일 확정기)
3. Phase 3 (5일 분할 실행기)
4. Phase 4 (스케줄 연결)
5. Phase 5 (UI/운영)
6. Phase 6 (검증/배포)

## Definition of Done
- 자동 모드 ON 상태에서, 3일 동일 신호 유지 시 캠페인이 자동 생성된다.
- 캠페인이 5거래일 동안 분할 집행되고, 일자별 상태가 DB/UI에 반영된다.
- 실패 건은 재시도 가능 상태로 남고, 운영자가 UI에서 원인/재처리를 수행할 수 있다.
- 회귀 테스트 + DB 통합 테스트 + Paper Trading 검증 결과가 문서화된다.
