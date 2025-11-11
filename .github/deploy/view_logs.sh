#!/bin/bash

# EC2 서버에서 Hobot 백엔드 로그를 보는 스크립트
# 사용법: ./view_logs.sh [옵션]

DEPLOY_PATH="${DEPLOY_PATH:-/home/ec2-user/hobot-service}"
LOG_DIR="${DEPLOY_PATH}/hobot/logs"
ACCESS_LOG="${LOG_DIR}/access.log"
ERROR_LOG="${LOG_DIR}/error.log"
APP_LOG="${DEPLOY_PATH}/hobot/log.txt"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 함수 정의
show_help() {
    echo "🔍 Hobot Backend Log Viewer"
    echo "================================================"
    echo "사용법: $0 [옵션]"
    echo ""
    echo "옵션:"
    echo "  -a, --access      액세스 로그 실시간 보기"
    echo "  -e, --error       에러 로그 실시간 보기"
    echo "  -p, --app         애플리케이션 로그 실시간 보기"
    echo "  -s, --systemd     systemd 서비스 로그 보기"
    echo "  -t, --tail N      최근 N줄 보기 (기본값: 50)"
    echo "  -f, --follow      실시간 모니터링 (tail -f)"
    echo "  -h, --help        도움말 표시"
    echo ""
    echo "로그 파일 위치:"
    echo "  액세스 로그: ${ACCESS_LOG}"
    echo "  에러 로그:   ${ERROR_LOG}"
    echo "  앱 로그:     ${APP_LOG}"
    echo "  Systemd:    journalctl -u hobot"
    echo ""
    echo "예제:"
    echo "  $0 -s              # systemd 로그 보기"
    echo "  $0 -a -f           # 액세스 로그 실시간 보기"
    echo "  $0 -e -t 100       # 에러 로그 최근 100줄 보기"
    echo "  $0 -p -f           # 애플리케이션 로그 실시간 보기"
}

show_systemd_logs() {
    echo -e "${BLUE}📋 Systemd Service Logs${NC}"
    echo "================================================"
    sudo journalctl -u hobot -n 100 --no-pager
    echo ""
    echo "실시간 모니터링: sudo journalctl -u hobot -f"
}

show_access_logs() {
    local lines=${1:-50}
    local follow=${2:-false}
    
    if [ ! -f "${ACCESS_LOG}" ]; then
        echo -e "${YELLOW}⚠️  액세스 로그 파일이 없습니다: ${ACCESS_LOG}${NC}"
        return
    fi
    
    echo -e "${GREEN}📝 Access Logs${NC}"
    echo "================================================"
    if [ "$follow" = "true" ]; then
        tail -f "${ACCESS_LOG}"
    else
        tail -n "${lines}" "${ACCESS_LOG}"
    fi
}

show_error_logs() {
    local lines=${1:-50}
    local follow=${2:-false}
    
    if [ ! -f "${ERROR_LOG}" ]; then
        echo -e "${YELLOW}⚠️  에러 로그 파일이 없습니다: ${ERROR_LOG}${NC}"
        return
    fi
    
    echo -e "${RED}❌ Error Logs${NC}"
    echo "================================================"
    if [ "$follow" = "true" ]; then
        tail -f "${ERROR_LOG}"
    else
        tail -n "${lines}" "${ERROR_LOG}"
    fi
}

show_app_logs() {
    local lines=${1:-50}
    local follow=${2:-false}
    
    if [ ! -f "${APP_LOG}" ]; then
        echo -e "${YELLOW}⚠️  애플리케이션 로그 파일이 없습니다: ${APP_LOG}${NC}"
        return
    fi
    
    echo -e "${BLUE}📱 Application Logs${NC}"
    echo "================================================"
    if [ "$follow" = "true" ]; then
        tail -f "${APP_LOG}"
    else
        tail -n "${lines}" "${APP_LOG}"
    fi
}

# 기본값
LINES=50
FOLLOW=false
SHOW_ACCESS=false
SHOW_ERROR=false
SHOW_APP=false
SHOW_SYSTEMD=false

# 인자 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--access)
            SHOW_ACCESS=true
            shift
            ;;
        -e|--error)
            SHOW_ERROR=true
            shift
            ;;
        -p|--app)
            SHOW_APP=true
            shift
            ;;
        -s|--systemd)
            SHOW_SYSTEMD=true
            shift
            ;;
        -t|--tail)
            LINES="$2"
            shift 2
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            show_help
            exit 1
            ;;
    esac
done

# 옵션이 없으면 기본적으로 모든 로그 보기
if [ "$SHOW_ACCESS" = "false" ] && [ "$SHOW_ERROR" = "false" ] && [ "$SHOW_APP" = "false" ] && [ "$SHOW_SYSTEMD" = "false" ]; then
    echo "🔍 Hobot Backend Logs Summary"
    echo "================================================"
    echo ""
    
    # Systemd 로그
    echo -e "${BLUE}📋 Systemd Service Logs (최근 10줄)${NC}"
    echo "----------------------------------------"
    sudo journalctl -u hobot -n 10 --no-pager 2>/dev/null || echo "Systemd 로그를 확인할 수 없습니다"
    echo ""
    
    # 액세스 로그
    if [ -f "${ACCESS_LOG}" ]; then
        echo -e "${GREEN}📝 Access Logs (최근 5줄)${NC}"
        echo "----------------------------------------"
        tail -n 5 "${ACCESS_LOG}"
        echo ""
    fi
    
    # 에러 로그
    if [ -f "${ERROR_LOG}" ]; then
        echo -e "${RED}❌ Error Logs (최근 5줄)${NC}"
        echo "----------------------------------------"
        tail -n 5 "${ERROR_LOG}"
        echo ""
    fi
    
    # 앱 로그
    if [ -f "${APP_LOG}" ]; then
        echo -e "${BLUE}📱 Application Logs (최근 5줄)${NC}"
        echo "----------------------------------------"
        tail -n 5 "${APP_LOG}"
        echo ""
    fi
    
    echo "💡 더 많은 로그를 보려면:"
    echo "   $0 -s              # systemd 로그"
    echo "   $0 -a -f           # 액세스 로그 실시간"
    echo "   $0 -e -f           # 에러 로그 실시간"
    echo "   $0 -p -f           # 앱 로그 실시간"
    exit 0
fi

# 선택된 로그 보기
if [ "$SHOW_SYSTEMD" = "true" ]; then
    if [ "$FOLLOW" = "true" ]; then
        sudo journalctl -u hobot -f
    else
        show_systemd_logs
    fi
fi

if [ "$SHOW_ACCESS" = "true" ]; then
    show_access_logs "$LINES" "$FOLLOW"
fi

if [ "$SHOW_ERROR" = "true" ]; then
    show_error_logs "$LINES" "$FOLLOW"
fi

if [ "$SHOW_APP" = "true" ]; then
    show_app_logs "$LINES" "$FOLLOW"
fi

