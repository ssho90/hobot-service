# Top50 OHLCV 연속성 + 장마감 스케줄 개선 계획

## 목표
- KR/US Top50이 월별로 교체되어도 OHLCV 시계열 연속성을 유지한다.
- KR/US Top50 일별 OHLCV 수집 스케줄의 기본 실행 시각을 장마감 이후로 조정한다.

## 작업 범위
1. KR/US 수집기에서 Top50 최신 스냅샷 + 최근 N일 스냅샷 유니버스 병합 로직 추가
2. 스케줄러에서 continuity_days 환경변수 전달 및 기본값 추가
3. 스케줄 기본 시각 변경 (KR 16:20, US 07:10 KST)
4. 관련 테스트 보강/수정 후 검증 실행

## 연속성 정책
- 저장 연속성: OHLCV 테이블은 심볼/일자 기준 누적(upsert)하고 삭제하지 않는다.
- 수집 연속성: 최신 Top50 + 최근 continuity_days 내 Top50 스냅샷 등장 종목을 모두 수집 대상으로 삼는다.
- 기본 continuity_days: 120일 (환경변수로 조정 가능)

## 검증 기준
- collect_top50_daily_ohlcv 결과에 연속성 관련 대상 수 집계가 반영된다.
- scheduler hotpath/from_env에서 continuity_days가 collector로 전달된다.
- scheduler setup 테스트에서 기본 시각이 장마감 이후 값으로 검증된다.
