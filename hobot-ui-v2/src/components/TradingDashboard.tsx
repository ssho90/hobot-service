import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useBalance, useRebalancing } from '../hooks/useMacroData';
import { formatCurrency, formatPercent, safeNumber } from '../utils/formatters';
import { Wallet, TrendingUp, TrendingDown, RefreshCw, PieChart, BarChart3, AlertCircle, Loader2 } from 'lucide-react';
import { TotalAssetTrendChart } from './TotalAssetTrendChart';

// Color palette for charts
const COLORS = ['#3b82f6', '#10b981', '#ef4444', '#8b5cf6', '#f59e0b', '#06b6d4'];

const StackedBar = ({ items, total = 100 }: { items: { label: string; value: number; color?: string }[]; total?: number }) => {
    return (
        <div className="h-8 flex rounded-md overflow-hidden bg-slate-200 w-full relative">
            {items.map((item, idx) => {
                const width = Math.max((item.value / total) * 100, 0);
                if (width === 0) return null;
                return (
                    <div
                        key={idx}
                        style={{ width: `${width}%`, backgroundColor: item.color || COLORS[idx % COLORS.length] }}
                        className="h-full flex items-center justify-center relative group transition-all duration-300 hover:brightness-110"
                        title={`${item.label}: ${item.value.toFixed(1)}%`}
                    >
                        {width > 8 && (
                            <span className="text-[10px] font-bold text-white shadow-sm whitespace-nowrap overflow-hidden px-1">
                                {item.label} {item.value.toFixed(1)}%
                            </span>
                        )}
                    </div>
                );
            })}
        </div>
    );
};

export const TradingDashboard: React.FC = () => {
    const { isAuthenticated, loading: authLoading } = useAuth();
    const [activeTab, setActiveTab] = useState<'account' | 'rebalancing'>('account');
    const { data: balance, loading: balanceLoading, error: balanceError, refreshing: balanceRefreshing, refresh: refreshBalance } = useBalance();
    const { data: rebalancing, loading: rebalancingLoading, error: rebalancingError, refreshing: rebalancingRefreshing, refresh: refreshRebalancing } = useRebalancing({
        enabled: activeTab === 'rebalancing'
    });

    // UI Toggle States
    const [showMpDetails, setShowMpDetails] = useState(false);
    const [showSubMpDetails, setShowSubMpDetails] = useState<Record<string, boolean>>({});

    const toggleSubMpDetails = (assetClass: string) => {
        setShowSubMpDetails(prev => ({ ...prev, [assetClass]: !prev[assetClass] }));
    };
    const loading = authLoading || (activeTab === 'account' ? balanceLoading : rebalancingLoading);
    const error = activeTab === 'account' ? balanceError : rebalancingError;
    const refreshing = activeTab === 'account' ? balanceRefreshing : rebalancingRefreshing;

    const handleRefresh = () => {
        if (!isAuthenticated || refreshing) return;
        if (activeTab === 'rebalancing') {
            refreshRebalancing();
        } else {
            refreshBalance();
        }
    };

    const isRecentUpdate = (dateStr?: string) => {
        if (!dateStr) return false;
        const date = new Date(dateStr);
        const now = new Date();
        return (now.getTime() - date.getTime()) < 24 * 60 * 60 * 1000;
    };

    // MP 적용 경과일 계산
    const getDaysElapsed = (dateStr?: string): number | null => {
        if (!dateStr) return null;
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        return Math.floor(diffMs / (1000 * 60 * 60 * 24));
    };

    // 경과 시간 포맷팅 (예: "3일", "2주", "1개월")
    const formatElapsedTime = (days: number | null): string => {
        if (days === null) return '-';
        if (days === 0) return '오늘';
        if (days < 7) return `${days}일`;
        if (days < 30) return `${Math.floor(days / 7)}주`;
        if (days < 365) return `${Math.floor(days / 30)}개월`;
        return `${Math.floor(days / 365)}년`;
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center">
                <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
            </div>
        );
    }

    if (!isAuthenticated) {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center">
                <div className="text-center">
                    <AlertCircle className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
                    <h2 className="text-xl font-bold text-zinc-900 mb-2">로그인이 필요합니다</h2>
                    <p className="text-zinc-500">Trading 기능을 사용하려면 먼저 로그인해주세요.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8">
            <div className="max-w-7xl mx-auto">
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h1 className="text-3xl font-bold text-zinc-900">Trading Dashboard</h1>
                        <p className="text-zinc-500 mt-1">실시간 자산 현황 및 리밸런싱 관리</p>
                    </div>
                    <button
                        onClick={handleRefresh}
                        disabled={refreshing}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-zinc-200 rounded-lg text-zinc-600 hover:bg-slate-50 hover:text-zinc-900 transition-all disabled:opacity-50 shadow-sm"
                    >
                        <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                        새로고침
                    </button>
                </div>

                {/* Tabs */}
                <div className="border-b border-zinc-200 mb-8">
                    <nav className="-mb-px flex space-x-8">
                        <button
                            onClick={() => setActiveTab('account')}
                            className={`${activeTab === 'account'
                                ? 'border-blue-500 text-blue-600'
                                : 'border-transparent text-zinc-500 hover:text-zinc-700'
                                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                        >
                            계좌/자산
                        </button>
                        <button
                            onClick={() => setActiveTab('rebalancing')}
                            className={`${activeTab === 'rebalancing'
                                ? 'border-blue-500 text-blue-600'
                                : 'border-transparent text-zinc-500 hover:text-zinc-700'
                                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                        >
                            리밸런싱 현황
                        </button>
                    </nav>
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-xl flex items-center gap-3">
                        <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
                        <p className="text-red-300">{error}</p>
                    </div>
                )}

                {/* Account Tab */}
                {activeTab === 'account' && balance && (
                    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                            <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
                                <div className="flex items-center gap-3 mb-3">
                                    <div className="p-2 bg-blue-50 rounded-lg">
                                        <Wallet className="h-5 w-5 text-blue-600" />
                                    </div>
                                    <span className="text-zinc-500 text-sm">총 평가금액</span>
                                </div>
                                <p className="text-2xl font-bold text-zinc-900">{formatCurrency(balance.total_eval_amount)}</p>
                            </div>

                            <div className="bg-white border border-zinc-200 rounded-2xl p-6 relative group shadow-sm">
                                <div className="flex items-center gap-3 mb-3">
                                    <div className="p-2 bg-slate-100 rounded-lg">
                                        <BarChart3 className="h-5 w-5 text-zinc-500" />
                                    </div>
                                    <span className="text-zinc-500 text-sm">순 입금금액 (추정)</span>
                                </div>
                                <p className="text-2xl font-bold text-zinc-900">
                                    {formatCurrency(balance.net_invested_amount ?? (balance.total_eval_amount - balance.total_profit_loss))}
                                </p>
                                <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-[10px] text-zinc-600 p-2 rounded border border-zinc-200 pointer-events-none whitespace-pre-line z-10 w-48 shadow-lg">
                                    순 입금금액 = 총 평가금액 - 총 평가손익{'\n'}
                                    (실현손익 제외, 단순 자산 가치 역산)
                                </div>
                            </div>

                            <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
                                <div className="flex items-center gap-3 mb-3">
                                    <div className={`p-2 rounded-lg ${safeNumber(balance.total_profit_loss) >= 0 ? 'bg-emerald-50' : 'bg-red-50'}`}>
                                        {safeNumber(balance.total_profit_loss) >= 0 ?
                                            <TrendingUp className="h-5 w-5 text-emerald-600" /> :
                                            <TrendingDown className="h-5 w-5 text-red-600" />
                                        }
                                    </div>
                                    <span className="text-zinc-500 text-sm">평가손익</span>
                                </div>
                                <p className={`text-2xl font-bold ${safeNumber(balance.total_profit_loss) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                    {formatCurrency(balance.total_profit_loss)}
                                </p>
                            </div>

                            <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
                                <div className="flex items-center gap-3 mb-3">
                                    <div className={`p-2 rounded-lg ${safeNumber(balance.total_return_rate ?? balance.total_profit_loss_rate) >= 0 ? 'bg-emerald-50' : 'bg-red-50'}`}>
                                        <PieChart className="h-5 w-5 text-zinc-500" />
                                    </div>
                                    <span className="text-zinc-500 text-sm">수익률</span>
                                </div>
                                <p className={`text-2xl font-bold ${safeNumber(balance.total_return_rate ?? balance.total_profit_loss_rate) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                    {formatPercent(balance.total_return_rate ?? balance.total_profit_loss_rate)}
                                </p>
                            </div>
                        </div>

                        {/* ============ TOTAL ASSET TREND CHART START ============ */}
                        <TotalAssetTrendChart />
                        {/* ============ TOTAL ASSET TREND CHART END ============ */}

                        <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm">
                            <div className="px-6 py-4 border-b border-zinc-200">
                                <h3 className="text-lg font-semibold text-zinc-900">보유 종목</h3>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full">
                                    <thead className="bg-slate-50">
                                        <tr className="text-left text-xs text-zinc-500 uppercase tracking-wider">
                                            <th className="px-6 py-3">종목명</th>
                                            <th className="px-6 py-3 text-right">수량</th>
                                            <th className="px-6 py-3 text-right">현재가</th>
                                            <th className="px-6 py-3 text-right">평가금액</th>
                                            <th className="px-6 py-3 text-right">수익률</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-zinc-200">
                                        {balance?.holdings && balance.holdings.length > 0 ? (
                                            balance.holdings.map((item) => (
                                                <tr key={item.stock_code} className="hover:bg-slate-50 transition-colors">
                                                    <td className="px-6 py-4">
                                                        <div>
                                                            <p className="text-sm font-medium text-zinc-900">{item.stock_name}</p>
                                                            <p className="text-xs text-zinc-500">{item.stock_code}</p>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4 text-right text-sm text-zinc-600">{safeNumber(item.quantity).toLocaleString()}</td>
                                                    <td className="px-6 py-4 text-right text-sm text-zinc-600">{formatCurrency(item.current_price)}</td>
                                                    <td className="px-6 py-4 text-right text-sm text-zinc-900 font-medium">{formatCurrency(item.eval_amount)}</td>
                                                    <td className={`px-6 py-4 text-right text-sm font-medium ${safeNumber(item.profit_loss_rate) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                                        {formatPercent(item.profit_loss_rate)}
                                                    </td>
                                                </tr>
                                            ))
                                        ) : (
                                            <tr>
                                                <td colSpan={5} className="px-6 py-12 text-center text-zinc-500">
                                                    보유 종목이 없습니다.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                    </div>
                )}

                {/* Rebalancing Tab */}
                {activeTab === 'rebalancing' && rebalancing && (
                    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        {/* Status Header */}
                        <div className="bg-white border border-zinc-200 rounded-2xl p-6 flex items-center justify-between shadow-sm">
                            <div>
                                <h3 className="text-lg font-bold text-zinc-900 mb-1">Rebalancing Status</h3>
                                <div className="flex items-center gap-2">
                                    <span className={`w-2.5 h-2.5 rounded-full ${rebalancing.rebalancing_status?.needed ? 'bg-yellow-500 animate-pulse' : 'bg-emerald-500'}`}></span>
                                    <p className={`text-sm ${rebalancing.rebalancing_status?.needed ? 'text-yellow-600' : 'text-emerald-600'}`}>
                                        {rebalancing.rebalancing_status?.needed ? '리밸런싱 필요' : '최적 상태 유지 중 (허용오차 내)'}
                                    </p>
                                </div>
                            </div>
                            <button className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm">
                                Rebalancing Test
                            </button>
                        </div>

                        {rebalancing.mp && (
                            <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
                                <h3 className="text-lg font-semibold text-zinc-900 mb-6 pl-2 border-l-4 border-green-500 flex items-center gap-3">
                                    MP Target vs Actual
                                    {rebalancing.mp.name && (
                                        <span className="text-sm font-normal text-zinc-600 bg-slate-100 px-2 py-0.5 rounded-full border border-zinc-200">
                                            {rebalancing.mp.name}
                                        </span>
                                    )}
                                    {isRecentUpdate(rebalancing.mp.updated_at) && (
                                        <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse" title="최근 24시간 내 업데이트됨"></span>
                                    )}
                                    <button
                                        onClick={() => setShowMpDetails(!showMpDetails)}
                                        className="ml-auto p-1.5 text-zinc-400 hover:text-zinc-700 bg-slate-50 hover:bg-slate-100 rounded transition-colors"
                                        title="상세 정보 보기"
                                    >
                                        <AlertCircle className="w-4 h-4" />
                                    </button>
                                </h3>

                                {/* MP 적용 경과 정보 */}
                                {rebalancing.mp.started_at && (
                                    <div className="mb-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-100">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <div className="p-2 bg-blue-100 rounded-lg">
                                                    <PieChart className="h-5 w-5 text-blue-600" />
                                                </div>
                                                <div>
                                                    <p className="text-sm text-zinc-500">현재 전략 적용 중</p>
                                                    <p className="text-lg font-bold text-zinc-900">
                                                        {rebalancing.mp.name || 'Model Portfolio'}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-2xl font-bold text-blue-600">
                                                    {formatElapsedTime(getDaysElapsed(rebalancing.mp.started_at))}
                                                </p>
                                                <p className="text-xs text-zinc-500">
                                                    {rebalancing.mp.started_at?.split(' ')[0]} 부터
                                                </p>
                                            </div>
                                        </div>
                                        {rebalancing.mp.decision_date && (
                                            <div className="mt-3 pt-3 border-t border-blue-100">
                                                <p className="text-xs text-zinc-500">
                                                    마지막 AI 분석: <span className="font-medium text-zinc-700">{rebalancing.mp.decision_date}</span>
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {showMpDetails && (rebalancing.mp.description || rebalancing.mp.updated_at) && (
                                    <div className="mb-6 bg-slate-50 p-4 rounded-lg border border-zinc-200 animate-in fade-in slide-in-from-top-2 duration-200">
                                        {rebalancing.mp.description && (
                                            <div className="mb-3">
                                                <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-1">Description</h4>
                                                <p className="text-sm text-zinc-700 leading-relaxed">{rebalancing.mp.description}</p>
                                            </div>
                                        )}
                                        {rebalancing.mp.updated_at && (
                                            <div>
                                                <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-1">Last Updated</h4>
                                                <p className="text-xs text-zinc-500 flex items-center gap-2">
                                                    {rebalancing.mp.updated_at}
                                                    {isRecentUpdate(rebalancing.mp.updated_at) && (
                                                        <span className="px-1.5 py-0.5 bg-blue-100 text-blue-600 text-[10px] font-bold rounded border border-blue-200">NEW</span>
                                                    )}
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}
                                <div className="space-y-6 px-2">
                                    <div>
                                        <div className="flex justify-between text-sm mb-2 px-1">
                                            <span className="text-zinc-500 font-medium">목표 (Target)</span>
                                            <span className="text-blue-600 text-xs">Model Portfolio</span>
                                        </div>
                                        <StackedBar items={[
                                            { label: '주식', value: rebalancing.mp.target_allocation.stocks || 0, color: '#3b82f6' },
                                            { label: '채권', value: rebalancing.mp.target_allocation.bonds || 0, color: '#10b981' },
                                            { label: '대체', value: rebalancing.mp.target_allocation.alternatives || 0, color: '#ef4444' },
                                            { label: '현금', value: rebalancing.mp.target_allocation.cash || 0, color: '#8b5cf6' },
                                        ]} />
                                    </div>
                                    <div>
                                        <div className="flex justify-between text-sm mb-2 px-1">
                                            <span className="text-zinc-500 font-medium">실제 (Actual)</span>
                                            <span className="text-emerald-600 text-xs">Current Portfolio</span>
                                        </div>
                                        <StackedBar items={[
                                            { label: '주식', value: rebalancing.mp.actual_allocation.stocks || 0, color: '#3b82f6' },
                                            { label: '채권', value: rebalancing.mp.actual_allocation.bonds || 0, color: '#10b981' },
                                            { label: '대체', value: rebalancing.mp.actual_allocation.alternatives || 0, color: '#ef4444' },
                                            { label: '현금', value: rebalancing.mp.actual_allocation.cash || 0, color: '#8b5cf6' },
                                        ]} />
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Sub-MP Charts */}
                        {rebalancing.sub_mp && (
                            <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
                                <h3 className="text-lg font-semibold text-zinc-900 mb-6 pl-2 border-l-4 border-blue-500">
                                    Sub-MP Details
                                </h3>
                                <div className="space-y-8">
                                    {rebalancing.sub_mp.map((section) => (
                                        <div key={section.asset_class} className="p-5 border border-zinc-200 rounded-xl bg-slate-50">
                                            <div className="flex items-center gap-2 mb-4">
                                                <div className="w-2 h-2 rounded-full bg-zinc-400"></div>
                                                <h4 className="text-md font-bold text-zinc-900 uppercase tracking-wider flex items-center gap-2">
                                                    {section.asset_class}
                                                    {section.sub_mp_name && (
                                                        <span className="text-xs font-normal text-zinc-500 bg-white px-2 py-0.5 rounded-full border border-zinc-200 normal-case">
                                                            {section.sub_mp_name}
                                                        </span>
                                                    )}
                                                    {isRecentUpdate(section.updated_at) && (
                                                        <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse" title="최근 24시간 내 업데이트됨"></span>
                                                    )}
                                                </h4>
                                                <button
                                                    onClick={() => toggleSubMpDetails(section.asset_class)}
                                                    className="ml-auto p-1 text-zinc-400 hover:text-zinc-700 transition-colors"
                                                    title="상세 정보 보기"
                                                >
                                                    <AlertCircle className="w-4 h-4" />
                                                </button>
                                            </div>

                                            {showSubMpDetails[section.asset_class] && (section.sub_mp_description || section.updated_at) && (
                                                <div className="mb-4 bg-white p-3 rounded-lg border border-zinc-200 animate-in fade-in slide-in-from-top-1 duration-200">
                                                    {section.sub_mp_description && <p className="text-xs text-zinc-600 mb-2 leading-relaxed">{section.sub_mp_description}</p>}
                                                    {section.updated_at && (
                                                        <p className="text-[10px] text-zinc-500 flex items-center gap-2">
                                                            Updated: {section.updated_at}
                                                            {isRecentUpdate(section.updated_at) && (
                                                                <span className="px-1 py-0.5 bg-blue-100 text-blue-600 text-[9px] font-bold rounded border border-blue-200">NEW</span>
                                                            )}
                                                        </p>
                                                    )}
                                                </div>
                                            )}

                                            <div className="space-y-5">
                                                <div>
                                                    <div className="flex justify-between text-xs text-zinc-500 mb-1.5 px-0.5">
                                                        <span className="font-semibold text-blue-600/80">TARGET</span>
                                                    </div>
                                                    <StackedBar items={section.target.map((item, i) => ({
                                                        label: item.name,
                                                        value: item.weight_percent,
                                                        color: COLORS[i % COLORS.length]
                                                    }))} />
                                                </div>

                                                <div>
                                                    <div className="flex justify-between text-xs text-zinc-500 mb-1.5 px-0.5">
                                                        <span className="font-semibold text-emerald-600/80">ACTUAL</span>
                                                    </div>
                                                    <StackedBar items={section.actual.map((item, i) => ({
                                                        label: item.name,
                                                        value: item.weight_percent,
                                                        color: COLORS[i % COLORS.length]
                                                    }))} />
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default TradingDashboard;
