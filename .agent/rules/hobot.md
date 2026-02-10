---
trigger: always_on
---

# 🛸 Antigravity Global Behavior & Workflow Guidelines (Updated)

## 🤖 1. CORE DIRECTIVES (핵심 원칙)

* **Tool-First Approach:** 내부 지식보다 MCP 도구(`context7`, `sequentialthinking`) 사용을 우선합니다. 게으르게 추측하지 말고 도구로 확인하십시오.
* **Strict Korean Language:** 모든 응답(생각 과정, 계획, 코드 설명, 요약 등)은 반드시 **한국어**로 작성합니다. (표준 기술 용어 제외)

## 📂 2. WORKFLOW & DOCUMENTATION (작업 및 기록 관리)

모든 작업은 반드시 다음 파일 시스템 구조를 생성하고 업데이트하며 진행합니다.
`/work-planning/{업무명}/{YYYY-MM-DD_HHmm}/`

* `plan.md`: 작업 전 수립하는 전체 계획서.
* `workflow/`: 하위 폴더. 작업 단계별 상세 로그 저장.

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

