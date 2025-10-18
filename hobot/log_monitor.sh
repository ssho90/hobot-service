#!/bin/bash

# Hobot 백엔드 로그 모니터링 스크립트

LOG_DIR="/Users/ssho/project/hobot-service/hobot/logs"
ACCESS_LOG="$LOG_DIR/access.log"
ERROR_LOG="$LOG_DIR/error.log"
APP_LOG="/Users/ssho/project/hobot-service/hobot/log.txt"

echo "🔍 Hobot Backend Log Monitor"
echo "================================================"
echo "📁 Log Directory: $LOG_DIR"
echo "📝 Access Log: $ACCESS_LOG"
echo "❌ Error Log: $ERROR_LOG"
echo "📱 App Log: $APP_LOG"
echo "================================================"
echo ""

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 로그 파일이 없으면 생성
touch "$ACCESS_LOG" "$ERROR_LOG"

echo "📊 Available log monitoring options:"
echo "1. Real-time access logs"
echo "2. Real-time error logs"
echo "3. Real-time app logs"
echo "4. All logs combined"
echo "5. Search in logs"
echo "6. Log statistics"
echo ""

read -p "Select option (1-6): " choice

case $choice in
    1)
        echo "📝 Monitoring access logs (Ctrl+C to stop)..."
        tail -f "$ACCESS_LOG"
        ;;
    2)
        echo "❌ Monitoring error logs (Ctrl+C to stop)..."
        tail -f "$ERROR_LOG"
        ;;
    3)
        echo "📱 Monitoring app logs (Ctrl+C to stop)..."
        tail -f "$APP_LOG"
        ;;
    4)
        echo "📊 Monitoring all logs (Ctrl+C to stop)..."
        echo "Press Ctrl+C to stop monitoring"
        tail -f "$ACCESS_LOG" "$ERROR_LOG" "$APP_LOG"
        ;;
    5)
        read -p "Enter search term: " search_term
        echo "🔍 Searching for '$search_term' in all logs..."
        echo ""
        echo "=== ACCESS LOG ==="
        grep -n "$search_term" "$ACCESS_LOG" 2>/dev/null || echo "No matches in access log"
        echo ""
        echo "=== ERROR LOG ==="
        grep -n "$search_term" "$ERROR_LOG" 2>/dev/null || echo "No matches in error log"
        echo ""
        echo "=== APP LOG ==="
        grep -n "$search_term" "$APP_LOG" 2>/dev/null || echo "No matches in app log"
        ;;
    6)
        echo "📊 Log Statistics:"
        echo "================================================"
        echo "Access Log:"
        echo "  Lines: $(wc -l < "$ACCESS_LOG" 2>/dev/null || echo "0")"
        echo "  Size: $(du -h "$ACCESS_LOG" 2>/dev/null | cut -f1 || echo "0B")"
        echo ""
        echo "Error Log:"
        echo "  Lines: $(wc -l < "$ERROR_LOG" 2>/dev/null || echo "0")"
        echo "  Size: $(du -h "$ERROR_LOG" 2>/dev/null | cut -f1 || echo "0B")"
        echo ""
        echo "App Log:"
        echo "  Lines: $(wc -l < "$APP_LOG" 2>/dev/null || echo "0")"
        echo "  Size: $(du -h "$APP_LOG" 2>/dev/null | cut -f1 || echo "0B")"
        echo ""
        echo "Recent Errors:"
        tail -5 "$ERROR_LOG" 2>/dev/null || echo "No recent errors"
        ;;
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac
