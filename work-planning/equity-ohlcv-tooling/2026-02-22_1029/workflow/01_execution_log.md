# 실행 로그

- 초기 분석: `equity_analyst_agent`는 SQL 템플릿으로 OHLCV 최신행을 조회하고, 이를 agent LLM에 전달하는 구조임을 확인.
- 보완 필요점:
  - OHLCV 컬럼명이 `open_price/close_price`인 환경 대응 필요
  - 시계열 가공(이평/수익률/실적 반응) 부재
- 구현 계획 확정 후 코드 수정 진행.
- 추가 진단:
  - `equity_analysis` 키는 내려오지만 내부 값이 `null`인 케이스 발견.
  - 원인 분석 결과, US 종목 질의에서도 KR 테이블이 먼저 선택되는 SQL 템플릿 우선순위 이슈 확인.
