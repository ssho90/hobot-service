import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Settings, PieChart, Layers, Bitcoin, Save, X, Plus, Trash2, Edit2, AlertCircle, Check, Lightbulb } from 'lucide-react';

interface RebalancingConfig {
    mp_threshold_percent: number;
    sub_mp_threshold_percent: number;
    updated_at?: string;
}

interface Allocation {
    Stocks: number;
    Bonds: number;
    Alternatives: number;
    Cash: number;
}

interface ModelPortfolio {
    id: number;
    name: string;
    description: string;
    strategy: string;
    allocation: Allocation;
    display_order: number;
    is_active: boolean;
}

interface ETFDetail {
    category: string;
    ticker: string;
    name: string;
    weight: number;
    [key: string]: string | number;
}

interface SubModelPortfolio {
    id: number;
    name: string;
    description: string;
    asset_class: string;
    etf_details: ETFDetail[];
    display_order: number;
    is_active: boolean;
}

interface CryptoConfig {
    market_status: string;
}

interface ReplayMetrics {
    decision_count: number;
    mp_change_count: number;
    mp_transition_count: number;
    mp_change_rate: number;
    sub_mp_change_count: Record<string, number>;
    sub_mp_transition_count: Record<string, number>;
    sub_mp_change_rate: Record<string, number>;
    overall_sub_mp_change_rate: number;
    whipsaw_count: number;
    whipsaw_triplet_count: number;
    whipsaw_rate: number;
    whipsaw_events: Array<{
        decision_date: string;
        pattern: string[];
    }>;
}

interface ReplayReport {
    lookback_days: number;
    reference_now: string;
    period_start: string;
    first_decision_date: string | null;
    last_decision_date: string | null;
    baselines: {
        min_decision_count: number;
        mp_change_rate: { stable_max: number; caution_max: number };
        overall_sub_mp_change_rate: { stable_max: number; caution_max: number };
        whipsaw_rate: { stable_max: number; caution_max: number };
    };
    metrics: ReplayMetrics;
    evaluation: {
        overall_status: 'stable' | 'caution' | 'warning' | 'insufficient';
        status: Record<string, 'stable' | 'caution' | 'warning' | 'insufficient'>;
        notes: string[];
    };
}

export const AdminRebalancing: React.FC = () => {
    const [activeTab, setActiveTab] = useState('advice'); // 'advice' | 'settings' | 'mp' | 'sub-mp' | 'crypto'

    // Data States
    const [rebalancingConfig, setRebalancingConfig] = useState<RebalancingConfig | null>(null);
    const [modelPortfolios, setModelPortfolios] = useState<ModelPortfolio[]>([]);
    const [subModelPortfolios, setSubModelPortfolios] = useState<SubModelPortfolio[]>([]);
    const [cryptoConfig, setCryptoConfig] = useState<CryptoConfig | null>(null);
    const [replayReport, setReplayReport] = useState<ReplayReport | null>(null);

    // Loading/Error States
    const [loading, setLoading] = useState(false);
    const [replayLoading, setReplayLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    // Editing States
    const [isEditingConfig, setIsEditingConfig] = useState(false);
    const [configForm, setConfigForm] = useState({ mp_threshold_percent: 3.0, sub_mp_threshold_percent: 5.0 });

    const [isEditingCrypto, setIsEditingCrypto] = useState(false);
    const [cryptoForm, setCryptoForm] = useState({ market_status: 'BULL' });

    const [editingMpId, setEditingMpId] = useState<number | null>(null);
    const [mpForm, setMpForm] = useState<Partial<ModelPortfolio>>({});

    const [editingSubMpId, setEditingSubMpId] = useState<number | null>(null);
    const [subMpForm, setSubMpForm] = useState<Partial<SubModelPortfolio>>({});

    const { getAuthHeaders } = useAuth();

    // --- Fetching Functions ---
    const fetchRebalancingConfig = useCallback(async () => {
        try {
            const response = await fetch('/api/macro-trading/rebalancing/config', { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success') {
                    setRebalancingConfig(data.data || {});
                    setConfigForm({
                        mp_threshold_percent: data.data?.mp_threshold_percent ?? 3.0,
                        sub_mp_threshold_percent: data.data?.sub_mp_threshold_percent ?? 5.0,
                    });
                }
            }
        } catch (err) { console.error(err); }
    }, [getAuthHeaders]);

    const fetchModelPortfolios = useCallback(async () => {
        try {
            setLoading(true);
            const response = await fetch('/api/admin/portfolios/model-portfolios', { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                setModelPortfolios(data.portfolios || []);
            }
        } catch { setError('Failed to fetch Model Portfolios'); }
        finally { setLoading(false); }
    }, [getAuthHeaders]);

    const fetchSubModelPortfolios = useCallback(async () => {
        try {
            setLoading(true);
            const response = await fetch('/api/admin/portfolios/sub-model-portfolios', { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                setSubModelPortfolios(data.portfolios || []);
            }
        } catch { setError('Failed to fetch Sub-Model Portfolios'); }
        finally { setLoading(false); }
    }, [getAuthHeaders]);

    const fetchCryptoConfig = useCallback(async () => {
        try {
            const response = await fetch('/api/macro-trading/crypto-config', { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success') {
                    setCryptoConfig(data.data || {});
                    setCryptoForm({ market_status: data.data?.market_status || 'BULL' });
                }
            }
        } catch (err) { console.error(err); }
    }, [getAuthHeaders]);

    const fetchReplayReport = useCallback(async () => {
        try {
            setReplayLoading(true);
            const response = await fetch('/api/macro-trading/rebalancing/replay-report?days=90', { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success') {
                    setReplayReport(data.data || null);
                    return;
                }
            }
            setError('리플레이 회귀 지표를 불러오지 못했습니다.');
        } catch (err) {
            console.error(err);
            setError('리플레이 회귀 지표 조회 중 오류가 발생했습니다.');
        } finally {
            setReplayLoading(false);
        }
    }, [getAuthHeaders]);

    // --- Effects ---
    useEffect(() => {
        if (activeTab === 'advice') {
            fetchRebalancingConfig();
            fetchCryptoConfig();
            fetchReplayReport();
        }
        if (activeTab === 'settings') fetchRebalancingConfig();
        if (activeTab === 'mp') fetchModelPortfolios();
        if (activeTab === 'sub-mp') fetchSubModelPortfolios();
        if (activeTab === 'crypto') fetchCryptoConfig();
    }, [activeTab, fetchRebalancingConfig, fetchModelPortfolios, fetchSubModelPortfolios, fetchCryptoConfig, fetchReplayReport]);

    // --- Handlers: Rebalancing Config ---
    const handleSaveConfig = async () => {
        try {
            const response = await fetch('/api/macro-trading/rebalancing/config', {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(configForm)
            });
            if (response.ok) {
                await fetchRebalancingConfig();
                setIsEditingConfig(false);
                showSuccess('리밸런싱 설정이 저장되었습니다.');
            } else { setError('설정 저장 실패'); }
        } catch { setError('설정 저장 중 오류 발생'); }
    };

    // --- Handlers: Crypto Config ---
    const handleSaveCrypto = async () => {
        try {
            const response = await fetch('/api/macro-trading/crypto-config', {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(cryptoForm)
            });
            if (response.ok) {
                await fetchCryptoConfig();
                setIsEditingCrypto(false);
                showSuccess('Crypto 설정이 저장되었습니다.');
            } else { setError('Crytpo 설정 저장 실패'); }
        } catch { setError('Crypto 설정 저장 중 오류 발생'); }
    };

    // --- Handlers: Model Portfolios ---
    const enableEditMp = (mp: ModelPortfolio) => {
        setEditingMpId(mp.id);
        setMpForm(JSON.parse(JSON.stringify(mp))); // Deep copy
    };

    const handleSaveMp = async () => {
        if (!editingMpId || !mpForm) return;
        try {
            const response = await fetch(`/api/admin/portfolios/model-portfolios/${editingMpId}`, {
                method: 'PUT',
                headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(mpForm)
            });
            if (response.ok) {
                await fetchModelPortfolios();
                setEditingMpId(null);
                showSuccess('모델 포트폴리오가 업데이트되었습니다.');
            } else { setError('업데이트 실패'); }
        } catch { setError('업데이트 중 오류 발생'); }
    };

    // --- Handlers: Sub-Model Portfolios ---
    const enableEditSubMp = (subMp: SubModelPortfolio) => {
        setEditingSubMpId(subMp.id);
        setSubMpForm(JSON.parse(JSON.stringify(subMp))); // Deep copy
    };

    const handleSubMpEtfChange = (index: number, field: string, value: string) => {
        const newEtfs = [...(subMpForm.etf_details || [])];
        let val: string | number = value;
        if (field === 'weight') val = parseFloat(value) / 100 || 0; // Input is 0-100, stored as 0-1
        newEtfs[index] = { ...newEtfs[index], [field]: val };
        setSubMpForm({ ...subMpForm, etf_details: newEtfs });
    };

    const addSubMpEtf = () => {
        if (subMpForm.asset_class === 'Cash') return;
        setSubMpForm({
            ...subMpForm,
            etf_details: [...(subMpForm.etf_details || []), { category: '', ticker: '', name: '', weight: 0 }]
        });
    };

    const removeSubMpEtf = (index: number) => {
        if (subMpForm.asset_class === 'Cash') return;
        const newEtfs = (subMpForm.etf_details || []).filter((_, i) => i !== index);
        setSubMpForm({ ...subMpForm, etf_details: newEtfs });
    };

    const handleSaveSubMp = async () => {
        if (!editingSubMpId || !subMpForm) return;

        const payload = { ...subMpForm };
        if (payload.asset_class === 'Cash') {
            payload.etf_details = [{ category: 'KRW', ticker: 'CASH', name: '현금', weight: 1 }];
        }

        try {
            const response = await fetch(`/api/admin/portfolios/sub-model-portfolios/${editingSubMpId}`, {
                method: 'PUT',
                headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (response.ok) {
                await fetchSubModelPortfolios();
                setEditingSubMpId(null);
                showSuccess('Sub-MP 포트폴리오가 업데이트되었습니다.');
            } else { setError('Sub-MP 업데이트 실패'); }
        } catch { setError('Sub-MP 업데이트 중 오류 발생'); }
    };

    const showSuccess = (msg: string) => {
        setSuccessMessage(msg);
        setTimeout(() => setSuccessMessage(''), 3000);
    };

    const mpThreshold = rebalancingConfig?.mp_threshold_percent;
    const subMpThreshold = rebalancingConfig?.sub_mp_threshold_percent;

    const mpAdvice = typeof mpThreshold !== 'number'
        ? 'MP 임계값을 불러오지 못했습니다. 설정 탭에서 값을 확인하세요.'
        : mpThreshold < 2.5
            ? 'MP 임계값이 낮아 작은 노이즈에도 MP가 자주 바뀔 수 있습니다. Whipsaw 위험을 주의하세요.'
            : mpThreshold <= 5.0
                ? 'MP 임계값이 안정성과 민감도 사이의 균형 구간입니다. 현재 설정을 기준선으로 운영하기 좋습니다.'
                : 'MP 임계값이 높아 불필요한 변경은 줄지만, 국면 전환 반응이 늦어질 수 있습니다.';

    const subMpAdvice = typeof subMpThreshold !== 'number'
        ? 'Sub-MP 임계값을 불러오지 못했습니다. 설정 탭에서 값을 확인하세요.'
        : subMpThreshold < 4.0
            ? 'Sub-MP 임계값이 낮아 자산군 내 교체가 잦아질 수 있습니다. 거래비용 증가를 점검하세요.'
            : subMpThreshold <= 7.0
                ? 'Sub-MP 임계값이 무난한 범위입니다. 자산군별 미세 조정과 안정성의 균형이 좋습니다.'
                : 'Sub-MP 임계값이 높아 교체 빈도는 줄지만, 상대 강도 변화 반영이 느릴 수 있습니다.';

    const marketToneAdvice = cryptoConfig?.market_status === 'BULL'
        ? 'Crypto 상태가 BULL입니다. 공격적 노출 확대 전, MP/Sub-MP 변경 빈도와 함께 리스크를 병행 점검하세요.'
        : cryptoConfig?.market_status === 'BEAR'
            ? 'Crypto 상태가 BEAR입니다. 방어적 유지 편향이 커지므로 과도한 저점 추격 신호를 경계하세요.'
            : cryptoConfig?.market_status === 'SIDEWAYS'
                ? 'Crypto 상태가 SIDEWAYS입니다. 추세 신호보다 변동성 관리와 보수적 리밸런싱이 유효합니다.'
                : 'Crypto 시장 상태 정보를 불러오지 못했습니다.';

    const replayMetrics = replayReport?.metrics;
    const replayEvaluation = replayReport?.evaluation;
    const replayBaselines = replayReport?.baselines;

    const formatRatePercent = (value?: number) => (
        typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : 'N/A'
    );

    const getRiskBadgeByStatus = (status?: string) => {
        if (!status || status === 'insufficient') {
            return { label: 'N/A', className: 'bg-slate-100 text-zinc-500 border-zinc-200' };
        }
        if (status === 'stable') {
            return { label: '안정', className: 'bg-emerald-100 text-emerald-700 border-emerald-200' };
        }
        if (status === 'caution') {
            return { label: '주의', className: 'bg-amber-100 text-amber-700 border-amber-200' };
        }
        return { label: '경고', className: 'bg-rose-100 text-rose-700 border-rose-200' };
    };

    const mpChangeBadge = getRiskBadgeByStatus(replayEvaluation?.status?.mp_change_rate);
    const subChangeBadge = getRiskBadgeByStatus(replayEvaluation?.status?.overall_sub_mp_change_rate);
    const whipsawBadge = getRiskBadgeByStatus(replayEvaluation?.status?.whipsaw_rate);

    const replayAdvice = !replayMetrics
        ? '최근 90일 리플레이 지표를 아직 불러오지 못했습니다.'
        : replayEvaluation?.overall_status === 'insufficient'
            ? '리플레이 표본 수가 작아 추세 해석의 신뢰도가 낮습니다. 기간을 확장해 추가 확인이 필요합니다.'
            : replayEvaluation?.overall_status === 'warning'
                ? 'Whipsaw 비율이 높습니다. MP 전환 조건을 보수적으로 조정하거나 HOLD 정책 강화를 고려하세요.'
                : replayEvaluation?.overall_status === 'caution'
                    ? '일부 지표가 주의 구간입니다. 전환 임계값 및 quality gate를 점진 조정해 안정성을 점검하세요.'
                    : '리플레이 기준 전략 전환 안정성은 현재 허용 범위 내입니다.';

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-zinc-900">
            <h1 className="text-3xl font-bold tracking-tight mb-2">리밸런싱 관리</h1>
            <p className="text-zinc-500 mb-8">리밸런싱 임계값과 모델 포트폴리오(MP), Sub-MP 포트폴리오를 관리합니다.</p>

            {/* Error/Success Messages */}
            {error && <div className="mb-4 p-4 bg-red-900/30 text-red-400 rounded-xl flex items-center gap-2 border border-red-800"><AlertCircle className="w-5 h-5" />{error}</div>}
            {successMessage && <div className="mb-4 p-4 bg-emerald-900/30 text-emerald-400 rounded-xl flex items-center gap-2 border border-emerald-800"><Check className="w-5 h-5" />{successMessage}</div>}
            {loading && <div className="mb-4 p-4 bg-blue-900/30 text-blue-400 rounded-xl flex items-center gap-2 border border-blue-800">로딩 중...</div>}

            {/* Tabs */}
            <div className="flex bg-white p-1 rounded-xl mb-8 w-fit border border-zinc-200 shadow-sm">
                {[
                    { id: 'advice', label: '조언', icon: Lightbulb },
                    { id: 'settings', label: '설정', icon: Settings },
                    { id: 'mp', label: '모델 포트폴리오', icon: PieChart },
                    { id: 'sub-mp', label: 'Sub-MP', icon: Layers },
                    { id: 'crypto', label: 'Crypto 설정', icon: Bitcoin },
                ].map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-medium transition-all ${activeTab === tab.id
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100'
                            }`}
                    >
                        <tab.icon className="w-4 h-4" /> {tab.label}
                    </button>
                ))}
            </div>

            {/* Content: Advice */}
            {activeTab === 'advice' && (
                <div className="space-y-6 max-w-4xl">
                    <div className="bg-white rounded-xl border border-zinc-200 p-8 shadow-sm">
                        <h2 className="text-xl font-bold mb-2 flex items-center gap-2 text-zinc-900">
                            <Lightbulb className="w-5 h-5 text-amber-500" /> 리밸런싱 조언
                        </h2>
                        <p className="text-sm text-zinc-500">
                            이 탭은 조언 전용입니다. 실행/저장/주문 동작 없이 현재 설정을 기반으로 점검 포인트만 제공합니다.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-white rounded-xl border border-zinc-200 p-5 shadow-sm">
                            <div className="text-xs font-semibold text-zinc-500 mb-1">MP 임계값</div>
                            <div className="text-2xl font-bold text-zinc-900">
                                {typeof mpThreshold === 'number' ? `${mpThreshold.toFixed(1)}%` : 'N/A'}
                            </div>
                        </div>
                        <div className="bg-white rounded-xl border border-zinc-200 p-5 shadow-sm">
                            <div className="text-xs font-semibold text-zinc-500 mb-1">Sub-MP 임계값</div>
                            <div className="text-2xl font-bold text-zinc-900">
                                {typeof subMpThreshold === 'number' ? `${subMpThreshold.toFixed(1)}%` : 'N/A'}
                            </div>
                        </div>
                        <div className="bg-white rounded-xl border border-zinc-200 p-5 shadow-sm">
                            <div className="text-xs font-semibold text-zinc-500 mb-1">Crypto 시장 상태</div>
                            <div className="text-2xl font-bold text-zinc-900">{cryptoConfig?.market_status || 'N/A'}</div>
                        </div>
                    </div>

                    <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
                        <div className="flex items-center justify-between gap-3 mb-4">
                            <h3 className="text-sm font-semibold text-zinc-900">최근 90일 리플레이 지표</h3>
                            {replayLoading && <span className="text-xs text-zinc-500">지표 로딩 중...</span>}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                            <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-semibold text-zinc-500">MP 변경률</span>
                                    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${mpChangeBadge.className}`}>{mpChangeBadge.label}</span>
                                </div>
                                <div className="text-xl font-bold text-zinc-900">{formatRatePercent(replayMetrics?.mp_change_rate)}</div>
                                <div className="text-[11px] text-zinc-500 mt-1">
                                    {replayMetrics ? `${replayMetrics.mp_change_count}/${replayMetrics.mp_transition_count} 전환` : 'N/A'}
                                </div>
                            </div>

                            <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-semibold text-zinc-500">Sub-MP 변경률</span>
                                    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${subChangeBadge.className}`}>{subChangeBadge.label}</span>
                                </div>
                                <div className="text-xl font-bold text-zinc-900">{formatRatePercent(replayMetrics?.overall_sub_mp_change_rate)}</div>
                                <div className="text-[11px] text-zinc-500 mt-1">
                                    전체 자산군 전환 기준
                                </div>
                            </div>

                            <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-semibold text-zinc-500">Whipsaw 비율</span>
                                    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${whipsawBadge.className}`}>{whipsawBadge.label}</span>
                                </div>
                                <div className="text-xl font-bold text-zinc-900">{formatRatePercent(replayMetrics?.whipsaw_rate)}</div>
                                <div className="text-[11px] text-zinc-500 mt-1">
                                    {replayMetrics ? `${replayMetrics.whipsaw_count}/${replayMetrics.whipsaw_triplet_count} 패턴` : 'N/A'}
                                </div>
                            </div>
                        </div>

                        <div className="text-xs text-zinc-500">
                            기준 기간:
                            {' '}
                            {replayReport?.period_start || 'N/A'}
                            {' '}
                            ~
                            {' '}
                            {replayReport?.reference_now || 'N/A'}
                            {' '}
                            / 의사결정 수:
                            {' '}
                            {replayMetrics?.decision_count ?? 0}
                        </div>
                        <div className="text-xs text-zinc-500 mt-2">
                            임의 기준선:
                            {' '}
                            MP
                            {' '}
                            ≤
                            {formatRatePercent(replayBaselines?.mp_change_rate?.stable_max)}
                            {' '}
                            안정 /
                            {' '}
                            ≤
                            {formatRatePercent(replayBaselines?.mp_change_rate?.caution_max)}
                            {' '}
                            주의,
                            {' '}
                            Sub-MP
                            {' '}
                            ≤
                            {formatRatePercent(replayBaselines?.overall_sub_mp_change_rate?.stable_max)}
                            {' '}
                            안정 /
                            {' '}
                            ≤
                            {formatRatePercent(replayBaselines?.overall_sub_mp_change_rate?.caution_max)}
                            {' '}
                            주의,
                            {' '}
                            Whipsaw
                            {' '}
                            ≤
                            {formatRatePercent(replayBaselines?.whipsaw_rate?.stable_max)}
                            {' '}
                            안정 /
                            {' '}
                            ≤
                            {formatRatePercent(replayBaselines?.whipsaw_rate?.caution_max)}
                            {' '}
                            주의
                        </div>
                    </div>

                    <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
                        <h3 className="text-sm font-semibold text-zinc-900 mb-4">현재 설정 기반 조언</h3>
                        <div className="space-y-3">
                            <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
                                <div className="text-xs font-semibold text-zinc-500 mb-1">MP 변경 안정성</div>
                                <p className="text-sm text-zinc-700 leading-relaxed">{mpAdvice}</p>
                            </div>
                            <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
                                <div className="text-xs font-semibold text-zinc-500 mb-1">Sub-MP 변경 빈도</div>
                                <p className="text-sm text-zinc-700 leading-relaxed">{subMpAdvice}</p>
                            </div>
                            <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
                                <div className="text-xs font-semibold text-zinc-500 mb-1">시장 상태 해석</div>
                                <p className="text-sm text-zinc-700 leading-relaxed">{marketToneAdvice}</p>
                            </div>
                            <div className="rounded-lg border border-zinc-200 bg-slate-50 p-4">
                                <div className="text-xs font-semibold text-zinc-500 mb-1">리플레이 진단</div>
                                <p className="text-sm text-zinc-700 leading-relaxed">{replayAdvice}</p>
                                {Array.isArray(replayEvaluation?.notes) && replayEvaluation.notes.length > 0 && (
                                    <ul className="mt-2 text-xs text-zinc-500 list-disc pl-5 space-y-1">
                                        {replayEvaluation.notes.map((note, idx) => (
                                            <li key={`replay-note-${idx}`}>{note}</li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Content: Settings */}
            {activeTab === 'settings' && (
                <div className="bg-white rounded-xl border border-zinc-200 p-8 max-w-2xl shadow-sm">
                    <h2 className="text-xl font-bold mb-6 flex items-center gap-2 text-zinc-900">
                        <Settings className="w-5 h-5 text-blue-600" /> 리밸런싱 임계값
                    </h2>

                    {isEditingConfig ? (
                        <div className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-zinc-600 mb-2">MP 임계값 (%)</label>
                                <input
                                    type="number" step="0.1"
                                    value={configForm.mp_threshold_percent}
                                    onChange={e => setConfigForm({ ...configForm, mp_threshold_percent: parseFloat(e.target.value) })}
                                    className="w-full bg-white border border-zinc-200 rounded-lg p-3 text-zinc-900 focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-zinc-600 mb-2">Sub-MP 임계값 (%)</label>
                                <input
                                    type="number" step="0.1"
                                    value={configForm.sub_mp_threshold_percent}
                                    onChange={e => setConfigForm({ ...configForm, sub_mp_threshold_percent: parseFloat(e.target.value) })}
                                    className="w-full bg-white border border-zinc-200 rounded-lg p-3 text-zinc-900 focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            </div>
                            <div className="flex gap-2 justify-end pt-4">
                                <button onClick={() => setIsEditingConfig(false)} className="px-4 py-2 text-zinc-500 hover:text-zinc-900">취소</button>
                                <button onClick={handleSaveConfig} className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2">
                                    <Save className="w-4 h-4" /> 저장
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <div className="bg-slate-50 rounded-lg p-4 flex justify-between items-center border border-zinc-200">
                                <span className="text-zinc-600">MP 임계값</span>
                                <span className="text-2xl font-bold text-zinc-900">{rebalancingConfig?.mp_threshold_percent?.toFixed(1)}%</span>
                            </div>
                            <div className="bg-slate-50 rounded-lg p-4 flex justify-between items-center border border-zinc-200">
                                <span className="text-zinc-600">Sub-MP 임계값</span>
                                <span className="text-2xl font-bold text-zinc-900">{rebalancingConfig?.sub_mp_threshold_percent?.toFixed(1)}%</span>
                            </div>
                            <div className="flex justify-end pt-4">
                                <button onClick={() => setIsEditingConfig(true)} className="px-6 py-2 bg-white hover:bg-zinc-50 text-zinc-700 rounded-lg flex items-center gap-2 border border-zinc-300">
                                    <Edit2 className="w-4 h-4" /> 수정
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Content: MP */}
            {activeTab === 'mp' && (
                <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden shadow-sm">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="bg-slate-50 text-zinc-500 uppercase text-xs border-b border-zinc-200">
                                <tr>
                                    <th className="px-6 py-3">ID</th>
                                    <th className="px-6 py-3">이름/설명</th>
                                    <th className="px-6 py-3">전략</th>
                                    <th className="px-6 py-3">자산 배분 (S/B/A/C)</th>
                                    <th className="px-6 py-3">순서</th>
                                    <th className="px-6 py-3">상태</th>
                                    <th className="px-6 py-3 text-right">작업</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-200">
                                {modelPortfolios.map(mp => (
                                    <tr key={mp.id} className="hover:bg-slate-50">
                                        <td className="px-6 py-4 text-zinc-500">{mp.id}</td>

                                        {editingMpId === mp.id ? (
                                            <>
                                                <td className="px-6 py-4">
                                                    <input
                                                        className="w-full bg-black border border-zinc-700 rounded p-1.5 mb-2 text-white"
                                                        value={mpForm.name} onChange={e => setMpForm({ ...mpForm, name: e.target.value })}
                                                    />
                                                    <textarea
                                                        className="w-full bg-black border border-zinc-700 rounded p-1.5 text-zinc-300 text-xs"
                                                        value={mpForm.description} onChange={e => setMpForm({ ...mpForm, description: e.target.value })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4">
                                                    <input
                                                        className="w-full bg-black border border-zinc-700 rounded p-1.5 text-white"
                                                        value={mpForm.strategy} onChange={e => setMpForm({ ...mpForm, strategy: e.target.value })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4">
                                                    <div className="grid grid-cols-2 gap-2 w-48">
                                                        {(['Stocks', 'Bonds', 'Alternatives', 'Cash'] as const).map(key => (
                                                            <div key={key} className="flex flex-col">
                                                                <span className="text-[10px] text-zinc-500">{key[0]}</span>
                                                                <input
                                                                    type="number" step="0.1"
                                                                    className="bg-black border border-zinc-700 rounded p-1 text-white text-xs"
                                                                    value={mpForm.allocation?.[key]}
                                                                    onChange={e => setMpForm({
                                                                        ...mpForm,
                                                                        allocation: { ...mpForm.allocation!, [key]: parseFloat(e.target.value) || 0 }
                                                                    })}
                                                                />
                                                            </div>
                                                        ))}
                                                    </div>
                                                </td>
                                                <td className="px-6 py-4">
                                                    <input
                                                        type="number"
                                                        className="w-16 bg-black border border-zinc-700 rounded p-1.5 text-white"
                                                        value={mpForm.display_order} onChange={e => setMpForm({ ...mpForm, display_order: parseInt(e.target.value) })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4">
                                                    <div className="flex items-center">
                                                        <input
                                                            type="checkbox"
                                                            checked={mpForm.is_active} onChange={e => setMpForm({ ...mpForm, is_active: e.target.checked })}
                                                            className="w-4 h-4 rounded border-zinc-700 bg-black text-blue-600 focus:ring-blue-500"
                                                        />
                                                    </div>
                                                </td>
                                                <td className="px-6 py-4 text-right">
                                                    <div className="flex justify-end gap-2">
                                                        <button onClick={handleSaveMp} className="p-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded"><Save className="w-4 h-4" /></button>
                                                        <button onClick={() => setEditingMpId(null)} className="p-1.5 bg-zinc-700 hover:bg-zinc-600 text-white rounded"><X className="w-4 h-4" /></button>
                                                    </div>
                                                </td>
                                            </>
                                        ) : (
                                            <>
                                                <td className="px-6 py-4">
                                                    <div className="font-medium text-zinc-900">{mp.name}</div>
                                                    <div className="text-xs text-zinc-500">{mp.description}</div>
                                                </td>
                                                <td className="px-6 py-4 text-zinc-700">{mp.strategy}</td>
                                                <td className="px-6 py-4">
                                                    <div className="flex gap-2 text-xs">
                                                        <span className="text-blue-600">S:{mp.allocation.Stocks}%</span>
                                                        <span className="text-emerald-600">B:{mp.allocation.Bonds}%</span>
                                                        <span className="text-purple-600">A:{mp.allocation.Alternatives}%</span>
                                                        <span className="text-zinc-500">C:{mp.allocation.Cash}%</span>
                                                    </div>
                                                </td>
                                                <td className="px-6 py-4 text-zinc-700">{mp.display_order}</td>
                                                <td className="px-6 py-4">
                                                    {mp.is_active
                                                        ? <span className="text-xs px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full border border-emerald-200">Active</span>
                                                        : <span className="text-xs px-2 py-0.5 bg-slate-100 text-zinc-500 rounded-full border border-zinc-200">Inactive</span>
                                                    }
                                                </td>
                                                <td className="px-6 py-4 text-right">
                                                    <button onClick={() => enableEditMp(mp)} className="p-1.5 hover:bg-slate-100 text-zinc-500 hover:text-zinc-900 rounded transition-colors">
                                                        <Edit2 className="w-4 h-4" />
                                                    </button>
                                                </td>
                                            </>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Content: Sub-MP */}
            {activeTab === 'sub-mp' && (
                <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden shadow-sm">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="bg-slate-50 text-zinc-500 uppercase text-xs border-b border-zinc-200">
                                <tr>
                                    <th className="px-6 py-3 w-12">ID</th>
                                    <th className="px-6 py-3 w-48">이름/설명</th>
                                    <th className="px-6 py-3 w-24">자산군</th>
                                    <th className="px-6 py-3">ETF 구성 (카테고리: 티커 / 비중)</th>
                                    <th className="px-6 py-3 w-20">순서</th>
                                    <th className="px-6 py-3 w-24">상태</th>
                                    <th className="px-6 py-3 w-24 text-right">작업</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-200">
                                {subModelPortfolios.map(subMp => (
                                    <tr key={subMp.id} className="hover:bg-slate-50">
                                        <td className="px-6 py-4 text-zinc-500 align-top">{subMp.id}</td>

                                        {editingSubMpId === subMp.id ? (
                                            <>
                                                <td className="px-6 py-4 align-top">
                                                    <input
                                                        className="w-full bg-black border border-zinc-700 rounded p-1.5 mb-2 text-white"
                                                        value={subMpForm.name} onChange={e => setSubMpForm({ ...subMpForm, name: e.target.value })}
                                                    />
                                                    <textarea
                                                        className="w-full bg-black border border-zinc-700 rounded p-1.5 text-zinc-300 text-xs"
                                                        value={subMpForm.description} onChange={e => setSubMpForm({ ...subMpForm, description: e.target.value })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4 align-top">
                                                    <select
                                                        value={subMpForm.asset_class}
                                                        onChange={e => {
                                                            const cls = e.target.value;
                                                            const updates: Partial<SubModelPortfolio> = { asset_class: cls };
                                                            if (cls === 'Cash') updates.etf_details = [{ category: 'KRW', ticker: 'CASH', name: '현금', weight: 1 }];
                                                            setSubMpForm({ ...subMpForm, ...updates });
                                                        }}
                                                        className="w-full bg-black border border-zinc-700 rounded p-1.5 text-white"
                                                    >
                                                        <option value="Stocks">Stocks</option>
                                                        <option value="Bonds">Bonds</option>
                                                        <option value="Alternatives">Alternatives</option>
                                                        <option value="Cash">Cash</option>
                                                    </select>
                                                </td>
                                                <td className="px-6 py-4 align-top">
                                                    {subMpForm.asset_class === 'Cash' ? (
                                                        <div className="text-zinc-500 italic p-2">현금 자산군은 편집할 수 없습니다 (자동 100%)</div>
                                                    ) : (
                                                        <div className="space-y-2">
                                                            {subMpForm.etf_details?.map((etf, idx) => (
                                                                <div key={idx} className="flex gap-2 items-center">
                                                                    <input className="w-20 bg-black border border-zinc-700 rounded p-1 text-xs" placeholder="Category" value={etf.category} onChange={e => handleSubMpEtfChange(idx, 'category', e.target.value)} />
                                                                    <input className="w-16 bg-black border border-zinc-700 rounded p-1 text-xs" placeholder="Ticker" value={etf.ticker} onChange={e => handleSubMpEtfChange(idx, 'ticker', e.target.value)} />
                                                                    <input className="flex-1 bg-black border border-zinc-700 rounded p-1 text-xs" placeholder="Name" value={etf.name} onChange={e => handleSubMpEtfChange(idx, 'name', e.target.value)} />
                                                                    <input className="w-14 bg-black border border-zinc-700 rounded p-1 text-xs" type="number" placeholder="%" value={(etf.weight * 100).toFixed(0)} onChange={e => handleSubMpEtfChange(idx, 'weight', e.target.value)} />
                                                                    <button onClick={() => removeSubMpEtf(idx)} className="text-red-400 hover:text-red-300"><Trash2 className="w-3 h-3" /></button>
                                                                </div>
                                                            ))}
                                                            <button onClick={addSubMpEtf} className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-2">
                                                                <Plus className="w-3 h-3" /> ETF 추가
                                                            </button>
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4 align-top">
                                                    <input
                                                        type="number"
                                                        className="w-16 bg-black border border-zinc-700 rounded p-1.5 text-white"
                                                        value={subMpForm.display_order} onChange={e => setSubMpForm({ ...subMpForm, display_order: parseInt(e.target.value) })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4 align-top">
                                                    <input
                                                        type="checkbox"
                                                        checked={subMpForm.is_active} onChange={e => setSubMpForm({ ...subMpForm, is_active: e.target.checked })}
                                                        className="w-4 h-4 rounded border-zinc-700 bg-black text-blue-600"
                                                    />
                                                </td>
                                                <td className="px-6 py-4 align-top text-right">
                                                    <div className="flex justify-end gap-2">
                                                        <button onClick={handleSaveSubMp} className="p-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded"><Save className="w-4 h-4" /></button>
                                                        <button onClick={() => setEditingSubMpId(null)} className="p-1.5 bg-zinc-700 hover:bg-zinc-600 text-white rounded"><X className="w-4 h-4" /></button>
                                                    </div>
                                                </td>
                                            </>
                                        ) : (
                                            <>
                                                <td className="px-6 py-4 align-top">
                                                    <div className="font-medium text-zinc-900">{subMp.name}</div>
                                                    <div className="text-xs text-zinc-500">{subMp.description}</div>
                                                </td>
                                                <td className="px-6 py-4 align-top text-zinc-700">{subMp.asset_class}</td>
                                                <td className="px-6 py-4 align-top">
                                                    <div className="space-y-1">
                                                        {subMp.etf_details.map((etf, i) => (
                                                            <div key={i} className="text-xs text-zinc-600 flex justify-between gap-4 border-b border-zinc-100 pb-1 last:border-0">
                                                                <span><span className="text-zinc-500">[{etf.category}]</span> {etf.ticker}</span>
                                                                <span className="font-medium text-zinc-900">{(etf.weight * 100).toFixed(0)}%</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </td>
                                                <td className="px-6 py-4 align-top text-zinc-700">{subMp.display_order}</td>
                                                <td className="px-6 py-4 align-top">
                                                    {subMp.is_active
                                                        ? <span className="text-xs px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full border border-emerald-200">Active</span>
                                                        : <span className="text-xs px-2 py-0.5 bg-slate-100 text-zinc-500 rounded-full border border-zinc-200">Inactive</span>
                                                    }
                                                </td>
                                                <td className="px-6 py-4 align-top text-right">
                                                    <button onClick={() => enableEditSubMp(subMp)} className="p-1.5 hover:bg-slate-100 text-zinc-500 hover:text-zinc-900 rounded transition-colors">
                                                        <Edit2 className="w-4 h-4" />
                                                    </button>
                                                </td>
                                            </>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Content: Crypto */}
            {activeTab === 'crypto' && (
                <div className="bg-white rounded-xl border border-zinc-200 p-8 max-w-2xl shadow-sm">
                    <h2 className="text-xl font-bold mb-6 flex items-center gap-2 text-zinc-900">
                        <Bitcoin className="w-5 h-5 text-orange-500" /> Crypto 시장 설정
                    </h2>

                    {isEditingCrypto ? (
                        <div className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-zinc-600 mb-2">Market Status</label>
                                <select
                                    value={cryptoForm.market_status}
                                    onChange={e => setCryptoForm({ ...cryptoForm, market_status: e.target.value })}
                                    className="w-full bg-white border border-zinc-200 rounded-lg p-3 text-zinc-900 focus:ring-2 focus:ring-blue-500 outline-none"
                                >
                                    <option value="BULL">BULL (상승장)</option>
                                    <option value="BEAR">BEAR (하락장)</option>
                                    <option value="SIDEWAYS">SIDEWAYS (횡보장)</option>
                                </select>
                            </div>
                            <div className="flex gap-2 justify-end pt-4">
                                <button onClick={() => setIsEditingCrypto(false)} className="px-4 py-2 text-zinc-500 hover:text-zinc-900">취소</button>
                                <button onClick={handleSaveCrypto} className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2">
                                    <Save className="w-4 h-4" /> 저장
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <div className="bg-slate-50 rounded-lg p-4 flex justify-between items-center border border-zinc-200">
                                <span className="text-zinc-600">현재 시장 상태</span>
                                <span className={`text-xl font-bold ${cryptoConfig?.market_status === 'BULL' ? 'text-red-500' :
                                    cryptoConfig?.market_status === 'BEAR' ? 'text-blue-600' : 'text-zinc-700'
                                    }`}>
                                    {cryptoConfig?.market_status || 'UNKNOWN'}
                                </span>
                            </div>
                            <div className="flex justify-end pt-4">
                                <button onClick={() => setIsEditingCrypto(true)} className="px-6 py-2 bg-white hover:bg-zinc-50 text-zinc-700 rounded-lg flex items-center gap-2 border border-zinc-300">
                                    <Edit2 className="w-4 h-4" /> 수정
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
