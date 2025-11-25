# config.py
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# KIS Developers API 키 정보 (환경 변수에서 불러오기)
APP_KEY = os.getenv("HT_API_KEY")
APP_SECRET = os.getenv("HT_SECRET_KEY")

# 계좌 정보 (환경 변수에서 불러오기)
ACCOUNT_NO = os.getenv("HT_ACCOUNT")

# 투자 대상 정보
TARGET_TICKER = "005930"  # 매매할 종목 코드 (예: 삼성전자)
TARGET_TICKER_NAME = "삼성전자" # 매매할 종목 이름
INTERVAL = "D" # 캔들 데이터 주기 (D: 일봉, W: 주봉, M: 월봉)

