import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Header } from './components/Header';
import { TickerTape } from './components/TickerTape';
import { AIMacroReport } from './components/AIMacroReport';
import { MacroIndicators } from './components/MacroIndicators';
import { GeminiAnalyst } from './components/GeminiAnalyst';
import { AboutPage } from './components/AboutPage';
import { TradingDashboard } from './components/TradingDashboard';
import { AdminUserManagement } from './components/admin/AdminUserManagement';
import { AdminLogManagement } from './components/admin/AdminLogManagement';
import { AdminLLMMonitoring } from './components/admin/AdminLLMMonitoring';
import { AdminRebalancing } from './components/admin/AdminRebalancing';
import { AdminFileUpload } from './components/admin/AdminFileUpload';
import { AnalysisHistoryModal } from './components/AnalysisHistoryModal';
import { BriefingSummaryModal } from './components/BriefingSummaryModal';
import { EconomicNewsModal } from './components/EconomicNewsModal';

import { Search, RefreshCw, Clock, ExternalLink, Newspaper } from 'lucide-react';


// Register Page Component
const RegisterPage: React.FC = () => {
  const { register } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('비밀번호가 일치하지 않습니다.');
      return;
    }
    setLoading(true);
    setError('');

    const result = await register(username, password);
    if (result.success) {
      setSuccess(result.message || '회원가입이 완료되었습니다.');
    } else {
      setError(result.error || '회원가입에 실패했습니다.');
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <div className="bg-zinc-900/40 rounded-2xl border border-zinc-800 p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold text-white mb-6 text-center">회원가입</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-zinc-400 mb-2">아이디</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              placeholder="사용자 이름"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-2">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              placeholder="비밀번호"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-2">비밀번호 확인</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              placeholder="비밀번호 확인"
            />
          </div>
          {error && <p className="text-rose-400 text-sm">{error}</p>}
          {success && <p className="text-emerald-400 text-sm">{success}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg transition-all disabled:opacity-50"
          >
            {loading ? '가입 중...' : '회원가입'}
          </button>
        </form>
        <p className="text-zinc-500 text-sm text-center mt-4">
          이미 계정이 있으신가요? <Link to="/login" className="text-blue-400 hover:underline">로그인</Link>
        </p>
      </div>
    </div>
  );
};



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

  const getTimeAgo = (dateString?: string) => {
    if (!dateString) return '';
    const now = new Date();
    const date = new Date(dateString);
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffInSeconds < 60) return `${diffInSeconds}s ago`;
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
    return `${Math.floor(diffInSeconds / 86400)}d ago`;
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

// Main App Component
const AppLayout: React.FC = () => {
  const location = useLocation();

  // Don't show header on register page
  const showHeader = !['/register'].includes(location.pathname);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {showHeader && <Header />}
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/trading" element={<TradingDashboard />} />
        <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
        <Route path="/admin/users" element={<AdminUserManagement />} />
        <Route path="/admin/logs" element={<AdminLogManagement />} />
        <Route path="/admin/llm" element={<AdminLLMMonitoring />} />
        <Route path="/admin/rebalancing" element={<AdminRebalancing />} />
        <Route path="/admin/files" element={<AdminFileUpload />} />
        <Route path="/" element={<Dashboard />} />
      </Routes>
    </div>
  );
};


// Main App Component
function App() {
  return (
    <AuthProvider>
      <Router>
        <AppLayout />
      </Router>
    </AuthProvider>
  );
}

export default App;
