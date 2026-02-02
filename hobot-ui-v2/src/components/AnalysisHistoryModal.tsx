import React, { useEffect, useState } from 'react';
import { X, FileText } from 'lucide-react';

interface AnalysisHistoryModalProps {
    isOpen: boolean;
    onClose: () => void;
}

interface StrategyDecision {
    id: number;
    decision_date: string;
    analysis_summary: string;
    target_allocation: string; // JSON string or Object depending on API response
    sub_mp?: string | any; // JSON string or Object
    created_at: string;
}

interface Allocation {
    Stocks: number;
    Bonds: number;
    Alternatives: number;
    Cash: number;
}

export const AnalysisHistoryModal: React.FC<AnalysisHistoryModalProps> = ({ isOpen, onClose }) => {
    const [history, setHistory] = useState<StrategyDecision[]>([]);
    const [loading, setLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    const fetchHistory = async (pageNum: number) => {
        setLoading(true);
        try {
            const response = await fetch(`http://localhost:8991/api/macro-trading/strategy-decisions-history?page=${pageNum}&limit=5`);
            const data = await response.json();
            if (data.status === 'success') {
                if (Array.isArray(data.data)) {
                    setHistory(data.data);
                    setTotalPages(data.total_pages || 1);
                } else if (data.data?.history) {
                    setHistory(data.data.history);
                    setTotalPages(data.data.pagination?.total_pages || 1);
                }
            }
        } catch (error) {
            console.error("Failed to fetch history", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchHistory(page);
        }
    }, [isOpen, page]);

    if (!isOpen) return null;

    const parseData = (data: string | any) => {
        if (typeof data === 'string') {
            try {
                return JSON.parse(data);
            } catch (e) {
                return null;
            }
        }
        return data;
    };

    const parseAllocation = (data: any): Allocation => {
        const parsed = parseData(data);
        return parsed || { Stocks: 0, Bonds: 0, Alternatives: 0, Cash: 0 };
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-stone-200 bg-stone-50">
                    <div>
                        <h2 className="text-xl font-bold text-stone-900 font-serif">Previous Analysis Search</h2>
                        <p className="text-sm text-stone-500 mt-1">과거 AI 분석 이력 및 자산 배분 결과를 조회합니다.</p>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-stone-200 rounded-full transition-colors text-stone-500 hover:text-stone-700">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 bg-[#fcfbf9]">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-20 gap-3">
                            <div className="w-8 h-8 border-4 border-stone-200 border-t-stone-800 rounded-full animate-spin"></div>
                            <span className="text-stone-500 text-sm">데이터를 불러오는 중입니다...</span>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {history.length === 0 ? (
                                <div className="text-center py-20 text-stone-400">조회된 이력이 없습니다.</div>
                            ) : (
                                history.map((item) => {
                                    const allocation = parseAllocation(item.target_allocation);
                                    const subMp = parseData(item.sub_mp);
                                    const date = new Date(item.decision_date);

                                    return (
                                        <div key={item.id} className="bg-white p-5 border border-stone-200 rounded-xl hover:border-blue-400 hover:shadow-lg transition-all cursor-pointer group shadow-sm">
                                            <div className="flex justify-between items-start mb-4">
                                                <div className="flex items-center gap-3">
                                                    <div className="bg-stone-100 text-stone-600 p-2.5 rounded-lg group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
                                                        <FileText className="w-5 h-5" />
                                                    </div>
                                                    <div>
                                                        <h4 className="font-bold text-stone-900 text-lg leading-tight group-hover:text-blue-700 transition-colors font-serif">
                                                            Analysis Report #{item.id}
                                                        </h4>
                                                        <div className="flex items-center gap-2 text-xs text-stone-500 mt-0.5">
                                                            <span className="font-medium bg-stone-100 px-1.5 py-0.5 rounded text-stone-600">{date.toLocaleDateString()}</span>
                                                            <span>{date.toLocaleTimeString()}</span>
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Allocation & Sub-MP Badges */}
                                                <div className="flex flex-col items-end gap-2 text-right">
                                                    <div className="flex flex-wrap gap-2 justify-end">
                                                        <Badge label="Stocks" value={allocation.Stocks} color="bg-red-50 text-red-700 border-red-100" />
                                                        <Badge label="Bonds" value={allocation.Bonds} color="bg-blue-50 text-blue-700 border-blue-100" />
                                                        <Badge label="Alt" value={allocation.Alternatives} color="bg-purple-50 text-purple-700 border-purple-100" />
                                                        <Badge label="Cash" value={allocation.Cash} color="bg-stone-50 text-stone-700 border-stone-200" />
                                                    </div>
                                                    {subMp && (
                                                        <div className="flex flex-wrap gap-2 justify-end">
                                                            {subMp.stocks && <SubMpBadge label="EQ" name={subMp.stocks.sub_mp_name} color="bg-red-50 text-red-600 border-red-100" />}
                                                            {subMp.bonds && <SubMpBadge label="BND" name={subMp.bonds.sub_mp_name} color="bg-blue-50 text-blue-600 border-blue-100" />}
                                                            {subMp.alternatives && <SubMpBadge label="ALT" name={subMp.alternatives.sub_mp_name} color="bg-purple-50 text-purple-600 border-purple-100" />}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="text-sm text-stone-600 line-clamp-3 leading-relaxed border-t border-stone-100 pt-3">
                                                {item.analysis_summary}
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    )}
                </div>

                {/* Footer (Pagination) */}
                <div className="p-4 border-t border-stone-200 flex justify-between items-center bg-white">
                    <span className="text-sm text-stone-500 font-medium">Page {page} of {totalPages}</span>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            disabled={page === 1}
                            className="px-4 py-2 border border-stone-200 rounded-lg text-sm font-medium text-stone-600 bg-white hover:bg-stone-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                        >
                            Previous
                        </button>
                        <button
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            disabled={page === totalPages}
                            className="px-4 py-2 border border-stone-200 rounded-lg text-sm font-medium text-stone-600 bg-white hover:bg-stone-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                        >
                            Next
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

const Badge = ({ label, value, color }: { label: string, value: number, color: string }) => (
    <div className={`flex flex-col items-center justify-center px-3 py-1.5 rounded-lg border ${color} min-w-[70px]`}>
        <span className="text-[10px] uppercase font-bold opacity-70 mb-0.5">{label}</span>
        <span className="text-sm font-bold">{value}%</span>
    </div>
);

const SubMpBadge = ({ label, name, color }: { label: string, name: string, color: string }) => {
    // 괄호 앞부분만 추출하여 짧게 표시 (예: "Aggressive (성장 공격형)" -> "Aggressive")
    const shortName = name.split('(')[0].trim();
    return (
        <div className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium border ${color}`} title={name}>
            <span className="opacity-70 text-[10px] font-bold">{label}</span>
            <span className="truncate max-w-[80px]">{shortName}</span>
        </div>
    );
};
