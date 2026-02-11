import React, { useState } from 'react';
import { Brain, PieChart, RefreshCw, Loader2, AlertCircle, TrendingUp, Landmark, Gem, CheckCircle2, FileText, Info } from 'lucide-react';
import { useOverview } from '../hooks/useMacroData';
import type { SubMPCategory, OverviewData } from '../hooks/useMacroData';

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

  const parseDate = (dateStr?: string): Date | null => {
    if (!dateStr) return null;
    const normalized = dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T');
    const direct = new Date(normalized);
    if (!Number.isNaN(direct.getTime())) return direct;

    const match = dateStr.match(
      /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/
    );
    if (!match) return null;
    const [, year, month, day, hour = '0', minute = '0', second = '0'] = match;
    const parsed = new Date(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second)
    );
    if (Number.isNaN(parsed.getTime())) return null;
    return parsed;
  };

  const isRecentUpdate = (dateStr?: string) => {
    const date = parseDate(dateStr);
    if (!date) return false;
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    return diffMs >= 0 && diffMs < 24 * 60 * 60 * 1000;
  };

  const getDurationText = (dateStr?: string, durationDays?: number) => {
    if (typeof durationDays === 'number' && Number.isFinite(durationDays) && durationDays > 0) {
      return `${Math.floor(durationDays)}d`;
    }

    const date = parseDate(dateStr);
    if (!date) return null;
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    if (!Number.isFinite(diffMs)) return null;

    if (diffMs < 0) return '1d';
    const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000));
    return `${Math.max(1, diffDays)}d`;
  };

  const handleRefresh = () => {
    refresh();
  };

  const formatLastUpdated = (dateStr: string) => {
    try {
      const date = parseDate(dateStr);
      if (!date) return 'Unknown';
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
  const mpDurationText = getDurationText(
    data.mp_info?.started_at || data.mp_info?.updated_at,
    data.mp_info?.duration_days
  );

  const SubMPCard: React.FC<{
    icon: React.ReactNode;
    title: string;
    category: SubMPCategory;
    colorClass: string;
    cardKey: string;
  }> = ({ icon, title, category, colorClass, cardKey }) => {
    const durationText = getDurationText(
      category.started_at || category.updated_at,
      category.duration_days
    );
    const recentBaseDate = category.started_at || category.updated_at;

    return (
      <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden shadow-sm">
      <div className={`px-4 py-3 border-b border-zinc-200 flex items-center gap-2 ${colorClass}`}>
        {icon}
        <span className="font-semibold text-sm flex-1 min-w-0 break-words">
          {title} Sub-MP: {category.sub_mp_id} - {category.sub_mp_name}
        </span>
        {durationText && (
          <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-zinc-500 rounded-full border border-zinc-200" title={`적용 기간: ${durationText}`}>
            +{durationText}
          </span>
        )}
        {isRecentUpdate(recentBaseDate) && (
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
  };

  return (
    <div className="space-y-6">
      {/* ========== 상단: MP 비율 + Sub-MP 세부종목 ========== */}
      <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-zinc-200 bg-gradient-to-r from-slate-50 to-white flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex w-full items-center gap-3 sm:w-auto">
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
          <div className="flex w-full items-center justify-between gap-3 sm:w-auto sm:justify-end">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="p-2 text-zinc-400 hover:text-zinc-700 hover:bg-slate-100 rounded-lg transition-all disabled:opacity-50"
              title="새로고침"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <div className="max-w-full px-3 py-1 bg-emerald-100 border border-emerald-200 rounded-full">
              <span className="text-xs font-semibold text-emerald-600 whitespace-nowrap">Regime: {regime}</span>
            </div>
          </div>
        </div>

        {/* MP Target Allocation */}
        <div className="p-6">
          <div className="mb-4 flex flex-wrap items-center gap-2">
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
            {mpDurationText && (
              <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-600 rounded-full border border-emerald-200" title={`적용 기간: ${mpDurationText}`}>
                +{mpDurationText}
              </span>
            )}
            {isRecentUpdate(data.mp_info?.started_at || data.mp_info?.updated_at) && (
              <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse" title="최근 24시간 내 업데이트됨"></span>
            )}
            {data.mp_info && (
              <button
                onClick={() => setShowMpDetails(!showMpDetails)}
                className="sm:ml-auto p-1.5 text-zinc-400 hover:text-zinc-700 bg-slate-100 hover:bg-slate-200 rounded transition-colors"
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
          <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
            <div className="bg-slate-50 p-3 sm:p-4 rounded-xl border border-zinc-200 text-center min-w-0">
              <span className="block text-2xl font-bold text-blue-600">{data.target_allocation.Stocks}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tight leading-tight break-words">STOCKS</span>
            </div>
            <div className="bg-slate-50 p-3 sm:p-4 rounded-xl border border-zinc-200 text-center min-w-0">
              <span className="block text-2xl font-bold text-indigo-600">{data.target_allocation.Bonds}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tight leading-tight break-words">BONDS</span>
            </div>
            <div className="bg-slate-50 p-3 sm:p-4 rounded-xl border border-zinc-200 text-center min-w-0">
              <span className="block text-2xl font-bold text-amber-600">{data.target_allocation.Alternatives}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tight leading-tight break-words">ALTERNATIVES</span>
            </div>
            <div className="bg-slate-50 p-3 sm:p-4 rounded-xl border border-zinc-200 text-center min-w-0">
              <span className="block text-2xl font-bold text-emerald-600">{data.target_allocation.Cash}%</span>
              <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-tight leading-tight break-words">CASH</span>
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
  const [showQualityInfo, setShowQualityInfo] = useState(false);
  const [showRiskAdvice, setShowRiskAdvice] = useState(false);
  if (!data) return null;
  const decisionMeta = data.decision_meta;
  const riskSummary = decisionMeta?.risk_summary;

  const formatConfidence = (value?: number) => {
    if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A';
    const normalized = value <= 1 ? value * 100 : value;
    return `${normalized.toFixed(0)}%`;
  };

  const formatRiskAction = (action?: string) => {
    if (!action) return 'N/A';
    const normalized = action.trim().toUpperCase();
    const labels: Record<string, string> = {
      HOLD_PREVIOUS: '기존 전략 유지',
      REDUCE_RISK: '위험 노출 축소',
      ALLOW_SWITCH: '전략 전환 허용',
      REBALANCE: '리밸런싱 권고'
    };
    return labels[normalized] || action;
  };

  const formatRiskLevel = (level?: string) => {
    if (!level) return 'N/A';
    const normalized = level.trim().toUpperCase();
    const labels: Record<string, string> = {
      CRITICAL: '매우 높음',
      HIGH: '높음',
      MEDIUM: '보통',
      LOW: '낮음',
      STABLE: '안정'
    };
    return labels[normalized] || level;
  };

  const toRatio = (value?: number) => {
    if (typeof value !== 'number' || Number.isNaN(value)) return undefined;
    if (value > 1) return value / 100;
    if (value < 0) return undefined;
    return value;
  };

  const confidenceRatio = toRatio(decisionMeta?.confidence);
  const thresholdRatio = toRatio(decisionMeta?.min_confidence_to_switch_mp);
  const isGateApplied = !!decisionMeta?.quality_gate_applied;

  const signalState: 'green' | 'yellow' | 'red' | 'gray' = (() => {
    if (confidenceRatio === undefined) return 'gray';
    if (isGateApplied) return 'yellow';
    if (thresholdRatio !== undefined && confidenceRatio < thresholdRatio) return 'red';
    return 'green';
  })();

  const signalLabel = (() => {
    if (signalState === 'green') return '정상';
    if (signalState === 'yellow') return '게이트 개입';
    if (signalState === 'red') return '주의';
    return '데이터 부족';
  })();

  const hasQualityMeta =
    !!decisionMeta &&
    (typeof decisionMeta.confidence === 'number' ||
      typeof decisionMeta.min_confidence_to_switch_mp === 'number' ||
      typeof decisionMeta.quality_gate_applied === 'boolean' ||
      !!decisionMeta.quality_gate_reason ||
      !!decisionMeta.quality_gate_risk_action);

  const hasRiskSummary =
    !!riskSummary &&
    (typeof riskSummary.divergence_detected === 'boolean' ||
      !!riskSummary.risk_level ||
      !!riskSummary.recommended_action ||
      typeof riskSummary.whipsaw_warning === 'boolean' ||
      (Array.isArray(riskSummary.constraint_violations) && riskSummary.constraint_violations.length > 0) ||
      !!riskSummary.adjustment_advice);

  const subMpReasoningByAsset = data.sub_mp_reasoning_by_asset || {};
  const subMpReasoningItems = [
    {
      key: 'stocks',
      label: '주식',
      subMpId: data.sub_mp?.stocks?.sub_mp_id,
      text: subMpReasoningByAsset.stocks,
      colorClass: 'text-blue-600 border-blue-200 bg-blue-50'
    },
    {
      key: 'bonds',
      label: '채권',
      subMpId: data.sub_mp?.bonds?.sub_mp_id,
      text: subMpReasoningByAsset.bonds,
      colorClass: 'text-indigo-600 border-indigo-200 bg-indigo-50'
    },
    {
      key: 'alternatives',
      label: '대체자산',
      subMpId: data.sub_mp?.alternatives?.sub_mp_id,
      text: subMpReasoningByAsset.alternatives,
      colorClass: 'text-amber-700 border-amber-200 bg-amber-50'
    },
    {
      key: 'cash',
      label: '현금',
      subMpId: data.sub_mp?.cash?.sub_mp_id,
      text: subMpReasoningByAsset.cash,
      colorClass: 'text-emerald-700 border-emerald-200 bg-emerald-50'
    }
  ];
  const hasAssetReasoning = subMpReasoningItems.some(item => !!item.text);

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="p-5 border-b border-zinc-200 bg-gradient-to-r from-slate-50 to-white flex items-center gap-3">
        <FileText className="h-5 w-5 text-purple-600" />
        <h2 className="text-lg font-bold text-zinc-900">AI 분석 상세</h2>
      </div>

      <div className="p-6 space-y-6 flex-1 overflow-y-auto">
        {/* 품질 게이트 / 신뢰도 */}
        <section>
          <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className={`h-3 w-3 rounded-full ${
                    signalState === 'green'
                      ? 'bg-emerald-500'
                      : signalState === 'yellow'
                        ? 'bg-amber-400'
                        : signalState === 'red'
                          ? 'bg-rose-500'
                          : 'bg-zinc-400'
                  }`}
                ></span>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-zinc-900">
                    분석 신뢰도: {formatConfidence(decisionMeta?.confidence)}
                  </p>
                  <span className="text-xs text-zinc-500">
                    (기준선: {formatConfidence(decisionMeta?.min_confidence_to_switch_mp)})
                  </span>
                </div>
              </div>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowQualityInfo(prev => !prev)}
                  className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-zinc-300 bg-white text-zinc-500 hover:bg-zinc-50"
                  title="품질 게이트 상세 정보"
                >
                  <Info className="h-3.5 w-3.5" />
                </button>
                {showQualityInfo && (
                  <div className="absolute right-0 top-8 z-20 w-72 bg-white border border-zinc-200 rounded-lg shadow-lg p-3 text-xs text-zinc-600 space-y-1">
                    <p><span className="font-semibold text-zinc-700">게이트 상태:</span> {signalLabel}</p>
                    <p><span className="font-semibold text-zinc-700">적용 여부:</span> {isGateApplied ? '적용됨' : '미적용'}</p>
                    <p><span className="font-semibold text-zinc-700">Risk Action:</span> {formatRiskAction(decisionMeta?.quality_gate_risk_action)}</p>
                    <p><span className="font-semibold text-zinc-700">Threshold:</span> {formatConfidence(decisionMeta?.min_confidence_to_switch_mp)}</p>
                    {decisionMeta?.quality_gate_reason && (
                      <p className="pt-1 border-t border-zinc-100 whitespace-pre-wrap">
                        {decisionMeta.quality_gate_reason}
                      </p>
                    )}
                    {!hasQualityMeta && (
                      <p className="pt-1 border-t border-zinc-100 text-zinc-500">품질 게이트 메타데이터가 없습니다.</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

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
        {(hasAssetReasoning || data.sub_mp_reasoning) && (
          <section className="pt-4 border-t border-zinc-200">
            <h3 className="text-sm uppercase tracking-wider text-purple-600 font-bold mb-3 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-purple-500"></div>
              Sub-MP 판단 근거
            </h3>
            {hasAssetReasoning ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {subMpReasoningItems.map(item => (
                  <div key={item.key} className="bg-slate-50 p-4 rounded-lg border border-zinc-100">
                    <div className="flex items-center justify-between mb-2">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${item.colorClass}`}>
                        {item.label}
                      </span>
                      {item.subMpId && (
                        <span className="text-[11px] text-zinc-500 font-medium">{item.subMpId}</span>
                      )}
                    </div>
                    <p className="text-sm text-zinc-600 leading-relaxed whitespace-pre-wrap">
                      {item.text || '해당 자산군 판단 근거가 없습니다.'}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-zinc-600 leading-relaxed bg-slate-50 p-4 rounded-lg border border-zinc-100 whitespace-pre-wrap max-h-32 overflow-y-auto">
                {data.sub_mp_reasoning}
              </div>
            )}
          </section>
        )}

        {/* 리스크 매니저 요약 */}
        <section className="pt-4 border-t border-zinc-200">
          <h3 className="text-sm uppercase tracking-wider text-rose-600 font-bold mb-2 flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-rose-500"></div>
            리스크 매니저 요약
          </h3>
          <p className="text-xs text-zinc-500 mb-3">
            이 섹션은 분석 자체의 위험이 아니라, 현재 거시경제/시장 국면에서 포트폴리오 운용 시 확인해야 할 리스크 신호입니다.
          </p>
          <div className="bg-slate-50 p-4 rounded-lg border border-zinc-100 space-y-3">
            {hasRiskSummary ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                  <div className="bg-white border border-zinc-200 rounded-md px-3 py-2">
                    <p className="text-[11px] text-zinc-500 font-semibold uppercase">시장 위험도</p>
                    <p className="text-zinc-800 font-semibold">{formatRiskLevel(riskSummary?.risk_level)}</p>
                  </div>
                  <div className="bg-white border border-zinc-200 rounded-md px-3 py-2">
                    <p className="text-[11px] text-zinc-500 font-semibold uppercase">권고 액션</p>
                    <p className="text-zinc-800 font-semibold">{formatRiskAction(riskSummary?.recommended_action)}</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {typeof riskSummary?.divergence_detected === 'boolean' && (
                    <span className={`px-2 py-0.5 rounded-full border font-semibold ${
                      riskSummary.divergence_detected
                        ? 'bg-amber-100 text-amber-700 border-amber-200'
                        : 'bg-emerald-100 text-emerald-700 border-emerald-200'
                    }`}>
                      거시 신호 괴리: {riskSummary.divergence_detected ? '감지됨' : '없음'}
                    </span>
                  )}
                  {typeof riskSummary?.whipsaw_warning === 'boolean' && (
                    <span className={`px-2 py-0.5 rounded-full border font-semibold ${
                      riskSummary.whipsaw_warning
                        ? 'bg-rose-100 text-rose-700 border-rose-200'
                        : 'bg-emerald-100 text-emerald-700 border-emerald-200'
                    }`}>
                      잦은 전환(Whipsaw): {riskSummary.whipsaw_warning ? '주의' : '안정'}
                    </span>
                  )}
                </div>
                {Array.isArray(riskSummary?.constraint_violations) && riskSummary.constraint_violations.length > 0 && (
                  <div className="text-sm bg-white border border-zinc-200 rounded-md p-3">
                    <p className="text-zinc-600 font-semibold mb-1">제약 조건 위반</p>
                    <ul className="list-disc pl-5 text-zinc-600 space-y-1">
                      {riskSummary.constraint_violations.map((item, idx) => (
                        <li key={`${item}-${idx}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {riskSummary?.adjustment_advice && (
                  <div className="text-sm text-zinc-600 bg-white border border-zinc-200 rounded-md p-3">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <p className="text-zinc-600 font-semibold">조정 가이드</p>
                      <button
                        type="button"
                        onClick={() => setShowRiskAdvice(prev => !prev)}
                        className="text-xs px-2 py-1 rounded border border-zinc-200 bg-zinc-50 text-zinc-600 hover:bg-zinc-100"
                      >
                        {showRiskAdvice ? '접기' : '더보기'}
                      </button>
                    </div>
                    {showRiskAdvice ? (
                      <p className="leading-relaxed whitespace-pre-wrap">{riskSummary.adjustment_advice}</p>
                    ) : (
                      <p className="text-xs text-zinc-500">조정 가이드는 더보기를 누르면 확인할 수 있습니다.</p>
                    )}
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-zinc-500">최근 분석에 저장된 리스크 매니저 요약 데이터가 없습니다.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
