# EC2 서버에서 백엔드 로그 확인 가이드

EC2 서버에서 Hobot 백엔드의 로그를 확인하는 여러 방법을 안내합니다.

## 📋 로그 파일 위치

백엔드 로그는 다음 위치에 저장됩니다:

- **액세스 로그**: `/home/ec2-user/hobot-service/hobot/logs/access.log`
- **에러 로그**: `/home/ec2-user/hobot-service/hobot/logs/error.log`
- **애플리케이션 로그**: `/home/ec2-user/hobot-service/hobot/log.txt`
- **Systemd 로그**: `journalctl` 명령어로 확인

## 🔍 로그 확인 방법

### 1. Systemd 서비스 로그 (권장)

가장 권장하는 방법입니다. systemd가 관리하는 모든 로그를 확인할 수 있습니다.

```bash
# 최근 로그 보기 (100줄)
sudo journalctl -u hobot -n 100

# 실시간 로그 모니터링
sudo journalctl -u hobot -f

# 특정 시간 이후 로그
sudo journalctl -u hobot --since "1 hour ago"

# 오늘 로그만 보기
sudo journalctl -u hobot --since today

# 에러만 필터링
sudo journalctl -u hobot -p err

# 로그 파일로 저장
sudo journalctl -u hobot > /tmp/hobot-logs.txt
```

### 2. 로그 파일 직접 확인

#### 액세스 로그 (HTTP 요청 로그)
```bash
# 최근 50줄 보기
tail -50 /home/ec2-user/hobot-service/hobot/logs/access.log

# 실시간 모니터링
tail -f /home/ec2-user/hobot-service/hobot/logs/access.log

# 특정 키워드 검색
grep "error" /home/ec2-user/hobot-service/hobot/logs/access.log
```

#### 에러 로그
```bash
# 최근 50줄 보기
tail -50 /home/ec2-user/hobot-service/hobot/logs/error.log

# 실시간 모니터링
tail -f /home/ec2-user/hobot-service/hobot/logs/error.log

# 에러만 필터링
grep -i "error\|exception\|traceback" /home/ec2-user/hobot-service/hobot/logs/error.log
```

#### 애플리케이션 로그
```bash
# 최근 50줄 보기
tail -50 /home/ec2-user/hobot-service/hobot/log.txt

# 실시간 모니터링
tail -f /home/ec2-user/hobot-service/hobot/log.txt

# 특정 날짜 로그 검색
grep "2024-01-01" /home/ec2-user/hobot-service/hobot/log.txt
```

### 3. 편리한 스크립트 사용

배포 스크립트와 함께 제공되는 `view_logs.sh` 스크립트를 사용할 수 있습니다:

```bash
# 스크립트에 실행 권한 부여 (최초 1회)
chmod +x /home/ec2-user/hobot-service/.github/deploy/view_logs.sh

# 도움말 보기
/home/ec2-user/hobot-service/.github/deploy/view_logs.sh --help

# systemd 로그 보기
/home/ec2-user/hobot-service/.github/deploy/view_logs.sh -s

# 액세스 로그 실시간 보기
/home/ec2-user/hobot-service/.github/deploy/view_logs.sh -a -f

# 에러 로그 최근 100줄 보기
/home/ec2-user/hobot-service/.github/deploy/view_logs.sh -e -t 100

# 애플리케이션 로그 실시간 보기
/home/ec2-user/hobot-service/.github/deploy/view_logs.sh -p -f
```

## 🛠️ 유용한 명령어 조합

### 모든 로그 동시 모니터링
```bash
tail -f /home/ec2-user/hobot-service/hobot/logs/access.log \
        /home/ec2-user/hobot-service/hobot/logs/error.log \
        /home/ec2-user/hobot-service/hobot/log.txt
```

### 로그 파일 크기 확인
```bash
ls -lh /home/ec2-user/hobot-service/hobot/logs/
ls -lh /home/ec2-user/hobot-service/hobot/log.txt
```

### 로그 파일 검색
```bash
# 특정 API 엔드포인트 검색
grep "/api/health" /home/ec2-user/hobot-service/hobot/logs/access.log

# 에러 발생 시간 확인
grep -i "error" /home/ec2-user/hobot-service/hobot/logs/error.log | tail -20

# 특정 사용자 활동 추적
grep "username" /home/ec2-user/hobot-service/hobot/logs/access.log
```

### 로그 파일 정리 (오래된 로그 삭제)
```bash
# 7일 이상 된 로그 삭제 (주의: 백업 후 실행)
find /home/ec2-user/hobot-service/hobot/logs -name "*.log" -mtime +7 -delete
```

## 📊 서비스 상태 확인

로그를 확인하기 전에 서비스가 실행 중인지 확인하세요:

```bash
# 서비스 상태 확인
sudo systemctl status hobot

# 서비스 재시작 (문제 해결 시)
sudo systemctl restart hobot

# 서비스 로그 확인
sudo journalctl -u hobot -n 50
```

## 🔧 문제 해결

### 로그 파일이 없는 경우
```bash
# 로그 디렉토리 생성
mkdir -p /home/ec2-user/hobot-service/hobot/logs

# 권한 설정
chmod 755 /home/ec2-user/hobot-service/hobot/logs
```

### 로그 파일 권한 문제
```bash
# 로그 디렉토리 권한 확인
ls -la /home/ec2-user/hobot-service/hobot/logs/

# 권한 수정 (필요시)
sudo chown -R ec2-user:ec2-user /home/ec2-user/hobot-service/hobot/logs
```

### 로그가 너무 많은 경우
```bash
# 로그 파일 크기 확인
du -sh /home/ec2-user/hobot-service/hobot/logs/*

# 로그 로테이션 설정 (logrotate 사용)
# 또는 gunicorn.conf.py에서 로그 로테이션 설정 확인
```

## 💡 팁

1. **실시간 모니터링**: `tail -f` 명령어로 실시간으로 로그를 모니터링할 수 있습니다.
2. **로그 필터링**: `grep` 명령어로 특정 키워드를 검색할 수 있습니다.
3. **로그 저장**: 중요한 로그는 파일로 저장하여 나중에 분석할 수 있습니다.
4. **로그 로테이션**: 로그 파일이 너무 커지지 않도록 정기적으로 정리하세요.

