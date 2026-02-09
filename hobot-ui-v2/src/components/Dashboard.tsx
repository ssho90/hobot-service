import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Network, Search, RefreshCw, Clock, ExternalLink, Newspaper } from 'lucide-react';
import { TickerTape } from './TickerTape';
import { AIMacroReport } from './AIMacroReport';
import { MacroIndicators } from './MacroIndicators';
import { BitcoinCycleChart } from './BitcoinCycleChart';
import { GeminiAnalyst } from './GeminiAnalyst';
import { AnalysisHistoryModal } from './AnalysisHistoryModal';
import { BriefingSummaryModal } from './BriefingSummaryModal';
import { EconomicNewsModal } from './EconomicNewsModal';
import { getTimeAgo } from '../utils/formatters';

const Dashboard: React.FC = () => {
  const activeTab = 'macro' as const;
  const [marketBriefing, setMarketBriefing] = useState<{
    briefing: string;
    summary_text?: string;
    created_at: string;
    headlines?: { title: string; link: string; published_at: string; source: string; }[];
  } | null>(null);
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isBriefingModalOpen, setIsBriefingModalOpen] = useState(false);
  const [isNewsModalOpen, setIsNewsModalOpen] = useState(false);

  const handleManualUpdate = async () => {
    if (isUpdating) return;
    if (!confirm("AI 경제 분석을 수동으로 시작하시겠습니까? (약 1분 소요)")) return;

    setIsUpdating(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/macro-trading/run-ai-analysis', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      if (response.ok && data.status === 'success') {
        alert("AI 분석이 완료되었습니다. 페이지를 새로고침하여 최신 데이터를 확인하세요.");
        window.location.reload();
      } else {
        throw new Error(data.detail || data.message || "분석 실패");
      }
    } catch (error) {
      console.error('Manual update failed:', error);
      alert(`업데이트 실패: ${error}`);
    } finally {
      setIsUpdating(false);
    }
  };

  useEffect(() => {
    const checkAdmin = async () => {
      const token = localStorage.getItem('token');
      if (!token) return;
      try {
        const response = await fetch('/api/auth/me', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          if (data.role === 'admin' || data.is_system_admin) {
            setIsAdmin(true);
          }
        }
      } catch (e) {
        console.error('Admin check failed:', e);
      }
    };
    checkAdmin();

    const fetchBriefing = async () => {
      try {
        const response = await fetch('/api/macro-trading/briefing');
        const data = await response.json();
        if (data.status === 'success' && data.briefing) {
          setMarketBriefing(data);
        }
      } catch (error) {
        console.error('Failed to fetch market briefing:', error);
      }
    };

    fetchBriefing();
  }, []);

  return (
    <>
      <TickerTape />
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        {/* Page Title & Action Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold text-zinc-900 tracking-tight">Macro Dashboard</h1>
            <p className="text-zinc-500 text-sm mt-1">Real-time economic monitoring and AI-driven asset allocation.</p>
          </div>

          <div className="flex items-center gap-3 self-start md:self-auto">
            <Link
              to="/ontology/macro"
              className="group hidden lg:flex items-center gap-3 rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-white px-4 py-2 shadow-sm transition-colors hover:from-blue-100 hover:to-white"
              title="Ontology 기반 Macro Graph로 이동"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white shadow-sm">
                <Network className="h-5 w-5" />
              </span>
              <span className="flex flex-col leading-tight">
                <span className="text-sm font-semibold text-zinc-900">Macro Ontology Graph</span>
                <span className="text-xs text-zinc-500">온톨로지로 근거 기반 거시경제 분석</span>
              </span>
              <ArrowRight className="h-4 w-4 text-zinc-400 transition-colors group-hover:text-zinc-700" />
            </Link>

            <Link
              to="/ontology/macro"
              className="group lg:hidden flex items-center gap-2 px-4 py-2 bg-white border border-blue-200 text-blue-700 text-sm font-semibold rounded-lg hover:bg-blue-50 transition-all shadow-sm"
              title="Macro Graph로 이동"
            >
              <Network className="h-4 w-4" />
              Macro Graph
              <ArrowRight className="h-4 w-4 text-blue-400 transition-colors group-hover:text-blue-600" />
            </Link>

            <button
              className="flex items-center gap-2 px-6 py-2 bg-white border border-zinc-200 text-zinc-600 text-sm font-medium rounded-lg hover:bg-zinc-50 hover:text-zinc-900 transition-all shadow-sm"
              onClick={() => setIsHistoryModalOpen(true)}
            >
              <Search className="h-4 w-4" />
              이전분석 검색
            </button>

            {isAdmin && (
              <button
                className="flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg border border-zinc-800 hover:bg-zinc-800 transition-all shadow-sm disabled:opacity-70 disabled:cursor-not-allowed"
                onClick={handleManualUpdate}
                disabled={isUpdating}
              >
                <RefreshCw className={`h-4 w-4 text-blue-400 ${isUpdating ? 'animate-spin' : ''}`} />
                {isUpdating ? '업데이트 중...' : '수동 업데이트'}
              </button>
            )}
          </div>
        </div>

        {activeTab === 'macro' ? (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <AIMacroReport>
              {/* 뉴스 섹션 - 신문 지면 스타일 (Newspaper Layout) */}
              <div className="bg-[#fcfbf9] rounded-xl border border-stone-200 shadow-sm overflow-hidden h-full flex flex-col font-serif">
                {/* Newspaper Masthead (제호) */}
                <div className="bg-[#f4f1ea] border-b-2 border-stone-800 p-4 flex items-center justify-between relative">
                  <div className="flex flex-col z-10">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[9px] font-bold tracking-[0.2em] text-stone-500 uppercase">Est. 2026</span>
                      <div className="h-px w-6 bg-stone-400"></div>
                      <span className="text-[9px] font-bold tracking-[0.2em] text-stone-500 uppercase">Vol. 1</span>
                    </div>
                    <div className="flex flex-col w-full">
                      <h3 className="text-3xl font-black text-stone-900 tracking-tight uppercase leading-none mb-1">
                        The Macro Daily
                      </h3>
                      <div className="flex items-center justify-between border-t border-b border-stone-700 py-1 mt-1">
                        <span className="text-xs font-bold text-stone-700 uppercase tracking-wider">
                          {marketBriefing
                            ? new Date(marketBriefing.created_at).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
                            : new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
                          }
                        </span>
                        <span className="text-[10px] text-stone-500 font-medium italic">Global Economic Intelligence</span>
                      </div>
                    </div>
                  </div>
                  <Newspaper className="h-12 w-12 text-stone-300 absolute -bottom-2 -right-2 rotate-12 opacity-50" />
                </div>

                {/* Content Area */}
                <div className="p-0 flex-1 overflow-y-auto bg-[url('https://www.transparenttextures.com/patterns/cream-paper.png')]">

                  {/* 1. Market Briefing (Summary) */}
                  <div className="p-5 border-b border-stone-300">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="bg-stone-900 text-[#fcfbf9] text-[9px] px-1.5 py-px font-bold uppercase tracking-wider">Market Briefing</span>
                    </div>
                    <div className="flex justify-between items-end mb-2">
                      <h4 className="text-sm font-bold text-stone-900 leading-tight">
                        Global Market Overview
                      </h4>
                      {marketBriefing?.summary_text && (
                        <button
                          onClick={() => setIsBriefingModalOpen(true)}
                          className="text-[10px] font-bold text-blue-600 hover:text-blue-800 underline decoration-blue-200 underline-offset-2 transition-colors cursor-pointer"
                        >
                          Read Detailed Analysis →
                        </button>
                      )}
                    </div>
                    <p className="text-stone-800 leading-relaxed text-xs text-justify font-serif whitespace-pre-line">
                      {marketBriefing ? marketBriefing.briefing : "최신 시장 브리핑을 불러오고 있습니다. 잠시만 기다려주세요..."}
                    </p>
                  </div>

                  {/* 2. Headlines (List) */}
                  <div className="p-5 bg-[#f9f7f2]">
                    <div className="flex items-center justify-between gap-2 mb-4 border-b-2 border-stone-800 pb-1.5">
                      <h4 className="text-xs font-black text-stone-900 uppercase tracking-widest">Headlines</h4>
                      <div className="flex gap-0.5">
                        <div className="w-0.5 h-0.5 rounded-full bg-stone-800"></div>
                        <div className="w-0.5 h-0.5 rounded-full bg-stone-800"></div>
                        <div className="w-0.5 h-0.5 rounded-full bg-stone-800"></div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      {marketBriefing?.headlines?.map((item, index) => (
                        <div key={index} className="group cursor-pointer" onClick={() => window.open(item.link, '_blank')}>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-[8px] font-bold text-blue-800 border border-blue-800/30 bg-blue-50 px-1 py-px uppercase tracking-wider">
                                {item.source}
                              </span>
                            </div>
                            <h5 className="text-xs font-bold text-stone-900 leading-snug group-hover:underline decoration-stone-400 underline-offset-4 mb-1.5">
                              {item.title}
                            </h5>
                            <div className="flex items-center gap-2 text-[9px] text-stone-500 font-medium italic">
                              <Clock className="h-2.5 w-2.5" /> {getTimeAgo(item.published_at)}
                            </div>
                          </div>
                          {index < (marketBriefing.headlines?.length || 0) - 1 && (
                            <div className="border-b border-stone-300 border-dashed mt-4"></div>
                          )}
                        </div>
                      ))}
                      {(!marketBriefing?.headlines || marketBriefing.headlines.length === 0) && (
                        <div className="text-center py-4 text-stone-400 text-xs italic">
                          No headlines available.
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Footer */}
                <div className="p-2 bg-stone-100 border-t border-stone-200 text-center">
                  <button
                    onClick={() => setIsNewsModalOpen(true)}
                    className="text-[9px] font-bold text-stone-500 hover:text-stone-900 uppercase tracking-[0.2em] flex items-center justify-center gap-1.5 mx-auto transition-colors w-full"
                  >
                    View All Articles <ExternalLink className="h-2.5 w-2.5" />
                  </button>
                </div>
              </div>
            </AIMacroReport>

            {/* MacroIndicators - 전체 너비 */}
            <MacroIndicators />

            {/* Bitcoin Cycle - 하단 섹션 */}
            <BitcoinCycleChart />
          </div>
        ) : (
          <div className="h-[700px] animate-in fade-in zoom-in-95 duration-300">
            <GeminiAnalyst />
          </div>
        )}
      </main>
      <AnalysisHistoryModal isOpen={isHistoryModalOpen} onClose={() => setIsHistoryModalOpen(false)} />
      <BriefingSummaryModal
        isOpen={isBriefingModalOpen}
        onClose={() => setIsBriefingModalOpen(false)}
        summary={marketBriefing?.summary_text || ''}
        createdAt={marketBriefing?.created_at || ''}
      />
      <EconomicNewsModal isOpen={isNewsModalOpen} onClose={() => setIsNewsModalOpen(false)} />

      <footer className="border-t border-zinc-200 bg-white py-8 mt-12">
        <div className="max-w-7xl mx-auto px-4 text-center text-sm text-zinc-500">
          StockOverflow Macro Intelligence • Powered by Gemini AI
        </div>
      </footer>
    </>
  );
};

export default Dashboard;
