import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  BarChart3,
  Building2,
  ChevronDown,
  ChevronUp,
  Database,
  MapPinned,
  RefreshCw,
  Search,
} from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  fetchRealEstateQuery,
  type RealEstateQueryResponse,
  type RealEstateView,
} from '../services/realEstateService';
import {
  getLawdRegionName,
  getLawdRegionTree,
  parseLawdInputToCodes,
  searchLawdRegions,
  type LawdRegionItem,
} from '../constants/krRegion';

type FilterState = {
  startYm: string;
  endYm: string;
  lawdCodes: string;
  propertyType: string;
  transactionType: string;
};

type DataPanelTab = 'list' | 'chart';

type TrendPoint = {
  statYm: string;
  statYmLabel: string;
  txCount: number;
  totalPrice: number;
  avgPrice: number;
  regionCount: number;
} & Record<string, string | number | null>;

type ChartCompareRegion = {
  id: string;
  label: string;
  codes: string[];
  color: string;
};

const VIEW_LIMIT: Record<RealEstateView, number> = {
  detail: 200,
  monthly: 5000,
  region: 500,
};

const VIEW_LABEL: Record<RealEstateView, string> = {
  detail: '상세 거래',
  monthly: '월별 집계',
  region: '지역 집계',
};

const PROPERTY_TYPE_OPTIONS = [
  { value: 'apartment', label: '아파트' },
  { value: 'officetel', label: '오피스텔' },
  { value: 'multi_family', label: '연립/다세대' },
  { value: 'single_family', label: '단독/다가구' },
];

const TRANSACTION_TYPE_OPTIONS = [
  { value: 'sale', label: '매매' },
  { value: 'jeonse', label: '전세' },
  { value: 'monthly_rent', label: '월세' },
  { value: 'rent', label: '임대(통합)' },
];

// Colorblind-friendly palette extended
const CHART_COMPARE_COLORS = [
  '#0072B2', // Blue
  '#E69F00', // Orange
  '#009E73', // Green
  '#D55E00', // Red
  '#CC79A7', // Purple
  '#56B4E9', // Sky Blue
  '#F0E442', // Yellow (Readable on dark/mixed) - Check contrast
  '#8C564B', // Brown
  '#E377C2', // Pink
  '#7F7F7F', // Gray
  '#BCBD22', // Olive
  '#17BECF', // Cyan
];
const CHART_BASE_AVG_COLOR = CHART_COMPARE_COLORS[0];
const CHART_BASE_TX_COLOR = CHART_COMPARE_COLORS[1];
const MAX_CHART_COMPARE_REGIONS = 10;

const numberFormatter = new Intl.NumberFormat('ko-KR');
const ONE_MILLION = 1_000_000;
const TEN_MILLION = 10_000_000;
const HUNDRED_MILLION = 100_000_000;
const AUTO_APPLY_DEBOUNCE_MS = 350;

const isSameFilterState = (left: FilterState, right: FilterState): boolean =>
  left.startYm === right.startYm &&
  left.endYm === right.endYm &&
  left.lawdCodes === right.lawdCodes &&
  left.propertyType === right.propertyType &&
  left.transactionType === right.transactionType;

const parseNumeric = (value: unknown): number | null => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.replace(/,/g, ''));
    if (!Number.isNaN(parsed) && Number.isFinite(parsed)) return parsed;
  }
  return null;
};

const formatNumber = (value: unknown): string => {
  if (typeof value === 'number') return numberFormatter.format(value);
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (!Number.isNaN(parsed)) return numberFormatter.format(parsed);
  }
  return '-';
};

const formatKrwShort = (value: number): string => {
  if (!Number.isFinite(value)) return '-';
  const sign = value < 0 ? '-' : '';
  const truncated = Math.trunc(Math.abs(value) / ONE_MILLION) * ONE_MILLION;

  if (truncated === 0) return `${sign}0원`;

  if (truncated >= HUNDRED_MILLION) {
    const tenthEok = Math.trunc((truncated * 10) / HUNDRED_MILLION);
    const integerPart = Math.trunc(tenthEok / 10);
    const decimalPart = tenthEok % 10;
    return decimalPart === 0
      ? `${sign}${integerPart}억`
      : `${sign}${integerPart}.${decimalPart}억`;
  }

  if (truncated >= TEN_MILLION) {
    const tenthCheonMan = Math.trunc((truncated * 10) / TEN_MILLION);
    const integerPart = Math.trunc(tenthCheonMan / 10);
    const decimalPart = tenthCheonMan % 10;
    return decimalPart === 0
      ? `${sign}${integerPart}천만원`
      : `${sign}${integerPart}.${decimalPart}천만원`;
  }

  return `${sign}${Math.trunc(truncated / ONE_MILLION)}백만원`;
};

const formatCurrency = (value: unknown): string => {
  const parsed = parseNumeric(value);
  if (parsed === null) return '-';
  return formatKrwShort(parsed);
};

const formatDate = (value: unknown): string => {
  if (typeof value !== 'string' || !value.trim()) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString('ko-KR');
};

const toNumber = (value: unknown): number => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return 0;
};

const formatYmLabel = (value: string): string => {
  if (!/^\d{6}$/.test(value)) return value;
  return `${value.slice(0, 4)}-${value.slice(4, 6)}`;
};

const formatKrwCompact = (value: number): string => {
  return formatKrwShort(value);
};

const buildTrendData = (rows: Record<string, unknown>[]): TrendPoint[] => {
  const monthMap = new Map<
    string,
    { txCount: number; totalPrice: number; regionCodes: Set<string> }
  >();

  rows.forEach((row) => {
    const statYm = String(row.stat_ym ?? '').trim();
    if (!/^\d{6}$/.test(statYm)) return;

    const txCount = toNumber(row.tx_count);
    const totalPrice = toNumber(row.total_price);
    const lawdCd = String(row.lawd_cd ?? '').trim();

    const current = monthMap.get(statYm) ?? {
      txCount: 0,
      totalPrice: 0,
      regionCodes: new Set<string>(),
    };
    current.txCount += txCount;
    current.totalPrice += totalPrice;
    if (lawdCd) current.regionCodes.add(lawdCd);
    monthMap.set(statYm, current);
  });

  return Array.from(monthMap.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([statYm, aggregate]) => ({
      statYm,
      statYmLabel: formatYmLabel(statYm),
      txCount: aggregate.txCount,
      totalPrice: aggregate.totalPrice,
      avgPrice: aggregate.txCount > 0 ? aggregate.totalPrice / aggregate.txCount : 0,
      regionCount: aggregate.regionCodes.size,
    }));
};

const toYmString = (year: number, month: number): string => {
  return `${year}${String(month).padStart(2, '0')}`;
};

const iterateYmRange = (startYm: string, endYm: string): string[] => {
  if (!/^\d{6}$/.test(startYm) || !/^\d{6}$/.test(endYm)) return [];
  let year = Number(startYm.slice(0, 4));
  let month = Number(startYm.slice(4, 6));
  const endYear = Number(endYm.slice(0, 4));
  const endMonth = Number(endYm.slice(4, 6));
  const result: string[] = [];

  while (year < endYear || (year === endYear && month <= endMonth)) {
    result.push(toYmString(year, month));
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }

  return result;
};

const normalizeRegionToken = (value: string): string => value.replace(/\s+/g, '').toLowerCase();

const isAllRegionToken = (value: string): boolean => {
  const normalized = normalizeRegionToken(value);
  return (
    normalized === '전체' ||
    normalized === '전국' ||
    normalized === '전국전체' ||
    normalized === '전체지역' ||
    normalized === 'all'
  );
};

const buildTrendComparisonData = (
  rows: Record<string, unknown>[],
  regions: ChartCompareRegion[],
  startYm: string,
  endYm: string
): TrendPoint[] => {
  if (regions.length === 0) return buildTrendData(rows);
  const months = iterateYmRange(startYm, endYm);
  if (months.length === 0) return [];

  const monthRowMap = new Map<string, TrendPoint>(
    months.map((statYm) => [
      statYm,
      {
        statYm,
        statYmLabel: formatYmLabel(statYm),
        txCount: 0,
        totalPrice: 0,
        avgPrice: 0,
        regionCount: regions.length,
      },
    ])
  );
  const regionCodeSets = new Map(regions.map((region) => [region.id, new Set(region.codes)]));
  const regionMonthAgg = new Map<
    string,
    Map<string, { txCount: number; totalPrice: number }>
  >(
    regions.map((region) => [region.id, new Map()])
  );

  rows.forEach((row) => {
    const statYm = String(row.stat_ym ?? '').trim();
    if (!monthRowMap.has(statYm)) return;
    const lawdCd = String(row.lawd_cd ?? '').trim();
    if (!/^\d{5}$/.test(lawdCd)) return;
    const txCount = toNumber(row.tx_count);
    const totalPrice = toNumber(row.total_price);

    regions.forEach((region) => {
      const codes = regionCodeSets.get(region.id);
      if (!codes?.has(lawdCd)) return;
      const byMonth = regionMonthAgg.get(region.id);
      if (!byMonth) return;
      const current = byMonth.get(statYm) ?? { txCount: 0, totalPrice: 0 };
      current.txCount += txCount;
      current.totalPrice += totalPrice;
      byMonth.set(statYm, current);
    });
  });

  const trendRows: TrendPoint[] = [];
  months.forEach((statYm) => {
    const row = monthRowMap.get(statYm);
    if (!row) return;
    let sumTxCount = 0;
    let sumTotalPrice = 0;

    regions.forEach((region) => {
      const byMonth = regionMonthAgg.get(region.id);
      const aggregate = byMonth?.get(statYm);
      const txCount = aggregate?.txCount ?? 0;
      const totalPrice = aggregate?.totalPrice ?? 0;
      row[`tx_${region.id}`] = txCount;
      row[`avg_${region.id}`] = txCount > 0 ? totalPrice / txCount : null;
      sumTxCount += txCount;
      sumTotalPrice += totalPrice;
    });

    row.txCount = sumTxCount;
    row.totalPrice = sumTotalPrice;
    row.avgPrice = sumTxCount > 0 ? sumTotalPrice / sumTxCount : 0;
    trendRows.push(row);
  });

  return trendRows;
};

const parseTrendSeriesName = (name: string): { region: string; metric: 'tx' | 'avg' | null } => {
  if (name.endsWith(' 거래건수')) {
    return { region: name.slice(0, -' 거래건수'.length), metric: 'tx' };
  }
  if (name.endsWith(' 평균가')) {
    return { region: name.slice(0, -' 평균가'.length), metric: 'avg' };
  }
  return { region: name, metric: null };
};

const renderTrendTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ name?: string; value?: unknown; color?: string }>;
  label?: string | number;
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const regionMap = new Map<
    string,
    { color: string; tx?: number; avg?: number }
  >();

  payload.forEach((entry) => {
    const seriesName = String(entry.name ?? '');
    const { region, metric } = parseTrendSeriesName(seriesName);
    if (!metric) return;

    const numericValue = toNumber(entry.value);
    const current = regionMap.get(region) ?? { color: CHART_BASE_AVG_COLOR };
    if (entry.color && !current.color) {
      current.color = entry.color;
    }
    if (metric === 'avg') {
      current.avg = numericValue;
      if (entry.color) current.color = entry.color;
    } else {
      current.tx = numericValue;
      if (!current.color && entry.color) current.color = entry.color;
    }
    regionMap.set(region, current);
  });

  const rows = Array.from(regionMap.entries());
  if (rows.length === 0) return null;

  return (
    <div
      className="w-[170px] rounded-md border border-zinc-200 bg-white/95 backdrop-blur-sm shadow-xl"
      style={{ transform: 'translate(-50%, calc(-100% - 12px))' }}
    >
      <div className="px-2 py-1 border-b border-zinc-100 bg-gradient-to-r from-zinc-50 to-white rounded-t-md">
        <p className="text-[10px] font-semibold text-zinc-900 leading-tight">{label}</p>
      </div>
      <div className="p-1.5 space-y-1">
        {rows.map(([region, data]) => (
          <div key={`tooltip-${region}`} className="flex items-center gap-1 text-[10px] leading-tight">
            <span
              className="h-2 w-2 rounded-full shrink-0"
              style={{ backgroundColor: data.color }}
            />
            <span className="font-medium text-zinc-900 truncate">{region}</span>
            <span className="ml-auto text-zinc-500 shrink-0">{formatNumber(data.tx)}건</span>
            <span className="font-semibold text-blue-700 shrink-0">{formatCurrency(data.avg)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const getDefaultFilterState = (): FilterState => {
  const now = new Date();
  const endYear = now.getFullYear();
  const endMonth = now.getMonth() + 1;
  const end = toYmString(endYear, endMonth);

  const startDate = new Date(endYear, endMonth - 1, 1);
  startDate.setMonth(startDate.getMonth() - 11);
  const start = toYmString(startDate.getFullYear(), startDate.getMonth() + 1);

  return {
    startYm: start,
    endYm: end,
    lawdCodes: '전국 전체',
    propertyType: 'apartment',
    transactionType: 'sale',
  };
};

const RealEstatePage: React.FC = () => {
  const [view, setView] = useState<RealEstateView>('monthly');
  const [panelTab, setPanelTab] = useState<DataPanelTab>('chart');
  const [filters, setFilters] = useState<FilterState>(getDefaultFilterState);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(getDefaultFilterState);
  const [offset, setOffset] = useState(0);

  const [response, setResponse] = useState<RealEstateQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queriedAt, setQueriedAt] = useState<Date | null>(null);
  const [lawdWarning, setLawdWarning] = useState<string | null>(null);
  const [isLawdComposing, setIsLawdComposing] = useState(false);

  const [trendData, setTrendData] = useState<TrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [chartTooltipPosition, setChartTooltipPosition] = useState<{ x: number; y: number }>();
  const [chartRegionInput, setChartRegionInput] = useState('');
  const [chartRegionError, setChartRegionError] = useState<string | null>(null);
  const [chartCompareRegions, setChartCompareRegions] = useState<ChartCompareRegion[]>([]);
  const [isChartRegionComposing, setIsChartRegionComposing] = useState(false);
  const [isChartAutocompleteOpen, setIsChartAutocompleteOpen] = useState(false);
  const [isRegionTreeOpen, setIsRegionTreeOpen] = useState(false);
  const [isAutocompleteOpen, setIsAutocompleteOpen] = useState(false);
  const [colorPickerRegionId, setColorPickerRegionId] = useState<string | null>(null);
  const regionInputWrapperRef = useRef<HTMLDivElement | null>(null);
  const chartInputWrapperRef = useRef<HTMLDivElement | null>(null);
  const colorPickerRef = useRef<HTMLDivElement | null>(null);

  const pageLimit = VIEW_LIMIT[view];
  const regionTree = useMemo(() => getLawdRegionTree(), []);
  const parsedRegionPreview = useMemo(() => parseLawdInputToCodes(filters.lawdCodes), [filters.lawdCodes]);
  const isAllRegionInput = useMemo(() => isAllRegionToken(filters.lawdCodes), [filters.lawdCodes]);

  const regionQueryToken = useMemo(() => {
    const tokens = filters.lawdCodes.split(',');
    return (tokens[tokens.length - 1] ?? '').trim();
  }, [filters.lawdCodes]);

  const regionSuggestions = useMemo(
    () => searchLawdRegions(regionQueryToken, 16),
    [regionQueryToken]
  );

  const chartRegionQueryToken = useMemo(() => chartRegionInput.trim(), [chartRegionInput]);
  const chartRegionSuggestions = useMemo(
    () => searchLawdRegions(chartRegionQueryToken, 16),
    [chartRegionQueryToken]
  );

  const applyAutocompleteSelection = useCallback((item: LawdRegionItem) => {
    setFilters((prev) => {
      const parts = prev.lawdCodes.split(',');
      if (parts.length === 0) return { ...prev, lawdCodes: item.name };
      parts[parts.length - 1] = ` ${item.name}`;
      const nextValue = parts
        .map((part) => part.trim())
        .filter((part) => part.length > 0)
        .join(', ');
      return { ...prev, lawdCodes: nextValue };
    });
    setIsAutocompleteOpen(false);
  }, []);

  const appendRegionFromTree = useCallback((item: LawdRegionItem) => {
    setFilters((prev) => {
      const existing = prev.lawdCodes
        .split(',')
        .map((token) => token.trim())
        .filter((token) => token.length > 0);
      if (existing.includes(item.name)) return prev;
      const next = [...existing, item.name].join(', ');
      return { ...prev, lawdCodes: next };
    });
  }, []);

  const addChartCompareRegion = useCallback((inputValue: string): boolean => {
    const rawInput = inputValue.trim();
    if (!rawInput) {
      setChartRegionError('추가할 지역을 입력해주세요.');
      return false;
    }
    if (chartCompareRegions.length >= MAX_CHART_COMPARE_REGIONS) {
      setChartRegionError(`비교 지역은 최대 ${MAX_CHART_COMPARE_REGIONS}개까지 추가할 수 있습니다.`);
      return false;
    }

    const parsed = parseLawdInputToCodes(rawInput);
    if (parsed.codes.length === 0) {
      setChartRegionError('지역을 인식하지 못했습니다. 예: 서울, 서울 강남구, 11680');
      return false;
    }

    const codes = [...parsed.codes].sort();
    const id = codes.join('-');
    if (chartCompareRegions.some((region) => region.id === id)) {
      setChartRegionError('이미 추가된 지역입니다.');
      return false;
    }

    const label = /^\d{5}$/.test(rawInput) ? getLawdRegionName(rawInput) : rawInput;

    const usedColors = new Set(chartCompareRegions.map((r) => r.color));
    const availableColor = CHART_COMPARE_COLORS.find((c) => !usedColors.has(c));
    // Fallback usually shouldn't happen if MAX <= COLORS.length, but safe to cycle
    const nextColor =
      availableColor ??
      CHART_COMPARE_COLORS[chartCompareRegions.length % CHART_COMPARE_COLORS.length];

    const nextRegion: ChartCompareRegion = {
      id,
      label,
      codes,
      color: nextColor,
    };
    setChartCompareRegions((prev) => [...prev, nextRegion]);
    setChartRegionError(null);
    return true;
  }, [chartCompareRegions]);

  const handleAddChartRegion = useCallback(() => {
    const added = addChartCompareRegion(chartRegionInput);
    if (added) {
      setChartRegionInput('');
      setIsChartAutocompleteOpen(false);
    }
  }, [addChartCompareRegion, chartRegionInput]);

  const handleSelectChartRegionSuggestion = useCallback((item: LawdRegionItem) => {
    const added = addChartCompareRegion(item.name);
    if (added) {
      setChartRegionInput('');
      setIsChartAutocompleteOpen(false);
    }
  }, [addChartCompareRegion]);

  const handleRemoveChartRegion = useCallback((regionId: string) => {
    setChartCompareRegions((prev) => prev.filter((region) => region.id !== regionId));
    setChartRegionError(null);
  }, []);

  const handleResetChartRegions = useCallback(() => {
    setChartCompareRegions([]);
    setChartRegionInput('');
    setChartRegionError(null);
  }, []);

  const handleUpdateChartRegionColor = useCallback((regionId: string, newColor: string) => {
    setChartCompareRegions((prev) =>
      prev.map((region) => (region.id === regionId ? { ...region, color: newColor } : region))
    );
    setColorPickerRegionId(null);
  }, []);

  useEffect(() => {
    const onDocumentMouseDown = (event: MouseEvent) => {
      if (
        regionInputWrapperRef.current &&
        !regionInputWrapperRef.current.contains(event.target as Node)
      ) {
        setIsAutocompleteOpen(false);
      }
      if (
        chartInputWrapperRef.current &&
        !chartInputWrapperRef.current.contains(event.target as Node)
      ) {
        setIsChartAutocompleteOpen(false);
      }
      if (
        colorPickerRef.current &&
        !colorPickerRef.current.contains(event.target as Node)
      ) {
        setColorPickerRegionId(null);
      }
    };
    document.addEventListener('mousedown', onDocumentMouseDown);
    return () => document.removeEventListener('mousedown', onDocumentMouseDown);
  }, []);

  const runQuery = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const parsedLawd = parseLawdInputToCodes(appliedFilters.lawdCodes);
      const hasLawdInput = appliedFilters.lawdCodes.trim().length > 0;
      if (hasLawdInput && parsedLawd.codes.length === 0) {
        setError('지역 입력을 인식하지 못했습니다. 예: 서울, 경기, 서울 종로구, 11110');
        return;
      }

      setLawdWarning(
        parsedLawd.unknownTokens.length > 0
          ? `인식되지 않은 지역: ${parsedLawd.unknownTokens.join(', ')}`
          : null
      );

      const payload = await fetchRealEstateQuery({
        view,
        startYm: appliedFilters.startYm,
        endYm: appliedFilters.endYm,
        lawdCodes: parsedLawd.codes.join(','),
        propertyType: appliedFilters.propertyType,
        transactionType: appliedFilters.transactionType,
        limit: pageLimit,
        offset,
      });
      setResponse(payload);
      setQueriedAt(new Date());
    } catch (queryError) {
      const message =
        queryError instanceof Error
          ? queryError.message
          : '부동산 데이터를 불러오는 중 오류가 발생했습니다.';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [appliedFilters, offset, pageLimit, view]);

  const runTrendQuery = useCallback(async () => {
    setTrendLoading(true);
    setTrendError(null);
    try {
      const parsedLawd = parseLawdInputToCodes(appliedFilters.lawdCodes);
      const hasLawdInput = appliedFilters.lawdCodes.trim().length > 0;
      if (hasLawdInput && parsedLawd.codes.length === 0) {
        setTrendData([]);
        return;
      }

      const requestedCodes =
        chartCompareRegions.length > 0
          ? Array.from(new Set(chartCompareRegions.flatMap((region) => region.codes))).sort()
          : parsedLawd.codes;

      const payload = await fetchRealEstateQuery({
        view: 'monthly',
        startYm: appliedFilters.startYm,
        endYm: appliedFilters.endYm,
        lawdCodes: requestedCodes.join(','),
        propertyType: appliedFilters.propertyType,
        transactionType: appliedFilters.transactionType,
        limit: 5000,
        offset: 0,
      });

      if (chartCompareRegions.length > 0) {
        setTrendData(
          buildTrendComparisonData(
            payload.rows,
            chartCompareRegions,
            appliedFilters.startYm,
            appliedFilters.endYm
          )
        );
      } else {
        setTrendData(buildTrendData(payload.rows));
      }
    } catch (queryError) {
      const message =
        queryError instanceof Error
          ? queryError.message
          : '추이 차트를 불러오는 중 오류가 발생했습니다.';
      setTrendError(message);
      setTrendData([]);
    } finally {
      setTrendLoading(false);
    }
  }, [appliedFilters, chartCompareRegions]);

  useEffect(() => {
    runQuery();
  }, [runQuery]);

  useEffect(() => {
    runTrendQuery();
  }, [runTrendQuery]);

  useEffect(() => {
    if (isLawdComposing) return;
    if (filters.lawdCodes === appliedFilters.lawdCodes) return;

    const timeoutId = window.setTimeout(() => {
      setOffset(0);
      setAppliedFilters((prev) => {
        if (isSameFilterState(prev, filters)) return prev;
        return { ...filters };
      });
    }, AUTO_APPLY_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [
    appliedFilters.lawdCodes,
    filters.endYm,
    filters.lawdCodes,
    filters.propertyType,
    filters.startYm,
    filters.transactionType,
    isLawdComposing,
  ]);

  const total = response?.total ?? 0;
  const currentPage = Math.floor(offset / pageLimit) + 1;
  const totalPages = total > 0 ? Math.ceil(total / pageLimit) : 1;

  const canPrev = offset > 0 && !loading;
  const canNext = offset + pageLimit < total && !loading;

  const handleApplyFilters = useCallback(() => {
    setOffset(0);
    setAppliedFilters((prev) => {
      if (isSameFilterState(prev, filters)) return prev;
      return { ...filters };
    });
  }, [filters]);

  const handleResetFilters = useCallback(() => {
    const defaults = getDefaultFilterState();
    setFilters(defaults);
    setAppliedFilters(defaults);
    setOffset(0);
    setLawdWarning(null);
  }, []);

  const handleViewChange = useCallback((nextView: RealEstateView) => {
    setView(nextView);
    setOffset(0);
  }, []);

  const rows = response?.rows ?? [];

  const sourceLabel = useMemo(() => {
    if (!response) return '-';
    if (response.source === 'mysql_transactions') return 'MySQL 상세 원본';
    if (response.source === 'neo4j_monthly_summary') return 'Neo4j 집계 그래프';
    if (response.source === 'mysql_monthly_summary_fallback') return 'MySQL 집계 폴백';
    return response.source;
  }, [response]);

  const statusLabel = useMemo(() => {
    if (!response) return '-';
    if (response.source === 'mysql_transactions') return 'RDB 상세 조회';
    if (response.fallback_used) return 'Fallback 적용됨';
    return 'Graph 우선 조회';
  }, [response]);

  const statusClassName = useMemo(() => {
    if (!response) return 'text-zinc-700';
    if (response.source === 'mysql_transactions') return 'text-blue-700';
    if (response.fallback_used) return 'text-amber-700';
    return 'text-emerald-700';
  }, [response]);

  const isChartComparisonMode = chartCompareRegions.length > 0;
  const chartFilterRegionLabels = useMemo(() => {
    const raw = appliedFilters.lawdCodes.trim();
    if (!raw) return ['전체 지역'];
    if (isAllRegionToken(raw)) return ['전체 지역'];
    const labels = raw
      .split(',')
      .map((token) => token.trim())
      .filter((token) => token.length > 0)
      .map((token) => (/^\d{5}$/.test(token) ? getLawdRegionName(token) : token));
    return Array.from(new Set(labels));
  }, [appliedFilters.lawdCodes]);
  const defaultChartRegionLabel = useMemo(() => {
    if (chartFilterRegionLabels.length === 0) return '전체 지역';
    if (chartFilterRegionLabels.length === 1) return chartFilterRegionLabels[0];
    if (chartFilterRegionLabels.length <= 3) return chartFilterRegionLabels.join('/');
    return `${chartFilterRegionLabels[0]} 외 ${chartFilterRegionLabels.length - 1}`;
  }, [chartFilterRegionLabels]);
  const chartBarSize = useMemo(() => {
    const regionCount = Math.max(chartCompareRegions.length, 1);
    return Math.max(3, Math.floor(20 / regionCount));
  }, [chartCompareRegions.length]);

  return (
    <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
      <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-zinc-900 tracking-tight flex items-center gap-3">
            <Building2 className="h-8 w-8 text-blue-600" />
            KR 부동산
          </h1>
          <p className="text-zinc-500 mt-1">
            상세 거래(RDB)와 월/지역 집계(Graph)를 같은 화면에서 조회합니다.
          </p>
        </div>
        <div className="text-sm text-zinc-500">
          마지막 조회: {queriedAt ? queriedAt.toLocaleString('ko-KR', { hour12: false }) : '-'}
        </div>
      </div>

      <div className="bg-white border border-zinc-200 rounded-2xl p-4 md:p-5 shadow-sm mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-3">
          <input
            value={filters.startYm}
            onChange={(event) => setFilters((prev) => ({ ...prev, startYm: event.target.value }))}
            placeholder="조회 시작월 (YYYYMM)"
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            value={filters.endYm}
            onChange={(event) => setFilters((prev) => ({ ...prev, endYm: event.target.value }))}
            placeholder="조회 종료월 (YYYYMM)"
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div ref={regionInputWrapperRef} className="relative md:col-span-2">
            <input
              value={filters.lawdCodes}
              onFocus={() => setIsAutocompleteOpen(true)}
              onCompositionStart={() => setIsLawdComposing(true)}
              onCompositionEnd={() => setIsLawdComposing(false)}
              onChange={(event) => {
                setFilters((prev) => ({ ...prev, lawdCodes: event.target.value }));
                setIsAutocompleteOpen(true);
              }}
              placeholder="지역/코드 CSV (예: 서울 전체, 경기, 서울 종로구, 11110, 전국 전체)"
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {isAutocompleteOpen && regionQueryToken.length > 0 && (
              <div className="absolute z-20 mt-1 w-full rounded-xl border border-zinc-200 bg-white shadow-lg overflow-hidden">
                {regionSuggestions.length > 0 ? (
                  <div className="max-h-72 overflow-y-auto py-1">
                    {regionSuggestions.map((item) => (
                      <button
                        type="button"
                        key={`${item.code}-${item.name}`}
                        onClick={() => applyAutocompleteSelection(item)}
                        className="w-full px-3 py-2 text-left hover:bg-zinc-50 transition-colors"
                      >
                        <div className="text-sm font-medium text-zinc-900">{item.name}</div>
                        <div className="text-xs text-zinc-500">{item.code}</div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="px-3 py-2 text-xs text-zinc-500">일치하는 지역이 없습니다.</div>
                )}
              </div>
            )}
          </div>
          <select
            value={filters.propertyType}
            onChange={(event) => setFilters((prev) => ({ ...prev, propertyType: event.target.value }))}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {PROPERTY_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            value={filters.transactionType}
            onChange={(event) => setFilters((prev) => ({ ...prev, transactionType: event.target.value }))}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {TRANSACTION_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={handleApplyFilters}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 text-white px-4 py-2 text-sm font-medium hover:bg-zinc-800 disabled:opacity-60"
          >
            <Search className="h-4 w-4" />
            조회
          </button>
          <button
            type="button"
            onClick={() => setIsRegionTreeOpen((prev) => !prev)}
            className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100"
          >
            {isRegionTreeOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            지역 트리 보기
          </button>
          <button
            onClick={handleResetFilters}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
          >
            <RefreshCw className="h-4 w-4" />
            초기화
          </button>
          <button
            type="button"
            onClick={() =>
              appendRegionFromTree({
                code: 'ALL',
                name: '전국 전체',
                sidoName: '전국',
                districtName: '전체',
              })
            }
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
          >
            전국 전체 추가
          </button>
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          지역 입력은 코드(`11110`) 또는 이름(`서울`, `Seoul`, `서울 전체`, `전국 전체`)을 지원합니다.
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          금액 표시는 백만원 미만 절사 후 `1.5억`, `12억`, `9천만원` 형식으로 보여줍니다.
        </p>
        {filters.lawdCodes.trim().length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-xs text-zinc-500">입력 인식 결과:</span>
            {isAllRegionInput ? (
              <span className="inline-flex items-center rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-xs text-zinc-700">
                전국 전체
              </span>
            ) : parsedRegionPreview.codes.length > 0 ? (
              <>
                {parsedRegionPreview.codes.slice(0, 8).map((code) => (
                  <span
                    key={code}
                    className="inline-flex items-center rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-xs text-zinc-700"
                  >
                    {getLawdRegionName(code)}
                  </span>
                ))}
                {parsedRegionPreview.codes.length > 8 && (
                  <span className="text-xs text-zinc-500">
                    +{parsedRegionPreview.codes.length - 8}개
                  </span>
                )}
              </>
            ) : (
              <span className="text-xs text-zinc-500">아직 인식된 지역이 없습니다.</span>
            )}
          </div>
        )}
      </div>

      {isRegionTreeOpen && (
        <div className="bg-white border border-zinc-200 rounded-2xl shadow-sm overflow-hidden mb-6">
          <div className="px-5 py-4 border-b border-zinc-100 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-zinc-900">입력 가능한 지역 트리</h2>
              <p className="text-sm text-zinc-500 mt-1">원하는 지역을 클릭하면 입력칸에 자동 추가됩니다.</p>
            </div>
            <button
              type="button"
              onClick={() => setIsRegionTreeOpen(false)}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
            >
              닫기
            </button>
          </div>
          <div className="p-4 max-h-[420px] overflow-y-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {regionTree.map((group) => (
              <details
                key={group.sidoName}
                open={group.sidoName === '서울' || group.sidoName === '경기'}
                className="rounded-lg border border-zinc-200 bg-zinc-50/50 px-3 py-2"
              >
                <summary className="cursor-pointer text-sm font-semibold text-zinc-800">
                  {group.sidoName} ({group.items.length})
                </summary>
                <div className="mt-2 max-h-52 overflow-y-auto space-y-1">
                  <button
                    type="button"
                    onClick={() =>
                      appendRegionFromTree({
                        code: `${group.sidoName}-all`,
                        name: `${group.sidoName} 전체`,
                        sidoName: group.sidoName,
                        districtName: '전체',
                      })
                    }
                    className="w-full flex items-center justify-between rounded-md px-2 py-1.5 text-left bg-blue-50 text-blue-700 hover:bg-blue-100"
                  >
                    <span className="text-xs font-medium">{group.sidoName} 전체</span>
                    <span className="text-[11px]">ALL</span>
                  </button>
                  {group.items.map((item) => (
                    <button
                      type="button"
                      key={item.code}
                      onClick={() => appendRegionFromTree(item)}
                      className="w-full flex items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-white"
                    >
                      <span className="text-xs text-zinc-800">{item.name}</span>
                      <span className="text-[11px] text-zinc-500">{item.code}</span>
                    </button>
                  ))}
                </div>
              </details>
            ))}
          </div>
        </div>
      )}

      <div className="border-b border-zinc-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {(['chart', 'list'] as DataPanelTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setPanelTab(tab)}
              className={`${panelTab === tab
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-zinc-500 hover:text-zinc-700'
                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
            >
              {tab === 'chart' ? '차트 보기' : '리스트 보기'}
            </button>
          ))}
        </nav>
      </div>

      {panelTab === 'list' && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {(['detail', 'monthly', 'region'] as RealEstateView[]).map((tab) => (
            <button
              key={tab}
              onClick={() => handleViewChange(tab)}
              className={`rounded-lg px-4 py-2 text-sm font-medium border transition-colors ${view === tab
                ? 'bg-blue-600 border-blue-600 text-white'
                : 'bg-white border-zinc-200 text-zinc-700 hover:bg-zinc-50'
                }`}
            >
              {VIEW_LABEL[tab]}
            </button>
          ))}
        </div>
      )}

      {panelTab === 'list' && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="rounded-xl border border-zinc-200 bg-white p-4">
            <p className="text-xs text-zinc-500">전체 건수</p>
            <p className="text-2xl font-semibold text-zinc-900">{formatNumber(total)}</p>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4">
            <p className="text-xs text-zinc-500">현재 뷰</p>
            <p className="text-base font-semibold text-zinc-900">{VIEW_LABEL[view]}</p>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4">
            <p className="text-xs text-zinc-500">데이터 소스</p>
            <p className="text-sm font-semibold text-zinc-900">{sourceLabel}</p>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4">
            <p className="text-xs text-zinc-500">상태</p>
            <p className={`text-sm font-semibold ${statusClassName}`}>{statusLabel}</p>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-red-700 font-medium">조회 실패</p>
            <p className="text-red-600 text-sm mt-1">{error}</p>
          </div>
        </div>
      )}

      {lawdWarning && (
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-amber-700 font-medium">일부 지역을 인식하지 못했습니다</p>
            <p className="text-amber-700 text-sm mt-1">{lawdWarning}</p>
          </div>
        </div>
      )}

      {panelTab === 'chart' && (
        <>
          <div className="bg-white border border-zinc-200 rounded-2xl shadow-sm p-4 mb-4">
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">지역 비교</h2>
            <div className="flex flex-col md:flex-row gap-2">
              <div ref={chartInputWrapperRef} className="relative flex-1">
                <input
                  value={chartRegionInput}
                  onFocus={() => setIsChartAutocompleteOpen(true)}
                  onChange={(event) => {
                    setChartRegionInput(event.target.value);
                    setIsChartAutocompleteOpen(true);
                    if (chartRegionError) setChartRegionError(null);
                  }}
                  onCompositionStart={() => setIsChartRegionComposing(true)}
                  onCompositionEnd={() => setIsChartRegionComposing(false)}
                  onKeyDown={(event) => {
                    if (isChartRegionComposing || event.nativeEvent.isComposing) return;
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      handleAddChartRegion();
                    }
                  }}
                  placeholder="비교 지역 입력 (예: 서울 강남구, 서울 전체, 경기, 11680)"
                  className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {isChartAutocompleteOpen && chartRegionQueryToken.length > 0 && (
                  <div className="absolute z-20 mt-1 w-full rounded-xl border border-zinc-200 bg-white shadow-lg overflow-hidden">
                    {chartRegionSuggestions.length > 0 ? (
                      <div className="max-h-72 overflow-y-auto py-1">
                        {chartRegionSuggestions.map((item) => (
                          <button
                            type="button"
                            key={`chart-${item.code}-${item.name}`}
                            onClick={() => handleSelectChartRegionSuggestion(item)}
                            className="w-full px-3 py-2 text-left hover:bg-zinc-50 transition-colors"
                          >
                            <div className="text-sm font-medium text-zinc-900">{item.name}</div>
                            <div className="text-xs text-zinc-500">{item.code}</div>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="px-3 py-2 text-xs text-zinc-500">일치하는 지역이 없습니다.</div>
                    )}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={handleAddChartRegion}
                disabled={chartCompareRegions.length >= MAX_CHART_COMPARE_REGIONS}
                className="inline-flex items-center justify-center rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-500 disabled:opacity-50"
              >
                지역 추가
              </button>
              <button
                type="button"
                onClick={handleResetChartRegions}
                className="inline-flex items-center justify-center rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
              >
                지역 초기화
              </button>
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              비교 지역은 최대 {MAX_CHART_COMPARE_REGIONS}개까지 추가됩니다. (미입력 시 필터 지역 기준 단일 추이)
            </p>
            {chartRegionError && <p className="mt-2 text-xs text-red-600">{chartRegionError}</p>}
            {chartCompareRegions.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {chartCompareRegions.map((region) => (
                  <div
                    key={region.id}
                    className="relative inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs shadow-sm transition-all hover:bg-zinc-100"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setColorPickerRegionId(colorPickerRegionId === region.id ? null : region.id)
                      }
                      className="group relative flex items-center justify-center focus:outline-none"
                    >
                      <span
                        className="h-3 w-3 rounded-full ring-2 ring-transparent transition-all group-hover:scale-110 group-active:scale-95"
                        style={{ backgroundColor: region.color }}
                      />
                      <span className="sr-only">색상 변경</span>
                    </button>

                    <span className="font-medium text-zinc-700">{region.label}</span>

                    <button
                      type="button"
                      onClick={() => handleRemoveChartRegion(region.id)}
                      className="ml-1 -mr-1 rounded-full p-0.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-600 focus:outline-none"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        className="h-4 w-4"
                      >
                        <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                      </svg>
                    </button>

                    {colorPickerRegionId === region.id && (
                      <div
                        ref={colorPickerRef}
                        className="absolute left-0 top-full z-50 mt-2 w-48 rounded-xl border border-zinc-200 bg-white p-3 shadow-xl ring-1 ring-black ring-opacity-5"
                      >
                        <div className="mb-2 text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                          색상 선택
                        </div>
                        <div className="grid grid-cols-4 gap-2">
                          {CHART_COMPARE_COLORS.map((color) => (
                            <button
                              key={color}
                              type="button"
                              onClick={() => handleUpdateChartRegionColor(region.id, color)}
                              className={`h-6 w-6 rounded-full transition-transform hover:scale-110 focus:outline-none ring-2 ring-offset-1 ${region.color === color ? 'ring-zinc-400 scale-110' : 'ring-transparent'
                                }`}
                              style={{ backgroundColor: color }}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-white border border-zinc-200 rounded-2xl shadow-sm overflow-visible mb-6">
            <div className="px-5 py-4 border-b border-zinc-100">
              <h2 className="text-lg font-semibold text-zinc-900">가격/거래건수 추이</h2>
              <p className="text-sm text-zinc-500 mt-1">
                월별 평균가(가중 평균)와 거래건수 흐름입니다.
              </p>
            </div>
            {isChartComparisonMode && (
              <div className="px-5 pt-3 flex flex-wrap items-center gap-3">
                {chartCompareRegions.map((region) => (
                  <span key={`legend-${region.id}`} className="inline-flex items-center gap-2 text-xs text-zinc-700">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: region.color }} />
                    {region.label}
                  </span>
                ))}
              </div>
            )}
            {!isChartComparisonMode && (
              <div className="px-5 pt-3 flex flex-wrap items-center gap-2">
                <span className="text-xs text-zinc-500 mr-1">대상 지역</span>
                {chartFilterRegionLabels.slice(0, 6).map((label) => (
                  <span
                    key={`filter-region-${label}`}
                    className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs text-zinc-700"
                  >
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: CHART_BASE_AVG_COLOR }} />
                    {label}
                  </span>
                ))}
                {chartFilterRegionLabels.length > 6 && (
                  <span className="text-xs text-zinc-500">+{chartFilterRegionLabels.length - 6}개</span>
                )}
              </div>
            )}
            <div className="p-4 h-[340px]">
              {trendLoading ? (
                <div className="h-full flex items-center justify-center">
                  <div className="h-8 w-8 border-4 border-zinc-200 border-t-blue-500 rounded-full animate-spin" />
                </div>
              ) : trendError ? (
                <div className="h-full flex items-center justify-center text-red-600 text-sm">
                  {trendError}
                </div>
              ) : trendData.length === 0 ? (
                <div className="h-full flex items-center justify-center text-zinc-500 text-sm">
                  차트 데이터가 없습니다.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={trendData}
                    margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
                    onMouseMove={(state: any) => {
                      if (
                        state &&
                        state.isTooltipActive &&
                        typeof state.chartX === 'number' &&
                        typeof state.chartY === 'number'
                      ) {
                        setChartTooltipPosition({ x: state.chartX, y: state.chartY });
                      }
                    }}
                    onMouseLeave={() => setChartTooltipPosition(undefined)}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                    <XAxis dataKey="statYmLabel" tick={{ fontSize: 12, fill: '#52525b' }} />
                    <YAxis
                      yAxisId="left"
                      tick={{ fontSize: 12, fill: '#52525b' }}
                      tickFormatter={(value) => formatKrwCompact(Number(value))}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      tick={{ fontSize: 12, fill: '#52525b' }}
                      tickFormatter={(value) => formatNumber(value)}
                    />
                    <Tooltip
                      content={renderTrendTooltip}
                      offset={0}
                      animationDuration={80}
                      position={chartTooltipPosition}
                      allowEscapeViewBox={{ x: true, y: true }}
                      wrapperStyle={{ zIndex: 50, pointerEvents: 'none' }}
                      cursor={{ stroke: '#94a3b8', strokeWidth: 1, strokeDasharray: '3 3' }}
                    />
                    {!isChartComparisonMode && <Legend />}

                    {isChartComparisonMode ? (
                      <>
                        {chartCompareRegions.map((region) => (
                          <Bar
                            key={`bar-${region.id}`}
                            yAxisId="right"
                            dataKey={`tx_${region.id}`}
                            name={`${region.label} 거래건수`}
                            fill={region.color}
                            barSize={chartBarSize}
                          />
                        ))}
                        {chartCompareRegions.map((region) => (
                          <Line
                            key={`line-${region.id}`}
                            yAxisId="left"
                            type="monotone"
                            dataKey={`avg_${region.id}`}
                            name={`${region.label} 평균가`}
                            stroke={region.color}
                            strokeWidth={2.2}
                            dot={false}
                            connectNulls={false}
                          />
                        ))}
                      </>
                    ) : (
                      <>
                        <Bar
                          yAxisId="right"
                          dataKey="txCount"
                          name={`${defaultChartRegionLabel} 거래건수`}
                          fill={CHART_BASE_TX_COLOR}
                          barSize={20}
                        />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="avgPrice"
                          name={`${defaultChartRegionLabel} 평균가`}
                          stroke={CHART_BASE_AVG_COLOR}
                          strokeWidth={2.5}
                          dot={false}
                        />
                      </>
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </>
      )
      }

      {
        panelTab === 'list' && (
          <>
            <div className="bg-white border border-zinc-200 rounded-2xl shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-zinc-100 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-900 flex items-center gap-2">
                  {view === 'detail' && <Database className="h-5 w-5 text-blue-600" />}
                  {view === 'monthly' && <BarChart3 className="h-5 w-5 text-blue-600" />}
                  {view === 'region' && <MapPinned className="h-5 w-5 text-blue-600" />}
                  {VIEW_LABEL[view]} 데이터
                </h2>
                <button
                  onClick={runQuery}
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
                >
                  <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                  새로고침
                </button>
              </div>

              <div className="overflow-x-auto">
                {loading ? (
                  <div className="py-16 flex items-center justify-center">
                    <div className="h-8 w-8 border-4 border-zinc-200 border-t-blue-500 rounded-full animate-spin" />
                  </div>
                ) : rows.length === 0 ? (
                  <div className="py-16 text-center text-zinc-500">
                    조건에 맞는 데이터가 없습니다.
                  </div>
                ) : (
                  <>
                    {view === 'detail' && (
                      <table className="min-w-full text-sm">
                        <thead className="bg-zinc-50 text-zinc-600">
                          <tr>
                            <th className="px-4 py-3 text-left font-medium">계약일</th>
                            <th className="px-4 py-3 text-left font-medium">지역</th>
                            <th className="px-4 py-3 text-left font-medium">아파트명</th>
                            <th className="px-4 py-3 text-left font-medium">동</th>
                            <th className="px-4 py-3 text-left font-medium">지번</th>
                            <th className="px-4 py-3 text-right font-medium">거래가</th>
                            <th className="px-4 py-3 text-right font-medium">면적(㎡)</th>
                            <th className="px-4 py-3 text-right font-medium">층</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-100">
                          {rows.map((row, index) => (
                            <tr key={`${String(row.id ?? 'detail')}-${index}`} className="hover:bg-zinc-50">
                              <td className="px-4 py-3">{formatDate(row.contract_date)}</td>
                              <td className="px-4 py-3">
                                <div className="font-medium text-zinc-900">{getLawdRegionName(row.lawd_cd)}</div>
                                <div className="text-xs text-zinc-500">{String(row.lawd_cd ?? '-')}</div>
                              </td>
                              <td className="px-4 py-3">{String(row.apt_name ?? '-')}</td>
                              <td className="px-4 py-3">{String(row.umd_name ?? '-')}</td>
                              <td className="px-4 py-3">{String(row.jibun ?? '-')}</td>
                              <td className="px-4 py-3 text-right font-medium">{formatCurrency(row.price)}</td>
                              <td className="px-4 py-3 text-right">{formatNumber(row.area_m2)}</td>
                              <td className="px-4 py-3 text-right">{formatNumber(row.floor_no)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}

                    {view === 'monthly' && (
                      <table className="min-w-full text-sm">
                        <thead className="bg-zinc-50 text-zinc-600">
                          <tr>
                            <th className="px-4 py-3 text-left font-medium">월</th>
                            <th className="px-4 py-3 text-left font-medium">지역</th>
                            <th className="px-4 py-3 text-right font-medium">거래건수</th>
                            <th className="px-4 py-3 text-right font-medium">평균가</th>
                            <th className="px-4 py-3 text-right font-medium">평균 ㎡당가</th>
                            <th className="px-4 py-3 text-right font-medium">최저가</th>
                            <th className="px-4 py-3 text-right font-medium">최고가</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-100">
                          {rows.map((row, index) => (
                            <tr key={`${String(row.stat_ym ?? 'monthly')}-${String(row.lawd_cd ?? index)}`} className="hover:bg-zinc-50">
                              <td className="px-4 py-3">{String(row.stat_ym ?? '-')}</td>
                              <td className="px-4 py-3">
                                <div className="font-medium text-zinc-900">{getLawdRegionName(row.lawd_cd)}</div>
                                <div className="text-xs text-zinc-500">{String(row.lawd_cd ?? '-')}</div>
                              </td>
                              <td className="px-4 py-3 text-right">{formatNumber(row.tx_count)}</td>
                              <td className="px-4 py-3 text-right font-medium">{formatCurrency(row.avg_price)}</td>
                              <td className="px-4 py-3 text-right">{formatCurrency(row.avg_price_per_m2)}</td>
                              <td className="px-4 py-3 text-right">{formatCurrency(row.min_price)}</td>
                              <td className="px-4 py-3 text-right">{formatCurrency(row.max_price)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}

                    {view === 'region' && (
                      <table className="min-w-full text-sm">
                        <thead className="bg-zinc-50 text-zinc-600">
                          <tr>
                            <th className="px-4 py-3 text-left font-medium">지역</th>
                            <th className="px-4 py-3 text-right font-medium">거래건수</th>
                            <th className="px-4 py-3 text-right font-medium">평균가</th>
                            <th className="px-4 py-3 text-right font-medium">누적 거래금액</th>
                            <th className="px-4 py-3 text-right font-medium">집계 월수</th>
                            <th className="px-4 py-3 text-right font-medium">최저가</th>
                            <th className="px-4 py-3 text-right font-medium">최고가</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-100">
                          {rows.map((row, index) => (
                            <tr key={`${String(row.lawd_cd ?? 'region')}-${index}`} className="hover:bg-zinc-50">
                              <td className="px-4 py-3">
                                <div className="font-medium text-zinc-900">{getLawdRegionName(row.lawd_cd)}</div>
                                <div className="text-xs text-zinc-500">{String(row.lawd_cd ?? '-')}</div>
                              </td>
                              <td className="px-4 py-3 text-right">{formatNumber(row.tx_count)}</td>
                              <td className="px-4 py-3 text-right font-medium">{formatCurrency(row.avg_price)}</td>
                              <td className="px-4 py-3 text-right">{formatCurrency(row.total_price)}</td>
                              <td className="px-4 py-3 text-right">{formatNumber(row.month_points)}</td>
                              <td className="px-4 py-3 text-right">{formatCurrency(row.min_price)}</td>
                              <td className="px-4 py-3 text-right">{formatCurrency(row.max_price)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </>
                )}
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <p className="text-sm text-zinc-500">
                Page {currentPage} / {totalPages} ({formatNumber(total)}건)
              </p>
              <div className="flex items-center gap-2">
                <button
                  disabled={!canPrev}
                  onClick={() => setOffset((prev) => Math.max(0, prev - pageLimit))}
                  className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-40"
                >
                  이전
                </button>
                <button
                  disabled={!canNext}
                  onClick={() => setOffset((prev) => prev + pageLimit)}
                  className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-40"
                >
                  다음
                </button>
              </div>
            </div>
          </>
        )
      }
    </main >
  );
};

export default RealEstatePage;
