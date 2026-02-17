# US-KR Ontology Macro Graph 상세 실행 로드맵 (Phase 분할)

기준 문서: `global_ontology_macro_graph_master_plan.md`  
작성일: 2026-02-15

## 1. Phase 구성
1. Phase 0: US Focus 안정화 (즉시)
2. Phase 1: 데이터/스키마 기반 공사 (2주)
3. Phase 2: US/KR 정량 데이터 확장 (3주)
4. Phase 2.5: 한국 주식/기업 데이터 확장 P2/P3 (2주)
5. Phase 3: US/KR 텍스트/정책 데이터 확장 (3주)
6. Phase 4: QA 엔진 고도화 (2~3주)
7. Phase 5: 평가/운영 전환 (2주)

## 2. 권장 일정 (캘린더 기준)
- Phase 0: 2026-02-16 ~ 2026-02-18
- Phase 1: 2026-02-16 ~ 2026-02-27
- Phase 2: 2026-03-02 ~ 2026-03-20
- Phase 2.5: 2026-03-23 ~ 2026-04-03
- Phase 3: 2026-04-06 ~ 2026-04-24
- Phase 4: 2026-04-27 ~ 2026-05-15
- Phase 5: 2026-05-18 ~ 2026-05-29

## 3. 파일 맵
- `workflow/01_phase_0_us_focus_stabilization.md`
- `workflow/phase0_country_filter_audit.md`
- `workflow/02_phase_1_data_schema_foundation.md`
- `workflow/03_phase_2_uskr_quant_expansion.md`
- `workflow/04_phase_2_5_kr_equity_corporate_expansion.md`
- `workflow/05_phase_3_text_policy_expansion.md`
- `workflow/06_phase_4_qa_engine_hardening.md`
- `workflow/07_phase_5_eval_ops_transition.md`

## 4. 크리티컬 경로
1. Phase 1의 `country_code` 표준화/마이그레이션이 완료되어야 Phase 2~4의 질의 필터 일관성 확보 가능
2. Phase 2/2.5의 정량 데이터 온보딩과 코드 매핑이 완료되어야 Phase 4 답변 템플릿 품질 확보 가능
3. Phase 3의 문서-이벤트-기업 연결이 완료되어야 필수 질문(Q1~Q6) 대응 가능
4. Phase 5 골든셋/회귀 자동화가 완료되어야 운영 전환 승인 가능

## 5. 현재 상태 스냅샷 (2026-02-16)
- Phase 2.5 핵심 진척:
  - KR 기업 공시/재무/실적 기대값 파이프라인 동작
  - 기대값 feed 강제 정책 적용(기본 baseline 비활성)
  - Top50 고정 스냅샷을 DB 테이블(`kr_top50_universe_snapshot`)로 전환
  - 내부 기본 feed(`internal://kr-top50-ondemand`)로 `.env` 의존도 축소
  - 온디맨드 수집 구현은 보류, 질의 범위는 Top50 중심으로 운영
- 다음 집중 구간:
  - US 기업 실적/재무 정합성 마무리
  - Top50 월간 갱신 배치 + 이력 비교
  - Phase 3 텍스트/정책 파이프라인 본격 착수
