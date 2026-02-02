import React from 'react';
import type { MarketIndex } from '../types';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

const mockIndices: MarketIndex[] = [
  { name: 'S&P 500', value: 4783.45, change: 12.3, changePercent: 0.26 },
  { name: 'NASDAQ', value: 15628.90, change: -45.2, changePercent: -0.29 },
  { name: 'DOW JONES', value: 37400.12, change: 89.1, changePercent: 0.24 },
  { name: 'BTC/USD', value: 42350.00, change: 1250.5, changePercent: 3.05 },
  { name: 'ETH/USD', value: 2250.80, change: 45.2, changePercent: 2.05 },
  { name: 'GOLD', value: 2045.30, change: -5.1, changePercent: -0.25 },
];

export const TickerTape: React.FC = () => {
  return (
    <div className="w-full bg-black border-b border-zinc-900 overflow-hidden py-2">
      <div className="relative flex overflow-x-hidden">
        <div className="animate-marquee whitespace-nowrap flex items-center space-x-8 px-4">
          {[...mockIndices, ...mockIndices].map((index, i) => ( // Duplicate for seamless loop
            <div key={`${index.name}-${i}`} className="flex items-center space-x-2">
              <span className="text-zinc-500 text-xs font-semibold uppercase tracking-wider">{index.name}</span>
              <span className="text-zinc-200 text-sm font-medium">{index.value.toLocaleString()}</span>
              <div className={`flex items-center text-xs ${index.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {index.change >= 0 ? <ArrowUpRight className="h-3 w-3 mr-0.5" /> : <ArrowDownRight className="h-3 w-3 mr-0.5" />}
                <span>{index.changePercent}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <style>{`
        .animate-marquee {
          animation: marquee 25s linear infinite;
        }
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
};