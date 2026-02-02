import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const data = [
  { time: '10:00', value: 4750 },
  { time: '10:30', value: 4755 },
  { time: '11:00', value: 4748 },
  { time: '11:30', value: 4760 },
  { time: '12:00', value: 4762 },
  { time: '12:30', value: 4758 },
  { time: '13:00', value: 4765 },
  { time: '13:30', value: 4770 },
  { time: '14:00', value: 4768 },
  { time: '14:30', value: 4775 },
  { time: '15:00', value: 4780 },
  { time: '15:30', value: 4783 },
];

export const MarketChart: React.FC = () => {
  return (
    <div className="bg-slate-800/50 rounded-xl border border-slate-700 p-6 shadow-sm">
      <div className="flex justify-between items-center mb-6">
        <div>
            <h3 className="text-lg font-semibold text-slate-100">S&P 500 Performance</h3>
            <p className="text-sm text-slate-400">Intraday</p>
        </div>
        <div className="flex space-x-1 bg-slate-700/50 rounded-lg p-1">
            {['1D', '1W', '1M', '3M', '1Y', 'ALL'].map(period => (
                <button 
                    key={period} 
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${period === '1D' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700'}`}
                >
                    {period}
                </button>
            ))}
        </div>
      </div>
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis 
                dataKey="time" 
                stroke="#64748b" 
                fontSize={12} 
                tickLine={false} 
                axisLine={false}
                dy={10}
            />
            <YAxis 
                stroke="#64748b" 
                fontSize={12} 
                tickLine={false} 
                axisLine={false} 
                domain={['auto', 'auto']}
                dx={-10}
            />
            <Tooltip 
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', color: '#f1f5f9' }}
                itemStyle={{ color: '#60a5fa' }}
            />
            <Area 
                type="monotone" 
                dataKey="value" 
                stroke="#3b82f6" 
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
