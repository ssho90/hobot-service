#!/bin/bash

# Hobot 백엔드 로그 보기 스크립트

LOG_DIR="/Users/ssho/project/hobot-service/hobot/logs"
ACCESS_LOG="$LOG_DIR/access.log"
ERROR_LOG="$LOG_DIR/error.log"
APP_LOG="/Users/ssho/project/hobot-service/hobot/log.txt"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

echo "🔍 Hobot Backend Logs"
echo "================================================"

# 최근 로그 보기
echo "📝 Recent Access Logs (last 20 lines):"
echo "----------------------------------------"
tail -20 "$ACCESS_LOG" 2>/dev/null || echo "No access logs yet"

echo ""
echo "❌ Recent Error Logs (last 10 lines):"
echo "----------------------------------------"
tail -10 "$ERROR_LOG" 2>/dev/null || echo "No error logs yet"

echo ""
echo "📱 Recent App Logs (last 15 lines):"
echo "----------------------------------------"
tail -15 "$APP_LOG" 2>/dev/null || echo "No app logs yet"

echo ""
echo "📊 Quick Commands:"
echo "  Real-time access: tail -f $ACCESS_LOG"
echo "  Real-time errors: tail -f $ERROR_LOG"
echo "  Real-time app:    tail -f $APP_LOG"
echo "  All logs:         tail -f $ACCESS_LOG $ERROR_LOG $APP_LOG"
echo "  Monitor script:   ./log_monitor.sh"
