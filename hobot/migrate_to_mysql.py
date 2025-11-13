#!/usr/bin/env python3
"""
JSON에서 MySQL로 데이터 마이그레이션 스크립트

사용법:
    python migrate_to_mysql.py

이 스크립트는 기존 JSON 파일의 데이터를 MySQL 데이터베이스로 마이그레이션합니다.

환경 변수 설정 필요:
    DB_HOST=localhost
    DB_PORT=3306
    DB_USER=root
    DB_PASSWORD=your_password
    DB_NAME=hobot
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from service.database.db import init_database, migrate_from_json

def main():
    print("=" * 60)
    print("JSON → MySQL 마이그레이션 시작")
    print("=" * 60)
    
    # 환경 변수 확인
    required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("\n⚠️  다음 환경 변수가 설정되지 않았습니다:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n.env 파일 또는 환경 변수로 설정해주세요.")
        print("\n예시:")
        print("  DB_HOST=localhost")
        print("  DB_PORT=3306")
        print("  DB_USER=root")
        print("  DB_PASSWORD=your_password")
        print("  DB_NAME=hobot")
        sys.exit(1)
    
    try:
        # 데이터베이스 초기화
        print("\n1. 데이터베이스 초기화 중...")
        init_database()
        print("✅ 데이터베이스 초기화 완료")
        
        # 데이터 마이그레이션
        print("\n2. JSON 데이터 마이그레이션 중...")
        migrate_from_json()
        print("✅ 데이터 마이그레이션 완료")
        
        print("\n" + "=" * 60)
        print("마이그레이션 완료!")
        print("=" * 60)
        print(f"\n이제 MySQL 데이터베이스가 사용됩니다.")
        print(f"데이터베이스: {os.getenv('DB_NAME')}")
        print(f"호스트: {os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}")
        print("\n참고: 기존 JSON 파일은 백업으로 유지됩니다.")
        print("      필요시 수동으로 삭제할 수 있습니다.")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

