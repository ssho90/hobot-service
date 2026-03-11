# Daily History

## 2026-03-11
- 세션: [01_agentation_setup.md](./01_agentation_setup.md)
- 핵심 요약: `hobot-ui-v2`에 Agentation을 dev-only로 통합했고, Codex 전역 MCP 설정에 `agentation-mcp` 서버를 추가했으며, 빌드와 `/health` 응답으로 검증까지 마쳤다.
- 이슈/해결: 공식 예시는 `process.env.NODE_ENV` 기준이지만 Vite 프로젝트라 `import.meta.env.DEV` 기반 dynamic import 래퍼로 바꿨고, `add-mcp`는 대화형 선택 때문에 중단한 뒤 Codex TOML을 직접 최소 수정했다.
- 다음 목표: Codex 앱/세션을 재시작해 새 MCP 서버를 로드하고 실제 annotation workflow를 사용한다.
