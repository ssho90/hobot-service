import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Maximize2 } from 'lucide-react';

interface SparklineData {
  date: string;
  value: number;
}

interface ChartCardProps {
  title: string;
  subtitle: string;
  data: SparklineData[];
  color: string;
  icon: React.ReactNode;
  onExpand?: () => void;
  frequency?: string;
  latestValue?: number;
  unit?: string;
  isStale?: boolean;
  lastCollectedAt?: string | null;
}

const formatTimeAgo = (dateString: string | null | undefined) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) return 'Just now';
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)}d ago`;
  return `${Math.floor(diffInSeconds / 2592000)}mo ago`;
};

export const ChartCard: React.FC<ChartCardProps> = ({
  title,
  subtitle,
  data,
  color,
  icon,
  onExpand,
  frequency,
  latestValue,
  unit,
  isStale,
  lastCollectedAt
}) => {
  const timeAgo = formatTimeAgo(lastCollectedAt);

  return (
    <div className="bg-white rounded-xl border border-zinc-200 p-4 shadow-sm hover:border-zinc-300 hover:shadow-md transition-all flex flex-col h-full group relative overflow-hidden">
      {isStale && (
        <div className="absolute top-0 left-0 w-full h-1 bg-red-500 animate-pulse z-20" />
      )}
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0 pr-2">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-bold text-zinc-800 truncate" title={title}>{title}</h4>
            {isStale && (
              <div className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse shadow-sm flex-shrink-0" title="Data update delayed" />
            )}
          </div>
          <p className="text-[10px] text-zinc-400 uppercase tracking-tight truncate">{subtitle}</p>

          {latestValue !== undefined && (
            <div className="mt-1 flex items-baseline gap-1">
              <span className="text-lg font-bold text-zinc-900">{latestValue.toLocaleString()}</span>
              <span className="text-xs text-zinc-500">{unit}</span>
            </div>
          )}
        </div>
        <div className="flex gap-2 items-start">
          <div className="flex flex-col items-end gap-1">
            {frequency && (
              <div className={`px-1.5 py-0.5 rounded text-[10px] font-medium h-fit whitespace-nowrap ${isStale ? 'bg-red-50 text-red-600' : 'bg-zinc-100 text-zinc-600'}`}>
                {frequency}
              </div>
            )}
            {lastCollectedAt && (
              <div className="text-[9px] text-zinc-400 font-medium whitespace-nowrap">
                {timeAgo}
              </div>
            )}
          </div>
          <button
            onClick={onExpand}
            className="p-1.5 rounded-lg bg-zinc-50 hover:bg-white hover:shadow-md border border-zinc-100 hover:border-zinc-200 text-zinc-400 hover:text-blue-500 transition-all opacity-0 group-hover:opacity-100"
            title="Expand Chart"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="h-32 w-full mt-auto">
        {data && data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id={`grad-${title.replace(/\s+/g, '-')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} horizontal={false} />
              <XAxis dataKey="date" hide />
              <YAxis domain={['auto', 'auto']} hide />
              <Tooltip
                contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: '8px', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                itemStyle={{ color: '#334155' }}
                labelStyle={{ display: 'none' }}
                formatter={(value: number) => [value?.toLocaleString() || '', 'Value']}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={color}
                fill={`url(#grad-${title.replace(/\s+/g, '-')})`}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center bg-zinc-50 rounded-lg border border-dashed border-zinc-200">
            <span className="text-xs text-zinc-400">No Data Available</span>
          </div>
        )}
      </div>
    </div>
  );
};
