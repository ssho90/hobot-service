# Gemini Model Update

## 비즈니스 목표
- 기존 `gemini-3.0-pro-preview` (및 관련 표기) 모델 명칭을 신규 버전인 `gemini-3.1-pro-preview`로 일괄 업데이트.

## 요구사항
- 프로젝트 내의 Python 소스 코드, HTML/UI 코드, 설정 파일(`json`), 마크다운 문서 등에서 사용 중인 구버전 명칭을 추적하여 신버전 명칭으로 안전하게 치환.

## Phase 1: 일괄 업데이트 수행
- [x] 변경 대상 식별: `grep_search`로 `gemini-3.0-pro-preview`, `gemini-3-pro-preview`, `gemini-3.0-pro` 로 사용되는 패턴 분석.
- [x] 자동 치환 스크립트 작성 및 실행: Python 스크립트로 작업 자동화 진행.
- [x] 검증: 전체 소스코드 재검색을 통한 누락 여부 확인.
