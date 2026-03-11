# Session 01. KIS SSL 번들 충돌 수정

## 목표

- 로컬에서 `REQUESTS_CA_BUNDLE`가 설정되어 있어도 KIS OpenAPI 토큰 발급과 조회 요청이 실패하지 않도록 한다.

## 진행 기록

1. 에러는 `requests.post(.../oauth2/tokenP)`에서 `SSLCertVerificationError`로 발생했다.
2. 현재 로컬 프로세스에는 `REQUESTS_CA_BUNDLE=/Users/ssho/Downloads/SSL240227/LGCNS_CA_v3.crt`가 설정되어 있었다.
3. `kis_api.py`는 `verify`를 명시하지 않아 전역 `requests` 환경을 그대로 따르고 있었다.
4. 수정 전략은 KIS 요청에만 기본 certifi 번들과 추가 CA를 합친 임시 번들을 명시적으로 적용하는 것이다.
5. `kis_api.py`에 `_build_kis_verify_bundle_path()`와 `_send_request()`를 추가하고, 토큰 발급/재발급/일반 요청 경로를 모두 공통 helper로 통일했다.
6. `py_compile` 검증을 통과했고, 로컬 환경에서 임시 병합 번들 파일 생성도 확인했다.
