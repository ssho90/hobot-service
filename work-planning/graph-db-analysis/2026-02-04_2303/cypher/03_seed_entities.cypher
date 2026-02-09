// ============================================
// Macro Knowledge Graph (MKG) - Entity & Alias Seed
// Phase A: 핵심 기관/인물 Entity 10개 + Alias
// ============================================

// Core Entities
UNWIND [
  {id: 'ORG_FED', name: 'Federal Reserve', type: 'organization'},
  {id: 'ORG_ECB', name: 'European Central Bank', type: 'organization'},
  {id: 'ORG_BOJ', name: 'Bank of Japan', type: 'organization'},
  {id: 'ORG_BOK', name: 'Bank of Korea', type: 'organization'},
  {id: 'ORG_PBOC', name: "People's Bank of China", type: 'organization'},
  {id: 'ORG_TREASURY', name: 'U.S. Department of Treasury', type: 'organization'},
  {id: 'PERSON_POWELL', name: 'Jerome Powell', type: 'person'},
  {id: 'PERSON_YELLEN', name: 'Janet Yellen', type: 'person'},
  {id: 'GEO_US', name: 'United States', type: 'country'},
  {id: 'GEO_KR', name: 'South Korea', type: 'country'}
] AS row
MERGE (e:Entity {canonical_id: row.id})
SET e.name = row.name, e.entity_type = row.type, e.created_at = datetime();

// Aliases
UNWIND [
  {entity_id: 'ORG_FED', alias: '연준', lang: 'ko'},
  {entity_id: 'ORG_FED', alias: 'Fed', lang: 'en'},
  {entity_id: 'ORG_FED', alias: 'FOMC', lang: 'en'},
  {entity_id: 'ORG_FED', alias: '미 연방준비제도', lang: 'ko'},
  {entity_id: 'ORG_FED', alias: 'Federal Reserve', lang: 'en'},
  {entity_id: 'ORG_ECB', alias: 'ECB', lang: 'en'},
  {entity_id: 'ORG_ECB', alias: '유럽중앙은행', lang: 'ko'},
  {entity_id: 'ORG_BOJ', alias: 'BOJ', lang: 'en'},
  {entity_id: 'ORG_BOJ', alias: '일본은행', lang: 'ko'},
  {entity_id: 'ORG_BOK', alias: 'BOK', lang: 'en'},
  {entity_id: 'ORG_BOK', alias: '한국은행', lang: 'ko'},
  {entity_id: 'ORG_PBOC', alias: 'PBOC', lang: 'en'},
  {entity_id: 'ORG_PBOC', alias: '인민은행', lang: 'ko'},
  {entity_id: 'ORG_TREASURY', alias: 'Treasury', lang: 'en'},
  {entity_id: 'ORG_TREASURY', alias: '미 재무부', lang: 'ko'},
  {entity_id: 'ORG_TREASURY', alias: '재무부', lang: 'ko'},
  {entity_id: 'PERSON_POWELL', alias: '파월', lang: 'ko'},
  {entity_id: 'PERSON_POWELL', alias: 'Powell', lang: 'en'},
  {entity_id: 'PERSON_POWELL', alias: '제롬 파월', lang: 'ko'},
  {entity_id: 'PERSON_YELLEN', alias: '옐런', lang: 'ko'},
  {entity_id: 'PERSON_YELLEN', alias: 'Yellen', lang: 'en'},
  {entity_id: 'PERSON_YELLEN', alias: '재닛 옐런', lang: 'ko'},
  {entity_id: 'GEO_US', alias: '미국', lang: 'ko'},
  {entity_id: 'GEO_US', alias: 'US', lang: 'en'},
  {entity_id: 'GEO_US', alias: 'USA', lang: 'en'},
  {entity_id: 'GEO_US', alias: 'America', lang: 'en'},
  {entity_id: 'GEO_US', alias: 'United States', lang: 'en'},
  {entity_id: 'GEO_KR', alias: '한국', lang: 'ko'},
  {entity_id: 'GEO_KR', alias: 'Korea', lang: 'en'},
  {entity_id: 'GEO_KR', alias: 'South Korea', lang: 'en'},
  {entity_id: 'GEO_KR', alias: 'KR', lang: 'en'}
] AS row
MATCH (e:Entity {canonical_id: row.entity_id})
MERGE (a:EntityAlias {canonical_id: row.entity_id, alias: row.alias, lang: row.lang})
MERGE (e)-[:HAS_ALIAS]->(a);
