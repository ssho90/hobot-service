export interface Stock {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: string;
}

export interface NewsItem {
  id: number;
  title: string;
  source: string;
  time: string;
  summary: string;
}

export interface MarketIndex {
  name: string;
  value: number;
  change: number;
  changePercent: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'model';
  text: string;
  sources?: { uri: string; title: string }[];
  isThinking?: boolean;
}

export interface MacroReport {
  summary: string;
  judgment: string[];
  allocation: {
    equity: number;
    bonds: number;
    alts: number;
    cash: number;
  };
  strategies: {
    title: string;
    type: 'aggressive' | 'defensive' | 'inflation';
    description: string;
    tickers: { symbol: string; name: string; weight: string }[];
  }[];
}
