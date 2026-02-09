// ============================================
// Macro Knowledge Graph (MKG) - MacroTheme Seed
// Phase A: 6개 거시 테마 노드 생성
// ============================================

UNWIND [
  {theme_id: 'rates', name: 'Rates (금리)', description: '기준금리, 국채금리, 금리 커브 관련'},
  {theme_id: 'inflation', name: 'Inflation (물가)', description: 'CPI, PCE, 기대인플레이션 관련'},
  {theme_id: 'growth', name: 'Growth (성장)', description: 'GDP, 경기선행지수, 제조업 지표'},
  {theme_id: 'labor', name: 'Labor (고용)', description: '실업률, 비농업고용, 임금 관련'},
  {theme_id: 'liquidity', name: 'Liquidity (유동성)', description: '연준 대차대조표, TGA, 역레포'},
  {theme_id: 'risk', name: 'Risk (리스크)', description: '하이일드 스프레드, VIX, 금융스트레스'}
] AS row
MERGE (t:MacroTheme {theme_id: row.theme_id})
SET t.name = row.name, t.description = row.description, t.created_at = datetime();
