import React from 'react';
import { Stock } from '../types';
import { ArrowUpRight, ArrowDownRight, MoreHorizontal } from 'lucide-react';

const trending: Stock[] = [
  { symbol: 'NVDA', name: 'NVIDIA Corp', price: 543.20, change: 12.45, changePercent: 2.35, volume: '45.2M' },
  { symbol: 'AMD', name: 'Adv. Micro Devices', price: 145.60, change: 5.20, changePercent: 3.70, volume: '32.1M' },
  { symbol: 'TSLA', name: 'Tesla Inc', price: 235.40, change: -4.50, changePercent: -1.88, volume: '89.5M' },
  { symbol: 'AAPL', name: 'Apple Inc', price: 185.10, change: -1.20, changePercent: -0.64, volume: '22.8M' },
  { symbol: 'MSFT', name: 'Microsoft Corp', price: 375.80, change: 2.10, changePercent: 0.56, volume: '18.4M' },
];

export const TrendingStocks: React.FC = () => {
  return (
    <div className="bg-slate-800/50 rounded-xl border border-slate-700 p-6 shadow-sm">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-lg font-semibold text-slate-100">Market Movers</h3>
        <button className="text-slate-400 hover:text-white p-1 rounded-full hover:bg-slate-700/50 transition-colors">
          <MoreHorizontal className="h-5 w-5" />
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-700 text-xs text-slate-400 uppercase tracking-wider">
              <th className="pb-3 pl-2">Symbol</th>
              <th className="pb-3 text-right">Price</th>
              <th className="pb-3 text-right">Change</th>
              <th className="pb-3 text-right hidden sm:table-cell">Volume</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {trending.map((stock) => (
              <tr key={stock.symbol} className="group hover:bg-slate-700/30 transition-colors">
                <td className="py-4 pl-2">
                  <div className="flex flex-col">
                    <span className="font-bold text-slate-100 group-hover:text-blue-400 transition-colors">{stock.symbol}</span>
                    <span className="text-xs text-slate-500 hidden sm:block">{stock.name}</span>
                  </div>
                </td>
                <td className="py-4 text-right font-medium text-slate-200">
                  ${stock.price.toFixed(2)}
                </td>
                <td className="py-4 text-right">
                  <div className={`flex items-center justify-end ${stock.changePercent >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                     {stock.changePercent >= 0 ? <ArrowUpRight className="h-4 w-4 mr-1" /> : <ArrowDownRight className="h-4 w-4 mr-1" />}
                     <span className="font-semibold">{Math.abs(stock.changePercent).toFixed(2)}%</span>
                  </div>
                </td>
                <td className="py-4 text-right text-slate-400 text-sm hidden sm:table-cell">
                  {stock.volume}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
