import pyupbit
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
import os
from typing import Optional, Dict, Any
from slack_bot import post_message

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data/bitcoin_csv_collector.log'),
        logging.StreamHandler()
    ]
)

class BitcoinCSVCollector:
    def __init__(self, ticker: str = "KRW-BTC", csv_path: str = "data/bitcoin_1m_ohlcv.csv"):
        """
        비트코인 1분봉 데이터를 CSV 파일에 저장하는 클래스
        
        Args:
            ticker (str): 수집할 티커 (기본값: KRW-BTC)
            csv_path (str): CSV 파일 저장 경로
        """
        self.ticker = ticker
        self.csv_path = csv_path
        self._ensure_data_directory()
        
    def _ensure_data_directory(self):
        """데이터 디렉토리가 존재하는지 확인하고 없으면 생성"""
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        
    def fetch_historical_data_to_csv(self, start_date: Optional[str] = None, 
                                   end_date: Optional[str] = None,
                                   batch_size: int = 200) -> Dict[str, Any]:
        """
        과거 1분봉 데이터를 수집하여 CSV 파일에 저장
        
        Args:
            start_date (str, optional): 시작 날짜 (YYYY-MM-DD 형식)
            end_date (str, optional): 종료 날짜 (YYYY-MM-DD 형식)
            batch_size (int): 한 번에 가져올 데이터 개수
            
        Returns:
            Dict[str, Any]: 수집 결과 정보
        """
        try:
            # 날짜 설정
            if not start_date:
                # 기본값: 업비트 비트코인 데이터 시작일 (2017년 10월 1일)
                start_date = "2017-10-01"
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
                
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            logging.info(f"CSV 데이터 수집 시작: {start_date} ~ {end_date}")
            
            # 기존 CSV 파일 확인
            existing_data = None
            if os.path.exists(self.csv_path):
                try:
                    existing_data = pd.read_csv(self.csv_path)
                    existing_data['timestamp'] = pd.to_datetime(existing_data['timestamp'])
                    existing_data.set_index('timestamp', inplace=True)
                    logging.info(f"기존 CSV 파일 발견: {len(existing_data)}개 레코드")
                    
                    # 이미 수집된 데이터가 있으면 그 이후부터 수집
                    if not existing_data.empty:
                        latest_dt = existing_data.index.max()
                        # 타입 체크 및 변환
                        if bool(pd.isnull(latest_dt)) or not isinstance(latest_dt, (pd.Timestamp, datetime)):
                            logging.warning(f'latest_dt 타입 이상: {type(latest_dt)}, 값: {latest_dt}')
                        else:
                            if latest_dt >= pd.Timestamp(start_dt):
                                start_dt = latest_dt + timedelta(minutes=1)
                                logging.info(f"기존 데이터 이후부터 수집: {start_dt}")
                except Exception as e:
                    logging.warning(f"기존 CSV 파읽기 실패: {e}")
                    existing_data = None
            
            all_data = []
            current_dt = start_dt
            total_collected = 0
            
            while isinstance(current_dt, (pd.Timestamp, datetime)) and current_dt <= end_dt:
                try:
                    # 배치 단위로 데이터 수집
                    # current_dt가 Timestamp/Datetime이 아닐 경우 변환
                    if not isinstance(current_dt, (pd.Timestamp, datetime)):
                        try:
                            current_dt = pd.to_datetime(current_dt)
                        except Exception as e:
                            logging.error(f"current_dt 변환 실패: {current_dt}, {e}")
                            break
                    df = pyupbit.get_ohlcv(
                        self.ticker, 
                        interval="minute1", 
                        to=current_dt.strftime('%Y-%m-%d %H:%M:%S'),
                        count=batch_size
                    )
                    
                    if df is None or df.empty:
                        logging.warning(f"데이터 없음: {current_dt}")
                        current_dt += timedelta(days=1)
                        continue
                    
                    # 데이터프레임을 리스트에 추가
                    all_data.append(df)
                    total_collected += len(df)
                    
                    logging.info(f"배치 수집 완료: {len(df)}개 레코드, 총 {total_collected}개")
                    
                    # API 호출 제한을 위한 대기
                    time.sleep(0.1)
                    
                    # 다음 배치로 이동
                    if len(df) < batch_size:
                        # 더 이상 데이터가 없으면 다음 날로
                        current_dt += timedelta(days=1)
                    else:
                        # 마지막 데이터의 다음 시간으로
                        current_dt = df.index[-1] + timedelta(minutes=1)
                        
                except Exception as e:
                    logging.error(f"배치 처리 중 오류: {e}")
                    current_dt += timedelta(days=1)
                    time.sleep(1)  # 오류 시 더 긴 대기
            
            if not all_data:
                logging.warning("수집된 데이터가 없습니다")
                return {"status": "warning", "message": "수집된 데이터가 없습니다"}
            
            # 모든 데이터를 하나의 데이터프레임으로 합치기
            combined_df = pd.concat(all_data)
            
            # 중복 제거 (인덱스 기준)
            combined_df = combined_df[~combined_df.index.duplicated(keep='first')]
            
            # 기존 데이터와 합치기
            if existing_data is not None:
                final_df = pd.concat([existing_data, combined_df])
                final_df = final_df[~final_df.index.duplicated(keep='first')]
                if not isinstance(final_df, pd.DataFrame):
                    final_df = pd.DataFrame(final_df)
                final_df = final_df.sort_index()
            else:
                final_df = combined_df
            
            # CSV 파일로 저장
            final_df.to_csv(self.csv_path, index=True, index_label='timestamp')
            
            logging.info(f"CSV 파일 저장 완료: {len(final_df)}개 레코드")
            
            # Slack 알림
            message = f"비트코인 1분봉 CSV 데이터 수집 완료\n"
            message += f"수집 기간: {start_date} ~ {end_date}\n"
            message += f"새로 추가된 레코드: {len(combined_df)}개\n"
            message += f"전체 데이터: {len(final_df)}개\n"
            message += f"파일 경로: {self.csv_path}"
            post_message(message, channel="#upbit-data")
            
            return {
                "status": "success",
                "new_records": len(combined_df),
                "total_records": len(final_df),
                "start_date": start_date,
                "end_date": end_date,
                "file_path": self.csv_path
            }
            
        except Exception as e:
            error_msg = f"CSV 데이터 수집 중 오류 발생: {e}"
            logging.error(error_msg)
            post_message(f"비트코인 CSV 데이터 수집 실패: {e}", channel="#upbit-data")
            return {"status": "error", "message": error_msg}
    
    def fetch_recent_data_to_csv(self, hours: int = 24) -> Dict[str, Any]:
        """
        최근 데이터를 수집하여 CSV 파일에 저장
        
        Args:
            hours (int): 수집할 시간 범위 (시간 단위)
            
        Returns:
            Dict[str, Any]: 수집 결과 정보
        """
        try:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(hours=hours)
            
            logging.info(f"최근 CSV 데이터 수집: {start_dt} ~ {end_dt}")
            
            # 기존 CSV 파일 확인
            existing_data = None
            if os.path.exists(self.csv_path):
                try:
                    existing_data = pd.read_csv(self.csv_path)
                    existing_data['timestamp'] = pd.to_datetime(existing_data['timestamp'])
                    existing_data.set_index('timestamp', inplace=True)
                    
                    # 이미 수집된 데이터가 있으면 그 이후부터 수집
                    if not existing_data.empty:
                        latest_dt = existing_data.index.max()
                        # 타입 체크 및 변환
                        if bool(pd.isnull(latest_dt)) or not isinstance(latest_dt, (pd.Timestamp, datetime)):
                            logging.warning(f'latest_dt 타입 이상: {type(latest_dt)}, 값: {latest_dt}')
                        else:
                            if latest_dt >= pd.Timestamp(start_dt):
                                start_dt = latest_dt + timedelta(minutes=1)
                                logging.info(f"기존 데이터 이후부터 수집: {start_dt}")
                except Exception as e:
                    logging.warning(f"기존 CSV 파읽기 실패: {e}")
            
            # 데이터 수집
            df = pyupbit.get_ohlcv(
                self.ticker,
                interval="minute1",
                to=end_dt.strftime('%Y-%m-%d %H:%M:%S'),
                count=hours * 60  # 시간 * 60분
            )
            
            if df is None or df.empty:
                logging.warning("최근 데이터가 없습니다")
                return {"status": "warning", "message": "최근 데이터가 없습니다"}
            
            # 필터링: 시작 시간 이후 데이터만
            df = df[df.index >= pd.Timestamp(start_dt)]
            
            if df.empty:
                logging.info("새로운 데이터가 없습니다")
                return {"status": "info", "message": "새로운 데이터가 없습니다"}
            
            # 기존 데이터와 합치기
            if existing_data is not None:
                final_df = pd.concat([existing_data, df])
                final_df = final_df[~final_df.index.duplicated(keep='first')]
                if not isinstance(final_df, pd.DataFrame):
                    final_df = pd.DataFrame(final_df)
                final_df = final_df.sort_index()
            else:
                final_df = df
            
            # CSV 파일로 저장
            final_df.to_csv(self.csv_path, index=True, index_label='timestamp')
            
            logging.info(f"최근 CSV 데이터 저장 완료: {len(df)}개 추가, 전체 {len(final_df)}개")
            
            return {
                "status": "success",
                "new_records": len(df),
                "total_records": len(final_df),
                "file_path": self.csv_path
            }
                
        except Exception as e:
            error_msg = f"최근 CSV 데이터 수집 중 오류: {e}"
            logging.error(error_msg)
            return {"status": "error", "message": error_msg}
    
    def get_csv_statistics(self) -> Dict[str, Any]:
        """CSV 파일의 통계 정보를 조회"""
        try:
            if not os.path.exists(self.csv_path):
                return {
                    "file_exists": False,
                    "total_records": 0,
                    "earliest_date": None,
                    "latest_date": None,
                    "duration_days": 0,
                    "duration_hours": 0
                }
            
            df = pd.read_csv(self.csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            if df.empty:
                return {
                    "file_exists": True,
                    "total_records": 0,
                    "earliest_date": None,
                    "latest_date": None,
                    "duration_days": 0,
                    "duration_hours": 0
                }
            
            earliest_dt = df['timestamp'].min()
            latest_dt = df['timestamp'].max()
            duration = latest_dt - earliest_dt
            
            return {
                "file_exists": True,
                "total_records": len(df),
                "earliest_date": earliest_dt.strftime('%Y-%m-%d %H:%M:%S'),
                "latest_date": latest_dt.strftime('%Y-%m-%d %H:%M:%S'),
                "duration_days": duration.days,
                "duration_hours": duration.total_seconds() / 3600,
                "file_size_mb": os.path.getsize(self.csv_path) / (1024 * 1024)
            }
                
        except Exception as e:
            logging.error(f"CSV 통계 조회 중 오류: {e}")
            return {"error": str(e)}
    
    def read_csv_data(self, start_date: Optional[str] = None, 
                     end_date: Optional[str] = None,
                     limit: Optional[int] = None) -> pd.DataFrame:
        """
        CSV 파일에서 데이터를 읽어오기
        
        Args:
            start_date (str, optional): 시작 날짜 (YYYY-MM-DD 형식)
            end_date (str, optional): 종료 날짜 (YYYY-MM-DD 형식)
            limit (int, optional): 조회할 레코드 수 제한
            
        Returns:
            pd.DataFrame: OHLCV 데이터
        """
        try:
            if not os.path.exists(self.csv_path):
                logging.warning("CSV 파일이 존재하지 않습니다")
                return pd.DataFrame()
            
            df = pd.read_csv(self.csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # 날짜 필터링
            if start_date:
                start_dt = pd.Timestamp(start_date)
                df = df[df.index >= start_dt]
            
            if end_date:
                end_dt = pd.Timestamp(end_date)
                df = df[df.index <= end_dt]
            
            # 정렬
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            df = df.sort_index()
            
            # 레코드 수 제한
            if limit:
                df = df.tail(limit)
            
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            return df
            
        except Exception as e:
            logging.error(f"CSV 데이터 읽기 중 오류: {e}")
            return pd.DataFrame()
    
    def cleanup_old_csv_data(self, days_to_keep: int = 365) -> Dict[str, Any]:
        """
        CSV 파일에서 오래된 데이터를 삭제
        
        Args:
            days_to_keep (int): 보관할 일수
            
        Returns:
            Dict[str, Any]: 삭제 결과
        """
        try:
            if not os.path.exists(self.csv_path):
                return {"status": "warning", "message": "CSV 파일이 존재하지 않습니다"}
            
            df = pd.read_csv(self.csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            original_count = len(df)
            
            # 오래된 데이터 필터링
            df = df[df['timestamp'] >= cutoff_date]
            
            # CSV 파일 다시 저장
            df.to_csv(self.csv_path, index=False)
            
            deleted_count = original_count - len(df)
            logging.info(f"CSV 오래된 데이터 삭제 완료: {deleted_count}개 삭제")
            
            return {
                "status": "success",
                "deleted_count": deleted_count,
                "remaining_count": len(df),
                "cutoff_date": cutoff_date.strftime('%Y-%m-%d')
            }
            
        except Exception as e:
            error_msg = f"CSV 데이터 정리 중 오류: {e}"
            logging.error(error_msg)
            return {"status": "error", "message": error_msg}


def main():
    """메인 실행 함수"""
    collector = BitcoinCSVCollector()
    
    # CSV 통계 출력
    stats = collector.get_csv_statistics()
    print("=== 비트코인 CSV 데이터 통계 ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    # 사용자 입력 받기
    print("\n=== CSV 데이터 수집 옵션 ===")
    print("1. 과거 데이터 수집 (전체 - 2017년 10월부터)")
    print("2. 최근 데이터 수집 (24시간)")
    print("3. 사용자 지정 기간 수집")
    print("4. CSV 데이터 조회")
    print("5. CSV 데이터 정리 (1년 이상 데이터 삭제)")
    print("6. 종료")
    
    choice = input("\n선택하세요 (1-6): ").strip()
    
    if choice == "1":
        result = collector.fetch_historical_data_to_csv()
        print(f"결과: {result}")
        
    elif choice == "2":
        result = collector.fetch_recent_data_to_csv()
        print(f"결과: {result}")
        
    elif choice == "3":
        start_date = input("시작 날짜 (YYYY-MM-DD): ").strip()
        end_date = input("종료 날짜 (YYYY-MM-DD): ").strip()
        result = collector.fetch_historical_data_to_csv(start_date, end_date)
        print(f"결과: {result}")
        
    elif choice == "4":
        start_date = input("시작 날짜 (YYYY-MM-DD, 선택사항): ").strip() or None
        end_date = input("종료 날짜 (YYYY-MM-DD, 선택사항): ").strip() or None
        limit = input("조회할 레코드 수 (선택사항): ").strip()
        limit = int(limit) if limit.isdigit() else None
        
        df = collector.read_csv_data(start_date, end_date, limit)
        if not df.empty:
            print(f"\n조회된 데이터: {len(df)}개 레코드")
            print(df.head())
            print(f"\n최근 데이터:")
            print(df.tail())
        else:
            print("조회된 데이터가 없습니다")
        
    elif choice == "5":
        days = input("보관할 일수 (기본값: 365): ").strip()
        days = int(days) if days.isdigit() else 365
        result = collector.cleanup_old_csv_data(days)
        print(f"결과: {result}")
        
    elif choice == "6":
        print("종료합니다.")
        
    else:
        print("잘못된 선택입니다.")


if __name__ == "__main__":
    main() 