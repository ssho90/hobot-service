# KR Earnings Sort Memory 근본 개선

## 목표
- KR 실적 핫패스에서 MySQL 1038(out of sort memory) 재발 방지
- DB sort 의존을 줄이고 인덱스 기반 조회/애플리케이션 dedupe로 전환

## 작업
1. `kr_corporate_earnings_expectations` 조회 쿼리에서 정렬(`ORDER BY`) 제거
2. 파이썬에서 최신값 우선 dedupe 로직으로 대체
3. 기대치 조회용 인덱스 자동 보강(없는 환경 마이그레이션)
4. 단위 테스트/정적 점검 실행

## 완료 기준
- 기존 기능(최신 expectation 선택) 유지
- 정렬 메모리 에러 유발 지점 제거
- 배포 후 추가 DB 파라미터 튜닝 없이 동작
