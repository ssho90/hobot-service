# 구현 로그

## 변경 파일
- `hobot/service/macro_trading/scheduler.py`

## 구현 내용
- 신규 함수 추가
  - `_parse_env_yyyymm`
  - `_shift_month`
  - `run_kr_macro_collection_from_env`
  - `run_kr_real_estate_pipeline_from_env`
  - `setup_kr_macro_scheduler`
  - `setup_kr_real_estate_scheduler`
- `start_all_schedulers()`에 아래 등록 추가
  - `setup_kr_macro_scheduler()`
  - `setup_kr_real_estate_scheduler()`

## 검증 결과
- `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile .../scheduler.py` 통과
- schedule 등록 시뮬레이션 결과 신규 태그 등록 확인
  - `kr_macro_collection_daily`
  - `kr_real_estate_collection_daily`
- 전체 setup 기준 총 24개 스케줄 등록 확인
