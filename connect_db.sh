#!/bin/bash

# EC2 터널링 환경 설정
PEM_FILE="/Users/ssho/project/test-EC2-key.pem"
EC2_USER="ec2-user" # ssh 접속 계정 (Ubuntu 환경의 경우 ubuntu, Amazon Linux는 ec2-user)
EC2_IP="3.34.13.230"

# 포트 매핑 (로컬 포트 -> EC2 내부 MySQL 포트)
# hobot/.env의 DB_PORT=3307 설정과 맞춘다.
LOCAL_PORT=3307  # 로컬 앱이 사용하는 포트로 터널링
REMOTE_PORT=3306 # EC2에 설치된 MySQL의 기본 포트

echo "==========================================================="
echo "🚀 SSH 터널링을 시작합니다."
echo "- EC2 서버   : ${EC2_IP}"
echo "- 매핑 정보  : 로컬포트(${LOCAL_PORT}) -> EC2 MySQL포트(${REMOTE_PORT})"
echo "==========================================================="
echo "💡 데이타베이스 클라이언트(DBeaver, DataGrip 등)에서 다음 정보로 접속하세요:"
echo "   Host : 127.0.0.1"
echo "   Port : ${LOCAL_PORT}"
echo "==========================================================="
echo "※ 종료하려면 현재 터미널 창에서 Ctrl + C 를 누르세요."
echo ""

ssh -i "${PEM_FILE}" -N -L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT} ${EC2_USER}@${EC2_IP}
