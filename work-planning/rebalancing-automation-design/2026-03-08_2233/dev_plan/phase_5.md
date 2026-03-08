# Phase 5. 운영 화면, 예외 처리, 결과 가시화

## 목표
- 관리자와 운영자가 자동 리밸런싱 상태와 테스트 결과를 추적할 수 있게 한다.
- 예외 처리, 수동 개입, retry/restart, kill switch를 제공한다.

## 대상 파일
- `hobot/main.py`
- `hobot-ui-v2/src/components/admin/`
- `hobot/admin_dashboard.html` 또는 후속 admin 화면
- 신규 `hobot/service/macro_trading/rebalancing/result_view_service.py`

## 구현 포인트
- active run 조회
- pending candidate 조회
- effective target 조회
- 테스트 세션 결과 조회
- `virtual_business_date` 표시
- user별 주문/체결 결과 표시
- kill switch
- retry/restart

## 체크리스트

### To-Do
- [ ] 관리자 API 정의
  - active runs
  - pending candidates
  - effective targets
  - test session results
- [ ] user별 order/result 조회 API 구현
- [ ] `+1 business day` 버튼 연결
- [ ] expected vs actual 비교 리포트 구현
- [ ] kill switch / auto rebalance on-off UI 구현
- [ ] retry/restart UI 또는 API 구현

### In Progress
- [ ] 결과 화면 정보 구조 설계
- [ ] 어떤 예외를 화면에서 직접 재시도할지 결정

### Done
- [ ] 테스트 결과 화면 요구사항 정의

## 완료 기준
- 운영자가 user별 run 상태, 주문 결과, 체결 결과를 볼 수 있다.
- `PAPER_TIME_TRAVEL` 테스트 세션 결과를 날짜별로 확인할 수 있다.
- 실패 원인과 상태 전이 로그를 추적할 수 있다.
- 긴급 중지와 재시도를 운영자가 제어할 수 있다.

## 리스크
- 화면 가시화가 없으면 운영 중 예외 상황에서 상태 판단이 늦어진다.
- kill switch가 백엔드 실행 경로와 완전히 연결되지 않으면 운영 안전성이 없다.
