import React from 'react';
import { X, Activity, TrendingUp, BarChart3 } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface ExpandedChartModalProps {
    isOpen: boolean;
    onClose: () => void;
    title: string;
    subtitle: string;
    data: any[];
    color: string;
    frequency?: string;
    unit?: string;
}

export const ExpandedChartModal: React.FC<ExpandedChartModalProps> = ({
    isOpen,
    onClose,
    title,
    subtitle,
    data,
    color,
    frequency,
    unit
}) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl h-[80vh] flex flex-col overflow-hidden">
                {/* Header */}
                <div className="p-5 border-b border-zinc-100 flex items-center justify-between bg-white sticky top-0 z-10">
                    <div>
                        <h2 className="text-2xl font-bold text-zinc-900 flex items-center gap-2">
                            {title}
                            <span className="text-sm font-normal text-zinc-500 bg-zinc-100 px-2 py-0.5 rounded-full ml-2">
                                {frequency}
                            </span>
                        </h2>
                        <p className="text-zinc-500">{subtitle}</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-zinc-100 rounded-lg text-zinc-400 hover:text-zinc-600 transition-colors"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Chart Content */}
                <div className="flex-1 p-6 relative">
                    <div className="absolute inset-0 p-6">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                                <defs>
                                    <linearGradient id={`grad-expanded-${title.replace(/\s+/g, '-')}`} x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                                        <stop offset="95%" stopColor={color} stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                <XAxis
                                    dataKey="date"
                                    tick={{ fontSize: 12, fill: '#64748b' }}
                                    tickFormatter={(value) => value.split('T')[0]}
                                    stroke="#cbd5e1"
                                />
                                <YAxis
                                    domain={['auto', 'auto']}
                                    tick={{ fontSize: 12, fill: '#64748b' }}
                                    stroke="#cbd5e1"
                                    label={{ value: unit || 'Value', angle: -90, position: 'insideLeft', fill: '#94a3b8' }}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                    itemStyle={{ color: '#334155' }}
                                    labelFormatter={(label) => new Date(label).toLocaleDateString()}
                                    formatter={(value: number) => [value.toLocaleString(), unit || 'Value']}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="value"
                                    stroke={color}
                                    fill={`url(#grad-expanded-${title.replace(/\s+/g, '-')})`}
                                    strokeWidth={3}
                                    activeDot={{ r: 6, strokeWidth: 0 }}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Footer info or controls could go here */}
                <div className="px-6 py-4 bg-zinc-50 border-t border-zinc-100 text-sm text-zinc-500 flex justify-between">
                    <div>Source: FRED (Federal Reserve Economic Data)</div>
                    <div>Showing recent history</div>
                </div>
            </div>
        </div>
    );
};
