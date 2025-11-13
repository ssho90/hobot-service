# 백업 설정 가이드

## 📋 개요

SQLite 데이터베이스 백업은 **시스템 경로**에 저장됩니다:
- **기본 경로**: `/var/backups/hobot/`
- **권한이 없는 경우**: `hobot/service/database/backups/` (자동 폴백)

## 🔧 백업 디렉토리 설정

### EC2/Linux 환경

#### 1. 백업 디렉토리 생성 및 권한 설정

```bash
# 백업 디렉토리 생성
sudo mkdir -p /var/backups/hobot

# 소유자 및 권한 설정 (현재 사용자로 실행하는 경우)
sudo chown $USER:$USER /var/backups/hobot
sudo chmod 755 /var/backups/hobot

# 또는 서비스 사용자로 실행하는 경우
sudo chown hobot:hobot /var/backups/hobot
sudo chmod 755 /var/backups/hobot
```

#### 2. 자동 백업 스크립트 설정 (선택사항)

```bash
# crontab 편집
crontab -e

# 매일 새벽 2시에 자동 백업
0 2 * * * cd /path/to/hobot-service/hobot && python -c "from service.database.db import backup_database; backup_database()" >> /var/log/hobot_backup.log 2>&1
```

### Windows 환경

Windows에서는 시스템 경로 접근이 제한되므로 자동으로 프로젝트 내부 경로로 폴백됩니다:
- `hobot/service/database/backups/`

## 📦 백업 사용 방법

### Python 함수 사용

```python
from service.database.db import backup_database, list_backups, restore_database

# 백업 실행
backup_path = backup_database()
print(f"백업 완료: {backup_path}")

# 백업 목록 조회
backups = list_backups()
for backup in backups:
    print(f"{backup['filename']} - {backup['created_at']}")

# 백업 복원
restore_database("/var/backups/hobot/hobot_backup_20240101_120000.db")
```

### 백업 유틸리티 사용

```bash
# 백업 실행
python hobot/service/database/backup_utils.py backup

# 백업 목록 조회
python hobot/service/database/backup_utils.py list

# 백업 복원
python hobot/service/database/backup_utils.py restore --file /var/backups/hobot/hobot_backup_20240101_120000.db
```

### 수동 백업

```bash
# 시스템 경로에 직접 복사
sudo cp hobot/service/database/hobot.db /var/backups/hobot/hobot_backup_$(date +%Y%m%d_%H%M%S).db

# SQL 덤프 생성
sqlite3 hobot/service/database/hobot.db .dump > /var/backups/hobot/backup_$(date +%Y%m%d_%H%M%S).sql
```

## 🗑️ 백업 자동 정리

백업 함수는 자동으로 30일 이상 된 백업 파일을 삭제합니다:

```python
from service.database.db import cleanup_old_backups

# 30일 이상 된 백업 파일 삭제 (기본값)
cleanup_old_backups(days=30)

# 7일 이상 된 백업 파일 삭제
cleanup_old_backups(days=7)
```

## 🔍 백업 확인

### 백업 파일 목록 조회

```bash
# Python 함수 사용
python -c "from service.database.db import list_backups; import json; print(json.dumps(list_backups(), indent=2))"

# 백업 유틸리티 사용
python hobot/service/database/backup_utils.py list

# 직접 확인
ls -lh /var/backups/hobot/
```

### 백업 파일 크기 확인

```bash
du -sh /var/backups/hobot/*
```

## ⚠️ 주의사항

1. **권한 문제**: `/var/backups`에 쓰기 권한이 없으면 자동으로 프로젝트 내부 경로로 폴백됩니다
2. **디스크 공간**: 정기적으로 백업 파일을 확인하고 오래된 백업을 삭제하세요
3. **백업 검증**: 복원 전에 백업 파일이 손상되지 않았는지 확인하세요

## 🔐 보안 고려사항

1. **백업 파일 권한**: 백업 파일은 민감한 데이터를 포함할 수 있으므로 적절한 권한을 설정하세요
   ```bash
   sudo chmod 600 /var/backups/hobot/*.db
   ```

2. **백업 암호화**: 필요시 백업 파일을 암호화하여 저장하세요
   ```bash
   # GPG로 암호화
   gpg --encrypt --recipient your-email@example.com /var/backups/hobot/hobot_backup_20240101_120000.db
   ```

3. **원격 백업**: 중요한 데이터는 원격 저장소에도 백업하세요
   ```bash
   # S3에 백업 업로드
   aws s3 cp /var/backups/hobot/hobot_backup_20240101_120000.db s3://your-backup-bucket/
   ```

## 📚 관련 문서

- [SQLite 마이그레이션 가이드](./SQLITE_MIGRATION.md)
- [데이터베이스 설정 가이드](./DATABASE_SETUP.md)

