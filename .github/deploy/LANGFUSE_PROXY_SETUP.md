# Langfuse 프록시 설정 가이드

EC2를 프록시로 사용하여 로컬에서 Langfuse에 접속하는 방법입니다.

## 1. Route53 DNS 설정

Route53에서 다음 서브도메인을 EC2 인스턴스의 IP 주소로 A 레코드를 추가하세요:

### langfuse.stockoverflow.com
- **레코드 타입**: A
- **이름**: `langfuse`
- **값**: EC2 인스턴스의 퍼블릭 IP 주소
- **TTL**: 300 (또는 원하는 값)

### langfuse-us.stockoverflow.com
- **레코드 타입**: A
- **이름**: `langfuse-us`
- **값**: EC2 인스턴스의 퍼블릭 IP 주소
- **TTL**: 300 (또는 원하는 값)

## 2. 배포 실행

배포를 실행하면 자동으로:
1. nginx에 Langfuse 프록시 설정이 추가됩니다
2. certbot이 SSL 인증서를 발급합니다
3. HTTPS로 접속할 수 있게 됩니다

```bash
# GitHub Actions를 통해 자동 배포되거나
# 또는 EC2에서 직접 실행:
./.github/deploy/deploy.sh
```

## 3. 접속 방법

배포가 완료되면 다음 URL로 접속할 수 있습니다:

- **Langfuse (Global)**: https://langfuse.stockoverflow.com
- **Langfuse (US)**: https://langfuse-us.stockoverflow.com

## 4. 수동 설정 (필요한 경우)

### certbot 수동 실행

배포 후 인증서가 자동으로 발급되지 않은 경우:

```bash
# Langfuse 인증서 발급
sudo certbot --nginx \
  -d langfuse.stockoverflow.com \
  --non-interactive --agree-tos \
  --email your-email@example.com \
  --redirect

# Langfuse US 인증서 발급
sudo certbot --nginx \
  -d langfuse-us.stockoverflow.com \
  --non-interactive --agree-tos \
  --email your-email@example.com \
  --redirect
```

### nginx 설정 확인

```bash
# nginx 설정 테스트
sudo nginx -t

# nginx 재시작
sudo systemctl restart nginx

# nginx 상태 확인
sudo systemctl status nginx
```

## 5. 문제 해결

### DNS가 아직 전파되지 않은 경우
- Route53에서 DNS 레코드가 생성된 후 몇 분 정도 기다려야 할 수 있습니다
- `dig langfuse.stockoverflow.com` 또는 `nslookup langfuse.stockoverflow.com`으로 확인

### SSL 인증서 발급 실패
- DNS가 올바르게 설정되었는지 확인
- EC2 보안 그룹에서 포트 80, 443이 열려있는지 확인
- certbot 로그 확인: `sudo tail -f /var/log/letsencrypt/letsencrypt.log`

### 프록시가 작동하지 않는 경우
- nginx 에러 로그 확인: `sudo tail -f /var/log/nginx/langfuse-error.log`
- nginx 액세스 로그 확인: `sudo tail -f /var/log/nginx/langfuse-access.log`
- EC2에서 직접 테스트: `curl -I https://langfuse.com`

## 6. 인증서 자동 갱신

certbot은 자동으로 인증서를 갱신합니다. 수동으로 갱신하려면:

```bash
sudo certbot renew
```

cron 작업이 자동으로 설정되어 있는지 확인:

```bash
sudo systemctl status certbot.timer
```

