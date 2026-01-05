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

from service.database.db import get_db_connection
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

def get_active_etf_mapping_from_db() -> Dict[str, str]:
    """
    최신 AI 전략 결정에 따른 ETF 티커 -> 자산군 매핑 정보를 DB에서 조회
    
    Returns:
        Dict[str, str]: 티커(ticker) -> 자산군(asset_class) 매핑
        예: {"005930": "stocks", "305080": "bonds"}
    """
    try:
        mapping = {}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 최신 AI 전략 결정의 target_allocation 조회
            cursor.execute("""
                SELECT target_allocation
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                return {}
            
            target_alloc_raw = row['target_allocation']
            if isinstance(target_alloc_raw, str):
                target_alloc = json.loads(target_alloc_raw)
            else:
                target_alloc = target_alloc_raw
            
            # "sub_mp" 필드 확인 (예: {"stocks": "Eq-D", "bonds": "Bnd-L", ...})
            sub_mp_map = target_alloc.get('sub_mp')
            if not sub_mp_map:
                # sub_mp가 없으면 매핑 불가
                return {}
            
            # 2. 각 자산군별 Sub-MP ID에 대해 티커 목록 조회
            # asset_class: stocks, bonds, alternatives, cash
            for asset_class, sub_mp_id in sub_mp_map.items():
                if asset_class == 'reasoning': continue  # reasoning 필드 제외

                # Sub-MP ID로 sub_portfolio_models의 ID 조회
                cursor.execute("SELECT id FROM sub_portfolio_models WHERE sub_model_id = %s", (sub_mp_id,))
                model_row = cursor.fetchone()
                if not model_row:
                    continue
                
                model_id = model_row['id']
                
                # 3. sub_portfolio_compositions에서 티커 조회
                cursor.execute("""
                    SELECT ticker 
                    FROM sub_portfolio_compositions 
                    WHERE sub_portfolio_model_id = %s
                """, (model_id,))
                
                tickers = cursor.fetchall()
                for t_row in tickers:
                    ticker = t_row.get('ticker')
                    if ticker:
                        mapping[ticker] = asset_class.lower() # 소문자로 통일 (stocks, bonds, ...)
                        
        return mapping
    except Exception as e:
        logging.error(f"Error fetching ETF mapping from DB: {e}")
        return {}

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
        ticker_to_asset_class = get_active_etf_mapping_from_db()
        
        # DB에서 매핑 정보가 없는 경우 (안전망), 설정 파일 로더는 사용하지 않음 (ConfigLoader.etf_mapping 없음)
        if not ticker_to_asset_class:
            logging.warning("No ETF mapping found in DB. Holdings classification may be incorrect.")
        
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
        
        total_eval_amt = int(float(output2[0]['tot_evlu_amt'])) if output2 else 0
        
        # 현금 잔액 (주문가능금액 사용)
        if output2:
            # ord_psbl_tot_amt (주문가능총액)만 사용 -> inquire-balance 응답에 없음
            # prvs_rcdl_excc_amt (가수도정산금액/D+2예수금) 사용: 매도 정산 예정 금액 포함
            cash_balance = int(float(output2[0].get('prvs_rcdl_excc_amt') or 0))
        else:
            cash_balance = 0
        
        # 보유 주식 정보
        holdings = []
        if output1:
            for item in output1:
                holdings.append({
                    "stock_code": item.get('pdno', ''),
                    "stock_name": item.get('prdt_name', ''),
                    "quantity": int(float(item.get('hldg_qty', 0))),
                    "avg_buy_price": int(float(item.get('pchs_avg_pric', 0))),
                    "current_price": int(float(item.get('prpr', 0))),
                    "eval_amount": int(float(item.get('evlu_amt', 0))),
                    "profit_loss": int(float(item.get('evlu_pfls_amt', 0))),
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


def get_current_price_api(user_id: str, ticker: str) -> Optional[int]:
    """
    특정 종목의 현재가를 조회합니다.
    """
    try:
        start_t = time.time()
        credentials = get_user_kis_credentials(user_id)
        if not credentials:
            logging.error(f"No credentials found for user {user_id}")
            return None
            
        api = KISAPI(
            credentials['app_key'], 
            credentials['app_secret'], 
            credentials['account_no'],
            is_simulation=credentials.get('is_simulation', False)
        )
        price = api.get_current_price(ticker)
        end_t = time.time()
        logging.info(f"Price fetch for {ticker} took {end_t - start_t:.4f}s")
        return price
    except Exception as e:
        logging.error(f"Error fetching current price for {ticker}: {e}")
        return None

