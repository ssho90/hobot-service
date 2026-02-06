import React, { useEffect, useState } from 'react';
import { X, Search, Database, RefreshCw, Activity } from 'lucide-react';
import { ChartCard } from './ChartCard';
import { ExpandedChartModal } from './ExpandedChartModal';

interface IndicatorStatus {
    code: string;
    name: string;
    frequency: string;
    unit: string;
    last_updated: string | null;
    latest_value: number | null;
    last_collected_at: string | null;
    description: string;
    sparkline?: { date: string; value: number }[];
    error?: string;
}

interface FredIndicatorStatusModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const FredIndicatorStatusModal: React.FC<FredIndicatorStatusModalProps> = ({ isOpen, onClose }) => {
    const [indicators, setIndicators] = useState<IndicatorStatus[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedIndicator, setSelectedIndicator] = useState<IndicatorStatus | null>(null);

    const mapSparklineToData = (sparkline?: { date: string; value: number }[]) => {
        if (!sparkline) return [];
        return sparkline.map(point => ({
            date: point.date,
            value: point.value
        }));
    };

    const handleExpand = (ind: IndicatorStatus) => {
        setSelectedIndicator(ind);
    };

    const fetchIndicators = async () => {
        setLoading(true);
        setError(null);
        try {
            // API 호출 - 환경변수 API_URL 사용 (설정되지 않은 경우 window.location.origin 사용)
            const apiUrl = (import.meta as any).env.VITE_API_URL || '';
            const response = await fetch(`${apiUrl}/api/macro-trading/fred-indicators`);

            if (!response.ok) {
                throw new Error('Failed to fetch indicators');
            }

            const data = await response.json();
            setIndicators(data.data);
        } catch (err: any) {
            console.error('Error fetching indicators:', err);
            setError(err.message || 'Failed to load data');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchIndicators();
        }
    }, [isOpen]);

    const filteredIndicators = indicators.filter(ind =>
        ind.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
        ind.description.toLowerCase().includes(searchTerm.toLowerCase())
    );

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[85vh] flex flex-col overflow-hidden">

                {/* Header */}
                <div className="p-5 border-b border-zinc-100 flex items-center justify-between bg-white sticky top-0 z-10">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-50 rounded-lg text-blue-600">
                            <Database className="w-5 h-5" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-zinc-900">FRED 지표 목록</h2>
                            <p className="text-sm text-zinc-500">수집 중인 거시경제 지표 및 최신 업데이트 현황</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-zinc-100 rounded-lg text-zinc-400 hover:text-zinc-600 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Toolbar */}
                <div className="p-4 bg-zinc-50/50 border-b border-zinc-100 flex gap-4">
                    <div className="relative flex-1">
                        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                        <input
                            type="text"
                            placeholder="Search ticker or description..."
                            className="w-full pl-9 pr-4 py-2 bg-white border border-zinc-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                    <button
                        onClick={fetchIndicators}
                        className="px-4 py-2 bg-white border border-zinc-200 rounded-lg text-sm font-medium text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900 transition-colors flex items-center gap-2"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto p-4 custom-scrollbar bg-zinc-50/30">
                    {error ? (
                        <div className="p-8 text-center text-red-500 bg-red-50 rounded-lg mx-4">
                            <p className="font-medium">Error loading data</p>
                            <p className="text-sm opacity-80 mt-1">{error}</p>
                        </div>
                    ) : loading && indicators.length === 0 ? (
                        <div className="flex items-center justify-center h-64">
                            <div className="text-zinc-500 flex flex-col items-center">
                                <RefreshCw className="w-8 h-8 animate-spin mb-2 opacity-50" />
                                <span>Loading indicators...</span>
                            </div>
                        </div>
                    ) : filteredIndicators.length === 0 ? (
                        <div className="p-8 text-center text-zinc-500">
                            No indicators found matching "{searchTerm}"
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                            {filteredIndicators.map((ind) => {
                                // Determine color based on frequency or type (simple heuristic)
                                let color = "#3b82f6"; // blue default
                                if (ind.frequency === 'daily') color = "#10b981"; // green
                                else if (ind.frequency === 'monthly') color = "#f59e0b"; // amber
                                else if (ind.frequency === 'weekly') color = "#8b5cf6"; // purple

                                // Icon selection
                                const icon = <Activity className={`h-4 w-4 ${ind.frequency === 'daily' ? 'text-emerald-500' : 'text-blue-500'}`} />;

                                return (
                                    <ChartCard
                                        key={ind.code}
                                        title={ind.name}
                                        subtitle={`${ind.code} • ${ind.frequency}`}
                                        data={mapSparklineToData(ind.sparkline)}
                                        color={color}
                                        icon={icon}
                                        frequency={ind.frequency}
                                        latestValue={ind.latest_value || undefined}
                                        unit={ind.unit}
                                        lastCollectedAt={ind.last_collected_at}
                                        onExpand={() => handleExpand(ind)}
                                    />
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-zinc-100 bg-zinc-50 flex justify-between items-center text-xs text-zinc-500">
                    <span>Total {indicators.length} indicators</span>
                    <span>Source: FRED API</span>
                </div>
            </div>

            {/* Expanded Chart Modal */}
            <ExpandedChartModal
                isOpen={!!selectedIndicator}
                onClose={() => setSelectedIndicator(null)}
                title={selectedIndicator?.name || ''}
                subtitle={`${selectedIndicator?.code || ''} - ${selectedIndicator?.description || ''}`}
                data={mapSparklineToData(selectedIndicator?.sparkline)}
                color={selectedIndicator?.frequency === 'daily' ? "#10b981" : "#3b82f6"}
                frequency={selectedIndicator?.frequency || ''}
                unit={selectedIndicator?.unit || ''}
            />
        </div>
    );
};
