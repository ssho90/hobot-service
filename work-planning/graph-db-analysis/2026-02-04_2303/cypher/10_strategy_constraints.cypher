// Phase E-1: StrategyDecision Graph Schema
// 전략 결정(MP/Sub-MP)을 Macro Graph에 저장하기 위한 제약조건 및 인덱스

// ============================================================================
// StrategyDecision Node Constraints
// ============================================================================

// StrategyDecision 노드: 일별 전략 결정 (Source-of-Truth는 MySQL, Graph는 미러)
// - decision_id: deterministic ID (date + mp_id + hash(sub_mp_json)), upsert 가능
// - decision_date: 결정 날짜 (date 타입)
// - mp_id: 선택된 Model Portfolio (예: "MP-4")
// - target_allocation: 목표 자산 배분 (JSON 문자열)
// - sub_mp: Sub-MP 선택 결과 (JSON 문자열)
// - reasoning: 결정 근거 요약
// - analysis_summary: 분석 요약
// - created_at: 생성 시간

CREATE CONSTRAINT IF NOT EXISTS FOR (sd:StrategyDecision) REQUIRE sd.decision_id IS UNIQUE;

// decision_date 기반 조회용 인덱스
CREATE INDEX IF NOT EXISTS FOR (sd:StrategyDecision) ON (sd.decision_date);

// mp_id 기반 조회용 인덱스
CREATE INDEX IF NOT EXISTS FOR (sd:StrategyDecision) ON (sd.mp_id);

// ============================================================================
// StrategyDecision Relationships
// ============================================================================

// (StrategyDecision)-[:BASED_ON]->(MacroState)
// - 해당 날짜의 MacroState를 기반으로 전략 결정
// - MacroState는 당일의 주요 테마/시그널 요약

// (StrategyDecision)-[:USED_EVIDENCE]->(Evidence)
// - 전략 결정에 사용된 근거 텍스트

// (StrategyDecision)-[:USED_NODE]->(Event|Story|MacroTheme|EconomicIndicator|Document)
// - 전략 결정에 참조된 그래프 노드들

// (StrategyDecision)-[:DERIVED_FROM]->(IndicatorObservation|DerivedFeature)
// - (선택) 전략 결정에 사용된 파생 지표

// ============================================================================
// ID 생성 규칙 (Deterministic)
// ============================================================================
// decision_id = f"sd:{decision_date}:{mp_id}:{hash(sub_mp_json)[:8]}"
// 예: "sd:2026-02-08:MP-4:a1b2c3d4"
// - 동일 날짜/MP/Sub-MP 조합은 동일 ID → upsert 가능

