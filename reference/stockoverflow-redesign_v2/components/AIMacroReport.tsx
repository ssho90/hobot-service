import React from 'react';
import { MacroReport } from '../types';
import { Brain, PieChart, Shield, TrendingUp, Zap, Target } from 'lucide-react';

const mockReport: MacroReport = {
  summary: "The economy is maintaining an expansionary phase, but 'Reflation' fears are resurfacing as price pressures persist. While the Philly Fed Manufacturing Index shows robustness, the rise in CPI suggests inflation is stickier than anticipated. We maintain a 'Goldilocks' outlook (MP-1) but are closely monitoring 'Bear Steepening' risks in the bond market.",
  judgment: [
    "Economic Resilience: Manufacturing data (Philly Fed) remains strong, signaling no immediate recession risk.",
    "Inflation Stickiness: Core CPI remains elevated. The labor market (NFP) is cooling but not collapsing.",
    "Yield Curve: The 10Y-2Y spread is narrowing but remains inverted. Watch for Bear Steepening as a risk signal.",
    "Conclusion: Maintain exposure to growth assets (50%) but hedge with inflation-resistant alternatives (30%)."
  ],
  allocation: {
    equity: 50.0,
    bonds: 10.0,
    alts: 30.0,
    cash: 10.0
  },
  strategies: [
    {
      title: "Aggressive Growth",
      type: 'aggressive',
      description: "Focus on Tech & Quality Growth despite rate volatility.",
      tickers: [
        { symbol: 'QQQ', name: 'Invesco QQQ', weight: '50%' },
        { symbol: 'SPY', name: 'SPDR S&P 500', weight: '30%' },
        { symbol: 'SOXX', name: 'iShares Semiconductor', weight: '20%' }
      ]
    },
    {
      title: "Short Duration (Cash Proxy)",
      type: 'defensive',
      description: "Park liquidity in short-term instruments to avoid duration risk.",
      tickers: [
        { symbol: 'SGOV', name: 'iShares 0-3 Month Treasury', weight: '80%' },
        { symbol: 'BIL', name: 'SPDR Bloomberg 1-3 Month', weight: '20%' }
      ]
    },
    {
      title: "Inflation Fighter",
      type: 'inflation',
      description: "Hedge against sticky inflation and commodity shocks.",
      tickers: [
        { symbol: 'GLD', name: 'SPDR Gold Shares', weight: '60%' },
        { symbol: 'PDBC', name: 'Invesco Optimum Yield Cmdty', weight: '40%' }
      ]
    }
  ]
};

export const AIMacroReport: React.FC = () => {
  return (
    <div className="bg-zinc-900/40 rounded-2xl border border-zinc-800 shadow-xl overflow-hidden backdrop-blur-sm">
      {/* Header */}
      <div className="p-6 border-b border-zinc-800 bg-gradient-to-r from-zinc-900 to-black flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600/20 p-2 rounded-xl border border-blue-500/30">
            <Brain className="h-6 w-6 text-blue-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">AI Economic Analysis</h2>
            <p className="text-sm text-zinc-500">Macro-based Asset Allocation Strategy • Updated: Just now</p>
          </div>
        </div>
        <div className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/30 rounded-full">
           <span className="text-xs font-semibold text-emerald-400">Regime: Expansion (Goldilocks)</span>
        </div>
      </div>

      <div className="p-6 grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Left: Analysis Text */}
        <div className="lg:col-span-7 space-y-8">
          
          {/* MP 분석 요약 - Contains "분석 요약" and "판단 근거" */}
          <section className="space-y-6">
            <h3 className="text-sm uppercase tracking-wider text-blue-400 font-bold mb-4 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div> MP 분석 요약
            </h3>
            
            <div className="space-y-4 pl-3">
              <div>
                <h4 className="text-xs text-zinc-600 uppercase font-semibold mb-2 ml-1">분석 요약</h4>
                <p className="text-zinc-200 leading-relaxed text-sm bg-black/60 p-4 rounded-lg border border-zinc-800">
                  {mockReport.summary}
                </p>
              </div>
              
              <div>
                <h4 className="text-xs text-zinc-600 uppercase font-semibold mb-3 ml-1">판단 근거</h4>
                <ul className="space-y-3">
                  {mockReport.judgment.slice(0, 2).map((item, idx) => (
                    <li key={idx} className="flex gap-3 text-sm text-zinc-300">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-zinc-950 flex items-center justify-center text-xs font-bold text-zinc-600 border border-zinc-800">
                        {idx + 1}
                      </span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>

          {/* SUB-MP 분석 요약 - Contains only "판단 근거" */}
          <section className="space-y-4 pt-4 border-t border-zinc-800/50">
            <h3 className="text-sm uppercase tracking-wider text-purple-400 font-bold mb-4 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-purple-500"></div> SUB-MP 분석 요약
            </h3>
            
            <div className="pl-3">
              <h4 className="text-xs text-zinc-600 uppercase font-semibold mb-3 ml-1">판단 근거</h4>
              <ul className="space-y-3">
                {mockReport.judgment.slice(2).map((item, idx) => (
                  <li key={idx} className="flex gap-3 text-sm text-zinc-300">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-zinc-950 flex items-center justify-center text-xs font-bold text-zinc-600 border border-zinc-800">
                      {idx + 3}
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </div>

        {/* Right: Allocation & Strategies */}
        <div className="lg:col-span-5 space-y-8">
          
          {/* Asset Allocation */}
          <section className="bg-black/50 p-5 rounded-xl border border-zinc-800">
            <h3 className="text-sm uppercase tracking-wider text-zinc-500 font-semibold mb-4 flex items-center gap-2">
              <PieChart className="h-4 w-4" /> TARGET ALLOCATION
            </h3>
            <div className="grid grid-cols-2 gap-4">
               <div className="bg-zinc-900 p-4 rounded-xl border border-zinc-800/50 text-center">
                  <span className="block text-2xl font-bold text-blue-400">{mockReport.allocation.equity}%</span>
                  <span className="text-[10px] text-zinc-600 uppercase font-bold tracking-tighter">EQUITIES</span>
               </div>
               <div className="bg-zinc-900 p-4 rounded-xl border border-zinc-800/50 text-center">
                  <span className="block text-2xl font-bold text-indigo-400">{mockReport.allocation.bonds}%</span>
                  <span className="text-[10px] text-zinc-600 uppercase font-bold tracking-tighter">BONDS</span>
               </div>
               <div className="bg-zinc-900 p-4 rounded-xl border border-zinc-800/50 text-center">
                  <span className="block text-2xl font-bold text-amber-400">{mockReport.allocation.alts}%</span>
                  <span className="text-[10px] text-zinc-600 uppercase font-bold tracking-tighter">ALTERNATIVE</span>
               </div>
               <div className="bg-zinc-900 p-4 rounded-xl border border-zinc-800/50 text-center">
                  <span className="block text-2xl font-bold text-emerald-400">{mockReport.allocation.cash}%</span>
                  <span className="text-[10px] text-zinc-600 uppercase font-bold tracking-tighter">CASH</span>
               </div>
            </div>
          </section>

          {/* Sub-MP Strategies */}
          <section>
            <h3 className="text-sm uppercase tracking-wider text-zinc-500 font-semibold mb-4 flex items-center gap-2">
               <Target className="h-4 w-4" /> SUB-STRATEGY DETAILS
            </h3>
            <div className="space-y-3">
              {mockReport.strategies.map((strategy, idx) => (
                <div key={idx} className="group relative bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800 hover:border-blue-500/50 rounded-lg p-3 transition-all cursor-default">
                  <div className="flex justify-between items-start mb-2">
                     <div className="flex items-center gap-2">
                        {strategy.type === 'aggressive' && <TrendingUp className="h-4 w-4 text-blue-400" />}
                        {strategy.type === 'defensive' && <Shield className="h-4 w-4 text-emerald-400" />}
                        {strategy.type === 'inflation' && <Zap className="h-4 w-4 text-amber-400" />}
                        <span className="text-sm font-semibold text-zinc-200">{strategy.title}</span>
                     </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    {strategy.tickers.slice(0, 2).map((t, i) => (
                      <div key={i} className="flex justify-between items-center bg-black/50 px-2 py-1.5 rounded text-xs">
                         <span className="text-zinc-400 font-medium">{t.symbol}</span>
                         <span className="text-zinc-600">{t.weight}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

      </div>
    </div>
  );
};