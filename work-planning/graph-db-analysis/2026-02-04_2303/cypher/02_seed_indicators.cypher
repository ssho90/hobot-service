// ============================================
// Macro Knowledge Graph (MKG) - EconomicIndicator Seed
// Phase A: 22개 FRED 지표 노드 + MacroTheme 연결
// ============================================

UNWIND [
  {code: 'DGS10', name: '10-Year Treasury Rate', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'DGS2', name: '2-Year Treasury Rate', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'FEDFUNDS', name: 'Fed Funds Rate', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'T10Y2Y', name: '10Y-2Y Spread', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'DFII10', name: '10-Year TIPS', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'CPIAUCSL', name: 'CPI', unit: 'Index', freq: 'monthly', theme: 'inflation'},
  {code: 'PCEPI', name: 'PCE Price Index', unit: 'Index', freq: 'monthly', theme: 'inflation'},
  {code: 'PCEPILFE', name: 'Core PCE', unit: 'Index', freq: 'monthly', theme: 'inflation'},
  {code: 'T10YIE', name: 'Breakeven Inflation', unit: '%', freq: 'daily', theme: 'inflation'},
  {code: 'GDP', name: 'Gross Domestic Product', unit: 'Billions USD', freq: 'quarterly', theme: 'growth'},
  {code: 'GACDFSA066MSFRBPHI', name: 'Philly Fed Leading', unit: 'Index', freq: 'monthly', theme: 'growth'},
  {code: 'NOCDFSA066MSFRBPHI', name: 'Philly Fed Coincident', unit: 'Index', freq: 'monthly', theme: 'growth'},
  {code: 'GAFDFSA066MSFRBPHI', name: 'Philly Fed Lagging', unit: 'Index', freq: 'monthly', theme: 'growth'},
  {code: 'UNRATE', name: 'Unemployment Rate', unit: '%', freq: 'monthly', theme: 'labor'},
  {code: 'PAYEMS', name: 'Nonfarm Payrolls', unit: 'Thousands', freq: 'monthly', theme: 'labor'},
  {code: 'WALCL', name: 'Fed Total Assets', unit: 'Millions USD', freq: 'weekly', theme: 'liquidity'},
  {code: 'WTREGEN', name: 'Treasury General Account', unit: 'Millions USD', freq: 'daily', theme: 'liquidity'},
  {code: 'RRPONTSYD', name: 'Reverse Repo', unit: 'Millions USD', freq: 'daily', theme: 'liquidity'},
  {code: 'NETLIQ', name: 'Net Liquidity (WALCL - TGA - RRP)', unit: 'Millions USD', freq: 'daily', theme: 'liquidity'},
  {code: 'BAMLH0A0HYM2', name: 'High Yield Spread', unit: '%', freq: 'daily', theme: 'risk'},
  {code: 'VIXCLS', name: 'VIX', unit: 'Index', freq: 'daily', theme: 'risk'},
  {code: 'STLFSI4', name: 'Financial Stress Index', unit: 'Index', freq: 'weekly', theme: 'risk'}
] AS row
MERGE (i:EconomicIndicator {indicator_code: row.code})
SET i.name = row.name, i.unit = row.unit, i.frequency = row.freq, 
    i.source = 'FRED', i.country = 'US', i.created_at = datetime()
WITH i, row
MATCH (t:MacroTheme {theme_id: row.theme})
MERGE (i)-[:BELONGS_TO]->(t);
