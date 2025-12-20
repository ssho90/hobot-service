# 정적 파일 404 오류 해결 방법

## 문제
EC2 서버에 빌드 후 사이트 접속 시 빈 화면이 출력되고, 브라우저 콘솔에 다음과 같은 오류가 발생:
```
GET https://stockoverflow.org/static/css/main.24029dc1.css net::ERR_ABORTED 404 (Not Found)
```

## 원인
nginx 설정에서 React 빌드 파일의 `/static/` 경로가 제대로 처리되지 않음

## 해결 방법

### 방법 1: 자동 배포 재실행 (권장)
GitHub Actions를 통해 자동 배포를 다시 실행하면 수정된 nginx 설정이 자동으로 적용됩니다.

### 방법 2: 수동 수정

#### 1. nginx 설정 파일 업데이트

EC2 서버에 SSH 접속 후 다음 명령어 실행:

```bash
cd /home/ec2-user/hobot-service

# nginx 설정 파일 백업
sudo cp /etc/nginx/conf.d/00-hobot.conf /etc/nginx/conf.d/00-hobot.conf.backup

# 수정된 nginx 설정 파일 복사
sudo cp .github/deploy/nginx.conf /etc/nginx/conf.d/00-hobot.conf

# 경로 수정 (필요한 경우)
sudo sed -i "s|/home/ec2-user/hobot-service|/home/ec2-user/hobot-service|g" /etc/nginx/conf.d/00-hobot.conf

# nginx 설정 테스트
sudo nginx -t

# nginx 재시작
sudo systemctl restart nginx
```

#### 2. 프론트엔드 재빌드

```bash
cd /home/ec2-user/hobot-service/hobot-ui

# 이전 빌드 삭제
rm -rf build

# 메모리 옵션 설정 후 빌드
export NODE_OPTIONS="--max-old-space-size=1536"
npm run build

# 빌드 결과 확인
ls -la build/
ls -la build/static/

# 권한 설정
sudo chown -R ec2-user:ec2-user build
sudo chmod -R 755 build

# nginx 사용자가 접근할 수 있도록 상위 디렉토리 권한 확인
chmod 755 /home/ec2-user
chmod 755 /home/ec2-user/hobot-service
chmod 755 /home/ec2-user/hobot-service/hobot-ui
```

#### 3. nginx 재시작 및 확인

```bash
# nginx 설정 테스트
sudo nginx -t

# nginx 재시작
sudo systemctl restart nginx

# nginx 상태 확인
sudo systemctl status nginx

# 에러 로그 확인 (문제가 있는 경우)
sudo tail -f /var/log/nginx/hobot-error.log
```

## 수정된 내용

### 1. nginx.conf
- `/static/` 경로를 명시적으로 처리하도록 `location /static/` 블록 추가
- 정적 파일 캐싱 설정 개선

### 2. package.json
- `homepage: "/"` 필드 추가하여 빌드 경로 명확화

### 3. deploy.sh
- 빌드 실패 시 로그 출력 개선
- 빌드 결과 검증 강화

## 확인 방법

1. 브라우저에서 사이트 접속
2. 개발자 도구(F12) 열기
3. Network 탭에서 정적 파일 로딩 확인
4. Console 탭에서 오류 메시지 확인

정적 파일이 정상적으로 로드되면 문제가 해결된 것입니다.

