"""
데이터베이스 백업 유틸리티
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from service.database.db import backup_database, list_backups, restore_database, BACKUP_DIR


def main():
    """백업 유틸리티 메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='MySQL 데이터베이스 백업 유틸리티')
    parser.add_argument('action', choices=['backup', 'list', 'restore'], 
                       help='실행할 작업: backup, list, restore')
    parser.add_argument('--file', '-f', help='복원할 백업 파일 경로 (restore 시 필요)')
    parser.add_argument('--days', '-d', type=int, default=30, 
                       help='백업 보관 기간 (일, 기본값: 30)')
    
    args = parser.parse_args()
    
    if args.action == 'backup':
        print("=" * 60)
        print("데이터베이스 백업 시작")
        print("=" * 60)
        backup_path = backup_database()
        if backup_path:
            print(f"\n✅ 백업 완료: {backup_path}")
            print(f"백업 위치: {BACKUP_DIR}")
        else:
            print("\n❌ 백업 실패")
            sys.exit(1)
    
    elif args.action == 'list':
        print("=" * 60)
        print("백업 파일 목록")
        print("=" * 60)
        backups = list_backups()
        if not backups:
            print("\n백업 파일이 없습니다.")
        else:
            print(f"\n총 {len(backups)}개의 백업 파일:")
            print("-" * 60)
            for i, backup in enumerate(backups, 1):
                size_mb = backup['size'] / (1024 * 1024)
                print(f"{i}. {backup['filename']}")
                print(f"   크기: {size_mb:.2f} MB")
                print(f"   생성일: {backup['created_at']}")
                print(f"   경로: {backup['path']}")
                print()
    
    elif args.action == 'restore':
        if not args.file:
            print("❌ 오류: 복원할 백업 파일 경로를 지정해주세요 (--file 옵션)")
            sys.exit(1)
        
        print("=" * 60)
        print("데이터베이스 복원 시작")
        print("=" * 60)
        print(f"백업 파일: {args.file}")
        
        confirm = input("\n⚠️  현재 데이터베이스를 덮어씁니다. 계속하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("복원이 취소되었습니다.")
            sys.exit(0)
        
        try:
            restore_database(args.file)
            print("\n✅ 복원 완료")
        except Exception as e:
            print(f"\n❌ 복원 실패: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()

