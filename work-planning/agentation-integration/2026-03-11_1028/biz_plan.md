# Agentation 통합 계획서

## 문서 목적

`hobot-ui-v2` 개발 환경에서 Agentation을 사용할 수 있게 만들고, Codex가 로컬 MCP 서버를 통해 세션을 읽을 수 있는 상태까지 정리한다.

## 목표

1. 공식 설치 문서 기준으로 `agentation`을 프런트엔드에 개발 전용으로 통합한다.
2. 기존 Vite + React 19 구조를 해치지 않고 루트 레벨에서만 로드되게 한다.
3. Codex 설정에 Agentation MCP 서버를 추가해 에이전트가 세션과 pending annotation을 읽을 수 있게 한다.
4. 최소 1회 빌드 또는 정적 검증으로 통합이 깨지지 않았는지 확인한다.

## 범위

### 포함

- `hobot-ui-v2` 의존성 추가
- dev-only Agentation 래퍼 컴포넌트 추가
- 루트 앱 트리에 Agentation 연결
- Codex MCP 서버 설정 추가
- 작업 계획/기록 문서 생성

### 제외

- Agentation 서버의 장기 실행 자동화
- 프로덕션 배포 환경 반영
- Agentation annotation 자체 작성/운영 프로세스 설계

## 설계 원칙

1. 개발 전용 도구는 `import.meta.env.DEV` 기준으로만 로드한다.
2. 루트 번들 오염을 줄이기 위해 third-party 컴포넌트는 조건부로 분리 로드한다.
3. Codex MCP 설정은 기존 `~/.codex/config.toml` 구조를 따른다.
4. 기존 미추적 변경(`.kis-api`)은 건드리지 않는다.

## 단계

### Phase 1. 앱 통합

- 설치 문서 확인
- Vite에 맞는 dev-only 로더 설계
- `App.tsx`에 루트 레벨 연결

### Phase 2. 에이전트 연결

- Agentation MCP 서버 실행 방식 확인
- Codex MCP 설정 반영
- 진단 명령으로 연결 가능 여부 확인

### Phase 3. 검증

- 프런트엔드 빌드 또는 타입 검증
- MCP 설정 결과 점검
- 작업 기록 정리
