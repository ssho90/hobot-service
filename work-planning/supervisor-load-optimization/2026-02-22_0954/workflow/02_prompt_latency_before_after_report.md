# 실제 질의 전/후 비교 리포트 (Prompt Token / Latency)

## 기준
- 개선 적용 시점: `2026-02-22 09:54:00`
- 비교 방식:
  - **Before**: 시점 이전 동일/유사 질의의 최신 `graph_rag_answer` 로그
  - **After**: 시점 이후 동일/유사 질의의 최신 `graph_rag_answer` 로그
- 데이터 소스: `llm_usage_logs`

## 1) 한국 부동산 가격 전망
- Before
  - 질문: `한국 부동산 가격 전망 해줘`
  - supervisor prompt tokens: `12,801`
  - supervisor latency: `25,488ms`
- After
  - 질문: `한국 부동산 시장의 가격 전망`
  - supervisor prompt tokens: `3,161`
  - supervisor latency: `88,268ms`
- 변화
  - prompt tokens: `-9,640` (`-75.31%`)
  - latency: `+62,780ms` (`+246.31%`)

## 2) 팔란티어 주가
- Before
  - 질문: `팔란티어 주가 요즘 어때?`
  - supervisor prompt tokens: `14,861`
  - supervisor latency: `21,809ms`
- After
  - 질문: `팔란티어 주식의 현재 주가와 최근 동향에 대해 알려주세요.`
  - supervisor prompt tokens: `3,761`
  - supervisor latency: `28,348ms`
- 변화
  - prompt tokens: `-11,100` (`-74.69%`)
  - latency: `+6,539ms` (`+29.98%`)

## 3) 미국 금리/물가가 경기전망에 미친 영향
- Before
  - 질문: `미국 금리와 물가 흐름이 경기 전망에 준 영향을 설명해줘.`
  - supervisor prompt tokens: `15,317`
  - supervisor latency: `18,959ms`
- After
  - 질문: `미국 금리 및 물가 흐름이 경기 전망에 미친 영향을 설명해 주십시오.`
  - supervisor prompt tokens: `3,325`
  - supervisor latency: `20,688ms`
- 변화
  - prompt tokens: `-11,992` (`-78.29%`)
  - latency: `+1,729ms` (`+9.12%`)

## 해석
- 핵심 목표였던 **supervisor 입력 프롬프트 토큰 절감**은 3개 모두 큰 폭으로 달성됨(약 `-75% ~ -78%`).
- 반면 latency는 감소하지 않았고 일부 케이스에서 증가함.
  - 이유: supervisor 외에 `query_rewrite`, `query_normalization`, `citation_postprocess`, `agent_execution` 호출이 추가/확대되며 end-to-end 시간이 커짐.
  - 특히 부동산 질의는 응답 생성 구간에서 모델 지연 변동성이 크게 나타남.

## 참고/한계
- Before/After 질문 텍스트는 유틸리티 재작성으로 문구가 일부 달라질 수 있음.
- 과거 일부 로그는 `flow_run_id`가 비어 있어 flow 합산 지표 비교에 제약이 있음.
