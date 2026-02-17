import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { AlertCircle, Database, Loader2, RefreshCw, Shield } from 'lucide-react';

type IndicatorHealth = 'healthy' | 'stale' | 'missing' | 'disabled';
type SourceGroupFilter = 'ALL' | 'US_MACRO' | 'KR_MACRO' | 'KR_CORPORATE' | 'OTHER';

interface IndicatorStatusRow {
  code: string;
  name: string;
  description: string;
  country: string;
  source: string;
  frequency: string;
  unit: string;
  collection_enabled: boolean;
  expected_interval_hours: number;
  last_observation_date: string | null;
  last_collected_at: string | null;
  latest_value: number | null;
  health: IndicatorHealth;
  lag_hours: number | null;
  stale_threshold_hours: number | null;
  is_stale: boolean;
  note: string;
  latest_source?: string | null;
}

interface SummaryCounter {
  total: number;
  healthy: number;
  stale: number;
  missing: number;
  disabled: number;
}

interface IndicatorApiResponse {
  status: string;
  generated_at: string;
  summary: SummaryCounter & {
    by_country: Record<string, SummaryCounter>;
  };
  indicators: IndicatorStatusRow[];
}

const HEALTH_LABELS: Record<IndicatorHealth, string> = {
  healthy: '정상',
  stale: '지연',
  missing: '미수집',
  disabled: '미연결',
};

const HEALTH_STYLES: Record<IndicatorHealth, string> = {
  healthy: 'bg-emerald-100 text-emerald-700',
  stale: 'bg-amber-100 text-amber-700',
  missing: 'bg-red-100 text-red-700',
  disabled: 'bg-zinc-200 text-zinc-600',
};

const SOURCE_GROUP_LABELS: Record<SourceGroupFilter, string> = {
  ALL: '소스 그룹 전체',
  US_MACRO: '미국 거시 (FRED)',
  KR_MACRO: '한국 거시 (ECOS/KOSIS/FRED)',
  KR_CORPORATE: '한국 기업 (DART/INTERNAL)',
  OTHER: '기타',
};

const SOURCE_GROUP_SORT_ORDER: Record<Exclude<SourceGroupFilter, 'ALL'>, number> = {
  KR_CORPORATE: 0,
  KR_MACRO: 1,
  US_MACRO: 2,
  OTHER: 3,
};

const resolveSourceGroup = (indicator: IndicatorStatusRow): Exclude<SourceGroupFilter, 'ALL'> => {
  const source = (indicator.source || '').toUpperCase();
  const country = (indicator.country || '').toUpperCase();
  const code = (indicator.code || '').toUpperCase();

  if (country === 'KR' && (source === 'DART' || source === 'INTERNAL' || code.startsWith('KR_DART_'))) {
    return 'KR_CORPORATE';
  }
  if (country === 'KR' && (source === 'ECOS' || source === 'KOSIS' || source === 'FRED')) {
    return 'KR_MACRO';
  }
  if (country === 'US' && source === 'FRED') {
    return 'US_MACRO';
  }
  return 'OTHER';
};

const formatTimestamp = (value: string | null): string => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('ko-KR', { hour12: false });
};

const formatHours = (value: number | null): string => {
  if (value === null || Number.isNaN(value)) return '-';
  const rounded = Math.round(value);
  const days = Math.floor(rounded / 24);
  const hours = rounded % 24;
  if (days <= 0) return `${hours}h`;
  return `${days}d ${hours}h`;
};

const formatInterval = (hours: number): string => {
  if (hours % (24 * 7) === 0) return `${hours / (24 * 7)}주`;
  if (hours % 24 === 0) return `${hours / 24}일`;
  return `${hours}시간`;
};

export const AdminIndicatorManagement: React.FC = () => {
  const { getAuthHeaders, isAuthenticated, user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [indicators, setIndicators] = useState<IndicatorStatusRow[]>([]);
  const [summary, setSummary] = useState<SummaryCounter>({
    total: 0,
    healthy: 0,
    stale: 0,
    missing: 0,
    disabled: 0,
  });
  const [countrySummary, setCountrySummary] = useState<Record<string, SummaryCounter>>({});
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchText, setSearchText] = useState('');
  const [countryFilter, setCountryFilter] = useState('ALL');
  const [healthFilter, setHealthFilter] = useState<'ALL' | IndicatorHealth>('ALL');
  const [sourceGroupFilter, setSourceGroupFilter] = useState<SourceGroupFilter>('ALL');

  const fetchIndicatorStatus = useCallback(async () => {
    if (!isAuthenticated || !isAdmin) {
      setLoading(false);
      return;
    }

    try {
      setError(null);
      const response = await fetch('/api/admin/macro-indicators/status', {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        if (response.status === 403) {
          throw new Error('관리자 권한이 필요합니다.');
        }
        throw new Error('지표 상태를 불러오지 못했습니다.');
      }

      const payload: IndicatorApiResponse = await response.json();
      setIndicators(payload.indicators || []);
      setSummary(
        payload.summary || {
          total: 0,
          healthy: 0,
          stale: 0,
          missing: 0,
          disabled: 0,
        }
      );
      setCountrySummary(payload.summary?.by_country || {});
      setGeneratedAt(payload.generated_at || null);
    } catch (fetchError) {
      const message =
        fetchError instanceof Error
          ? fetchError.message
          : '지표 상태 조회 중 오류가 발생했습니다.';
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [getAuthHeaders, isAdmin, isAuthenticated]);

  useEffect(() => {
    fetchIndicatorStatus();
  }, [fetchIndicatorStatus]);

  const countryOptions = useMemo(() => {
    const countries = Array.from(new Set(indicators.map((item) => item.country)));
    return ['ALL', ...countries];
  }, [indicators]);

  const filteredIndicators = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    return indicators
      .filter((indicator) => {
        const sourceGroup = resolveSourceGroup(indicator);
        const byCountry = countryFilter === 'ALL' || indicator.country === countryFilter;
        const byHealth = healthFilter === 'ALL' || indicator.health === healthFilter;
        const bySourceGroup = sourceGroupFilter === 'ALL' || sourceGroup === sourceGroupFilter;
        const byKeyword =
          keyword.length === 0 ||
          indicator.code.toLowerCase().includes(keyword) ||
          indicator.name.toLowerCase().includes(keyword) ||
          indicator.source.toLowerCase().includes(keyword);
        return byCountry && byHealth && bySourceGroup && byKeyword;
      })
      .sort((a, b) => {
        const groupA = resolveSourceGroup(a);
        const groupB = resolveSourceGroup(b);
        const groupOrderDiff = SOURCE_GROUP_SORT_ORDER[groupA] - SOURCE_GROUP_SORT_ORDER[groupB];
        if (groupOrderDiff !== 0) return groupOrderDiff;
        const sourceDiff = a.source.localeCompare(b.source, 'ko');
        if (sourceDiff !== 0) return sourceDiff;
        const countryDiff = a.country.localeCompare(b.country, 'ko');
        if (countryDiff !== 0) return countryDiff;
        return a.code.localeCompare(b.code, 'ko');
      });
  }, [countryFilter, healthFilter, indicators, searchText, sourceGroupFilter]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-yellow-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">로그인이 필요합니다</h2>
          <p className="text-zinc-400">Admin 페이지에 접근하려면 먼저 로그인해주세요.</p>
        </div>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="text-center">
          <Shield className="h-12 w-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">접근 권한이 없습니다</h2>
          <p className="text-zinc-400">관리자만 이 페이지에 접근할 수 있습니다.</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8 text-zinc-900">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Database className="h-8 w-8 text-blue-600" />
              경제지표 수집 관리
            </h1>
            <p className="text-zinc-500 mt-1">
              미국/한국 지표의 수집 간격 대비 최신 수집 상태를 모니터링합니다.
            </p>
          </div>
          <div className="text-sm text-zinc-500">
            마지막 갱신: {generatedAt ? formatTimestamp(generatedAt) : '-'}
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-100 border border-red-200 rounded-xl flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0" />
            <p className="text-red-700">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          <div className="rounded-xl border border-zinc-200 bg-white p-4">
            <p className="text-xs text-zinc-500">전체</p>
            <p className="text-2xl font-semibold">{summary.total}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <p className="text-xs text-emerald-700">정상</p>
            <p className="text-2xl font-semibold text-emerald-700">{summary.healthy}</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <p className="text-xs text-amber-700">지연</p>
            <p className="text-2xl font-semibold text-amber-700">{summary.stale}</p>
          </div>
          <div className="rounded-xl border border-red-200 bg-red-50 p-4">
            <p className="text-xs text-red-700">미수집</p>
            <p className="text-2xl font-semibold text-red-700">{summary.missing}</p>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-zinc-100 p-4">
            <p className="text-xs text-zinc-600">미연결</p>
            <p className="text-2xl font-semibold text-zinc-700">{summary.disabled}</p>
          </div>
        </div>

        <div className="bg-white border border-zinc-200 rounded-2xl p-4 md:p-5 mb-6 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="지표 코드/이름/소스 검색"
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <select
              value={countryFilter}
              onChange={(event) => setCountryFilter(event.target.value)}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {countryOptions.map((country) => (
                <option key={country} value={country}>
                  {country === 'ALL' ? '국가 전체' : country}
                </option>
              ))}
            </select>
            <select
              value={healthFilter}
              onChange={(event) => setHealthFilter(event.target.value as 'ALL' | IndicatorHealth)}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="ALL">상태 전체</option>
              <option value="healthy">정상</option>
              <option value="stale">지연</option>
              <option value="missing">미수집</option>
              <option value="disabled">미연결</option>
            </select>
            <select
              value={sourceGroupFilter}
              onChange={(event) => setSourceGroupFilter(event.target.value as SourceGroupFilter)}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {Object.entries(SOURCE_GROUP_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                setRefreshing(true);
                fetchIndicatorStatus();
              }}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
              disabled={refreshing}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              새로고침
            </button>
          </div>
        </div>

        <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm">
          <div className="px-5 py-4 border-b border-zinc-200 flex items-center justify-between">
            <h3 className="text-base font-semibold">지표 리스트</h3>
            <p className="text-sm text-zinc-500">{filteredIndicators.length}개 표시 중</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1320px]">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3">상태</th>
                  <th className="px-4 py-3">국가</th>
                  <th className="px-4 py-3">코드</th>
                  <th className="px-4 py-3">지표명</th>
                  <th className="px-4 py-3">소스</th>
                  <th className="px-4 py-3">최근 소스</th>
                  <th className="px-4 py-3">수집 간격</th>
                  <th className="px-4 py-3">최근 데이터 날짜</th>
                  <th className="px-4 py-3">최근 수집 시각</th>
                  <th className="px-4 py-3">현재 지연</th>
                  <th className="px-4 py-3">비교 결과</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200">
                {filteredIndicators.map((indicator) => {
                  const comparisonBaseHours =
                    indicator.stale_threshold_hours ?? indicator.expected_interval_hours;
                  const overdueHours =
                    indicator.lag_hours === null
                      ? null
                      : indicator.lag_hours - comparisonBaseHours;

                  return (
                    <tr key={indicator.code} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${HEALTH_STYLES[indicator.health]}`}
                        >
                          {HEALTH_LABELS[indicator.health]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm font-medium">{indicator.country}</td>
                      <td className="px-4 py-3 text-sm font-mono text-zinc-700">{indicator.code}</td>
                      <td className="px-4 py-3 text-sm">
                        <p className="font-medium text-zinc-900">{indicator.name}</p>
                        <p className="text-xs text-zinc-500">{indicator.note || indicator.description}</p>
                      </td>
                      <td className="px-4 py-3 text-sm text-zinc-600">{indicator.source}</td>
                      <td className="px-4 py-3 text-xs text-zinc-700">{indicator.latest_source || '-'}</td>
                      <td className="px-4 py-3 text-sm text-zinc-700">
                        {formatInterval(indicator.expected_interval_hours)} ({indicator.frequency})
                      </td>
                      <td className="px-4 py-3 text-sm text-zinc-700">
                        {indicator.last_observation_date ?? '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-zinc-700">
                        {formatTimestamp(indicator.last_collected_at)}
                      </td>
                      <td className="px-4 py-3 text-sm text-zinc-700">{formatHours(indicator.lag_hours)}</td>
                      <td className="px-4 py-3 text-sm">
                        {overdueHours === null ? (
                          <span className="text-zinc-500">-</span>
                        ) : overdueHours > 0 ? (
                          <span className="font-medium text-red-600">+{formatHours(overdueHours)} 초과</span>
                        ) : (
                          <span className="font-medium text-emerald-600">
                            {formatHours(Math.abs(overdueHours))} 여유
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {filteredIndicators.length === 0 && (
                  <tr>
                    <td colSpan={11} className="px-4 py-10 text-center text-zinc-500">
                      조건에 맞는 지표가 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {Object.keys(countrySummary).length > 0 && (
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(countrySummary).map(([country, countryData]) => (
              <div key={country} className="bg-white border border-zinc-200 rounded-xl p-4 shadow-sm">
                <p className="text-sm font-semibold text-zinc-900 mb-2">{country} 요약</p>
                <p className="text-xs text-zinc-500">
                  전체 {countryData.total} / 정상 {countryData.healthy} / 지연 {countryData.stale} /
                  미수집 {countryData.missing} / 미연결 {countryData.disabled}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
