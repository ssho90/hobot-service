import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, DollarSign, TrendingUp, AlertTriangle, Users, Briefcase, BarChart3, LineChart } from 'lucide-react';

const generateMockData = (startVal: number, trend: number, vol: number, count: number = 20) => {
  const data = [];
  let current = startVal;
  for (let i = 0; i < count; i++) {
    current = current + (Math.random() - 0.5) * vol + trend;
    data.push({ date: `2024-${i + 1}`, value: current });
  }
  return data;
};

const liquidityData = generateMockData(8000, -50, 200); // Fed Balance Sheet
const rrpData = generateMockData(500, -20, 50); // Reverse Repo
const tgaData = generateMockData(700, 10, 80); // Treasury General Account

const nfpData = generateMockData(200, 5, 40); // Non-farm Payrolls
const unemployData = generateMockData(3.7, 0.02, 0.1); // Unemployment Rate

const cpiData = generateMockData(3.2, 0.05, 0.1); // CPI
const pceData = generateMockData(2.6, 0.03, 0.08); // PCE
const fedFundsData = generateMockData(5.33, 0, 0.01); // Fed Funds Rate

const gdpData = generateMockData(24000, 100, 500); // GDP
const yieldData = generateMockData(-0.4, 0.02, 0.05); // Yield Curve (10Y-2Y)
const hySpreadData = generateMockData(3.5, 0.05, 0.2); // High Yield Spread

const ChartCard: React.FC<{ title: string; subtitle: string; data: any[]; color: string; icon: React.ReactNode }> = ({ title, subtitle, data, color, icon }) => (
  <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-4 shadow-sm hover:border-zinc-700 transition-all flex flex-col">
    <div className="flex items-start justify-between mb-4">
      <div>
        <h4 className="text-sm font-bold text-zinc-200">{title}</h4>
        <p className="text-[10px] text-zinc-600 uppercase tracking-tight">{subtitle}</p>
      </div>
      <div className={`p-1.5 rounded-lg bg-black border border-zinc-800 ${color.replace('stroke-', 'text-')}`}>
        {icon}
      </div>
    </div>
    <div className="h-32 w-full mt-auto">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id={`grad-${title.replace(/\s+/g, '-')}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.2}/>
              <stop offset="95%" stopColor={color} stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#18181b" vertical={false} horizontal={false} />
          <XAxis dataKey="date" hide />
          <YAxis domain={['auto', 'auto']} hide />
          <Tooltip 
            contentStyle={{ backgroundColor: '#000000', borderColor: '#27272a', borderRadius: '4px', fontSize: '12px' }}
            itemStyle={{ color: '#cbd5e1' }}
            labelStyle={{ display: 'none' }}
          />
          <Area type="monotone" dataKey="value" stroke={color} fill={`url(#grad-${title.replace(/\s+/g, '-')})`} strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  </div>
);

export const MacroIndicators: React.FC = () => {
  return (
    <div className="space-y-10">
      
      {/* 유동성 Section */}
      <div>
        <h3 className="text-lg font-bold text-zinc-100 mb-5 flex items-center gap-2">
           <DollarSign className="h-5 w-5 text-blue-400" /> 유동성
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
           <ChartCard 
              title="연준 총자산 (WALCL)" 
              subtitle="Fed Total Assets (Billions)" 
              data={liquidityData} 
              color="#60a5fa" 
              icon={<BarChart3 className="h-4 w-4 text-blue-400" />}
            />
           <ChartCard 
              title="역레포 잔액 (RRPONTSYD)" 
              subtitle="Reverse Repo Volume" 
              data={rrpData} 
              color="#3b82f6" 
              icon={<Activity className="h-4 w-4 text-blue-400" />}
            />
           <ChartCard 
              title="재무부 일반계정 (WTREGEN)" 
              subtitle="Treasury General Account" 
              data={tgaData} 
              color="#2563eb" 
              icon={<DollarSign className="h-4 w-4 text-blue-500" />}
            />
        </div>
      </div>

      {/* 고용 Section */}
      <div>
        <h3 className="text-lg font-bold text-zinc-100 mb-5 flex items-center gap-2">
           <Users className="h-5 w-5 text-emerald-400" /> 고용
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
           <ChartCard 
              title="비농업 고용자수 (PAYEMS)" 
              subtitle="Non-farm Payrolls" 
              data={nfpData} 
              color="#10b981" 
              icon={<Briefcase className="h-4 w-4 text-emerald-400" />}
            />
           <ChartCard 
              title="실업률 (UNRATE)" 
              subtitle="Unemployment Rate (%)" 
              data={unemployData} 
              color="#059669" 
              icon={<Users className="h-4 w-4 text-emerald-500" />}
            />
        </div>
      </div>

      {/* 물가 Section */}
      <div>
        <h3 className="text-lg font-bold text-zinc-100 mb-5 flex items-center gap-2">
           <AlertTriangle className="h-5 w-5 text-amber-400" /> 물가
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
           <ChartCard 
              title="CPI (소비자물가지수)" 
              subtitle="Consumer Price Index (YoY)" 
              data={cpiData} 
              color="#f59e0b" 
              icon={<AlertTriangle className="h-4 w-4 text-amber-400" />}
            />
           <ChartCard 
              title="PCE (개인소비지출)" 
              subtitle="Personal Consumption Expenditures" 
              data={pceData} 
              color="#d97706" 
              icon={<Activity className="h-4 w-4 text-amber-500" />}
            />
           <ChartCard 
              title="연준 금리 (FEDFUNDS)" 
              subtitle="Effective Fed Funds Rate" 
              data={fedFundsData} 
              color="#818cf8" 
              icon={<TrendingUp className="h-4 w-4 text-indigo-400" />}
            />
        </div>
      </div>

      {/* 경기성장 및 리스크 신호 Section */}
      <div>
        <h3 className="text-lg font-bold text-zinc-100 mb-5 flex items-center gap-2">
           <LineChart className="h-5 w-5 text-rose-400" /> 경기성장 및 리스크 신호
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
           <ChartCard 
              title="실질 GDP 성장률" 
              subtitle="Real GDP Growth Rate" 
              data={gdpData} 
              color="#fb7185" 
              icon={<TrendingUp className="h-4 w-4 text-rose-400" />}
            />
           <ChartCard 
              title="장단기 금리차 (10Y-2Y)" 
              subtitle="Yield Curve Spread" 
              data={yieldData} 
              color="#f43f5e" 
              icon={<Activity className="h-4 w-4 text-rose-500" />}
            />
           <ChartCard 
              title="하이일드 스프레드" 
              subtitle="High Yield Credit Spread" 
              data={hySpreadData} 
              color="#e11d48" 
              icon={<AlertTriangle className="h-4 w-4 text-rose-600" />}
            />
        </div>
      </div>

    </div>
  );
};