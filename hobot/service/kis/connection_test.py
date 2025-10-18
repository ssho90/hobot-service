# test_connection.py
import os
import json
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드 (필요한 경우)
load_dotenv(override=True)

# 설정 및 API 모듈 임포트
# 이 파일이 main.py와 같은 위치에 있다고 가정합니다.
from service.kis.config import APP_KEY, APP_SECRET, ACCOUNT_NO, TARGET_TICKER, TARGET_TICKER_NAME
from service.kis.kis_api import KISAPI
from service.kis.kis_utils import get_balance_info

def run_connection_test():
    """
    한국투자증권 API 연결 및 기본 기능 테스트를 수행합니다.
    """
    print("==================================================")
    print("   한국투자증권 API 연결 테스트를 시작합니다.   ")
    print("==================================================")

    # 1. 설정 값 확인
    print("\n[1/5] 설정 값 확인 중...")
    try:
        if not all([APP_KEY, APP_SECRET, ACCOUNT_NO, TARGET_TICKER]):
            raise ValueError("config.py 파일에 모든 값이 설정되었는지 확인해주세요.")
        print(f" - APP_KEY: ...{APP_KEY[-4:]} (OK)")
        print(f" - 계좌번호: {ACCOUNT_NO} (OK)")
        print(f" - 대상종목: {TARGET_TICKER_NAME}({TARGET_TICKER}) (OK)")
        print(">>> 설정 값 확인 완료.\n")
    except Exception as e:
        print(f"오류 발생: {e}")
        return

    # 2. API 객체 생성 및 토큰 발급 테스트
    print("[2/5] API 접근 토큰 발급 테스트 중...")
    try:
        api = KISAPI(app_key=APP_KEY, app_secret=APP_SECRET, account_no=ACCOUNT_NO)
        if api.access_token:
            print(f" - 접근 토큰: ...{api.access_token[-10:]} (OK)")
            print(">>> 토큰 발급 성공.\n")
        else:
            raise Exception("토큰 발급에 실패했습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
        print(">>> API 키 또는 계좌 정보가 올바른지 확인해주세요.")
        return

    # 3. 현재가 조회 테스트
    print(f"[3/5] 현재가 조회 테스트 중... (종목: {TARGET_TICKER_NAME})")
    try:
        current_price = api.get_current_price(TARGET_TICKER)
        if current_price:
            print(f" - 현재가: {format(current_price, ',')} 원 (OK)")
            print(">>> 현재가 조회 성공.\n")
        else:
            raise Exception("현재가 조회에 실패했습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
        return
        
    # 4. 잔고 조회 테스트
    print("[4/5] 계좌 잔고 조회 테스트 중...")
    try:
        balance_data = api.get_balance()
        if balance_data and balance_data.get('rt_cd') == '0':
            # kis_utils.py의 함수를 재활용하여 보기 좋게 출력
            info_str, _, _ = get_balance_info(balance_data, TARGET_TICKER, current_price)
            print("----------------------------------------")
            print(info_str.strip())
            print("----------------------------------------")
            print(">>> 잔고 조회 성공.\n")
        else:
            msg = balance_data.get('msg1', '알 수 없는 오류') if balance_data else '응답 없음'
            raise Exception(f"잔고 조회 실패: {msg}")
    except Exception as e:
        print(f"오류 발생: {e}")
        return

    # 5. 일봉 데이터 조회 테스트
    print(f"[5/5] 일봉 데이터 조회 테스트 중... (종목: {TARGET_TICKER_NAME}, 5개)")
    try:
        ohlcv_df = api.fetch_ohlcv(TARGET_TICKER, count=5)
        if ohlcv_df is not None and not ohlcv_df.empty:
            print(ohlcv_df.to_string(index=False))
            print("\n>>> 일봉 데이터 조회 성공.\n")
        else:
            raise Exception("일봉 데이터 조회에 실패했습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
        return

    print("==================================================")
    print("   모든 테스트를 성공적으로 완료했습니다!   ")
    print("==================================================")


if __name__ == "__main__":
    run_connection_test()
