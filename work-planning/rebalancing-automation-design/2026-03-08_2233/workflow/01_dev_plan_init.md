# 01. Dev Plan Init

## 목적
- `biz_plan.md`를 기준으로 실제 구현 단계를 `dev_plan/phase_1.md` ~ `phase_5.md`로 분해한다.

## 수행 내용
- `workflow/`는 작업 이력용, `dev_plan/`은 구현 계획용이라는 규칙 재확인
- `dev_plan` 폴더 생성
- 아래 phase 문서 작성
  - `phase_1.md`: 신호 안정화 계층
  - `phase_2.md`: 모의투자 + Time Travel 테스트 인프라
  - `phase_3.md`: 멀티데이 run 상태머신
  - `phase_4.md`: 스케줄러 fan-out
  - `phase_5.md`: 운영 화면/예외 처리

## 결과
- 구현 계획이 Phase 단위로 분리되었고, 이후 실제 코딩은 각 phase 문서의 체크리스트를 따라 진행할 수 있는 상태가 되었다.

## 다음 단계
- `phase_1.md`부터 실제 구현 착수
