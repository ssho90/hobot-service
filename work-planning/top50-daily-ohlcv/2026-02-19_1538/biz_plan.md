# Top50 Daily OHLCV 적재 계획

- 업무명: KR/US Top50 일별 OHLCV DB 적재
- 시작시각: 2026-02-19 15:38
- 목표:
  - KR/US Top50 유니버스 기준 일봉 OHLCV를 DB에 적재
  - 스케줄러에서 일별 자동 실행 가능하도록 연결
  - 단위 테스트 추가로 회귀 방지

## 작업 범위
- 수집기 확장
  - `kr_corporate_collector.py`
  - `us_corporate_collector.py`
- 스케줄러 확장
  - `scheduler.py`
- 테스트 추가/수정
  - `test_kr_corporate_collector.py`
  - `test_us_corporate_collector.py`
  - `test_scheduler_kr_top50_ohlcv.py` (신규)
  - `test_scheduler_us_top50_ohlcv.py` (신규)

## 구현 원칙
- 일별 데이터만 저장 (intraday 제외)
- 동일 종목/일자 데이터는 UPSERT
- Top50 스냅샷 우선 사용, 없을 경우 각 수집기 기본 타깃으로 보완
- 실패 심볼은 요약에 남기고 전체 작업은 지속

## 검증 계획
- 관련 테스트 파일 개별 실행
- 문법/임포트 오류 확인
