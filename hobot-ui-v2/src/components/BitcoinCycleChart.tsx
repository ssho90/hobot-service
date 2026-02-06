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

  // Prioritize payload that has isCurrent flag or label 'Current Price'
  const target =
    payload.find((item: any) => item.payload?.isCurrent || item.payload?.label === 'Current Price') ||
    payload.find((item: any) => item.payload?.event) ||
    payload[0];

  const data = target.payload || {};

  const dateLabel = Number.isFinite(data.timestamp)
    ? formatMonthLabel(data.timestamp)
    : typeof data.date === 'string'
      ? data.date
      : '';

  const priceLabel = typeof data.price === 'number' ? `$${formatPrice(data.price)}` : '';

  return (
    <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg shadow-xl text-xs z-50">
      <div className="font-semibold mb-1 text-zinc-300">
        {data.isCurrent || data.label === 'Current Price' ? 'Current Price' : data.event || 'Cycle Point'}
      </div>
      <div className="text-xl font-bold text-white mb-1">{priceLabel}</div>
      <div className="text-zinc-500">{dateLabel}</div>
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
    xValue: number;
    price: number;
    dateLabel: string;
  } | null>(null);

  const fetchLivePrice = async () => {
    // 1. Binance
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500); // Reduced timeout for faster fallback
      const res = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT&_=${Date.now()}`, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (res.ok) {
        const data = await res.json();
        return parseFloat(data.price);
      }
    } catch (e) {
      console.warn('Binance fetch failed, trying fallback...');
    }

    // 2. Coinbase
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      const res = await fetch(`https://api.coinbase.com/v2/prices/BTC-USD/spot?_=${Date.now()}`, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (res.ok) {
        const data = await res.json();
        return parseFloat(data.data.amount);
      }
    } catch (e) {
      console.warn('Coinbase fetch failed, trying fallback...');
    }

    // 3. CoinGecko (Backup)
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      const res = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&_=${Date.now()}`, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (res.ok) {
        const data = await res.json();
        return data.bitcoin.usd;
      }
    } catch (e) {
      console.warn('All live price fetches failed');
    }

    return null;
  };

  const fetchCycleData = async () => {
    try {
      if (initialLoadRef.current) {
        setLoading(true);
      }
      setError(null);

      // Fetch internal cycle data and live price in parallel
      const [cycleRes, livePrice] = await Promise.all([
        fetch('/api/bitcoin-cycle'),
        fetchLivePrice()
      ]);

      if (!cycleRes.ok) {
        throw new Error('비트코인 사이클 데이터를 불러오는데 실패했습니다.');
      }
      const result: ApiResponse = await cycleRes.json();
      if (!result.cycle_data) {
        throw new Error('사이클 데이터가 존재하지 않습니다.');
      }

      setCycleData(result.cycle_data);

      if (typeof livePrice === 'number') {
        // Use live price if available
        setCurrentPrice({ price: livePrice, timestamp: Date.now() });
        setLastUpdated(new Date());
        setPriceWarning(null);
      } else if (result.current_price && typeof result.current_price.price === 'number') {
        // Fallback to internal API price
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

      if (result.error && !livePrice) {
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

  const { chartData, indexTicks, hoverTargets } = useMemo(() => {
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

    const ticks: number[] = [];
    if (normalized.length > 0) {
      const minTime = normalized[0].timestamp as number;
      const maxTime = normalized[normalized.length - 1].timestamp as number;
      const minYear = new Date(minTime).getFullYear();
      const maxYear = new Date(maxTime).getFullYear();

      for (let y = minYear; y <= maxYear; y++) {
        ticks.push(new Date(Date.UTC(y, 0, 1)).getTime());
      }
    }

    return {
      chartData: normalized,
      indexTicks: ticks,   // These are now timestamps
      // Ensure hoverTargets (invisible scatter) have explicit x mapped to timestamp for correct positioning
      hoverTargets: normalized.filter((item) => item.isHoverTarget).map(d => ({
        ...d,
        x: d.timestamp,
        y: d.price
      }))
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

  // Current point logic is much simpler on a time scale axis
  // Explicitly map to x, y for Scatter to ensure correct positioning on number/time axis
  const currentPoint = currentPrice && chartData.length > 0
    ? [{
      x: currentPrice.timestamp, // Explicit x for Scatter
      y: currentPrice.price,     // Explicit y for Scatter
      timestamp: currentPrice.timestamp,
      price: currentPrice.price,
      isCurrent: true
    }]
    : [];

  const xAxisKey = 'timestamp';
  const xAxisScale = 'time'; // Recharts treats this as linear for numbers but good for semantics
  const xTickFormatter = (value: number) => {
    return new Date(value).getFullYear().toString();
  };

  // Domain is auto on time axis usually, or we can enforce
  const xAxisDomain: [number | 'auto', number | 'auto'] = ['auto', 'auto'];
  const xAxisTicks = indexTicks.length > 0 ? indexTicks : undefined;

  const formatHoverDate = (item: { date?: string; timestamp?: number | null }) => {
    if (typeof item.date === 'string' && item.date.length > 0) return item.date;
    if (item.timestamp !== null && item.timestamp !== undefined && Number.isFinite(item.timestamp)) return formatMonthLabel(item.timestamp);
    return '';
  };

  const resolveHoverPoint = (state: any) => {
    if (!state || !state.activePayload || state.activePayload.length === 0) {
      return null;
    }

    // Try to find a target point (Peak/Bottom or Current) in the active payload
    const targetPayload = state.activePayload.find((p: any) => {
      const data = p.payload;
      return data.isHoverTarget || data.isCurrent;
    });

    if (targetPayload) {
      const data = targetPayload.payload;
      return {
        xValue: Number(data.timestamp), // Now we use timestamp as xValue
        price: Number(data.price),
        dateLabel: formatHoverDate(data)
      };
    }

    return null;
  };

  const CustomXReferenceLabel = (props: any) => {
    const { viewBox, value } = props;
    const { x, y, height } = viewBox;
    return (
      <g>
        <rect
          x={x - 30}
          y={y + height}
          width={60}
          height={20}
          rx={4}
          fill="#374151"
        />
        <text
          x={x}
          y={y + height + 14}
          textAnchor="middle"
          fill="#ffffff"
          fontSize={11}
          fontWeight="bold"
        >
          {value}
        </text>
      </g>
    );
  };

  const CustomYReferenceLabel = (props: any) => {
    const { viewBox, value } = props;
    // Ensure we don't draw if coordinates are invalid (sometimes happens on initial render)
    if (!viewBox || !Number.isFinite(viewBox.x) || !Number.isFinite(viewBox.y)) return null;

    const { x, y } = viewBox;
    return (
      <g>
        <rect
          x={x - 50}
          y={y - 10}
          width={50}
          height={20}
          rx={4}
          fill="#374151"
        />
        <text
          x={x - 25}
          y={y + 4}
          textAnchor="middle"
          fill="#ffffff"
          fontSize={11}
          fontWeight="bold"
        >
          {value}
        </text>
      </g>
    );
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
                      x={hoverPoint.xValue}
                      stroke="#9ca3af"
                      strokeDasharray="3 3"
                      label={<CustomXReferenceLabel value={hoverPoint.dateLabel} />}
                    />
                    <ReferenceLine
                      y={hoverPoint.price}
                      stroke="#9ca3af"
                      strokeDasharray="3 3"
                      label={<CustomYReferenceLabel value={formatAxisPrice(hoverPoint.price)} />}
                    />
                  </>
                )}

                {/* Halving Vertical Lines - Dotted */}
                {halvingEvents.map((event, idx) => (
                  <ReferenceLine
                    key={idx}
                    x={event.timestamp!}
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

                {/* Invisible Scatter for Peak/Bottom targets to aid simple interaction if needed, 
                    though onMouseMove handles the math. It ensures data existence in chart context. */}
                <Scatter
                  data={hoverTargets}
                  dataKey="price"
                  fillOpacity={0} // Invisible
                  legendType="none"
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </section>
  );
};
