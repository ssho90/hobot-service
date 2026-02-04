import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Loader2, AlertCircle, TrendingUp } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface Snapshot {
    id: number;
    snapshot_date: string;
    total_value: number;
    cash_balance: number;
    pnl_total: number;
}

interface ChartData {
    date: string;
    value: number;
    pnl: number;
}

interface TotalAssetTrendChartProps {
    currentTotalValue?: number;
}

const getKstNow = (): Date => {
    const now = new Date();
    const utcMs = now.getTime() + now.getTimezoneOffset() * 60 * 1000;
    return new Date(utcMs + 9 * 60 * 60 * 1000);
};

const isBeforeSnapshotTimeKst = (kstNow: Date): boolean => {
    const hour = kstNow.getUTCHours();
    const minute = kstNow.getUTCMinutes();
    return hour < 15 || (hour === 15 && minute < 30);
};

export const TotalAssetTrendChart: React.FC<TotalAssetTrendChartProps> = ({ currentTotalValue }) => {
    const { getAuthHeaders } = useAuth();
    const [snapshots, setSnapshots] = useState<ChartData[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [days, setDays] = useState(30);

    const fetchData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const headers = getAuthHeaders();
            const response = await fetch(`/api/macro-trading/account-snapshots?days=${days}`, {
                headers: {
                    ...headers,
                    'Content-Type': 'application/json',
                }
            });
            if (response.ok) {
                const result = await response.json();
                if (result.status === 'success' && result.data) {
                    // data is already sorted by date ASC from backend
                    const chartData = result.data.map((item: Snapshot) => ({
                        date: item.snapshot_date,
                        value: item.total_value,
                        pnl: item.pnl_total
                    }));
                    setSnapshots(chartData);
                } else {
                    setError('데이터 형식이 올바르지 않습니다.');
                }
            } else {
                setError(`API 오류: ${response.status}`);
            }
        } catch (err) {
            console.error('Error fetching snapshots:', err);
            setError('데이터를 불러올 수 없습니다.');
        } finally {
            setLoading(false);
        }
    }, [days, getAuthHeaders]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const data = useMemo(() => {
        const chartData = [...snapshots];
        const hasCurrentValue = typeof currentTotalValue === 'number' && Number.isFinite(currentTotalValue);
        if (!hasCurrentValue) {
            return chartData;
        }

        const kstNow = getKstNow();
        const kstDate = kstNow.toISOString().slice(0, 10);
        const hasTodaySnapshot = chartData.some((item) => item.date === kstDate);
        if (!hasTodaySnapshot && isBeforeSnapshotTimeKst(kstNow)) {
            chartData.push({
                date: kstDate,
                value: currentTotalValue,
                pnl: 0
            });
        }

        return chartData;
    }, [snapshots, currentTotalValue]);

    if (loading && data.length === 0) {
        return (
            <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg p-12 flex items-center justify-center h-[400px]">
                <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
            </div>
        );
    }

    if (error && data.length === 0) {
        return (
            <div className="bg-white rounded-2xl border border-zinc-200 shadow-lg p-8 h-[400px] flex items-center justify-center">
                <div className="flex items-center gap-3 text-red-500">
                    <AlertCircle className="h-6 w-6" />
                    <span>{error}</span>
                    <button onClick={fetchData} className="ml-4 px-3 py-1 bg-slate-100 rounded-lg text-sm hover:bg-slate-200">
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    // Calculate stats
    const currentValue = data.length > 0 ? data[data.length - 1].value : 0;
    const startValue = data.length > 0 ? data[0].value : 0;
    const change = currentValue - startValue;
    const changePercent = startValue > 0 ? (change / startValue) * 100 : 0;
    const isPositive = change >= 0;

    return (
        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
            <div className="p-5 border-b border-zinc-200 bg-gradient-to-r from-slate-50 to-white flex justify-between items-center">
                <div className="flex items-center gap-3">
                    <div className="bg-emerald-100 p-2 rounded-xl border border-emerald-200">
                        <TrendingUp className="h-6 w-6 text-emerald-600" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-zinc-900 tracking-tight">Total Asset Trend</h2>
                        <div className="flex items-center gap-2">
                            <span className="text-2xl font-bold text-zinc-900">
                                ₩{currentValue.toLocaleString()}
                            </span>
                            <span className={`text-sm font-medium ${isPositive ? 'text-emerald-600' : 'text-red-600'}`}>
                                {isPositive ? '+' : ''}{changePercent.toFixed(2)}% ({days}D)
                            </span>
                        </div>
                    </div>
                </div>

                <div className="flex bg-slate-100 rounded-lg p-1">
                    {[30, 90, 180, 365].map((d) => (
                        <button
                            key={d}
                            onClick={() => setDays(d)}
                            className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${days === d
                                ? 'bg-white text-blue-600 shadow text-zinc-900'
                                : 'text-zinc-500 hover:text-zinc-900 hover:bg-slate-200'
                                }`}
                        >
                            {d === 365 ? '1Y' : `${d}D`}
                        </button>
                    ))}
                </div>
            </div>

            <div className="p-4 h-[350px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                        <XAxis
                            dataKey="date"
                            stroke="#94a3b8"
                            fontSize={12}
                            tickLine={false}
                            axisLine={false}
                            dy={10}
                            tickFormatter={(value) => {
                                const date = new Date(value);
                                return `${date.getMonth() + 1}/${date.getDate()}`;
                            }}
                            minTickGap={30}
                        />
                        <YAxis
                            stroke="#94a3b8"
                            fontSize={12}
                            tickLine={false}
                            axisLine={false}
                            domain={['auto', 'auto']}
                            dx={-10}
                            tickFormatter={(value) => `${(value / 1000000).toFixed(0)}M`}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: '8px', color: '#18181b', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                            itemStyle={{ color: '#10b981' }}
                            formatter={(value: any) => [`₩${Number(value).toLocaleString()}`, 'Total Value']}
                            labelFormatter={(label) => new Date(label).toLocaleDateString('ko-KR')}
                        />
                        <Area
                            type="monotone"
                            dataKey="value"
                            stroke="#10b981"
                            strokeWidth={2}
                            fillOpacity={1}
                            fill="url(#colorValue)"
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
