# Daily History

## 2026-03-11
- 세션: [01_kis_ssl_fix.md](./01_kis_ssl_fix.md)
- 핵심 요약: KIS API SSL 실패 원인을 전역 `REQUESTS_CA_BUNDLE` 충돌로 확인했고, `kis_api.py`에 기본 certifi + 추가 CA 병합 번들을 KIS 요청에만 적용하는 국소 패치를 구현했다.
- 이슈/해결: 전역 환경을 바꾸면 서버/다른 API 호출까지 영향이 갈 수 있어, `requests.Session`과 KIS 전용 `verify` 경로로 범위를 제한했다. `py_compile`과 병합 번들 생성 확인으로 정적 검증도 마쳤다.
- 다음 목표: 백엔드 재시작 후 `/api/kis/balance`를 다시 호출해 실제 KIS 토큰 발급이 통과하는지 확인
