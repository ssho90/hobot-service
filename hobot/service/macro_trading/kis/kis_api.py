# service/macro_trading/kis/kis_api.py
import requests
import json
import pandas as pd
import time
import os
from datetime import datetime

class KISAPI:
    # 토큰 파일 경로
    _token_file_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'data', 'access_token.json'
    )

    def __init__(self, app_key, app_secret, account_no, base_url="https://openapi.koreainvestment.com:9443"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.base_url = base_url
        self.access_token = self._get_access_token()

    def _ensure_data_directory(self):
        """data 디렉토리가 존재하는지 확인하고 없으면 생성"""
        data_dir = os.path.dirname(self._token_file_path)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

    def _load_token_from_file(self):
        """JSON 파일에서 토큰 정보 로드"""
        try:
            if not os.path.exists(self._token_file_path):
                return None
            
            with open(self._token_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('access_token'), data.get('issued_date')
        except Exception as e:
            print(f"Error loading token from file: {e}")
            return None

    def _save_token_to_file(self, token, issued_date):
        """토큰 정보를 JSON 파일에 저장 (보안: 파일 권한 제한)"""
        try:
            self._ensure_data_directory()
            data = {
                'access_token': token,
                'issued_date': issued_date
            }
            # 파일 쓰기 (임시 파일로 먼저 쓰고 이동하여 원자성 보장)
            temp_path = self._token_file_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 파일 권한 제한 (소유자만 읽기/쓰기 가능: 0o600)
            os.chmod(temp_path, 0o600)
            # 원자적으로 이동
            os.replace(temp_path, self._token_file_path)
            # 최종 파일 권한도 제한
            os.chmod(self._token_file_path, 0o600)
        except Exception as e:
            print(f"Error saving token to file: {e}")

    def _is_token_valid(self):
        """파일에서 로드한 토큰이 아직 유효한지 확인 (하루 이내)"""
        token_data = self._load_token_from_file()
        if token_data is None or token_data[0] is None or token_data[1] is None:
            return False
        
        token, issued_date_str = token_data
        try:
            issued_date = datetime.fromisoformat(issued_date_str)
            # 발급일이 오늘과 같은 날인지 확인
            today = datetime.now().date()
            issued_date_only = issued_date.date()
            return issued_date_only == today
        except Exception as e:
            print(f"Error parsing issued_date: {e}")
            return False

    def _get_access_token(self):
        """접근 토큰 발급 (파일에 저장된 토큰이 있으면 재사용)"""
        # 파일에서 토큰 로드 시도
        if self._is_token_valid():
            token_data = self._load_token_from_file()
            if token_data and token_data[0]:
                return token_data[0]
        
        # 새 토큰 발급
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        path = "/oauth2/tokenP"
        url = f"{self.base_url}{path}"
        res = requests.post(url, headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            token = res.json()["access_token"]
            issued_date = datetime.now().isoformat()
            # 토큰과 발급 시간을 파일에 저장
            self._save_token_to_file(token, issued_date)
            return token
        else:
            raise Exception(f"Error getting access token: {res.text}")

    def _get_common_headers(self, tr_id):
        """공통 헤더 생성"""
        return {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }

    def fetch_ohlcv(self, ticker, interval='D', count=250):
        """일/주/월봉 데이터 조회 (현재가 일자별)"""
        time.sleep(0.1) # 단기과열종목 지정 회피
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        url = f"{self.base_url}{path}"
        headers = self._get_common_headers("FHKST01010400")
        
        # KIS API는 '오늘'부터 과거 N일 데이터를 제공하므로,
        # 넉넉하게 조회하기 위해 count를 사용합니다.
        # 정확한 날짜 계산이 필요하다면 이 부분을 수정할 수 있습니다.
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": ticker,
            "fid_period_div_code": interval,
            "fid_org_adj_prc": "1" # 수정주가 반영
        }

        res = requests.get(url, headers=headers, params=params)

        if res.status_code == 200:
            data = res.json()['output']
            df = pd.DataFrame(data)
            # KIS API는 날짜 내림차순으로 데이터를 반환하므로, 오름차순으로 변경
            df = df.iloc[::-1].reset_index(drop=True) 
            
            # 칼럼명 변경 (기존 로직과 호환되도록)
            df = df[['stck_bsop_date', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr', 'acml_vol']]
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            
            # 데이터 타입을 숫자로 변경
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])

            return df.tail(count) # 요청한 개수만큼 잘라서 반환
        else:
            print(f"Error fetching ohlcv data: {res.text}")
            return None

    def get_balance(self):
        """계좌 잔고 조회"""
        time.sleep(0.1)
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.base_url}{path}"
        headers = self._get_common_headers("TTTC8434R") # 실전투자: TTTC8434R, 모의투자: VTTC8434R
        
        params = {
            "CANO": self.account_no.split('-')[0],
            "ACNT_PRDT_CD": self.account_no.split('-')[1],
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            return res.json()
        else:
            print(f"Error getting balance: {res.text}")
            return None

    def _place_order(self, ticker, quantity, order_type, tr_id):
        """주문 실행 (공통 로직)"""
        time.sleep(0.1)
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        url = f"{self.base_url}{path}"
        headers = self._get_common_headers(tr_id)
        
        data = {
            "CANO": self.account_no.split('-')[0],
            "ACNT_PRDT_CD": self.account_no.split('-')[1],
            "PDNO": ticker,
            "ORD_DVSN": "01",  # 01: 시장가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0", # 시장가는 0
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(data))
        if res.status_code == 200:
            return res.json()
        else:
            print(f"Error placing order: {res.text}")
            return {"rt_cd": "1", "msg1": f"주문 실패: {res.text}"}

    def buy_market_order(self, ticker, quantity):
        """시장가 매수"""
        # 실전투자: TTTC0802U, 모의투자: VTTC0802U
        return self._place_order(ticker, quantity, "buy", "TTTC0802U")

    def sell_market_order(self, ticker, quantity):
        """시장가 매도"""
        # 실전투자: TTTC0801U, 모의투자: VTTC0801U
        return self._place_order(ticker, quantity, "sell", "TTTC0801U")

    def get_current_price(self, ticker):
        """현재가 조회"""
        time.sleep(0.1)
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        url = f"{self.base_url}{path}"
        headers = self._get_common_headers("FHKST01010100")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }

        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            return int(res.json()['output']['stck_prpr'])
        else:
            print(f"Error getting current price: {res.text}")
            return None

