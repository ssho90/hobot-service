import os
import pyupbit
import traceback
from service.upbit.upbit_utils import read_current_strategy

def get_upbit_account_summary():
    try:
        access_key = os.environ.get("UP_ACCESS_KEY")
        secret_key = os.environ.get("UP_SECRET_KEY")
        
        if not access_key or not secret_key:
            return {"status": "error", "message": "Upbit API keys not found in environment variables."}

        upbit = pyupbit.Upbit(access_key, secret_key)
        
        # 1. 잔고 조회
        balances = upbit.get_balances()
        if not isinstance(balances, list):
             return {"status": "error", "message": "Failed to fetch balances from Upbit."}

        # 2. 현재 전략 조회
        current_strategy = read_current_strategy()

        total_krw_balance = 0
        total_asset_valuation = 0
        total_pnl = 0
        
        assets = []
        
        # 보유 코인 리스트 (KRW 제외)
        tickers = []
        for b in balances:
            if b['currency'] != 'KRW':
                tickers.append(f"KRW-{b['currency']}")
        
        # 3. 현재가 조회 (한번에 조회하여 효율성 증대)
        current_prices = {}
        if tickers:
            try:
                current_prices = pyupbit.get_current_price(tickers)
                # 만약 티커가 1개면 float으로 반환되므로 dict로 변환
                if isinstance(current_prices, float) or isinstance(current_prices, int):
                    current_prices = {tickers[0]: current_prices}
            except Exception as e:
                print(f"Error fetching prices: {e}")
                # 가격 조회 실패시 처리를 위해 비워둠 (개별 계산에서 0 처리)

        for b in balances:
            currency = b['currency']
            balance = float(b['balance']) + float(b['locked'])
            avg_buy_price = float(b['avg_buy_price'])
            
            if currency == 'KRW':
                total_krw_balance += balance
                total_asset_valuation += balance # 현금도 자산 평가액에 포함
                continue
            
            # 암호화폐 처리
            ticker = f"KRW-{currency}"
            current_price = current_prices.get(ticker, 0)
            
            valuation = balance * current_price
            buy_cost = balance * avg_buy_price
            pnl = valuation - buy_cost
            pnl_rate = (pnl / buy_cost * 100) if buy_cost > 0 else 0
            
            total_asset_valuation += valuation
            total_pnl += pnl
            
            assets.append({
                "currency": currency,
                "ticker": ticker,
                "balance": balance,
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "valuation": valuation,
                "pnl": pnl,
                "pnl_rate": pnl_rate
            })

        # 총 자산 (현금 + 암호화폐 평가액)
        # 총 손익 (암호화폐 평가손익 합계)
        
        # 수익률 (총 평가손익 / (총 자산 - 총 평가손익)) -> 원금 대비 수익률
        # 혹은 (총 자산 - 초기 자산) / 초기 자산인데, 초기 자산을 정확히 알 수 없음.
        # 화면의 "총 손익"이 암호화폐에 대한 손익인지 전체 자산에 대한 것인지에 따라 다름.
        # 보통 거래소 화면은 (총 보유자산 - 총 매수금액) / 총 매수금액 임.
        # 총 매수금액 = 현금 + 암호화폐 매수금액? 아니면 암호화폐 매수금액만?
        # 업비트 앱 기준:
        # 총 보유자산 = KRW + 암호화폐 평가금액
        # 총 매수금액 = 암호화폐 매수 총액
        # 평가손익 = 암호화폐 평가금액 - 암호화폐 매수 총액
        # 수익률 = 평가손익 / 총 매수금액 * 100
        
        total_buy_cost = sum(a['balance'] * a['avg_buy_price'] for a in assets)
        total_pnl_rate = (total_pnl / total_buy_cost * 100) if total_buy_cost > 0 else 0

        # 가수도정산(D+2)는 주식에 해당, 코인은 즉시 정산이므로 현금과 동일하거나 없음. 
        # 화면 구성을 위해 예수금 항목 사용.
        
        return {
            "status": "success",
            "account_info": {
                "total_krw": total_krw_balance,
                "total_asset_amount": total_asset_valuation,
                "total_invest_amount": total_buy_cost,
                "total_pnl": total_pnl,
                "total_pnl_rate": total_pnl_rate,
                "strategy": current_strategy
            },
            "assets": assets
        }

    except Exception as e:
        trace = traceback.format_exc()
        print(f"Error in get_upbit_account_summary: {e}")
        return {"status": "error", "message": str(e), "trace": trace}
