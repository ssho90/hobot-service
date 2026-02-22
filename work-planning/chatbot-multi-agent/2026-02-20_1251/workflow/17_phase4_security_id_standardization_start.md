# Phase 4 1차 착수 기록 - security_id 표준화

- 일시: 2026-02-20
- 목표: KR/US 종목 식별자를 `security_id` 기준으로 정규화하고 Equity SQL 템플릿에 우선 적용

## 변경 파일
- `hobot/service/graph/rag/security_id.py` (신규)
- `hobot/service/graph/rag/agents/live_executor.py`
- `hobot/tests/test_phase4_security_id.py` (신규)

## 구현 내용
1. `security_id` 정규화 유틸 추가
   - 표준: `security_id = "{country_code}:{native_code}"`
   - KR 코드 zero-pad(6자리), US 티커 대문자 정규화
   - `build_equity_focus_identifiers()`로 route/request 기반 식별자 컨텍스트 생성
2. Equity SQL 실행기 표준화
   - 템플릿 스펙에 `security_id_candidates` 추가
   - `security_id` 컬럼 존재 시 `symbol`보다 우선 필터
   - 실행 결과 `filters.security_id`, `identifier` 메타 기록

## 테스트
- `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase4_security_id.py`
  - 결과: `Ran 5 tests ... OK`
- 회귀 확인:
  - `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
  - `cd hobot && GRAPH_RAG_REQUIRE_DB_TESTS=1 PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
  - 결과: 모두 통과

## 다음 작업
1. Macro/RealEstate 템플릿 레지스트리 분리(`templates/*`) 및 required params 명시.
2. Ontology Text2Cypher 방향성 스키마 문자열/퓨샷 템플릿 고정.
3. `security_id` 매퍼를 context/router에도 연결해 입력 혼용(KR 종목코드/US 티커/`KR:005930`)을 공통 키로 수렴.
