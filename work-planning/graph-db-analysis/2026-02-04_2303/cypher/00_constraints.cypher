// ============================================
// Macro Knowledge Graph (MKG) - Constraints & Indexes
// Phase A: MVP 스키마 적재
// ============================================

// Unique Constraints (MVP)
CREATE CONSTRAINT IF NOT EXISTS FOR (t:MacroTheme) REQUIRE t.theme_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (i:EconomicIndicator) REQUIRE i.indicator_code IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.canonical_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:EntityAlias) REQUIRE (a.canonical_id, a.alias, a.lang) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (ev:Event) REQUIRE ev.event_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:Story) REQUIRE s.story_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (ar:AnalysisRun) REQUIRE ar.run_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (ms:MacroState) REQUIRE ms.date IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (call:GraphRagApiCall) REQUIRE call.call_id IS UNIQUE;

// Phase A에서는 vintage를 실제로 저장하지 않으므로 (indicator_code, obs_date) 유니크로 운영
// (Phase C에서 vintage 적재를 시작하면 제약조건을 (indicator_code, obs_date, vintage_date)로 마이그레이션)
CREATE CONSTRAINT IF NOT EXISTS FOR (o:IndicatorObservation) REQUIRE (o.indicator_code, o.obs_date) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (f:DerivedFeature) REQUIRE (f.indicator_code, f.feature_name, f.obs_date) IS UNIQUE;

// Indexes for Performance
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.published_at);
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.country);
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.category);
CREATE INDEX IF NOT EXISTS FOR (o:IndicatorObservation) ON (o.obs_date);
CREATE INDEX IF NOT EXISTS FOR (ev:Event) ON (ev.event_time);
CREATE INDEX IF NOT EXISTS FOR (a:EntityAlias) ON (a.alias);
CREATE INDEX IF NOT EXISTS FOR (ar:AnalysisRun) ON (ar.created_at);
CREATE INDEX IF NOT EXISTS FOR (call:GraphRagApiCall) ON (call.created_at);

// Phase D: GraphRAG Hybrid Search Index (Korean/English support)
CREATE FULLTEXT INDEX document_fulltext IF NOT EXISTS
FOR (n:Document)
ON EACH [n.title, n.text, n.title_ko, n.description_ko]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'cjk'
  }
};
