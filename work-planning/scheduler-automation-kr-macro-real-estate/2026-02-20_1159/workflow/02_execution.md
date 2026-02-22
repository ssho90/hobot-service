# 실행 로그 (수동 트리거)

## 실행 시각
- 2026-02-20 (KST)

## 수행 내용
1. `run_kr_macro_collection_from_env()` 실행
2. `run_kr_real_estate_pipeline_from_env()` 실행

## 결과 요약
- KR 거시:
  - 성공 7, 실패 1
  - 실패: `KR_BASE_RATE` (`ECOS_API_KEY` 미설정)
  - `KR_USDKRW` 247포인트 수집/적재
  - 부동산 보조지표 4종 수집 성공
- KR 부동산 파이프라인:
  - 수집: `84546` rows
  - DB 반영: `143179`
  - 월집계: `415` rows (`month_count=3`, `region_count=139`)
  - 그래프 동기화: 성공 (`properties_set=7055`)

## 참고
- 실행 환경의 샌드박스 제한에서는 로컬 DB/외부 API 접근이 차단되어 실패했고,
  권한 확장 실행에서 정상 수행됨.

## ECOS_API_KEY 반영 후 재검증
- 실행: `collect_kr_macro_data(indicator_codes=["KR_BASE_RATE"], days=3650)`
- 결과: `KR_BASE_RATE` 수집 성공 (points=119, rows=119, db_affected=119)
- 헬스 변화:
  - before: healthy 54 / stale 2 / missing 5
  - after:  healthy 55 / stale 2 / missing 4
- 상태: `KR_BASE_RATE` -> `healthy` 전환 확인 (`last_collected_at=2026-02-20T03:12:42`)
