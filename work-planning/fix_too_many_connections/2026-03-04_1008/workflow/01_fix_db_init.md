# 수정 작업 로그

## 수정 대상
`hobot/service/database/db.py`

## 변경 내용

### 1. `import time` 추가 (6번째 줄)
Cool-down 시간 측정을 위한 `time.monotonic()` 사용으로 필요.

### 2. 상태 변수 추가 (882~885번째 줄)
```python
_init_lock = threading.Lock()  # 멀티스레드 동시 초기화 방지 Lock
_init_failed_at: float = 0.0   # 마지막 초기화 실패 시각
_INIT_RETRY_INTERVAL = 60.0    # 실패 후 재시도 대기 시간 (초)
```

### 3. `ensure_database_initialized()` 로직 교체
**Before:** `_initializing` 플래그만으로 재귀 방지 → 멀티스레드 동시 시도 허용, 실패 시 매 요청마다 재시도
**After:**
- `_init_lock`으로 Lock 걸어 한 번에 하나의 스레드만 초기화 시도
- 초기화 실패 시 `_init_failed_at` 기록 → 60초 Cool-down
- Lock 획득 후 Double-check (TOCTOU 방지)

## 효과
- 서버 시작 시 여러 API가 동시 호출될 때 초기화 커넥션이 1개로 제한됨
- 초기화 실패 시 60초 동안 재시도 차단 → 커넥션 폭발 방지
