# 01. Baseline & Scope

## 목적
- 리밸런싱 자동화 전환 전 현재 구현 상태를 명확히 고정한다.

## 확인 결과
- 수동 실행 엔진 존재:
  - `hobot/service/macro_trading/rebalancing/rebalancing_engine.py`
  - `hobot/main.py`의 `POST /api/macro-trading/rebalance/test`
- 자동화 미구현:
  - 3일 신호 확정 상태머신 없음
  - 5일 분할 집행 상태머신 없음
  - 자동 리밸런싱 전용 스케줄러 없음
- 테스트/운영 화면:
  - `hobot-ui-v2/src/components/RebalancingTestModal.tsx` (수동 phase 실행)
  - `hobot/admin_dashboard.html` (레거시 테스트 상태 조회)

## 범위 정의
- 이번 작업은 "문서 기반 실행 계획 수립"까지 수행.
- 코드 구현은 다음 단계에서 Phase 1부터 순차 진행.

## 리스크 메모
- 상태 테이블 정규화 없이 기능만 붙이면 장애 복구/재시도 경로가 불투명해짐.
- 스케줄러 동시 실행 방지(lock) 미설계 시 중복 주문 위험 존재.
