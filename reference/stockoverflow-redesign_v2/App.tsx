import React, { useState } from 'react';
import { Header } from './components/Header';
import { TickerTape } from './components/TickerTape';
import { AIMacroReport } from './components/AIMacroReport';
import { MacroIndicators } from './components/MacroIndicators';
import { GeminiAnalyst } from './components/GeminiAnalyst';
import { Newspaper, LayoutDashboard, MessageSquare, Search, RefreshCw, Sparkles, Clock, ExternalLink } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'macro' | 'chat'>('macro');

  return (
    <div className="min-h-screen flex flex-col bg-black">
      <Header />
      <TickerTape />

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        
        {/* Page Title & Action Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Macro Dashboard</h1>
            <p className="text-zinc-400 text-sm mt-1">Real-time economic monitoring and AI-driven asset allocation.</p>
          </div>
          
          <div className="flex items-center gap-3 self-start md:self-auto">
             {/* 이전분석 검색 (Search Previous Analysis) - Now a Button */}
             <button 
               className="flex items-center gap-2 px-6 py-2 bg-zinc-950 border border-zinc-800 text-zinc-400 text-sm font-medium rounded-lg hover:bg-zinc-900 hover:text-zinc-200 transition-all shadow-sm"
               onClick={() => console.log('Search Analysis...')}
             >
               <Search className="h-4 w-4" />
               이전분석 검색
             </button>
             
             {/* 수동 업데이트 (Manual Update) */}
             <button 
               className="flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg border border-zinc-800 hover:bg-zinc-800 transition-all shadow-sm"
               onClick={() => console.log('Updating...')}
             >
               <RefreshCw className="h-4 w-4 text-blue-400" />
               수동 업데이트
             </button>
          </div>
        </div>

        {activeTab === 'macro' ? (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* 1. Hero: AI Analysis Report */}
            <AIMacroReport />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* 2. Left Col: Macro Indicators */}
              <div className="lg:col-span-2">
                <MacroIndicators />
              </div>

              {/* 3. Right Col: News Section (Replacing Market Movers) */}
              <div className="space-y-6">
                 {/* 최근 뉴스 요약 (Recent News Summary) */}
                 <div className="bg-zinc-900/40 rounded-2xl border border-zinc-800 p-6 shadow-xl backdrop-blur-sm">
                    <h3 className="text-sm font-bold text-blue-400 mb-4 flex items-center gap-2 uppercase tracking-wider">
                       <Sparkles className="h-4 w-4" /> 최근 뉴스 요약
                    </h3>
                    <div className="bg-black/60 rounded-xl p-4 border border-zinc-800">
                      <p className="text-sm text-zinc-300 leading-relaxed">
                        오늘의 시장은 연준의 금리 동결 시그널과 기술주 중심의 강력한 매수세가 맞물리며 전반적인 상승세를 보이고 있습니다. 특히 반도체 섹터는 AI 수요 지속 전망에 따라 신고가를 경신 중이며, 유가 변동성은 지정학적 리스크 완화로 다소 축소되었습니다. 투자자들은 내일 발표될 고용 지표를 앞두고 관망세를 유지하면서도 고성장주 위주의 포트폴리오 재편에 집중하는 모습입니다.
                      </p>
                    </div>
                 </div>
                 
                 {/* 최근 뉴스 목록 (Recent News List) */}
                 <div className="bg-zinc-900/40 rounded-2xl border border-zinc-800 p-6 shadow-xl backdrop-blur-sm">
                    <h3 className="text-sm font-bold text-zinc-200 mb-5 flex items-center gap-2 uppercase tracking-wider">
                       <Newspaper className="h-4 w-4 text-blue-400" /> 최근 뉴스 목록
                    </h3>
                    <div className="space-y-5">
                       <div className="group cursor-pointer">
                          <div className="flex items-center gap-2 mb-1.5">
                             <span className="text-[10px] font-bold text-blue-400 bg-blue-900/30 px-1.5 py-0.5 rounded uppercase">Breaking</span>
                             <span className="text-[11px] text-zinc-500 flex items-center gap-1">
                                <Clock className="h-3 w-3" /> 1h ago
                             </span>
                          </div>
                          <h4 className="text-[13px] text-zinc-300 font-semibold group-hover:text-blue-400 transition-colors line-clamp-2">US PPI Rises More Than Expected, Signaling Sticky Inflation for Late 2024</h4>
                          <div className="flex items-center gap-1 mt-2 text-[11px] text-zinc-500 font-medium">
                            Bloomberg Intelligence <ExternalLink className="h-2.5 w-2.5" />
                          </div>
                       </div>
                       
                       <div className="border-t border-zinc-800/50 pt-5 group cursor-pointer">
                          <div className="flex items-center gap-2 mb-1.5">
                             <span className="text-[10px] font-bold text-emerald-400 bg-emerald-900/30 px-1.5 py-0.5 rounded uppercase">Market</span>
                             <span className="text-[11px] text-zinc-500 flex items-center gap-1">
                                <Clock className="h-3 w-3" /> 3h ago
                             </span>
                          </div>
                          <h4 className="text-[13px] text-zinc-300 font-semibold group-hover:text-blue-400 transition-colors line-clamp-2">ECB Holds Rates Steady as Lagarde Warns on Eurozone Growth Outlook</h4>
                          <div className="flex items-center gap-1 mt-2 text-[11px] text-zinc-500 font-medium">
                            Reuters Financial <ExternalLink className="h-2.5 w-2.5" />
                          </div>
                       </div>
                       
                       <div className="border-t border-zinc-800/50 pt-5 group cursor-pointer">
                          <div className="flex items-center gap-2 mb-1.5">
                             <span className="text-[10px] font-bold text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded uppercase">Energy</span>
                             <span className="text-[11px] text-zinc-500 flex items-center gap-1">
                                <Clock className="h-3 w-3" /> 5h ago
                             </span>
                          </div>
                          <h4 className="text-[13px] text-zinc-300 font-semibold group-hover:text-blue-400 transition-colors line-clamp-2">Oil Prices Surge Amid Middle East Tensions and Supply Constraints</h4>
                          <div className="flex items-center gap-1 mt-2 text-[11px] text-zinc-500 font-medium">
                            WSJ Markets <ExternalLink className="h-2.5 w-2.5" />
                          </div>
                       </div>

                       <div className="border-t border-zinc-800/50 pt-5 group cursor-pointer">
                          <div className="flex items-center gap-2 mb-1.5">
                             <span className="text-[10px] font-bold text-purple-400 bg-purple-900/30 px-1.5 py-0.5 rounded uppercase">Tech</span>
                             <span className="text-[11px] text-zinc-500 flex items-center gap-1">
                                <Clock className="h-3 w-3" /> 8h ago
                             </span>
                          </div>
                          <h4 className="text-[13px] text-zinc-300 font-semibold group-hover:text-blue-400 transition-colors line-clamp-2">NVIDIA Blackwell Chips See Unprecedented Demand from Cloud Providers</h4>
                          <div className="flex items-center gap-1 mt-2 text-[11px] text-zinc-500 font-medium">
                            TechCrunch <ExternalLink className="h-2.5 w-2.5" />
                          </div>
                       </div>
                    </div>
                    
                    <button className="w-full mt-6 py-2 px-4 bg-zinc-950/50 hover:bg-zinc-900 border border-zinc-800 text-zinc-500 hover:text-zinc-200 text-xs font-semibold rounded-lg transition-all">
                      뉴스 더보기
                    </button>
                 </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="h-[700px] animate-in fade-in zoom-in-95 duration-300">
             <GeminiAnalyst />
          </div>
        )}

      </main>

      <footer className="border-t border-zinc-900 bg-black py-8 mt-12">
        <div className="max-w-7xl mx-auto px-4 text-center text-sm text-zinc-600">
          StockOverflow Macro Intelligence • Powered by Gemini AI
        </div>
      </footer>
    </div>
  );
};