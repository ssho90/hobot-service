# Phase 1. Agentation 통합

## To Do

- [x] 공식 설치 문서에서 기본 설치/연결 흐름 확인
- [x] `hobot-ui-v2`에 `agentation` devDependency 추가
- [x] Vite용 dev-only 래퍼 컴포넌트 작성
- [x] 앱 루트에 Agentation 연결
- [x] 프런트엔드 빌드 검증
- [x] Codex MCP 설정에 `agentation-mcp` 서버 추가
- [x] `agentation-mcp server` + `/health`로 로컬 서버 기동 검증

## 구현 메모

- 공식 문서는 `process.env.NODE_ENV === "development"` 예시를 제공하지만, 이 프로젝트는 Vite이므로 `import.meta.env.DEV`를 사용한다.
- 번들 크기와 프로덕션 제외를 위해 dynamic import 기반으로 래핑한다.
- 루트 레벨 연결은 `AuthProvider`/`Router` 구조를 유지한 채 하단에 삽입한다.
- 컴포넌트 endpoint는 기본값 `http://localhost:4747`을 사용하고, 필요 시 `VITE_AGENTATION_ENDPOINT`로 덮어쓴다.
