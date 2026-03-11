# connect_db 포트 정렬 계획서

## 목적

로컬 SSH 터널 스크립트 `connect_db.sh`의 포트를 백엔드 `.env` 설정과 일치시켜 MySQL 연결 거부를 방지한다.

## 범위

- `connect_db.sh`의 로컬 포트를 `hobot/.env`의 `DB_PORT`와 맞춘다.
- 변경 이유를 작업 기록에 남긴다.

## 완료 조건

1. `connect_db.sh`가 `3307 -> 3306` 터널을 열도록 수정된다.
2. 스크립트 안내 문구와 실제 동작 포트가 일치한다.
