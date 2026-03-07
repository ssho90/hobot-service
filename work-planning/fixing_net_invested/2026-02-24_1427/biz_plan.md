# KIS 순입금액 계산 정확도 향상 작업 계획서
  
## 목표
- Trading Dashboard에서 표시되는 '순 입금금액 (추정치)'을 KIS OpenAPI에서 실제 입출금 내역을 불러와 정확한 금액으로 대체합니다.
- 기존: `net_invested_amount = total_eval_amount - total_profit_loss` (잔고 API에서 계산된 임시 추정치, 현재 24,064,030원 출력 중)
- 개선: KIS OpenAPI의 **입출금내역조회 API (`CTRP6067R`)** 를 이용해 최근 입금액의 총합과 출금액의 총합 차이를 정확한 시드로 활용해 2400만원이 출력되도록 함.

## 세부 단계
1. `hobot/service/macro_trading/kis/kis_api.py` 파일 열고 신규 메서드 `get_deposit_withdrawal_list` 추가 
    - URL: `/uapi/domestic-stock/v1/trading/inquire-invest-deposit-withdrawal-list`
    - Parameter: CANO, ACNT_PRDT_CD, INQR_STRT_DT(계좌 개설일 또는 넉넉한 1~2년전), INQR_END_DT(오늘)
    - Response parsing: `output1` (반복부) 순회하며 `reit_amt` 합계 계산 후 `wdrw_amt` 감소
2. `hobot/service/macro_trading/kis/kis.py` 내 `get_balance_info_api` 에서 위 메서드를 호출해 `net_invested_amount` 변경 (API Rate Limit과 속도를 고려해 최대 3개월/1년 간격씩 분할 호출하거나 최근 데이터만 사용할 지 결정)
3. 단위 테스트 수행 및 Trading Dashboard 재조회 확인.

### 최종 해결 방법 (2026-02-25 수정)
- KIS OpenAPI의 경우 은행 간 이체 내역(입출금) API (CTRP6067R 등)가 RESTful 상에서 404를 내뱉으며 정상 지원되지 않음을 테스트 스크립트로 확인.
- HTS상에서 채택하고 있는 원금 계산 방식인 `매입금액합계금액(pchs_amt_smtl_amt) + 예수금(prvs_rcdl_excc_amt)`를 `kis.py`의 `net_invested_amount` 로직으로 교체.
- 사용자가 "추정치" 라는 단어에 혼란을 겪는 부분을 해소하기 위해 `TradingDashboard.tsx`의 렌더링 문자열에서 `순 입금금액 (추정)` 을 `투자원금` 으로 수정.

