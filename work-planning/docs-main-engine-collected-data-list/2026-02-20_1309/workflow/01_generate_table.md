# Workflow Log - Generate Collected Data Table

## 실행 계획
1. indicator_health 레지스트리에서 (country, code, name, description) 추출
2. code 기준 중복 제거 및 국가/코드 정렬
3. `docs-main-engine/collected-data-list.md`에 Markdown 테이블로 저장
4. 건수 검증

## 실행 결과
- `indicator_health` 레지스트리(KR/US/GRAPH/PIPELINE/FRED)에서 코드 목록을 추출.
- 코드 기준 중복 제거 후 국가/코드 순으로 정렬.
- `docs-main-engine/collected-data-list.md`에 Markdown 테이블 반영.
- 반영 건수: 총 61개 코드.

## 비고
- `docs-main-engine/base-data-list.md` 파일은 현재 경로에 존재하지 않음.
