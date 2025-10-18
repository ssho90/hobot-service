from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine
import pandas as pd

# SSH & DB 접속 정보
EC2_HOST = 'ec2-3-34-13-230.ap-northeast-2.compute.amazonaws.com'
EC2_USER = 'ec2-user'
EC2_PEM = 'D:\\Study\\test-EC2-key.pem'

RDS_HOST = 'price-db.ctnx0uhylu2v.ap-northeast-2.rds.amazonaws.com'
RDS_PORT = 3306
DB_USER = 'admin'
DB_PASSWORD = 'dlatl00!'
DB_NAME = 'hobot'


def get_engine_through_ssh():
    """
    EC2를 통한 SSH 터널링으로 RDS SQLAlchemy 엔진 생성
    Returns:
        engine (sqlalchemy.Engine): SQLAlchemy 엔진
        tunnel (SSHTunnelForwarder): SSH 터널 객체 (작업 후 tunnel.stop() 필수)
    """
    tunnel = SSHTunnelForwarder(
        (EC2_HOST, 22),
        ssh_username=EC2_USER,
        ssh_pkey=EC2_PEM,
        remote_bind_address=(RDS_HOST, RDS_PORT),
        local_bind_address=('127.0.0.1', 3306)
    )
    tunnel.start()

    engine = create_engine(
        f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{tunnel.local_bind_port}/{DB_NAME}',
        pool_recycle=3600
    )

    return engine, tunnel


def query_db(sql: str) -> pd.DataFrame:
    """
    SSH 터널을 통해 RDS에 접속 후 SQL 쿼리 실행
    Args:
        sql (str): 실행할 SQL 쿼리
    Returns:
        pd.DataFrame: 결과
    """
    engine, tunnel = get_engine_through_ssh()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
    finally:
        tunnel.stop()
    return df
