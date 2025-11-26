# 종목명-티커 초기 적재 스크립트

이 스크립트는 종목명-티커 매핑 데이터를 DB에 초기 적재하는 데 사용됩니다.

## 위치

```
hobot/service/macro_trading/kis/scripts/load_stock_tickers.py
```

## 사용법

### 1. 잔고 조회를 통한 수집 (기본값)

현재 계좌에 보유 중인 종목만 수집합니다.

```bash
cd hobot
python -m service.macro_trading.kis.scripts.load_stock_tickers --from-balance
```

또는 옵션 없이 실행 (기본값):

```bash
python -m service.macro_trading.kis.scripts.load_stock_tickers
```

### 2. CSV 파일에서 읽기

CSV 파일 형식:
```csv
ticker,stock_name,market_type
005930,삼성전자,J
360750,TIGER 미국 S&P500,J
133690,TIGER 미국나스닥100,J
```

실행:
```bash
python -m service.macro_trading.kis.scripts.load_stock_tickers --from-file stocks.csv
```

예시 CSV 파일: `stocks_example.csv`

### 3. 일반적인 종목 목록 사용

주요 ETF 및 주요 종목 목록을 자동으로 사용합니다.

```bash
python -m service.macro_trading.kis.scripts.load_stock_tickers --common
```

### 4. 수동 입력

대화형으로 종목 정보를 입력합니다.

```bash
python -m service.macro_trading.kis.scripts.load_stock_tickers --manual
```

입력 형식:
```
티커,종목명,시장구분(선택)
005930,삼성전자,J
360750,TIGER 미국 S&P500,J
```

### 5. 테스트 실행 (Dry Run)

실제 DB 저장 없이 테스트만 실행합니다.

```bash
python -m service.macro_trading.kis.scripts.load_stock_tickers --common --dry-run
```

## 옵션

- `--from-balance`: 잔고 조회를 통해 보유 종목만 수집 (기본값)
- `--from-file FILE`: CSV 파일에서 종목 정보 읽기
- `--manual`: 수동으로 종목 정보 입력
- `--common`: 일반적인 ETF 및 주요 종목 목록 사용
- `--dry-run`: 실제 DB 저장 없이 테스트만 실행

## 주의사항

1. 환경 변수 설정 확인
   - `.env` 파일에 KIS API 키가 설정되어 있어야 합니다.
   - `HT_API_KEY`, `HT_SECRET_KEY`, `HT_ACCOUNT`

2. 데이터베이스 연결 확인
   - MySQL 서버가 실행 중이어야 합니다.
   - `.env` 파일에 DB 연결 정보가 설정되어 있어야 합니다.

3. 중복 처리
   - 동일한 티커가 이미 존재하면 종목명과 시장구분이 업데이트됩니다.
   - `last_updated` 날짜가 갱신됩니다.

## 예시

### 일반적인 종목 목록으로 초기 적재

```bash
python -m service.macro_trading.kis.scripts.load_stock_tickers --common
```

### CSV 파일로 초기 적재

```bash
python -m service.macro_trading.kis.scripts.load_stock_tickers --from-file stocks_example.csv
```

### 테스트 실행 후 실제 저장

```bash
# 먼저 테스트
python -m service.macro_trading.kis.scripts.load_stock_tickers --common --dry-run

# 문제없으면 실제 저장
python -m service.macro_trading.kis.scripts.load_stock_tickers --common
```

## 로그

스크립트 실행 시 다음과 같은 정보가 출력됩니다:

- 수집된 종목 목록
- 저장된 종목 수
- 오류 메시지 (있는 경우)

## 문제 해결

### KIS API 연결 실패
- `.env` 파일의 API 키 확인
- 네트워크 연결 확인

### 데이터베이스 연결 실패
- MySQL 서버 실행 확인
- `.env` 파일의 DB 연결 정보 확인

### 종목 저장 실패
- 로그에서 구체적인 오류 메시지 확인
- 티커 형식 확인 (6자리 숫자)
- 종목명에 특수문자 포함 여부 확인

