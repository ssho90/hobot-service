# 데이터베이스 설정 가이드

## 📋 개요

이 프로젝트는 **SQLite** 데이터베이스를 사용하여 최소 비용으로 데이터를 관리합니다.

## 💰 비용 비교

| 옵션 | 월 비용 | 특징 |
|------|---------|------|
| **SQLite** (현재) | **$0** | 파일 기반, Python 내장 |
| PostgreSQL (EC2 내부) | $0 | EC2 리소스 공유 필요 |
| AWS RDS | $15-20+ | 관리형 서비스 |
| AWS DynamoDB | 사용량 기반 | 서버리스, NoSQL |

## ✅ SQLite 선택 이유

1. **완전 무료**: 추가 비용 없음
2. **설치 불필요**: Python 표준 라이브러리
3. **파일 기반**: JSON과 유사한 관리 방식
4. **ACID 트랜잭션**: 데이터 무결성 보장
5. **인덱싱 지원**: 빠른 검색 성능
6. **EC2 리소스만 사용**: 추가 인프라 불필요

## 🚀 빠른 시작

### 자동 설정

프로젝트를 시작하면 자동으로 데이터베이스가 초기화되고 JSON 데이터가 마이그레이션됩니다:

```bash
# 서비스 시작
python hobot/main.py
```

### 수동 마이그레이션

```bash
cd hobot
python migrate_to_sqlite.py
```

## 📁 데이터베이스 구조

### 위치
- **데이터베이스 파일**: `hobot/service/database/hobot.db`
- **백업 JSON 파일**: 기존 JSON 파일은 그대로 유지됩니다

### 테이블

1. **users**: 사용자 인증 정보
2. **memory_store**: LLM 메모리 저장소
3. **strategies**: 거래 전략 설정
4. **tokens**: API 토큰 저장 (향후 사용)

## 🔧 관리 명령어

### 데이터베이스 확인

```bash
# SQLite CLI로 연결
sqlite3 hobot/service/database/hobot.db

# 테이블 목록
.tables

# 데이터 조회
SELECT * FROM users;
SELECT COUNT(*) FROM memory_store;

# 종료
.quit
```

### 백업

백업 파일은 **시스템 경로**에 저장됩니다:
- **기본 경로**: `/var/backups/hobot/`
- **권한이 없는 경우**: `hobot/service/database/backups/` (자동 폴백)

#### Python 함수 사용

```python
from service.database.db import backup_database

backup_path = backup_database()
```

#### 백업 유틸리티 사용

```bash
# 백업 실행
python hobot/service/database/backup_utils.py backup

# 백업 목록 조회
python hobot/service/database/backup_utils.py list
```

#### 수동 백업

```bash
sudo mkdir -p /var/backups/hobot
sudo cp hobot/service/database/hobot.db /var/backups/hobot/hobot_backup_$(date +%Y%m%d_%H%M%S).db
```

### 복원

#### Python 함수 사용

```python
from service.database.db import restore_database

restore_database("/var/backups/hobot/hobot_backup_20240101_120000.db")
```

#### 백업 유틸리티 사용

```bash
python hobot/service/database/backup_utils.py restore --file /var/backups/hobot/hobot_backup_20240101_120000.db
```

#### 수동 복원

```bash
sudo cp /var/backups/hobot/hobot_backup_20240101_120000.db hobot/service/database/hobot.db
```

## ⚠️ 주의사항

1. **동시성 제한**: SQLite는 동시 쓰기에 제한이 있습니다
   - 읽기: 다중 프로세스 가능
   - 쓰기: 단일 프로세스만 가능
   - 현재 사용 패턴에서는 문제 없음

2. **파일 크기**: SQLite는 파일 기반이므로 대용량 데이터에는 부적합할 수 있습니다
   - 현재 규모에서는 문제 없음

3. **백업**: 정기적으로 데이터베이스 파일을 백업하세요

## 📊 성능

- **인덱스**: 자동으로 생성되어 빠른 검색 지원
- **트랜잭션**: ACID 보장으로 데이터 무결성 유지
- **메모리 사용**: 최소한의 메모리만 사용

## 🔄 마이그레이션된 데이터

다음 JSON 파일의 데이터가 SQLite로 마이그레이션되었습니다:

- ✅ `users.json` → `users` 테이블
- ✅ `memory_store.json` → `memory_store` 테이블
- ✅ `CurrentStrategy.json` → `strategies` 테이블

## 📚 추가 문서

- [SQLite 마이그레이션 상세 가이드](./SQLITE_MIGRATION.md)
- [SQLite 공식 문서](https://www.sqlite.org/docs.html)

## 🆘 문제 해결

### 데이터베이스가 생성되지 않는 경우

```python
from service.database.db import ensure_database_dir, init_database
ensure_database_dir()
init_database()
```

### 권한 오류

```bash
# 데이터베이스 디렉토리 권한 확인
ls -la hobot/service/database/

# 필요시 권한 부여
chmod 755 hobot/service/database/
```

### 디스크 공간 부족

```bash
# 디스크 사용량 확인
df -h

# 데이터베이스 파일 크기 확인
ls -lh hobot/service/database/hobot.db
```

