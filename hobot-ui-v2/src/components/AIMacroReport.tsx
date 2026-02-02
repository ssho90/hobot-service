import React, { useState } from 'react';
import { Brain, PieChart, RefreshCw, Loader2, AlertCircle, TrendingUp, Landmark, Gem, CheckCircle2, FileText, Info } from 'lucide-react';
import { useOverview } from '../hooks/useMacroData';
import type { SubMPCategory } from '../hooks/useMacroData';

const mpToRegime: Record<string, string> = {
  'MP-1': 'Expansion (Goldilocks)',
  'MP-2': 'Reflation',
  'MP-3': 'Stagflation',
  'MP-4': 'Deflation',
  'MP-5': 'Recovery'
};

export const AIMacroReport: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const { data, loading, error, refreshing, refresh } = useOverview();
  const [showMpDetails, setShowMpDetails] = useState(false);
  const [showSubMpDetails, setShowSubMpDetails] = useState<Record<string, boolean>>({});

  const toggleSubMpDetails = (key: string) => {
    setShowSubMpDetails(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const isRecentUpdate = (dateStr?: string) => {
    if (!dateStr) return false;
    const date = new Date(dateStr);
    const now = new Date();
    return (now.getTime() - date.getTime()) < 24 * 60 * 60 * 1000;
  };

  const getDurationText = (dateStr?: string) => {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000));
    if (diffDays < 1) {
      const diffHours = Math.floor(diffMs / (60 * 60 * 1000));
      return `${diffHours}h`;
    }
    return `${diffDays}d`;
  };

  const handleRefresh = () => {
    refresh();
  };

  const formatLastUpdated = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}분 전`;
      if (diffMins < 1440) return `${Math.floor(diffMins / 60)}시간 전`;
      return date.toLocaleDateString('ko-KR');
    } catch {
      return 'Unknown';
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg p-12 flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg p-8">
        <div className="flex items-center justify-center gap-3 text-red-500">
          <AlertCircle className="h-6 w-6" />
          <span>{error || '데이터를 불러올 수 없습니다.'}</span>
          <button onClick={handleRefresh} className="ml-4 px-3 py-1 bg-slate-100 rounded-lg text-sm hover:bg-slate-200">
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  const regime = mpToRegime[data.mp_id] || data.mp_id;

  const SubMPCard: React.FC<{
    icon: React.ReactNode;
    title: string;
    category: SubMPCategory;
    colorClass: string;
    cardKey: string;
  }> = ({ icon, title, category, colorClass, cardKey }) => (
    <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden shadow-sm">
      <div className={`px-4 py-3 border-b border-zinc-200 flex items-center gap-2 ${colorClass}`}>
        {icon}
        <span className="font-semibold text-sm flex-1">
          {title} Sub-MP: {category.sub_mp_id} - {category.sub_mp_name}
        </span>
        {getDurationText(category.started_at || category.updated_at) && (
          <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-zinc-500 rounded-full border border-zinc-200" title={`적용 기간: ${getDurationText(category.started_at || category.updated_at)}`}>
            +{getDurationText(category.started_at || category.updated_at)}
          </span>
        )}
        {isRecentUpdate(category.started_at || category.updated_at) && (
          <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse" title="최근 24시간 내 업데이트됨"></span>
        )}
        {(category.sub_mp_description || category.updated_at) && (
          <button
            onClick={() => toggleSubMpDetails(cardKey)}
            className="p-1 text-zinc-400 hover:text-zinc-700 transition-colors"
            title="Sub-MP 설명 보기"
          >
            <Info className="w-4 h-4" />
          </button>
        )}
      </div>
      {showSubMpDetails[cardKey] && (category.sub_mp_description || category.updated_at) && (
        <div className="p-3 bg-slate-50 border-b border-zinc-100">
          {category.sub_mp_description && <p className="text-xs text-zinc-600 mb-2 leading-relaxed">{category.sub_mp_description}</p>}
          {category.updated_at && (
            <p className="text-[10px] text-zinc-400 flex items-center gap-2">
              Updated: {category.updated_at}
              {isRecentUpdate(category.updated_at) && (
                <span className="px-1 py-0.5 bg-blue-100 text-blue-600 text-[9px] font-bold rounded border border-blue-200">NEW</span>
              )}
            </p>
          )}
        </div>
      )}
      <div className="p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50">
              <th className="text-left px-4 py-2 text-zinc-500 font-medium">종목명</th>
              <th className="text-right px-4 py-2 text-zinc-500 font-medium w-20">비중</th>
            </tr>
          </thead>
          <tbody>
            {category.etf_details.map((etf, idx) => (
              <tr key={idx} className="border-t border-zinc-100 hover:bg-slate-50">
                <td className="px-4 py-2.5 text-zinc-700">{etf.name}</td>
                <td className={`px-4 py-2.5 text-right font-semibold ${colorClass}`}>
                  {(etf.weight * 100).toFixed(0)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* ========== 상단: MP 비율 + Sub-MP 세부종목 ========== */}
      <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-zinc-200 bg-gradient-to-r from-slate-50 to-white flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="bg-blue-100 p-2 rounded-xl border border-blue-200">
              <Brain className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-zinc-900 tracking-tight">AI Economic Analysis</h2>
              <p className="text-sm text-zinc-500">
                Updated: {formatLastUpdated(data.decision_date)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="p-2 text-zinc-400 hover:text-zinc-700 hover:bg-slate-100 rounded-lg transition-all disabled:opacity-50"
              title="새로고침"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <div className="px-3 py-1 bg-emerald-100 border border-emerald-200 rounded-full">
              <span className="text-xs font-semibold text-emerald-600">Regime: {regime}</span>
            </div>
          </div>
        </div>

        {/* MP Target Allocation */}
        <div className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <PieChart className="h-5 w-5 text-zinc-500" />
            <h3 className="text-sm uppercase tracking-wider text-zinc-500 font-semibold">
              MP Target Allocation
            </h3>
            <span className="ml-2 px-2 py-0.5 text-xs bg-blue-100 text-blue-600 rounded">{data.mp_id}</span>
            {data.mp_info?.name && (
              <span className="px-2 py-0.5 text-xs bg-slate-100 text-zinc-600 rounded border border-zinc-200">
                {data.mp_info.name}
              </span>
            )}
            {getDurationText(data.mp_info?.started_at || data.mp_info?.updated_at) && (
              <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-600 rounded-full border border-emerald-200" title={`적용 기간: ${getDurationText(data.mp_info?.started_at || data.mp_info?.updated_at)}`}>
                +{getDurationText(data.mp_info?.started_at || data.mp_info?.updated_at)}
              </span>
            )}
            {isRecentUpdate(data.mp_info?.started_at || data.mp_info?.updated_at) && (
              <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse" title="최근 24시간 내 업데이트됨"></span>
            )}
            {data.mp_info && (
              <button
                onClick={() => setShowMpDetails(!showMpDetails)}
                className="ml-auto p-1.5 text-zinc-400 hover:text-zinc-700 bg-slate-100 hover:bg-slate-200 rounded transition-colors"
                title="MP 설명 보기"
              >
                <Info className="w-4 h-4" />
              </button>
            )}
          </div>
          {showMpDetails && data.mp_info && (
            <div className="mb-4 bg-slate-50 p-4 rounded-lg border border-zinc-200 animate-in fade-in slide-in-from-top-2 duration-200">
              <div className="mb-2">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-1">Description</h4>
                <p className="text-sm text-zinc-700 leading-relaxed">{data.mp_info.description}</p>
              </div>
              {data.mp_info.updated_at && (
                <div>
                  <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-1">Last Updated</h4>
                  <p className="text-xs text-zinc-500 flex items-center gap-2">
                    {data.mp_info.updated_at}
                    {isRecentUpdate(data.mp_info.updated_at) && (
                      <span className="px-1.5 py-0.5 bg-blue-100 text-blue-600 text-[10px] font-bold rounded border border-blue-200">NEW</span>
                    )}
                  </p>
                </div>
              )}
            </div>
          )}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-slate-50 p-4 rounded-xl border border-zinc-200 text-center">
              <span className="block text-2xl font-bold text-blue-600">{data.target_allocation.Stocks}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tighter">STOCKS</span>
            </div>
            <div className="bg-slate-50 p-4 rounded-xl border border-zinc-200 text-center">
              <span className="block text-2xl font-bold text-indigo-600">{data.target_allocation.Bonds}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tighter">BONDS</span>
            </div>
            <div className="bg-slate-50 p-4 rounded-xl border border-zinc-200 text-center">
              <span className="block text-2xl font-bold text-amber-600">{data.target_allocation.Alternatives}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tighter">ALTERNATIVES</span>
            </div>
            <div className="bg-slate-50 p-4 rounded-xl border border-zinc-200 text-center">
              <span className="block text-2xl font-bold text-emerald-600">{data.target_allocation.Cash}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tighter">CASH</span>
            </div>
          </div>
        </div>

        {/* Sub-MP 세부종목 */}
        {data.sub_mp && (
          <div className="px-6 pb-6">
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle2 className="h-5 w-5 text-zinc-500" />
              <h3 className="text-sm uppercase tracking-wider text-zinc-500 font-semibold">
                Sub-MP 세부종목
              </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {data.sub_mp.stocks && (
                <SubMPCard
                  icon={<TrendingUp className="h-4 w-4" />}
                  title="주식"
                  category={data.sub_mp.stocks}
                  colorClass="text-blue-400"
                  cardKey="stocks"
                />
              )}
              {data.sub_mp.bonds && (
                <SubMPCard
                  icon={<Landmark className="h-4 w-4" />}
                  title="채권"
                  category={data.sub_mp.bonds}
                  colorClass="text-indigo-400"
                  cardKey="bonds"
                />
              )}
              {data.sub_mp.alternatives && (
                <SubMPCard
                  icon={<Gem className="h-4 w-4" />}
                  title="대체자산"
                  category={data.sub_mp.alternatives}
                  colorClass="text-amber-400"
                  cardKey="alternatives"
                />
              )}
            </div>
          </div>
        )}
      </div>

      {/* ========== 하단: AI 분석 상세 + 뉴스 (3:1 그리드 레이아웃) ========== */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* AI 분석 상세 (3/4 너비) */}
        <div className="lg:col-span-3">
          <AIAnalysisDetails data={data} />
        </div>

        {/* 뉴스 섹션 (1/4 너비) */}
        {children && (
          <div className="space-y-6 flex flex-col lg:col-span-1">
            {children}
          </div>
        )}
      </div>
    </div>
  );
};

// AI 분석 상세 컴포넌트 (별도 export)
export const AIAnalysisDetails: React.FC<{ data: OverviewData | null }> = ({ data }) => {
  if (!data) return null;

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="p-5 border-b border-zinc-200 bg-gradient-to-r from-slate-50 to-white flex items-center gap-3">
        <FileText className="h-5 w-5 text-purple-600" />
        <h2 className="text-lg font-bold text-zinc-900">AI 분석 상세</h2>
      </div>

      <div className="p-6 space-y-6 flex-1 overflow-y-auto">
        {/* MP 분석 요약 */}
        <section>
          <h3 className="text-sm uppercase tracking-wider text-blue-600 font-bold mb-3 flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
            MP 분석 요약
          </h3>
          <div className="space-y-4">
            <div>
              <h4 className="text-xs text-zinc-500 uppercase font-semibold mb-2">분석 요약</h4>
              <p className="text-zinc-700 leading-relaxed text-sm bg-slate-50 p-4 rounded-lg border border-zinc-200">
                {data.analysis_summary}
              </p>
            </div>
            <div>
              <h4 className="text-xs text-zinc-500 uppercase font-semibold mb-2">판단 근거</h4>
              <div className="text-sm text-zinc-600 leading-relaxed bg-slate-50 p-4 rounded-lg border border-zinc-100 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {data.reasoning}
              </div>
            </div>
          </div>
        </section>

        {/* Sub-MP 판단 근거 */}
        {data.sub_mp_reasoning && (
          <section className="pt-4 border-t border-zinc-200">
            <h3 className="text-sm uppercase tracking-wider text-purple-600 font-bold mb-3 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-purple-500"></div>
              Sub-MP 판단 근거
            </h3>
            <div className="text-sm text-zinc-600 leading-relaxed bg-slate-50 p-4 rounded-lg border border-zinc-100 whitespace-pre-wrap max-h-32 overflow-y-auto">
              {data.sub_mp_reasoning}
            </div>
          </section>
        )}
      </div>
    </div>
  );
};
