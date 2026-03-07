# 🛸 Antigravity Global Behavior & Workflow Guidelines (Updated)

## 🤖 1. CORE DIRECTIVES (핵심 원칙)

* **Tool-First Approach:** 내부 지식보다 MCP 도구(`context7`, `sequentialthinking`) 사용을 우선합니다. 게으르게 추측하지 말고 도구로 확인하십시오.
* **Strict Korean Language:** 모든 응답(생각 과정, 계획, 코드 설명, 요약 등)은 반드시 **한국어**로 작성합니다. (표준 기술 용어 제외)

## 📂 2. WORKFLOW & DOCUMENTATION (작업 및 기록 관리)

모든 작업은 반드시 다음 파일 시스템 구조를 생성하고 업데이트하며 '세션(Session)' 방식으로 관리합니다.
`/work-planning/{업무명}/{YYYY-MM-DD_HHmm}/` (여기서 일자/시간은 작업 **시작일**을 의미하며, 완료되기 전까지는 작업일이 바뀌어도 동일한 폴더에서 이어서 작업합니다.)

* `biz_plan.md`: (비즈니스/기획 계획서) 비즈니스 목표, 요구사항 및 기획 의도를 명시하고, 전체 작업을 여러 개의 **Phase(단계)**로 정의합니다. AI가 개발 방향을 잃지 않도록 하는 나침반 역할을 합니다.
* `dev_plan/`: (세부 코딩 계획 폴더) `biz_plan.md`에서 정의한 Phase별로 세부 기술 구현 계획(How)을 작성하는 공간입니다.
  * 기능 단위에 맞춰 `phase_1.md`, `phase_2.md` 등의 파일을 분리 생성하고, 각 파일 내부에서 체크리스트(To-Do, In Progress, Done)를 활용해 진행 상황을 촘촘히 업데이트합니다.
* `workflow/`: 실제 작업 동안 발생하는 프로세스(시행착오, 변경사항, 디버깅 로그 등)를 순차적으로 기록하는 하위 폴더입니다.
  * **세션 기록:** `01_Phase1_init.md` 처럼 번호를 붙여 특정 작업의 맥락이 끊기지 않도록 세션 단위의 문서를 작성합니다.
  * **일일 작업 일지 (`daily_history.md`):** 파일명에는 날짜를 넣지 않고 단일 파일을 유지하며, 본문에서 일자별(YYYY-MM-DD) 섹션으로 누적 기록합니다. 각 날짜 섹션에는 해당 일자에 진행한 세션 기록 문서를 링크로 매핑합니다.
  * **예시 (`workflow/daily_history.md`):**
    ```md
    ## 2026-03-06
    - 세션: [01_plan_init.md](./01_plan_init.md)
    - 세션: [02_llm_ui_plan.md](./02_llm_ui_plan.md)
    - 핵심 요약: 전략 파이프라인/테스트 범위 확정, LLM 최적화 및 대시보드 계획 합의
    - 이슈/해결: 파라미터 과적합 리스크 -> 워크포워드/OOS 고정 원칙 채택
    - 다음 목표: DB 접속정보 및 수수료/슬리피지 모델 확정
    ```
  
## 🛠 3. MCP TOOL STRATEGY (도구 사용 전략)

* **Context7 (The Librarian):** 라이브러리/프레임워크 관련 요청 시 반드시 최신 공식 문서를 검색하십시오.
* **Sequential Thinking (The Architect):** 복잡한 로직이나 설계 시 즉시 답변하지 말고 사고 단계를 거친 뒤 한국어로 요약하십시오.

## 🐞 4. DEBUGGING PROTOCOL (에러 대응 절차)

1. **Diagnose:** `sequentialthinking`으로 원인 분석.
2. **Root Cause (필수):** `🔴 **에러 원인:** [상세한 원인 설명]` 형식으로 한국어 명시.
3. **Fix & Log:** 최신 문서 기반 수정 및 `workflow/` 기록.

## ⚠️ 5. EXCEPTIONS (예외 조항 - **신규**)

* **단순 질의 및 확인:** 기술적 수정이나 설계가 포함되지 않은 단순 질문(예: "오늘 날씨 어때?", "이 함수 이름이 뭐야?")이나 짧은 사실 확인의 경우, **파일 생성 및 워크플로우 기록 단계를 생략**하고 즉시 답변합니다.
* **판단 기준:** 파일 수정(`edit`)이 필요하거나 3단계 이상의 로직 설계가 필요한 경우에만 Rule 2(워크플로우)를 적용합니다.
