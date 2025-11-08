#!/usr/bin/env python3
"""
배포 시 전략을 PAUSE 상태로 초기화하는 스크립트
"""
import os
import json
import sys

def init_strategy_pause():
    """KIS와 Upbit의 전략을 STRATEGY_PAUSE로 설정"""
    
    # 현재 스크립트의 디렉토리 기준으로 경로 설정
    # 스크립트는 hobot/service/utils/ 디렉토리에 있음
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # utils 디렉토리의 상위 디렉토리(service)로 이동
    service_dir = os.path.dirname(script_dir)
    
    # 1. CurrentStrategy.json 파일 설정 (strategy_manager.py 사용)
    # strategy_manager.py는 hobot/service/CurrentStrategy.json을 사용
    strategy_json_path = os.path.join(service_dir, 'CurrentStrategy.json')
    
    try:
        # 기존 전략 읽기 (없으면 기본값 생성)
        if os.path.exists(strategy_json_path):
            with open(strategy_json_path, 'r', encoding='utf-8') as f:
                strategies = json.load(f)
        else:
            strategies = {
                'upbit': 'STRATEGY_NULL',
                'binance': 'STRATEGY_NULL',
                'kis': 'STRATEGY_NULL'
            }
        
        # KIS와 Upbit만 PAUSE로 설정
        strategies['kis'] = 'STRATEGY_PAUSE'
        strategies['upbit'] = 'STRATEGY_PAUSE'
        # binance는 그대로 유지
        
        # 파일에 저장
        with open(strategy_json_path, 'w', encoding='utf-8') as f:
            json.dump(strategies, f, indent=2, ensure_ascii=False)
        
        print(f"✅ CurrentStrategy.json 업데이트 완료: kis={strategies['kis']}, upbit={strategies['upbit']}")
    except Exception as e:
        print(f"❌ CurrentStrategy.json 업데이트 실패: {e}")
        sys.exit(1)
    
    # 2. CurrentStrategy.txt 파일 설정 (upbit_utils.py 사용 - 구버전 호환)
    # upbit_utils.py는 'service/CurrentStrategy.txt'를 사용 (현재 작업 디렉토리 기준)
    upbit_txt_path = os.path.join(service_dir, 'CurrentStrategy.txt')
    
    try:
        # 디렉토리가 없으면 생성
        os.makedirs(service_dir, exist_ok=True)
        with open(upbit_txt_path, 'w', encoding='utf-8') as f:
            f.write('STRATEGY_PAUSE')
        print(f"✅ CurrentStrategy.txt 업데이트 완료: STRATEGY_PAUSE")
    except Exception as e:
        print(f"❌ CurrentStrategy.txt 업데이트 실패: {e}")
        sys.exit(1)
    
    # 3. CurrentStrategy_kis.txt 파일 설정 (kis_utils.py 사용 - 구버전 호환)
    # kis_utils.py는 'service/CurrentStrategy_kis.txt'를 사용 (현재 작업 디렉토리 기준)
    kis_txt_path = os.path.join(service_dir, 'CurrentStrategy_kis.txt')
    
    try:
        with open(kis_txt_path, 'w', encoding='utf-8') as f:
            f.write('STRATEGY_PAUSE')
        print(f"✅ CurrentStrategy_kis.txt 업데이트 완료: STRATEGY_PAUSE")
    except Exception as e:
        print(f"❌ CurrentStrategy_kis.txt 업데이트 실패: {e}")
        sys.exit(1)
    
    print("🎉 모든 전략 파일이 STRATEGY_PAUSE로 초기화되었습니다.")

if __name__ == '__main__':
    init_strategy_pause()

