# SQLite 마이그레이션 가이드

## 개요

이 프로젝트는 JSON 파일 기반 데이터 저장에서 **SQLite** 데이터베이스로 마이그레이션되었습니다.

## 왜 SQLite인가?

- ✅ **완전 무료**: 추가 비용 없음
- ✅ **Python 내장**: 별도 설치 불필요
- ✅ **파일 기반**: JSON과 유사한 관리 방식
- ✅ **ACID 트랜잭션**: 데이터 무결성 보장
- ✅ **인덱싱 지원**: 빠른 검색 성능
- ✅ **EC2 리소스만 사용**: 추가 인프라 불필요

## 마이그레이션된 데이터

다음 데이터가 JSON에서 SQLite로 마이그레이션되었습니다:

1. **사용자 데이터** (`users.json` → `users` 테이블)
2. **메모리 저장소** (`memory_store.json` → `memory_store` 테이블)
3. **전략 설정** (`CurrentStrategy.json` → `strategies` 테이블)
4. **토큰 저장** (향후 `tokens` 테이블 사용 가능)

## 마이그레이션 방법

### 자동 마이그레이션

프로젝트를 시작하면 자동으로 마이그레이션이 실행됩니다. 또는 수동으로 실행할 수 있습니다:

```bash
cd hobot
python migrate_to_sqlite.py
```

### 수동 마이그레이션

1. 데이터베이스 초기화:
   ```python
   from service.database.db import init_database
   init_database()
   ```

2. 데이터 마이그레이션:
   ```python
   from service.database.db import migrate_from_json
   migrate_from_json()
   ```

## 데이터베이스 위치

- **데이터베이스 파일**: `hobot/service/database/hobot.db`
- **백업**: 기존 JSON 파일은 그대로 유지됩니다

## 데이터베이스 구조

### users 테이블
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### memory_store 테이블
```sql
CREATE TABLE memory_store (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### strategies 테이블
```sql
CREATE TABLE strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT UNIQUE NOT NULL,
    strategy TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### tokens 테이블
```sql
CREATE TABLE tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_type TEXT NOT NULL,
    token_data TEXT NOT NULL,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## 데이터베이스 관리

### SQLite CLI 사용

```bash
# 데이터베이스 연결
sqlite3 hobot/service/database/hobot.db

# 테이블 목록 확인
.tables

# 데이터 조회
SELECT * FROM users;
SELECT * FROM memory_store;
SELECT * FROM strategies;

# 종료
.quit
```

### Python으로 조회

```python
from service.database.db import get_db_connection

with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    for row in rows:
        print(dict(row))
```

## 백업 및 복원

### 백업 위치

백업 파일은 **시스템 경로**에 저장됩니다:
- **기본 경로**: `/var/backups/hobot/`
- **권한이 없는 경우**: `hobot/service/database/backups/` (자동 폴백)

### 백업 방법

#### 1. Python 함수 사용

```python
from service.database.db import backup_database

# 데이터베이스 백업
backup_path = backup_database()
print(f"백업 완료: {backup_path}")
```

#### 2. 백업 유틸리티 사용

```bash
# 백업 실행
python hobot/service/database/backup_utils.py backup

# 백업 목록 조회
python hobot/service/database/backup_utils.py list

# 백업 복원
python hobot/service/database/backup_utils.py restore --file /var/backups/hobot/hobot_backup_20240101_120000.db
```

#### 3. 수동 백업

```bash
# 시스템 경로에 직접 복사
sudo mkdir -p /var/backups/hobot
sudo cp hobot/service/database/hobot.db /var/backups/hobot/hobot_backup_$(date +%Y%m%d_%H%M%S).db

# 또는 SQL 덤프
sqlite3 hobot/service/database/hobot.db .dump > /var/backups/hobot/backup_$(date +%Y%m%d_%H%M%S).sql
```

### 복원 방법

#### 1. Python 함수 사용

```python
from service.database.db import restore_database

# 백업 파일로 복원
restore_database("/var/backups/hobot/hobot_backup_20240101_120000.db")
```

#### 2. 백업 유틸리티 사용

```bash
python hobot/service/database/backup_utils.py restore --file /var/backups/hobot/hobot_backup_20240101_120000.db
```

#### 3. 수동 복원

```bash
# 백업 파일로 복원
sudo cp /var/backups/hobot/hobot_backup_20240101_120000.db hobot/service/database/hobot.db

# 또는 SQL 덤프에서 복원
sqlite3 hobot/service/database/hobot.db < /var/backups/hobot/backup_20240101_120000.sql
```

### 백업 자동 정리

백업 함수는 자동으로 30일 이상 된 백업 파일을 삭제합니다:

```python
from service.database.db import cleanup_old_backups

# 30일 이상 된 백업 파일 삭제
cleanup_old_backups(days=30)

# 7일 이상 된 백업 파일 삭제
cleanup_old_backups(days=7)
```

## 성능 최적화

SQLite는 자동으로 인덱스를 생성합니다:
- `users.username` (UNIQUE)
- `users.email` (UNIQUE)
- `memory_store.topic`
- `strategies.platform` (UNIQUE)
- `tokens.token_type`

## 주의사항

1. **동시성 제한**: SQLite는 동시 쓰기에 제한이 있습니다. 읽기는 다중 가능하지만, 쓰기는 단일 프로세스만 가능합니다.
2. **파일 크기**: SQLite는 파일 기반이므로 대용량 데이터에는 부적합할 수 있습니다.
3. **백업**: 정기적으로 데이터베이스 파일을 백업하세요.

## 문제 해결

### 데이터베이스 파일이 생성되지 않는 경우

```python
from service.database.db import ensure_database_dir, init_database
ensure_database_dir()
init_database()
```

### 마이그레이션 오류

1. JSON 파일이 손상된 경우: 백업에서 복원
2. 권한 문제: 데이터베이스 디렉토리 쓰기 권한 확인
3. 디스크 공간 부족: EC2 인스턴스 디스크 공간 확인

## 추가 리소스

- [SQLite 공식 문서](https://www.sqlite.org/docs.html)
- [Python sqlite3 모듈](https://docs.python.org/3/library/sqlite3.html)

