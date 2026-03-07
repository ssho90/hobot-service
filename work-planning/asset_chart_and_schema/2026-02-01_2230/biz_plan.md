# Plan: 자산 추이 차트 및 데이터베이스 스키마 개선

## 1. 개요
사용자별 자산 상태를 관리하기 위해 `account_snapshots` 테이블에 `user_id` 컬럼을 추가하고, 이를 기반으로 총 자산 추이 차트를 구현합니다.

## 2. 데이터베이스 스키마 변경
`account_snapshots` 테이블 구조를 변경하여 다중 사용자를 지원하도록 합니다.

### SQL Query (사용자 요청 사항)
```sql
-- 1. 컬럼 추가
ALTER TABLE account_snapshots ADD COLUMN user_id VARCHAR(50) NOT NULL DEFAULT 'ssho' AFTER id;

-- 2. 기존 데이터에 사용자 ID 적용 (기본값 설정으로 이미 적용되지만 명시적으로 확인)
UPDATE account_snapshots SET user_id = 'ssho' WHERE user_id IS NULL;

-- 3. 기존 유니크 키 삭제 (날짜 기준)
ALTER TABLE account_snapshots DROP INDEX unique_date;

-- 4. 새로운 복합 유니크 키 추가 (사용자 + 날짜)
ALTER TABLE account_snapshots ADD UNIQUE KEY unique_user_date (user_id, snapshot_date);

-- 5. 인덱스 추가 (조회 성능 향상)
ALTER TABLE account_snapshots ADD INDEX idx_user_date (user_id, snapshot_date);
```

## 3. 백엔드 변경 (`hobot-service`)

### `hobot/service/macro_trading/account_service.py`
- `save_daily_account_snapshot` 함수 수정:
    - `user_id`를 조회하여 저장 시 포함.
    - 중복 체크 로직을 `snapshot_date` + `user_id` 기준으로 변경.
    - UPDATE 및 INSERT 쿼리에 `user_id` 조건 추가.

### `hobot/main.py`
- `get_account_snapshots` API 수정:
    - `admin_user` 의존성 대신 `current_user` 사용 (또는 둘 다 허용).
    - SQL 쿼리에 `WHERE user_id = %s` 조건 추가하여 본인 데이터만 조회하도록 변경.

## 4. 프론트엔드 변경 (`hobot-ui-v2`)

### `src/components/TotalAssetTrendChart.tsx` (신규)
- Recharts 라이브러리를 사용하여 라인 차트 구현.
- X축: `snapshot_date`, Y축: `total_value`.
- 툴팁에 상세 정보(현금, 자산 배분 등) 표시.

### `src/components/AIMacroReport.tsx` (수정)
- 신규 생성한 `TotalAssetTrendChart` 컴포넌트 삽입.
- API 데이터 연동.

## 5. 단계별 검증 계획
1.  **DB 마이그레이션**: 로컬 DB(있다면) 또는 테스트 환경에서 SQL 실행 후 스키마 확인.
2.  **API 테스트**: `curl` 명령어로 `get_account_snapshots` 호출하여 필터링 작동 확인.
3.  **UI 확인**: 브라우저에서 차트 렌더링 및 데이터 정확성 확인.
