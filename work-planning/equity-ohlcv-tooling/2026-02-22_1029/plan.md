# Equity OHLCV Tooling 개선 계획

## 목표
주가 에이전트(`equity_analyst_agent`)가 OHLCV 원시 행 조회를 넘어,
- 단기/장기 이평 기반 추세
- 실적 발표 전후 가격 반응
을 정량 지표로 가공하여 에이전트 LLM 및 supervisor 합성 단계에서 활용하도록 개선한다.

## 작업 범위
1. Equity SQL 템플릿 컬럼 후보 보강
2. Live Executor에 `equity_analysis` 계산기 추가
3. StructuredDataContext에 `equity_analysis` 요약 반영
4. 단위 테스트 추가 및 회귀 검증
5. 국가/심볼 기반 SQL 템플릿 우선순위 보정(US 질의가 KR 테이블을 먼저 타는 문제 수정)
6. 실제 질의 2~3건 런타임 검증 및 토큰/지연 리포트 수집

## 완료 기준
- `tool_probe`에 `equity_analysis`가 포함된다.
- `equity_analysis`에 MA(20/60/120), 기간 수익률, 실적 이벤트 반응이 계산된다.
- 관련 테스트가 통과한다.
- US 단일종목 질의 시 `us_top50_daily_ohlcv`가 우선 선택되고, `AAPL/NVDA`에서 비어있지 않은 MA/실적반응 값이 확인된다.
