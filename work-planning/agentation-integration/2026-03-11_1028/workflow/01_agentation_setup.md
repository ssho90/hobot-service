# Session 01. Agentation 설치 및 연결

## 목표

- Agentation 공식 설치 문서를 기준으로 현재 `hobot-ui-v2`에 맞는 통합 방식을 적용한다.
- Codex에서 Agentation MCP 서버를 사용할 수 있게 설정한다.

## 진행 기록

1. `https://www.agentation.com/install` 문서를 확인했다.
2. 공식 문서 기준 핵심 절차를 분리했다.
   - `npm install agentation -D`
   - React 루트 레벨에 `<Agentation />` 추가
   - 필요 시 `agentation-mcp` 서버를 `npx`로 연결
3. 현재 프로젝트 구조를 확인했다.
   - 프런트엔드 앱: `hobot-ui-v2`
   - 런타임: Vite 7 + React 19
   - Codex 전역 설정: `~/.codex/config.toml`
4. Vite에서는 `process.env.NODE_ENV`보다 `import.meta.env.DEV`가 적합하다고 판단했다.
5. `hobot-ui-v2`에 `agentation@^2.3.2`를 devDependency로 설치했다.
6. `src/components/dev/DevAgentation.tsx`를 추가하고 `src/App.tsx` 루트에 연결했다.
7. `npm run build`가 통과했고, production 번들에는 Agentation chunk가 포함되지 않았다.
8. `~/.codex/config.toml`에 아래 MCP 설정을 추가하고 원본을 `config.toml.agentation-backup-20260311`로 백업했다.

```toml
[mcp_servers.agentation]
args = ["-y", "agentation-mcp", "server"]
command = "npx"
enabled = true
```

9. `npx -y agentation-mcp server`를 실행해 `HTTP: http://localhost:4747` 기동 메시지를 확인했다.
10. `curl http://127.0.0.1:4747/health` 응답 `{"status":"ok","mode":"local"}`로 로컬 서버 상태를 검증했다.
