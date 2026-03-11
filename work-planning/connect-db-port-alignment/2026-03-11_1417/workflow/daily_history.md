# Daily History

## 2026-03-11
- 세션: [01_fix_connect_db_port.md](./01_fix_connect_db_port.md)
- 핵심 요약: `connect_db.sh`가 `3306`으로 터널을 열던 문제를 확인하고, `hobot/.env`의 `DB_PORT=3307`과 맞도록 수정했다.
- 이슈/해결: 앱은 `3307`에 붙는데 터널은 `3306`에 떠 있어 `Connection refused`가 발생할 수 있었다. 스크립트 포트를 `3307`로 통일했다.
- 다음 목표: 터널을 다시 띄우고 백엔드 프로세스를 재시작해 새 포트 매핑으로 연결 확인
