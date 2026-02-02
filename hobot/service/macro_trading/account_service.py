import json
import logging
import traceback
from datetime import date
from service.database.db import get_db_connection
from service.macro_trading.kis.kis import get_balance_info_api

logger = logging.getLogger(__name__)

def save_daily_account_snapshot():
    """
    매일 아침 9시 계좌 상태를 스냅샷으로 저장
    """
    try:
        logger.info("Daily account snapshot started")
        
        # 1. 대상 사용자 조회 (모든 사용자 대상)
        users = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM user_kis_credentials")
            rows = cursor.fetchall()
            if rows:
                users = [row['user_id'] for row in rows]
        
        if not users:
            logger.warning("No users found with KIS credentials. Skipping snapshot.")
            return

        for user_id in users:
            try:
                logger.info(f"Processing snapshot for user: {user_id}")
                
                # 2. 잔고 조회
                balance_info = get_balance_info_api(user_id)
                
                if balance_info.get('status') != 'success':
                    logger.error(f"Failed to fetch balance for user {user_id}: {balance_info.get('message')}")
                    continue

                # 3. 데이터 추출
                total_eval_amount = balance_info.get('total_eval_amount', 0)
                cash_balance = balance_info.get('cash_balance', 0)
                total_profit_loss = balance_info.get('total_profit_loss', 0)
                total_return_rate = balance_info.get('total_return_rate', 0.0) 
                
                asset_class_info = balance_info.get('asset_class_info', {})
                
                allocation_actual = {}
                # 자산 배분 계산
                # Make sure denominator is not zero
                calc_base = total_eval_amount if total_eval_amount > 0 else 1
                
                for ac, info in asset_class_info.items():
                    val = info.get('total_eval_amount', 0)
                    ratio = (val / calc_base) * 100
                    allocation_actual[ac] = round(ratio, 2)

                # pnl_by_asset
                pnl_by_asset = {}
                for ac, info in asset_class_info.items():
                    pnl_by_asset[ac] = info.get('profit_loss_rate', 0.0)

                snapshot_date = date.today()

                # 4. DB 저장
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Check duplication for today AND user
                    cursor.execute(
                        "SELECT id FROM account_snapshots WHERE snapshot_date = %s AND user_id = %s", 
                        (snapshot_date, user_id)
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Update
                        sql = """
                            UPDATE account_snapshots 
                            SET total_value = %s, cash_balance = %s, allocation_actual = %s, 
                                pnl_by_asset = %s, pnl_total = %s, updated_at = NOW()
                            WHERE id = %s
                        """
                        cursor.execute(sql, (
                            total_eval_amount, 
                            cash_balance, 
                            json.dumps(allocation_actual), 
                            json.dumps(pnl_by_asset), 
                            total_return_rate, 
                            existing['id']
                        ))
                        logger.info(f"Updated account snapshot for {snapshot_date} (user: {user_id})")
                    else:
                        # Insert
                        sql = """
                            INSERT INTO account_snapshots 
                            (snapshot_date, user_id, total_value, cash_balance, allocation_actual, pnl_by_asset, pnl_total)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql, (
                            snapshot_date,
                            user_id,
                            total_eval_amount, 
                            cash_balance, 
                            json.dumps(allocation_actual), 
                            json.dumps(pnl_by_asset), 
                            total_return_rate
                        ))
                        logger.info(f"Created account snapshot for {snapshot_date} (user: {user_id})")
                    
                    conn.commit()
            except Exception as e:
                logger.error(f"Error processing snapshot for user {user_id}: {e}", exc_info=True)
                # Continue to next user
                continue

    except Exception as e:
        logger.error(f"Error saving account snapshot: {e}", exc_info=True)
