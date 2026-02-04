import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Scatter,
  Legend,
  ReferenceLine,
  LabelList
} from 'recharts';

interface CyclePoint {
  date: string;
  price: number;
  type: 'history' | 'prediction';
  event: string;
}

interface CurrentPrice {
  price: number;
  timestamp: number;
}

interface ApiResponse {
  cycle_data: CyclePoint[];
  current_price: { price: number; timestamp?: string } | null;
  error?: string | null;
}

const parseCycleDate = (value: string) => {
  if (!value) return null;
  const trimmed = value.trim();
  const match = trimmed.match(/^(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?/);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = match[3] ? Number(match[3]) : 1;
    if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null;
    const timestamp = Date.UTC(year, month - 1, Number.isFinite(day) ? day : 1);
    return Number.isFinite(timestamp) ? timestamp : null;
  }
  const fallback = Date.parse(trimmed);
  return Number.isNaN(fallback) ? null : fallback;
};

const formatMonthLabel = (timestamp: number) => {
  const date = new Date(timestamp);
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  return `${year}-${month}`;
};

const formatAxisPrice = (value: number) => {
  if (value >= 1000000) return `$${Math.round(value / 1000000)}M`;
  if (value >= 1000) return `$${Math.round(value / 1000)}k`;
  return `$${Math.round(value)}`;
};

const formatPrice = (value: number) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);

const PulseDot: React.FC<{ cx?: number; cy?: number; payload?: { label?: string } }> = ({ cx, cy, payload }) => {
  if (cx == null || cy == null) return null;
  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={12}
        className="fill-red-500/30 animate-ping"
        style={{ transformOrigin: 'center', transformBox: 'fill-box' }}
      />
      <circle
        cx={cx}
        cy={cy}
        r={5}
        className="fill-red-500 stroke-white"
        strokeWidth={1.5}
      />
      {payload?.label && (
        <text x={cx + 12} y={cy} className="fill-red-500 text-[12px] font-bold" textAnchor="start" dominantBaseline="middle">
          {payload.label}
        </text>
      )}
    </g>
  );
};

const CustomTooltip: React.FC<any> = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null;
  const target =
    payload.find((item: any) => item.payload?.label) ||
    payload.find((item: any) => item.payload?.event) ||
    payload[0];
  const data = target.payload || {};
  const tooltipDate = Number.isFinite(data.timestamp)
    ? formatMonthLabel(data.timestamp)
    : typeof data.date === 'string'
      ? data.date
      : '';
  return (
    <div className="rounded-lg bg-zinc-900 text-white text-xs px-3 py-2 shadow-xl z-50">
      <div className="font-semibold mb-1 text-zinc-300">{data.label ? 'Current Price' : data.event || 'Cycle Point'}</div>
      <div className="text-white font-mono text-sm mb-1">${formatPrice(data.price)}</div>
      {tooltipDate && <div className="text-zinc-500">{tooltipDate}</div>}
    </div>
  );
};

const renderCustomizedLabel = (props: any) => {
  const { x, y, value } = props;
  // Access the full data point from the 'data' prop using index if passed, 
  // but LabelList usually passes 'value' as the dataKey value.
  // We need to access the 'event' field.
  // Recharts LabelList with dataKey="event" passes the event string as 'value'.

  if (!value || (!value.includes('Peak') && !value.includes('Bottom'))) return null;

  return (
    <text x={x} y={y} dy={-10} fill="#666" fontSize={11} textAnchor="middle" fontWeight="bold">
      {value.replace(' (Exp)', '')}
    </text>
  );
};

export const BitcoinCycleChart: React.FC = () => {
  const [cycleData, setCycleData] = useState<CyclePoint[]>([]);
  const [currentPrice, setCurrentPrice] = useState<CurrentPrice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [priceWarning, setPriceWarning] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const initialLoadRef = useRef(true);
  const [hoverPoint, setHoverPoint] = useState<{
    xIndex: number;
    price: number;
    dateLabel: string;
  } | null>(null);

  const fetchCycleData = async () => {
    try {
      if (initialLoadRef.current) {
        setLoading(true);
      }
      setError(null);
      const response = await fetch('/api/bitcoin-cycle');
      if (!response.ok) {
        throw new Error('비트코인 사이클 데이터를 불러오는데 실패했습니다.');
      }
      const result: ApiResponse = await response.json();
      if (!result.cycle_data) {
        throw new Error('사이클 데이터가 존재하지 않습니다.');
      }

      setCycleData(result.cycle_data);

      if (result.current_price && typeof result.current_price.price === 'number') {
        const timestamp = result.current_price.timestamp
          ? new Date(result.current_price.timestamp).getTime()
          : Date.now();
        setCurrentPrice({ price: result.current_price.price, timestamp });
        setLastUpdated(result.current_price.timestamp ? new Date(result.current_price.timestamp) : new Date());
        setPriceWarning(null);
      } else {
        setCurrentPrice(null);
        setPriceWarning('현재 가격을 불러오지 못했습니다.');
      }

      if (result.error) {
        setPriceWarning('현재 가격을 불러오지 못했습니다.');
      }
    } catch (err: any) {
      setError(err?.message || '데이터를 불러오는데 실패했습니다.');
    } finally {
      if (initialLoadRef.current) {
        setLoading(false);
        initialLoadRef.current = false;
      }
    }
  };

  useEffect(() => {
    fetchCycleData();
    const intervalId = setInterval(fetchCycleData, 30000); // 30 seconds
    return () => clearInterval(intervalId);
  }, []);

  const { chartData, indexLabels, indexTicks, hoverTargets } = useMemo(() => {
    const nowTimestamp = Date.now();
    const withTimestamps = cycleData.map((item, originalIndex) => ({
      ...item,
      timestamp: parseCycleDate(item.date),
      originalIndex
    }));

    const ordered = [...withTimestamps].sort((a, b) => a.originalIndex - b.originalIndex);

    const lastHistoryIndex = ordered.reduce((acc, item, idx) => {
      if (Number.isFinite(item.timestamp) && (item.timestamp as number) <= nowTimestamp) {
        return idx;
      }
      return acc;
    }, -1);

    const normalized = ordered.map((item, index) => {
      const isHistory = Number.isFinite(item.timestamp)
        ? (item.timestamp as number) <= nowTimestamp
        : item.type === 'history';

      const historyPrice = isHistory ? item.price : null;
      let predictionPrice = isHistory ? null : item.price;

      if (index === lastHistoryIndex) {
        predictionPrice = item.price;
      }

      return {
        ...item,
        historyPrice,
        predictionPrice,
        xIndex: index,
        isHoverTarget: item.event.includes('Peak') || item.event.includes('Bottom'),
        // Helper for reference lines
        isHalving: item.event.includes('Halving')
      };
    });

    const labels = normalized.map((item) => {
      if (typeof item.date === 'string') {
        const match = item.date.match(/^(\d{4})/);
        if (match) return match[1];
      }
      if (item.timestamp !== null && Number.isFinite(item.timestamp)) return new Date(item.timestamp).getUTCFullYear().toString();
      return '';
    });

    const ticks: number[] = [];
    let lastYear = '';
    labels.forEach((year, index) => {
      if (!year) return;
      if (year !== lastYear) {
        ticks.push(index);
        lastYear = year;
      }
    });

    return {
      chartData: normalized,
      indexLabels: labels,
      indexTicks: ticks,
      hoverTargets: normalized.filter((item) => item.isHoverTarget)
    };
  }, [cycleData]);

  // Halving events for vertical lines
  const halvingEvents = useMemo(() => {
    return chartData.filter(d => d.isHalving);
  }, [chartData]);

  const yDomain = useMemo(() => {
    // Fixed Log Scale: 10, 100, 1k, 10k, 100k, 1M, 10M
    return [10, 1000000]; // Covers $10 to $1M
  }, []);

  const yTicks = [10, 100, 1000, 10000, 100000, 1000000]; // Fixed ticks for clean log scale

  const currentPoint = currentPrice && chartData.length > 0
    ? [{
      timestamp: currentPrice.timestamp,
      xIndex: (() => {
        const timestamps = chartData.map((item) => item.timestamp);
        const validTimestamps = timestamps.filter((value): value is number => Number.isFinite(value));
        if (validTimestamps.length !== chartData.length) {
          return Math.max(chartData.length - 1, 0);
        }
        const first = validTimestamps[0];
        const last = validTimestamps[validTimestamps.length - 1];
        if (currentPrice.timestamp <= first) return 0;
        if (currentPrice.timestamp >= last) return Math.max(chartData.length - 1, 0);

        for (let i = 0; i < validTimestamps.length - 1; i += 1) {
          const start = validTimestamps[i];
          const end = validTimestamps[i + 1];
          if (currentPrice.timestamp >= start && currentPrice.timestamp <= end && end > start) {
            const ratio = (currentPrice.timestamp - start) / (end - start);
            return i + ratio;
          }
        }

        return Math.max(chartData.length - 1, 0);
      })(),
      price: currentPrice.price,
      isCurrent: true
    }]
    : [];

  const xAxisKey = 'xIndex';
  const xAxisScale = 'linear';
  const xTickFormatter = (value: number) => {
    const idx = Math.round(value);
    return indexLabels[idx] ?? '';
  };
  const xAxisDomain: [number, number] = [0, Math.max(chartData.length - 1, 0)];
  const xAxisTicks = indexTicks.length > 0 ? indexTicks : undefined;
  const formatHoverDate = (item: { date?: string; timestamp?: number | null }) => {
    if (typeof item.date === 'string' && item.date.length > 0) return item.date;
    if (item.timestamp !== null && item.timestamp !== undefined && Number.isFinite(item.timestamp)) return formatMonthLabel(item.timestamp);
    return '';
  };
  const resolveHoverPoint = (state: any) => {
    if (!state || !Number.isFinite(state.chartX) || !Number.isFinite(state.chartY)) {
      return null;
    }

    const yAxis = state.yAxisMap && Object.values(state.yAxisMap)[0];
    const xAxis = state.xAxisMap && Object.values(state.xAxisMap)[0];
    if (!yAxis || !xAxis) return null;

    const mouseValue = yAxis.scale.invert ? yAxis.scale.invert(state.chartY) : null;
    const mouseIndex = xAxis.scale.invert ? xAxis.scale.invert(state.chartX) : null;
    if (!Number.isFinite(mouseValue) || !Number.isFinite(mouseIndex)) return null;

    const candidates = [...hoverTargets, ...currentPoint].map((item) => ({
      xIndex: Number(item.xIndex),
      price: Number(item.price),
      dateLabel: formatHoverDate(item),
      isCurrent: Boolean((item as any).isCurrent)
    }));

    if (candidates.length === 0) return null;

    let best = candidates[0];
    let bestScore = Number.POSITIVE_INFINITY;
    for (const candidate of candidates) {
      const dx = Math.abs(candidate.xIndex - mouseIndex);
      const dy = Math.abs(Math.log(candidate.price) - Math.log(mouseValue));
      const score = dx + dy;
      if (score < bestScore) {
        bestScore = score;
        best = candidate;
      }
    }

    // Require the cursor to be reasonably close to a target point.
    if (bestScore > 0.6) return null;

    return {
      xIndex: best.xIndex,
      price: best.price,
      dateLabel: best.isCurrent ? 'Current' : best.dateLabel
    };
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-zinc-900">Bitcoin Cycle</h2>
          <p className="text-sm text-zinc-500 mt-1">비트코인 반감기 사이클 로그 차트 (Real-time)</p>
        </div>
        <div className="text-xs text-zinc-500 flex flex-col sm:items-end gap-1">
          {lastUpdated && <span>Updated: {lastUpdated.toLocaleString()}</span>}
          {priceWarning && <span className="text-orange-500 font-semibold">{priceWarning}</span>}
        </div>
      </div>

      <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
        {loading && <div className="py-20 text-center text-sm text-zinc-500">데이터를 불러오는 중...</div>}
        {error && <div className="py-20 text-center text-sm text-red-500">오류: {error}</div>}
        {!loading && !error && (
          <div className="h-[500px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={chartData}
                margin={{ top: 20, right: 40, left: 10, bottom: 20 }}
                onMouseMove={(state: any) => {
                  const next = resolveHoverPoint(state);
                  setHoverPoint(next);
                }}
                onMouseLeave={() => setHoverPoint(null)}
              >
                <CartesianGrid stroke="#f3f4f6" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey={xAxisKey}
                  type="number"
                  scale={xAxisScale}
                  domain={xAxisDomain}
                  allowDecimals={false}
                  ticks={xAxisTicks}
                  interval={0}
                  tickFormatter={xTickFormatter}
                  axisLine={{ stroke: '#e5e7eb' }}
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  tickMargin={10}
                />
                <YAxis
                  scale="log"
                  domain={yDomain}
                  ticks={yTicks}
                  tickFormatter={formatAxisPrice}
                  axisLine={false}
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  width={40}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  verticalAlign="top"
                  height={36}
                  iconType="plainline"
                  wrapperStyle={{ top: -10 }}
                />

                {hoverPoint && (
                  <>
                    <ReferenceLine
                      x={hoverPoint.xIndex}
                      stroke="#cbd5f5"
                      strokeDasharray="2 2"
                      ifOverflow="extendDomain"
                      label={{
                        position: 'bottom',
                        value: hoverPoint.dateLabel,
                        fill: '#6b7280',
                        fontSize: 11
                      }}
                    />
                    <ReferenceLine
                      y={hoverPoint.price}
                      stroke="#cbd5f5"
                      strokeDasharray="2 2"
                      ifOverflow="extendDomain"
                      label={{
                        position: 'left',
                        value: formatAxisPrice(hoverPoint.price),
                        fill: '#6b7280',
                        fontSize: 11
                      }}
                    />
                  </>
                )}

                {/* Halving Vertical Lines - Dotted */}
                {halvingEvents.map((event, idx) => (
                  <ReferenceLine
                    key={idx}
                    x={event.xIndex}
                    stroke="#e5e7eb"
                    strokeDasharray="3 3"
                    label={{
                      position: 'insideTop',
                      value: 'Halving',
                      fill: '#9ca3af',
                      fontSize: 10
                    }}
                  />
                ))}

                <Line
                  type="monotone"
                  dataKey="historyPrice"
                  name="Historical Path"
                  stroke="#111111"
                  strokeWidth={2}
                  dot={{ r: 3, strokeWidth: 0, fill: '#111111' }}
                  activeDot={{ r: 5, strokeWidth: 0 }}
                  connectNulls
                  isAnimationActive={false}
                >
                  <LabelList content={renderCustomizedLabel} dataKey="event" />
                </Line>
                <Line
                  type="monotone"
                  dataKey="predictionPrice"
                  name="Projected Path"
                  stroke="#111111"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ r: 3, strokeWidth: 1, fill: '#ffffff', stroke: '#111111' }}
                  activeDot={{ r: 5 }}
                  connectNulls
                  isAnimationActive={false}
                >
                  <LabelList content={renderCustomizedLabel} dataKey="event" />
                </Line>

                {/* Visual Scatter for Current Price */}
                {currentPoint.length > 0 && (
                  <Scatter
                    data={currentPoint}
                    dataKey="price"
                    shape={<PulseDot />}
                    legendType="none"
                    isAnimationActive={false}
                    zAxisId={0}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </section>
  );
};
