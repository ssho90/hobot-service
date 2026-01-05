import pandas as pd
import numpy as np

# ================
# current state Read/Write
# 현재 매수한 거래가 어떤 전략인지
# ================
def write_current_strategy(strategy):
    try:
        from service.database.db import get_db_connection
        import uuid
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 최신 설정 조회
            cursor.execute("SELECT id FROM crypto_config ORDER BY updated_at DESC LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                # 기존 설정 업데이트 (strategy만 변경, market_status 유지)
                cursor.execute("""
                    UPDATE crypto_config
                    SET strategy = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (strategy, row["id"]))
            else:
                # 설정이 없으면 새로 생성 (기본값 BULL)
                new_id = uuid.uuid4().hex
                cursor.execute("""
                    INSERT INTO crypto_config (id, market_status, strategy)
                    VALUES (%s, 'BULL', %s)
                """, (new_id, strategy))
            
            conn.commit()
            
        return "[System] Current Strategy : " + strategy
    except Exception as e:
        print(f"Error writing current strategy: {e}")
        return f"[System] Error writing strategy: {e}"

def read_current_strategy():
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT strategy FROM crypto_config
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                return row["strategy"]
            
        return "STRATEGY_NULL"
    except Exception as e:
        print(f"Error reading current strategy: {e}")
        return "STRATEGY_NULL"


def calculate_rsi(df):
    # 업비트에서 가상화폐의 일봉 데이터를 조회
    
    period=14

    # 가격 변동을 계산
    delta = df['close'].diff()
    delta = delta[1:]

    # 상승분과 하락분을 분리
    gain = delta.clip(lower=0)
    loss = delta.clip(upper=0).abs()
    
    # 평균 상승분과 평균 하락분을 계산
    avg_gain = gain.ewm(alpha=1 / period).mean()
    avg_loss = loss.ewm(alpha=1 / period).mean()

    # RS와 RSI를 계산
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def calculate_atr_df(df, period=14):
    # ATR
    tr1 = abs(df['high'] - df['low'])
    tr2 = abs(df['close'].shift(1) - df['high'])
    tr3 = abs(df['close'].shift(1) - df['low'])
    trs = pd.concat([tr1, tr2, tr3], axis=1)

    df['TR'] = trs.max(axis=1)
    df['ATR'] = df['TR'].rolling(window=period).mean()

    return df['ATR']

def calculate_true_range(df):
    df['high_low'] = df['high'] - df['low']
    df['high_prev_close'] = abs(df['high'] - df['close'].shift(1))
    df['low_prev_close'] = abs(df['low'] - df['close'].shift(1))
    
    df['True_Range'] = df[['high_low', 'high_prev_close', 'low_prev_close']].max(axis=1)
    
    return df

def calculate_atr(df, period=14, atr_type='rma'):
    df = calculate_true_range(df)
    
    if atr_type == 'rma':
        df['ATR'] = df['True_Range'].ewm(alpha=1/period, adjust=False).mean()
    elif atr_type == 'sma':
        df['ATR'] = df['True_Range'].rolling(window=period).mean()
    elif atr_type == 'ema':
        df['ATR'] = df['True_Range'].ewm(span=period, adjust=False).mean()
    elif atr_type == 'wma':
        weights = pd.Series(range(1, period + 1))
        df['ATR'] = df['True_Range'].rolling(window=period).apply(lambda x: (weights*x).sum() / weights.sum(), raw=True)
    else:
        raise ValueError(f"Unknown ATR type: {atr_type}")
    
    return df['ATR']


def current_time(type="time"):
    import datetime
    import pytz

    date = datetime.datetime.now(pytz.timezone('Asia/Seoul'))

    dict = {0:'(월)', 1:'(화)', 2:'(수)', 3:'(목)', 4:'(금)', 5:'(토)', 6:'(일)'}

    yoil = dict[date.weekday()]

    if type == "day":
        formatted_date = date.strftime("%Y.%m.%d") + " " + yoil
    else:
        formatted_date = date.strftime("%Y-%m-%d") + "" + yoil + " " + date.strftime("%H:%M:%S")
        #formatted_date = date.strftime("%Y.%m.%d %H:%M:%S")
        
    return formatted_date

def get_balance_info(upbit, current_currency, current_price):
    from service.upbit.upbit_utils import current_time

    current_time = current_time()
    
    try:
        balances = upbit.get_balances()
        
        # balances가 문자열인 경우 처리
        if isinstance(balances, str):
            print(f"Warning: get_balances() returned string: {balances}")
            return "API 응답 오류: 문자열 데이터 반환", 0, 0
        
        # balances가 None이거나 빈 리스트인 경우 처리
        if not balances or not isinstance(balances, list):
            print(f"Warning: get_balances() returned invalid data: {balances}")
            return "API 응답 오류: 유효하지 않은 데이터", 0, 0
            
    except Exception as e:
        print(f"Error in get_balances(): {e}")
        return f"API 호출 오류: {str(e)}", 0, 0

    # print("** get_balance_info : balance")
    # print(balances)
    
    dicts = []
    each_str = ""
    total_balance_won = 0
    balance_krw = 0
    balance_btc = 0

    try:
        for i in balances:
            # 각 항목이 딕셔너리인지 확인
            if not isinstance(i, dict):
                print(f"Warning: Invalid balance item: {i}")
                continue
                
            currency = i.get('currency', '')
            balance = i.get('balance', '0')
            avg_buy_price = i.get('avg_buy_price', '0')
            unit_currency = i.get('unit_currency', '')
            locked = i.get('locked', '0')

            dict = {
                "currency" : currency
                ,"balance" : balance
                ,"avg_buy_price" : round(float(avg_buy_price))
                ,"unit_currency" : unit_currency
                ,"locked" : round(float(locked))
            }

            # 적은 수량 제외
            if (float(avg_buy_price) * float(balance) > 4000 or currency == "KRW"):
                dicts.append(dict)
                
    except Exception as e:
        print(f"Error processing balance data: {e}")
        return f"데이터 처리 오류: {str(e)}", 0, 0

    for a in dicts:
        if a["currency"] == "KRW":
            each_avg_buy_price = format(a["avg_buy_price"], ",")
            each_balance = round(float(a["balance"]))
            each_currency = a["currency"]

            str_each_balance = format(each_balance, ",") + "원"

            each_str = each_str + f"""
<< KRW >>
- 보유현금: {str_each_balance}
            """

            balance_krw = each_balance - 10
            total_balance_won = total_balance_won + each_balance

        elif a["currency"] == current_currency:
            
            suik = (float(current_price) - a["avg_buy_price"])*100 / a["avg_buy_price"]
            suik = round(suik,2)
            esti_balance = round(float(a["balance"]) * float(current_price))
            sonik_won = float(a["balance"]) * float(current_price) - float(a["balance"]) * float(a["avg_buy_price"])

            str_balance = format(esti_balance, ",") + "원"
            str_avg_buy_price = format(a["avg_buy_price"], ",") + "원"
            str_currency = a["currency"]
            str_current_price = format(current_price,",") + "원"
            str_sonik_won = format(round(sonik_won),",") + "원"
            
            balance_btc = float(a["balance"])

            total_balance_won = total_balance_won + esti_balance

            each_str = each_str + f"""
<< {str_currency} >>
- 평가금액: {str_balance}
- 평가손익: {str_sonik_won} ({suik}%)
- 현재금액: {str_current_price}
- 매수평균가: {str_avg_buy_price}
            """

    total_balance_won = format((total_balance_won), ",") + "원"            

    header = f"""
--------------------------------------
            [Hello Hobot]
--------------------------------------
- 일시: {current_time}
- 보유자산: {total_balance_won}
        """
    
    result = header + each_str

    return result, balance_krw, balance_btc


def get_buy_info(strategy, balance_krw, current_price):
    from service.upbit.upbit_utils import current_time

    current_time = current_time()

    text = f"""
------------------------
  [매수 체결]
------------------------
- 일자: {current_time}
- 매매전략: {strategy}
- 매수금액: {balance_krw} 원
- 매수평균금액: {current_price} 원
    """
    
    return text

def get_sell_info(strategy):
    from service.upbit.upbit_utils import current_time

    current_time = current_time()

    text = f"""
------------------------
  [매도 체결]
------------------------
- 일자: {current_time}
- 매매전략: {strategy}
    """
    
    return text
    