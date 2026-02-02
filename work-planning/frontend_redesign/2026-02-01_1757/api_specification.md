# API Specification Document

> **문서 버전:** v1.0  
> **최종 업데이트:** 2026-02-01  
> **Backend Port:** 8991

이 문서는 `hobot-ui-v2` 프론트엔드에서 사용하는 모든 Backend API 엔드포인트를 정리합니다.

---

## 1. 인증 (Authentication)

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `POST` | `/api/auth/login` | 로그인 (MFA 지원) | Public |
| `POST` | `/api/auth/register` | 회원가입 | Public |
| `GET` | `/api/auth/me` | 현재 사용자 정보 조회 | User |

---

## 2. 사용자 프로필 (User Profile)

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/user/kis-credentials` | KIS 인증정보 조회 | User |
| `POST` | `/api/user/kis-credentials` | KIS 인증정보 저장 | User |
| `GET` | `/api/user/upbit-credentials` | Upbit 인증정보 조회 | User |
| `POST` | `/api/user/upbit-credentials` | Upbit 인증정보 저장 | User |
| `GET` | `/api/user/mfa/status` | MFA 활성화 상태 조회 | User |
| `POST` | `/api/user/mfa/setup` | MFA 설정 시작 | User |
| `POST` | `/api/user/mfa/verify-setup` | MFA 설정 검증 | User |
| `POST` | `/api/user/mfa/disable` | MFA 비활성화 | User |
| `POST` | `/api/user/mfa/regenerate-backup-codes` | 백업 코드 재생성 | User |

---

## 3. Macro Trading (Dashboard)

### 3.1 AI 분석 & Overview

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/macro-trading/overview` | AI 경제 분석 요약 조회 | User |
| `POST` | `/api/macro-trading/run-ai-analysis` | 수동 AI 분석 실행 | Admin |
| `GET` | `/api/macro-trading/strategy-decisions-history` | 분석 이력 조회 (Pagination) | User |

### 3.2 FRED 경제지표

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/macro-trading/yield-curve-spread` | 장단기 금리차 데이터 | User |
| `GET` | `/api/macro-trading/fred-data` | FRED 개별 지표 데이터 | User |
| `GET` | `/api/macro-trading/real-interest-rate` | 실질금리 데이터 | User |
| `GET` | `/api/macro-trading/net-liquidity` | 순유동성 데이터 | User |

**Query Parameters:**
- `indicator_code`: FRED 지표 코드 (예: `UNRATE`, `CPIAUCSL`)
- `days`: 조회 기간 (기본: 365)

### 3.3 경제 뉴스

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/news` | 뉴스 목록 조회 | User |
| `GET` | `/api/news-update` | 뉴스 새로고침 | Admin |
| `GET` | `/api/macro-trading/economic-news` | 경제 뉴스 목록 | User |

**Query Parameters:**
- `hours`: 최근 N시간 뉴스 (기본: 24)
- `force`: 강제 새로고침 여부

---

## 4. Trading

### 4.1 KIS 계좌

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/kis/balance` | KIS 계좌 잔액 및 보유자산 조회 | User |

### 4.2 리밸런싱

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/macro-trading/rebalancing-status` | 리밸런싱 현황 (MP/Sub-MP) | User |
| `GET` | `/api/macro-trading/account-snapshots` | 계좌 스냅샷 이력 | User |
| `GET` | `/api/macro-trading/rebalancing-history` | 리밸런싱 이력 조회 | User |
| `POST` | `/api/macro-trading/rebalance/test` | 리밸런싱 테스트 실행 | Admin |

**Query Parameters:**
- `days`: 조회 기간 (기본: 30)

### 4.3 Upbit

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/upbit/account-summary` | Upbit 계좌 요약 | User |
| `POST` | `/api/upbit/operation/start` | Upbit 자동매매 시작 | User |
| `POST` | `/api/upbit/operation/pause` | Upbit 자동매매 중지 | User |
| `GET` | `/api/upbit/strategy/current` | 현재 Upbit 전략 조회 | User |

---

## 5. Admin

### 5.1 사용자 관리

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/admin/users` | 사용자 목록 조회 | Admin |
| `PUT` | `/api/admin/users/:id` | 사용자 정보 수정 | Admin |
| `DELETE` | `/api/admin/users/:id` | 사용자 삭제 | Admin |

### 5.2 로그 관리

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/admin/logs` | 시스템 로그 조회 | Admin |

**Query Parameters:**
- `log_type`: 로그 타입 (예: `error`, `access`)
- `lines`: 조회 라인 수

### 5.3 LLM 모니터링

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/llm-monitoring/options` | 모니터링 옵션 조회 | Admin |
| `GET` | `/api/llm-monitoring/logs` | LLM 호출 로그 조회 | Admin |
| `GET` | `/api/llm-monitoring/token-usage` | 토큰 사용량 조회 | Admin |

### 5.4 파일 관리

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/admin/files` | 업로드된 파일 목록 | Admin |
| `POST` | `/api/admin/files/upload` | 파일 업로드 | Admin |
| `PUT` | `/api/admin/files/:id` | 파일 정보 수정 | Admin |
| `DELETE` | `/api/admin/files/:id` | 파일 삭제 | Admin |

### 5.5 포트폴리오 관리

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| `GET` | `/api/admin/portfolios/model-portfolios` | Model Portfolio 목록 | Admin |
| `PUT` | `/api/admin/portfolios/model-portfolios/:id` | MP 수정 | Admin |
| `GET` | `/api/admin/portfolios/sub-model-portfolios` | Sub-MP 목록 | Admin |
| `PUT` | `/api/admin/portfolios/sub-model-portfolios/:id` | Sub-MP 수정 | Admin |
| `GET` | `/api/macro-trading/rebalancing/config` | 리밸런싱 설정 조회 | Admin |
| `PUT` | `/api/macro-trading/rebalancing/config` | 리밸런싱 설정 수정 | Admin |
| `GET` | `/api/macro-trading/crypto-config` | 암호화폐 설정 조회 | Admin |
| `PUT` | `/api/macro-trading/crypto-config` | 암호화폐 설정 수정 | Admin |

---

## 6. EC2 배포 관련 참고사항

### 🔴 vite.config.ts 수정 필요

현재 설정:
```typescript
proxy: {
  '/api': {
    target: 'http://localhost:5000', // ❌ 잘못된 포트
    changeOrigin: true,
  }
}
```

수정 필요:
```typescript
proxy: {
  '/api': {
    target: 'http://localhost:8991', // ✅ 올바른 포트
    changeOrigin: true,
  }
}
```

### 🔴 Production 빌드 시 참고

Production 환경에서는 Nginx가 `/api` 요청을 Backend(8991 포트)로 프록시합니다.
Vite proxy 설정은 **개발 환경에서만** 적용됩니다.

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-01 | v1.0 | 초기 문서 작성 |
