# service/macro_trading/kis/kis.py
from dotenv import load_dotenv
import os
import json
import pandas as pd
import traceback
import logging
import time
from typing import Dict, List, Optional

# 프로젝트 루트의 .env 파일 로드
load_dotenv(override=True)

# 내부 모듈 임포트
from .kis_api import KISAPI
from .kis_utils import (
    calculate_rsi, write_current_strategy, get_balance_info, 
    current_time, read_current_strategy, get_buy_info, get_sell_info, calculate_atr
)
from service.slack_bot import post_message
from service.macro_trading.config.config_loader import ConfigLoader
from .user_credentials import get_user_kis_credentials

# ===============================================
# Helper Functions
# ===============================================
def fetch_candle_data(api, ticker, interval, count):
    """Fetches OHLCV data from KIS API."""
    try:
        df = api.fetch_ohlcv(ticker, interval=interval, count=count)
        if df is None or df.empty:
            raise ValueError(f"Could not fetch candle data for {ticker}")
        return df
    except Exception as e:
        print(f"Error fetching candle data: {e}")
        traceback.print_exc()
        return None

def calculate_moving_averages(close, spans=[7, 20, 99, 180]):
    """Calculates exponential moving averages."""
    ma = {}
    for span in spans:
        ma[span] = close.ewm(span=span, adjust=False).mean().iloc[-2]
    return ma


def health_check(user_id: Optional[str] = None):
    """KIS API 헬스체크 - 잔액조회
    
    Args:
        user_id: 사용자 ID. 필수. user_kis_credentials 테이블에서 사용자별 credential 사용
    """
    try:
        if not user_id:
            return {
                "status": "error",
                "message": "user_id가 필요합니다."
            }
        
        # 사용자별 credential 사용
        credentials = get_user_kis_credentials(user_id)
        if not credentials:
            return {
                "status": "error",
                "message": "KIS API 인증 정보가 등록되지 않았습니다."
            }
        
        api = KISAPI(
            credentials['app_key'], 
            credentials['app_secret'], 
            credentials['account_no'],
            is_simulation=credentials.get('is_simulation', False)
        )
        
        balance_data = api.get_balance()
        if balance_data and balance_data.get('rt_cd') == '0':
            return {"status": "success", "message": "Health check success"}
        else:
            return {
                "status": "error",
                "message": balance_data.get('msg1', '잔고 조회 실패') if balance_data else '잔고 조회 실패'
            }
    except Exception as e:
        trace = traceback.format_exc()
        post_message(f"Health Check Error: {e}\n{trace}", channel="#auto-trading-error")
        return {"status": "error", "message": str(e), "trace": trace}

def parse_holdings_by_asset_class(holdings: List[Dict]) -> Dict[str, List[Dict]]:
    """
    보유 종목을 자산군별로 분류
    DB의 사용자 설정을 우선 사용하고, 없으면 설정 파일 사용
    
    Args:
        holdings: 보유 종목 리스트
        
    Returns:
        자산군별로 분류된 holdings 딕셔너리
    """
    try:
        # 티커 → 자산군 매핑 딕셔너리 생성
        ticker_to_asset_class = {}
        
        # 설정 파일에서 로드
        config_loader = ConfigLoader()
        config = config_loader.load()
        etf_mapping = config.etf_mapping
        
        for asset_class, mapping in etf_mapping.items():
            for ticker in mapping.tickers:
                ticker_to_asset_class[ticker] = asset_class
        
        # 자산군별 holdings 분류
        classified_holdings = {
            "stocks": [],
            "bonds": [],
            "alternatives": [],
            "cash": [],
            "other": []  # 매핑되지 않은 종목
        }
        
        for holding in holdings:
            stock_code = holding.get('stock_code', '')
            asset_class = ticker_to_asset_class.get(stock_code, 'other')
            
            if asset_class in classified_holdings:
                classified_holdings[asset_class].append(holding)
            else:
                classified_holdings['other'].append(holding)
        
        return classified_holdings
    except Exception as e:
        print(f"Error parsing holdings by asset class: {e}")
        traceback.print_exc()
        # 에러 발생 시 빈 딕셔너리 반환
        return {
            "stocks": [],
            "bonds": [],
            "alternatives": [],
            "cash": [],
            "other": []
        }


def calculate_asset_class_pnl(holdings: List[Dict], cash_balance: int = 0) -> Dict[str, Dict]:
    """
    자산군별 수익률 계산
    
    Args:
        holdings: 보유 종목 리스트
        cash_balance: 현금 잔액
        
    Returns:
        자산군별 수익률 정보 딕셔너리
    """
    classified_holdings = parse_holdings_by_asset_class(holdings)
    
    asset_class_info = {}
    
    # 자산군별 정보 계산
    for asset_class, class_holdings in classified_holdings.items():
        if asset_class == 'other':
            continue
            
        total_eval_amount = sum(h.get('eval_amount', 0) for h in class_holdings)
        total_profit_loss = sum(h.get('profit_loss', 0) for h in class_holdings)
        total_avg_buy_amount = sum(
            h.get('avg_buy_price', 0) * h.get('quantity', 0) 
            for h in class_holdings
        )
        
        # 수익률 계산 (매입가 대비)
        profit_loss_rate = 0.0
        if total_avg_buy_amount > 0:
            profit_loss_rate = (total_profit_loss / total_avg_buy_amount) * 100
        
        asset_class_info[asset_class] = {
            "holdings": class_holdings,
            "total_eval_amount": total_eval_amount,
            "total_profit_loss": total_profit_loss,
            "total_avg_buy_amount": total_avg_buy_amount,
            "profit_loss_rate": round(profit_loss_rate, 2),
            "count": len(class_holdings)
        }
    
    # Cash 자산군에 현금 잔액 추가
    if 'cash' in asset_class_info:
        asset_class_info['cash']['total_eval_amount'] += cash_balance
        # 현금은 수익률 0%
        if asset_class_info['cash']['total_avg_buy_amount'] > 0:
            asset_class_info['cash']['profit_loss_rate'] = (
                asset_class_info['cash']['total_profit_loss'] / 
                asset_class_info['cash']['total_avg_buy_amount']
            ) * 100
        else:
            asset_class_info['cash']['profit_loss_rate'] = 0.0
    else:
        asset_class_info['cash'] = {
            "holdings": [],
            "total_eval_amount": cash_balance,
            "total_profit_loss": 0,
            "total_avg_buy_amount": cash_balance,
            "profit_loss_rate": 0.0,
            "count": 0
        }
    
    return asset_class_info


def get_balance_info_api(user_id: Optional[str] = None):
    """잔액조회 API용 함수 - 상세 정보 반환 (자산군별 정보 포함)
    
    Args:
        user_id: 사용자 ID. 필수. user_kis_credentials 테이블에서 사용자별 credential 사용
    """
    try:
        if not user_id:
            return {
                "status": "error",
                "message": "user_id가 필요합니다."
            }
        
        logging.info(f"KIS balance API 호출 시작 - user_id: {user_id}")
        
        # 사용자별 credential 사용
        logging.info(f"사용자별 credential 조회 중 - user_id: {user_id}")
        credentials = get_user_kis_credentials(user_id)
        if not credentials:
            logging.warning(f"KIS API 인증 정보 없음 - user_id: {user_id}")
            return {
                "status": "error",
                "message": "KIS API 인증 정보가 등록되지 않았습니다. 프로필에서 인증 정보를 등록해주세요."
            }
        logging.info(f"Credential 조회 성공 - account_no: {credentials.get('account_no', 'N/A')[:4]}****")
        api = KISAPI(
            credentials['app_key'], 
            credentials['app_secret'], 
            credentials['account_no'],
            is_simulation=credentials.get('is_simulation', False)
        )
        account_no = credentials['account_no']
        
        # 레이트리밋(EGW00201: 초당 거래건수 초과) 대응 재시도
        retry_delays = [0, 0.5, 1.0]  # seconds
        balance_data = None
        last_err_text = None

        for attempt, delay in enumerate(retry_delays, start=1):
            if delay > 0:
                logging.warning(f"KIS 잔고 조회 재시도 {attempt}/{len(retry_delays)} - 대기 {delay}s (직전 오류: {last_err_text})")
                time.sleep(delay)

            try:
                logging.info(f"잔고 조회 시작 (attempt={attempt})")
                balance_data = api.get_balance()
                logging.info(f"잔고 조회 완료 - balance_data keys: {list(balance_data.keys()) if balance_data else 'None'}")
            except Exception as e:
                last_err_text = str(e)
                if (("EGW00201" in last_err_text) or ("초당 거래건수" in last_err_text)) and attempt < len(retry_delays):
                    continue
                raise

            if not balance_data:
                last_err_text = "잔고 조회 결과 None"
                if attempt < len(retry_delays):
                    continue
                logging.error("잔고 조회 결과가 None입니다")
                return {
                    "status": "error",
                    "message": "잔고 조회 실패 (응답 없음)"
                }

            rt_cd = balance_data.get('rt_cd')
            msg_cd = balance_data.get('msg_cd', '')
            msg1 = balance_data.get('msg1', '')
            msg2 = balance_data.get('msg2', '')
            logging.info(f"잔고 조회 응답 - rt_cd: {rt_cd}, msg_cd: {msg_cd}, msg1: {msg1}, msg2: {msg2}")

            rate_limit_hit = (msg_cd == "EGW00201") or ("초당 거래건수" in msg1)
            if rt_cd != '0' and rate_limit_hit and attempt < len(retry_delays):
                last_err_text = f"rt_cd:{rt_cd}, msg_cd:{msg_cd}, msg1:{msg1}"
                continue

            break  # 정상 응답 or 마지막 시도
        
        if not balance_data:
            # 이론상 도달하지 않지만 안전망
            return {
                "status": "error",
                "message": "잔고 조회 실패 (응답 없음)"
            }
        
        rt_cd = balance_data.get('rt_cd')
        msg1 = balance_data.get('msg1', '')
        msg2 = balance_data.get('msg2', '')
        logging.info(f"잔고 조회 응답 - rt_cd: {rt_cd}, msg1: {msg1}, msg2: {msg2}")
        
        if rt_cd != '0':
            logging.error(f"잔고 조회 실패 - rt_cd: {rt_cd}, msg1: {msg1}, msg2: {msg2}, 전체 응답: {json.dumps(balance_data, ensure_ascii=False)}")
            return {
                "status": "error",
                "message": balance_data.get('msg1', '잔고 조회 실패') if balance_data else '잔고 조회 실패',
                "rt_cd": rt_cd,
                "msg1": msg1,
                "msg2": msg2
            }
        
        output1 = balance_data.get('output1', [])  # 주식 잔고
        output2 = balance_data.get('output2', [])  # 계좌 총 평가
        
        total_eval_amt = int(output2[0]['tot_evlu_amt']) if output2 else 0
        
        # 현금 잔액 (주문가능금액 사용)
        if output2:
            # ord_psbl_tot_amt (주문가능총액)만 사용
            cash_balance = int(output2[0].get('ord_psbl_tot_amt') or 0)
        else:
            cash_balance = 0
        
        # 보유 주식 정보
        holdings = []
        if output1:
            for item in output1:
                holdings.append({
                    "stock_code": item.get('pdno', ''),
                    "stock_name": item.get('prdt_name', ''),
                    "quantity": int(item.get('hldg_qty', 0)),
                    "avg_buy_price": int(item.get('pchs_avg_prc', 0)),
                    "current_price": int(item.get('prpr', 0)),
                    "eval_amount": int(item.get('evlu_amt', 0)),
                    "profit_loss": int(item.get('evlu_pfls_amt', 0)),
                    "profit_loss_rate": float(item.get('evlu_pfls_rt', 0))
                })
        
        # 자산군별 정보 계산
        asset_class_info = calculate_asset_class_pnl(holdings, cash_balance)
        
        return {
            "status": "success",
            "account_no": account_no,
            "total_eval_amount": total_eval_amt,
            "cash_balance": cash_balance,
            "holdings": holdings,
            "asset_class_info": asset_class_info  # 자산군별 정보 추가
        }
    except Exception as e:
        trace = traceback.format_exc()
        return {
            "status": "error",
            "message": str(e),
            "trace": trace
        }

