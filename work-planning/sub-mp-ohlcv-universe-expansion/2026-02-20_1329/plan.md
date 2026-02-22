# Sub-MP 세부 종목 OHLCV 수집 확장 계획

## 1. 목표
- 현재 KR/US Top50 중심 일봉 OHLCV 수집 범위를 Sub-MP 세부 종목(구성 티커/종목코드)까지 확장한다.
- 기존 Top50 연속성(continuity) 로직은 유지한다.

## 2. 구현 전략
1. Scheduler에서 활성 Sub-MP 구성 종목을 DB(`sub_portfolio_models`, `sub_portfolio_compositions`)에서 조회한다.
2. 국가별(KR/US)로 정규화/분류 후 OHLCV 수집 타깃에 병합한다.
3. Collector는 Top50 기본 타깃 + extra 타깃 병합을 지원하도록 확장한다.
4. env 스위치로 on/off 및 최대 개수 제어를 제공한다.

## 3. 변경 범위
- `hobot/service/macro_trading/scheduler.py`
- `hobot/service/macro_trading/collectors/kr_corporate_collector.py`
- `hobot/service/macro_trading/collectors/us_corporate_collector.py`
- 관련 테스트 파일

## 4. 검증
- Scheduler unit test: sub-mp 유니버스 병합/환경변수 전달 검증
- Collector unit test: extra 타깃이 해상/요약에 반영되는지 검증
