# Frontend Redesign 및 구조 개선 분석 보고서

## 1. 개요
본 문서는 `hobot-ui` 프로젝트의 UI/UX를 전면 개편하기 위해 참조 프로젝트(`stockoverflow-redesign_v2`)를 분석하고, 이를 기존 시스템에 통합하기 위한 기술적 전략을 수립한 결과입니다.

## 2. 시스템 분석

### 2.1. 현행 시스템 (AS-IS: `hobot-ui`)
*   **프레임워크**: React 18, Create React App (CRA)
*   **언어**: JavaScript (ES6+)
*   **스타일링**: CSS Modules / Global CSS (`App.css`, `index.css`)
*   **라우팅**: `react-router-dom` v6 (기본적인 `BrowserRouter` 구조)
*   **주요 라이브러리**: `lightweight-charts`, `axios`
*   **상태 관리**: Context API (`AuthContext` - 인증 관리)
*   **특이 사항**: 
    *   전형적인 CRA 구조.
    *   `RegisterPage`, `Dashboard`, `MainPage` 등으로 구성된 단순한 페이지 구조.
    *   인증(Auth) 로직이 Context로 구현되어 있음.

### 2.2. 목표 시스템 (TO-BE: `stockoverflow-redesign_v2` 참조)
*   **프레임워크**: React 19 (RC), **Vite**
*   **언어**: **TypeScript**
*   **스타일링**: **Tailwind CSS**, Lucide React (아이콘)
*   **차트**: `recharts` (데이터 시각화 강화)
*   **디자인 컨셉**: 
    *   "AI Macro Report" 중심의 대시보드.
    *   Dark Mode 기반의 고밀도 정보 표시 (TickerTape, Grid Layout).
    *   현대적인 UI 인터랙션 (Blur effects, gradients).

### 2.3. Gap Analysis (차이점 및 개선 필요 사항)

| 구분 | 현행 (`hobot-ui`) | 목표 (Reference) | 변경 전략 |
| :--- | :--- | :--- | :--- |
| **빌드 도구** | Webpack (CRA) | Vite | **Vite로 마이그레이션 권장** (속도 및 호환성) |
| **언어** | JavaScript | TypeScript | **TypeScript 도입** (안정성 확보) |
| **스타일링** | Plain CSS | Tailwind CSS | **Tailwind CSS 설치 및 설정** |
| **아이콘** | (없음/이미지) | Lucide React | 라이브러리 추가 |
| **차트** | Lightweight Charts | Recharts | Recharts 도입 (참조 디자인 유지) |

## 3. 마이그레이션 및 실행 계획

코딩을 시작하기 전, 다음과 같은 단계로 작업을 진행할 것을 제안합니다.

### Phase 1: 개발 환경 재구성 (Foundation) ✅ 완료
1.  ✅ **Vite + TypeScript 전환**: `hobot-ui-v2` 폴더에 신규 프로젝트 생성
2.  ✅ **Tailwind CSS 설치**: `@tailwindcss/vite` 플러그인 적용
3.  ✅ **패키지 의존성 최신화**: `recharts`, `lucide-react`, `@google/genai` 등 설치

### Phase 2: 레이아웃 및 스타일 이식 (Migration) ✅ 완료
1.  ✅ **Global Style 적용**: `index.css`를 Tailwind 기반의 Dark Theme으로 교체
2.  ✅ **공통 컴포넌트 이식**: `Header`, `TickerTape`, `AIMacroReport`, `MacroIndicators`, `GeminiAnalyst` 마이그레이션
3.  ✅ **레이아웃 구성**: `App.tsx`를 새로운 레이아웃(Header + Main Content) 구조로 구성

### Phase 3: 기능 통합 (Integration) 🔄 진행 중
1.  ✅ **페이지 교체**: 로그인, 회원가입, 대시보드 페이지 구현
2.  ✅ **Auth 연동**: `AuthContext`를 TypeScript로 변환 및 `ProtectedRoute` 구현
3.  ✅ **라우팅 정리**: `/login`, `/register`, `/dashboard` 라우트 설정
4.  ⏳ **API 연동 (Backend Port: 8991)**
    *   **Proxy 설정**: `vite.config.ts` 포트 변경 (5000 → 8991)
    *   **TradingDashboard**:
        *   `GET /api/kis/balance` (계좌 잔액)
        *   `GET /api/macro-trading/rebalancing-status` (리밸런싱 현황)
        *   `GET /api/macro-trading/account-snapshots` (자산 추이)
        *   `POST /api/macro-trading/rebalance/test` (리밸런싱 테스트)
    *   **AdminPage**:
        *   `GET /api/admin/users` (사용자 목록)
        *   `PUT /api/admin/users/:id` (사용자 수정)
        *   `DELETE /api/admin/users/:id` (사용자 삭제)
    *   **AIMacroReport**:
        *   `GET /api/macro-trading/overview` (메인 리포트)
        *   `GET /api/macro-trading/strategy-decisions-history` (이력 조회)
    *   **AboutPage**: 컨텐츠 마이그레이션

### Phase 4: 검증 (Verification)
1.  ✅ UI 렌더링 확인 - 로그인 페이지, 대시보드(Mock) 정상 표시
2.  ⏳ **기능 검증**:
    *   로그인/회원가입 실제 동작 확인
    *   실제 KIS/Macro 데이터 연동 확인
    *   관리자 페이지 권한 제어 확인
3.  ⏳ **최종 점검**: 모바일 반응형 및 다크모드 점검

## 4. 작업 진행 상태

### ✅ 완료된 작업 (2026-02-01)

| 작업 | 상태 | 산출물 |
|------|------|--------|
| Vite + TypeScript 프로젝트 셋업 | ✅ | `hobot-ui-v2/` |
| Tailwind CSS 설정 | ✅ | `vite.config.ts`, `index.css` |
| AuthContext TS 변환 | ✅ | `src/context/AuthContext.tsx` |
| 타입 정의 파일 생성 | ✅ | `src/types/index.ts` |
| 로그인/회원가입 페이지 | ✅ | `App.tsx` 내 구현 |
| 컴포넌트 마이그레이션 (6개) | ✅ | `src/components/*.tsx` |
| Gemini Service 수정 | ✅ | `src/services/geminiService.ts` |
| API 프록시 설정 | ✅ | `vite.config.ts` |

### 🐞 해결된 에러

1. **TypeScript type import 에러** → `import type` 구문 사용
2. **process.env 에러** → `import.meta.env` 사용 (Vite 호환)
3. **Gemini API 초기화 에러** → Lazy 초기화로 변경

### 📁 프로젝트 구조

```
hobot-ui-v2/
├── src/
│   ├── components/     # UI 컴포넌트
│   ├── context/        # AuthContext
│   ├── services/       # Gemini Service
│   ├── types/          # TypeScript 타입
│   ├── App.tsx         # 메인 앱
│   ├── main.tsx        # 엔트리 포인트
│   └── index.css       # Tailwind + 다크 테마
├── vite.config.ts      # Vite 설정
└── package.json
```

### 🔜 다음 단계

1. 백엔드 Proxy 포트 수정 (8991) 및 API 연동
2. TradingDashboard, AdminPage, AboutPage TypeScript 마이그레이션 및 구현
3. 실제 데이터 기반 기능 테스트
4. 반응형 디자인 검증

## 5. 결론
단순한 UI 교체가 아닌, 프로젝트의 기술 스택을 현대화(Vite, TS, Tailwind)하는 작업이 동반되어야 합니다. 이는 향후 유지보수성과 확장성을 크게 높여줄 것입니다.

---

**작업 이력:**
- 2026-02-01 17:57: 초기 분석 및 계획 수립
- 2026-02-01 18:28: Phase 1~3 완료, 로그인 페이지 동작 확인
- 2026-02-01 18:47: API 문서 작성 완료 (`api_specification.md`)

---

## 🔴 EC2 배포 시 주의사항

> **vite.config.ts** 프록시 포트가 `5000`으로 설정되어 있습니다.
> 개발 환경에서 Backend(8991)와 연결하려면 **반드시 `8991`로 변경**해야 합니다.
>
> Production 빌드 시에는 Nginx가 프록시 역할을 하므로 Vite 설정은 영향 없습니다.
