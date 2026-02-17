import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Info,
  Loader2,
  Network,
  RefreshCw,
  Shield,
  XCircle,
} from 'lucide-react';

type FlowStatus = 'healthy' | 'warning' | 'error';

interface Neo4jDatabaseSummary {
  database: string;
  status: 'success' | 'error';
  message: string;
  response_ms: number;
  node_count: number;
  relationship_count: number;
  label_counts: Record<string, number>;
  relationship_type_counts: Record<string, number>;
}

interface MacroExtractionSummary {
  status: 'success' | 'error';
  message?: string;
  total_documents: number;
  success_documents: number;
  failed_documents: number;
  pending_status_documents: number;
  null_status_documents: number;
  pending_candidates: number;
  retryable_failed_documents: number;
  extracted_last_24h: number;
  latest_published_at: string | null;
  latest_extraction_updated_at: string | null;
  recent_documents: Array<{
    doc_id: string;
    title: string;
    country_code: string | null;
    category: string | null;
    extraction_status: string;
    extraction_last_error: string | null;
    published_at: string | null;
    extraction_updated_at: string | null;
  }>;
  recent_failed_documents: Array<{
    doc_id: string;
    title: string;
    extraction_last_error: string | null;
    extraction_updated_at: string | null;
  }>;
}

interface NewsIngestionSummary {
  total_news: number;
  news_last_24h: number;
  news_last_7d: number;
  collected_last_24h: number;
  last_published_at: string | null;
  last_collected_at: string | null;
  by_country_last_7d: Array<{ country: string; count: number }>;
}

interface FredIngestionSummary {
  total_rows: number;
  indicator_count: number;
  rows_last_24h: number;
  rows_last_7d: number;
  last_observation_date: string | null;
  last_collected_at: string | null;
  daily_rows_last_7d: Array<{ day: string | null; rows: number }>;
}

interface IndicatorSummary {
  summary: {
    total?: number;
    healthy?: number;
    stale?: number;
    missing?: number;
    disabled?: number;
    by_country?: Record<
      string,
      {
        total: number;
        healthy: number;
        stale: number;
        missing: number;
        disabled: number;
      }
    >;
  };
  stale_or_missing_count: number;
  stale_or_missing_indicators: Array<{
    code: string;
    name: string;
    country: string;
    health: string;
    lag_hours: number | null;
    expected_interval_hours: number;
    last_collected_at: string | null;
    note: string;
  }>;
}

interface SchedulerJob {
  tags: string[];
  interval: number;
  unit: string;
  next_run: string | null;
  last_run: string | null;
  at_time: string | null;
}

interface PipelineFlowStep {
  id: string;
  title: string;
  description: string;
  schedule: string;
  status: FlowStatus;
  metric: string;
  reason?: string | null;
}

interface MonitoringSnapshot {
  status: string;
  generated_at: string;
  neo4j: {
    architecture: Neo4jDatabaseSummary;
    macro: Neo4jDatabaseSummary;
  };
  macro_graph: {
    extraction: MacroExtractionSummary;
  };
  ingestion: {
    news: NewsIngestionSummary;
    fred: FredIngestionSummary;
    indicators: IndicatorSummary;
  };
  scheduler: {
    jobs: SchedulerJob[];
    pipeline_flow: PipelineFlowStep[];
  };
}

const STATUS_LABEL: Record<FlowStatus, string> = {
  healthy: '정상',
  warning: '주의',
  error: '오류',
};

const STATUS_STYLE: Record<FlowStatus, string> = {
  healthy: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
  warning: 'bg-amber-100 text-amber-700 border border-amber-200',
  error: 'bg-red-100 text-red-700 border border-red-200',
};

const DOC_STATUS_STYLE: Record<string, string> = {
  success: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  pending: 'bg-amber-100 text-amber-700',
  unknown: 'bg-zinc-200 text-zinc-700',
};

const formatNumber = (value: number | null | undefined): string =>
  value === null || value === undefined ? '-' : value.toLocaleString('ko-KR');

const formatHours = (value: number | null | undefined): string => {
  if (value === null || value === undefined) {
    return '-';
  }
  const rounded = Math.round(value);
  const days = Math.floor(rounded / 24);
  const hours = rounded % 24;
  return days > 0 ? `${days}d ${hours}h` : `${hours}h`;
};

const formatTimestamp = (value: string | null | undefined): string => {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('ko-KR', { hour12: false });
};

const normalizeFlowStatus = (value: string): FlowStatus => {
  if (value === 'healthy' || value === 'warning' || value === 'error') {
    return value;
  }
  return 'warning';
};

const HealthBadge: React.FC<{ status: FlowStatus }> = ({ status }) => {
  if (status === 'healthy') {
    return (
      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_STYLE[status]}`}>
        <CheckCircle2 className="h-3.5 w-3.5" />
        {STATUS_LABEL[status]}
      </span>
    );
  }
  if (status === 'warning') {
    return (
      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_STYLE[status]}`}>
        <AlertTriangle className="h-3.5 w-3.5" />
        {STATUS_LABEL[status]}
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_STYLE[status]}`}>
      <XCircle className="h-3.5 w-3.5" />
      {STATUS_LABEL[status]}
    </span>
  );
};

export const AdminNeo4jMonitoring: React.FC = () => {
  const { getAuthHeaders, isAuthenticated, user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isFetchingRef = useRef(false);

  const [snapshot, setSnapshot] = useState<MonitoringSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSnapshot = useCallback(async (isAutoRefresh = false) => {
    if (!isAuthenticated || !isAdmin) {
      setLoading(false);
      return;
    }
    if (isFetchingRef.current) {
      return;
    }
    isFetchingRef.current = true;

    try {
      setError(null);
      if (!isAutoRefresh) {
        setRefreshing(true);
      }
      const response = await fetch('/api/admin/neo4j-monitoring', {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        if (response.status === 403) {
          throw new Error('관리자 권한이 필요합니다.');
        }
        throw new Error('모니터링 데이터를 불러오지 못했습니다.');
      }

      const payload: MonitoringSnapshot = await response.json();
      setSnapshot(payload);
    } catch (fetchError) {
      const message =
        fetchError instanceof Error ? fetchError.message : '모니터링 조회 중 오류가 발생했습니다.';
      setError(message);
    } finally {
      isFetchingRef.current = false;
      setLoading(false);
      if (!isAutoRefresh) {
        setRefreshing(false);
      }
    }
  }, [getAuthHeaders, isAdmin, isAuthenticated]);

  useEffect(() => {
    fetchSnapshot(true);
  }, [fetchSnapshot]);

  useEffect(() => {
    if (!isAuthenticated || !isAdmin) {
      return;
    }
    const intervalId = window.setInterval(() => {
      fetchSnapshot(true);
    }, 30000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [fetchSnapshot, isAdmin, isAuthenticated]);

  const macroLabelCounts = useMemo(() => {
    const entries = Object.entries(snapshot?.neo4j?.macro?.label_counts || {});
    return entries.sort((a, b) => b[1] - a[1]);
  }, [snapshot]);

  const macroRelationshipCounts = useMemo(() => {
    const entries = Object.entries(snapshot?.neo4j?.macro?.relationship_type_counts || {});
    return entries.sort((a, b) => b[1] - a[1]);
  }, [snapshot]);

  const flowSteps = useMemo(() => {
    return (snapshot?.scheduler?.pipeline_flow || []).map((item) => ({
      ...item,
      status: normalizeFlowStatus(item.status),
    }));
  }, [snapshot]);

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

  if (!snapshot) {
    return (
      <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-red-700">
          모니터링 데이터를 불러오지 못했습니다.
        </div>
      </div>
    );
  }

  const architectureDb = snapshot.neo4j.architecture;
  const macroDb = snapshot.neo4j.macro;
  const news = snapshot.ingestion.news;
  const fred = snapshot.ingestion.fred;
  const indicatorSummary = snapshot.ingestion.indicators;
  const extraction = snapshot.macro_graph.extraction;

  const architectureStatus: FlowStatus = architectureDb.status === 'success' ? 'healthy' : 'error';
  const macroStatus: FlowStatus = macroDb.status === 'success' ? 'healthy' : 'error';

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8 text-zinc-900">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Network className="h-8 w-8 text-blue-600" />
              Neo4j & 수집 파이프라인 모니터링
            </h1>
            <p className="text-zinc-500 mt-1">
              그래프 DB 상태와 뉴스/정량지표 수집 흐름을 실시간으로 점검합니다.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <p className="text-sm text-zinc-500">마지막 갱신: {formatTimestamp(snapshot.generated_at)}</p>
            <button
              onClick={() => {
                fetchSnapshot();
              }}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 text-sm font-medium transition-colors disabled:opacity-60"
              disabled={refreshing}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              새로고침
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-zinc-900">Architecture Neo4j</p>
              <HealthBadge status={architectureStatus} />
            </div>
            <p className="text-sm text-zinc-600 mb-4">{architectureDb.message}</p>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-slate-50 border border-zinc-200 p-3">
                <p className="text-xs text-zinc-500">응답 시간</p>
                <p className="text-lg font-semibold">{formatNumber(architectureDb.response_ms)}ms</p>
              </div>
              <div className="rounded-lg bg-slate-50 border border-zinc-200 p-3">
                <p className="text-xs text-zinc-500">노드</p>
                <p className="text-lg font-semibold">{formatNumber(architectureDb.node_count)}</p>
              </div>
              <div className="rounded-lg bg-slate-50 border border-zinc-200 p-3">
                <p className="text-xs text-zinc-500">관계</p>
                <p className="text-lg font-semibold">{formatNumber(architectureDb.relationship_count)}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-zinc-900">Macro Neo4j</p>
              <HealthBadge status={macroStatus} />
            </div>
            <p className="text-sm text-zinc-600 mb-4">{macroDb.message}</p>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-slate-50 border border-zinc-200 p-3">
                <p className="text-xs text-zinc-500">응답 시간</p>
                <p className="text-lg font-semibold">{formatNumber(macroDb.response_ms)}ms</p>
              </div>
              <div className="rounded-lg bg-slate-50 border border-zinc-200 p-3">
                <p className="text-xs text-zinc-500">노드</p>
                <p className="text-lg font-semibold">{formatNumber(macroDb.node_count)}</p>
              </div>
              <div className="rounded-lg bg-slate-50 border border-zinc-200 p-3">
                <p className="text-xs text-zinc-500">관계</p>
                <p className="text-lg font-semibold">{formatNumber(macroDb.relationship_count)}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="h-5 w-5 text-blue-600" />
            <h2 className="text-lg font-semibold">수집/적재 작업 흐름</h2>
          </div>
          <div className="overflow-x-auto">
            <div className="flex min-w-[980px] items-stretch gap-2">
              {flowSteps.map((step, index) => (
                <React.Fragment key={step.id}>
                  <div className="w-56 rounded-xl border border-zinc-200 bg-slate-50 p-3">
                    <div className="mb-2 flex items-center gap-1.5">
                      <HealthBadge status={step.status} />
                      {step.reason && step.status !== 'healthy' && (
                        <div className="relative group">
                          <button
                            type="button"
                            className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-500 hover:text-zinc-700"
                            aria-label="상태 설명"
                          >
                            <Info className="h-3.5 w-3.5" />
                          </button>
                          <div className="pointer-events-none absolute left-0 top-6 z-30 w-80 rounded-lg border border-zinc-200 bg-white p-3 text-xs text-zinc-700 shadow-xl opacity-0 transition-opacity group-hover:opacity-100">
                            <p className="mb-1 font-semibold text-zinc-900">주의 사유</p>
                            <p className="leading-relaxed">{step.reason}</p>
                          </div>
                        </div>
                      )}
                    </div>
                    <p className="text-sm font-semibold text-zinc-900">{step.title}</p>
                    <p className="text-xs text-zinc-500 mt-1">{step.description}</p>
                    <div className="mt-3 text-xs text-zinc-600">
                      <p className="font-medium">주기: {step.schedule}</p>
                      <p className="mt-1">{step.metric}</p>
                    </div>
                  </div>
                  {index < flowSteps.length - 1 && (
                    <div className="flex items-center px-1">
                      <ArrowRight className="h-4 w-4 text-zinc-400" />
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm p-5">
            <p className="text-sm font-semibold mb-3">뉴스 수집</p>
            <div className="space-y-1 text-sm text-zinc-700">
              <p>전체: {formatNumber(news.total_news)}건</p>
              <p>24시간 발행: {formatNumber(news.news_last_24h)}건</p>
              <p>24시간 수집: {formatNumber(news.collected_last_24h)}건</p>
              <p>7일 발행: {formatNumber(news.news_last_7d)}건</p>
              <p>최근 발행: {formatTimestamp(news.last_published_at)}</p>
              <p>최근 수집: {formatTimestamp(news.last_collected_at)}</p>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm p-5">
            <p className="text-sm font-semibold mb-3">FRED 정량 수집</p>
            <div className="space-y-1 text-sm text-zinc-700">
              <p>전체 행: {formatNumber(fred.total_rows)}</p>
              <p>지표 수: {formatNumber(fred.indicator_count)}개</p>
              <p>24시간 적재: {formatNumber(fred.rows_last_24h)}행</p>
              <p>7일 적재: {formatNumber(fred.rows_last_7d)}행</p>
              <p>최근 관측일: {formatTimestamp(fred.last_observation_date)}</p>
              <p>최근 적재: {formatTimestamp(fred.last_collected_at)}</p>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm p-5">
            <p className="text-sm font-semibold mb-3">뉴스 그래프 추출</p>
            <div className="space-y-1 text-sm text-zinc-700">
              <p>Document: {formatNumber(extraction.total_documents)}개</p>
              <p>성공: {formatNumber(extraction.success_documents)}개</p>
              <p>실패: {formatNumber(extraction.failed_documents)}개</p>
              <p>대기 후보: {formatNumber(extraction.pending_candidates)}개</p>
              <p>재시도 가능 실패: {formatNumber(extraction.retryable_failed_documents)}개</p>
              <p>24시간 추출: {formatNumber(extraction.extracted_last_24h)}개</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-zinc-200">
              <h3 className="font-semibold">Macro Graph 노드 분포</h3>
            </div>
            <div className="px-5 py-4 space-y-2">
              {macroLabelCounts.map(([label, count]) => (
                <div key={label} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-700">{label}</span>
                  <span className="font-mono text-zinc-900">{formatNumber(count)}</span>
                </div>
              ))}
              {macroLabelCounts.length === 0 && <p className="text-sm text-zinc-500">데이터 없음</p>}
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-zinc-200">
              <h3 className="font-semibold">Macro Graph 관계 분포</h3>
            </div>
            <div className="px-5 py-4 space-y-2">
              {macroRelationshipCounts.map(([type, count]) => (
                <div key={type} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-700">{type}</span>
                  <span className="font-mono text-zinc-900">{formatNumber(count)}</span>
                </div>
              ))}
              {macroRelationshipCounts.length === 0 && <p className="text-sm text-zinc-500">데이터 없음</p>}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-zinc-200">
              <h3 className="font-semibold">최근 뉴스 국가 분포 (7일)</h3>
            </div>
            <div className="px-5 py-4 space-y-2">
              {news.by_country_last_7d.map((row) => (
                <div key={row.country} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-700">{row.country}</span>
                  <span className="font-mono text-zinc-900">{formatNumber(row.count)}</span>
                </div>
              ))}
              {news.by_country_last_7d.length === 0 && <p className="text-sm text-zinc-500">데이터 없음</p>}
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-zinc-200">
              <h3 className="font-semibold">FRED 적재 추이 (7일)</h3>
            </div>
            <div className="px-5 py-4 space-y-2">
              {fred.daily_rows_last_7d.map((row, index) => (
                <div key={`${row.day || 'unknown'}-${index}`} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-700">{row.day || '-'}</span>
                  <span className="font-mono text-zinc-900">{formatNumber(row.rows)}</span>
                </div>
              ))}
              {fred.daily_rows_last_7d.length === 0 && <p className="text-sm text-zinc-500">데이터 없음</p>}
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-zinc-200 flex items-center justify-between">
            <h3 className="font-semibold">지연/미수집 지표 (Top 20)</h3>
            <span className="text-sm text-zinc-500">
              {formatNumber(indicatorSummary.stale_or_missing_count)}개
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[940px]">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3">상태</th>
                  <th className="px-4 py-3">국가</th>
                  <th className="px-4 py-3">코드</th>
                  <th className="px-4 py-3">지표명</th>
                  <th className="px-4 py-3">지연</th>
                  <th className="px-4 py-3">기대 주기</th>
                  <th className="px-4 py-3">최근 수집</th>
                  <th className="px-4 py-3">메모</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200">
                {indicatorSummary.stale_or_missing_indicators.map((indicator) => {
                  const status = indicator.health === 'stale' ? 'warning' : 'error';
                  return (
                    <tr key={indicator.code} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <HealthBadge status={status} />
                      </td>
                      <td className="px-4 py-3 text-sm">{indicator.country}</td>
                      <td className="px-4 py-3 text-sm font-mono">{indicator.code}</td>
                      <td className="px-4 py-3 text-sm">{indicator.name}</td>
                      <td className="px-4 py-3 text-sm">{formatHours(indicator.lag_hours)}</td>
                      <td className="px-4 py-3 text-sm">{formatHours(indicator.expected_interval_hours)}</td>
                      <td className="px-4 py-3 text-sm">{formatTimestamp(indicator.last_collected_at)}</td>
                      <td className="px-4 py-3 text-sm text-zinc-500">{indicator.note || '-'}</td>
                    </tr>
                  );
                })}
                {indicatorSummary.stale_or_missing_indicators.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-zinc-500">
                      지연/미수집 지표가 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-zinc-200">
              <h3 className="font-semibold">최근 Document 추출 상태</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px]">
                <thead className="bg-slate-50">
                  <tr className="text-left text-xs uppercase tracking-wider text-zinc-500">
                    <th className="px-4 py-3">상태</th>
                    <th className="px-4 py-3">문서</th>
                    <th className="px-4 py-3">국가/카테고리</th>
                    <th className="px-4 py-3">발행</th>
                    <th className="px-4 py-3">추출 업데이트</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200">
                  {extraction.recent_documents.map((row) => {
                    const statusClass = DOC_STATUS_STYLE[row.extraction_status] || DOC_STATUS_STYLE.unknown;
                    return (
                      <tr key={row.doc_id} className="hover:bg-slate-50">
                        <td className="px-4 py-3">
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusClass}`}>
                            {row.extraction_status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <p className="font-mono text-xs text-zinc-500">{row.doc_id}</p>
                          <p className="line-clamp-2">{row.title || '-'}</p>
                        </td>
                        <td className="px-4 py-3 text-sm text-zinc-600">
                          {row.country_code || '-'} / {row.category || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm">{formatTimestamp(row.published_at)}</td>
                        <td className="px-4 py-3 text-sm">{formatTimestamp(row.extraction_updated_at)}</td>
                      </tr>
                    );
                  })}
                  {extraction.recent_documents.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-zinc-500">
                        표시할 문서가 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-zinc-200">
              <h3 className="font-semibold">최근 실패 문서</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead className="bg-slate-50">
                  <tr className="text-left text-xs uppercase tracking-wider text-zinc-500">
                    <th className="px-4 py-3">문서</th>
                    <th className="px-4 py-3">오류</th>
                    <th className="px-4 py-3">업데이트 시각</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200">
                  {extraction.recent_failed_documents.map((row) => (
                    <tr key={row.doc_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-sm">
                        <p className="font-mono text-xs text-zinc-500">{row.doc_id}</p>
                        <p className="line-clamp-2">{row.title || '-'}</p>
                      </td>
                      <td className="px-4 py-3 text-sm text-red-600 line-clamp-3">{row.extraction_last_error || '-'}</td>
                      <td className="px-4 py-3 text-sm">{formatTimestamp(row.extraction_updated_at)}</td>
                    </tr>
                  ))}
                  {extraction.recent_failed_documents.length === 0 && (
                    <tr>
                      <td colSpan={3} className="px-4 py-8 text-center text-zinc-500">
                        최근 실패 문서가 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-zinc-200 flex items-center gap-2">
            <Clock3 className="h-4 w-4 text-zinc-500" />
            <h3 className="font-semibold">스케줄러 Job 상태</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3">태그</th>
                  <th className="px-4 py-3">간격</th>
                  <th className="px-4 py-3">단위</th>
                  <th className="px-4 py-3">at</th>
                  <th className="px-4 py-3">다음 실행</th>
                  <th className="px-4 py-3">최근 실행</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200">
                {snapshot.scheduler.jobs.map((job, index) => (
                  <tr key={`${job.tags.join('-')}-${index}`} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-sm">
                      <div className="flex flex-wrap gap-1">
                        {(job.tags || []).map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex rounded-full bg-zinc-100 text-zinc-700 text-xs px-2 py-0.5"
                          >
                            {tag}
                          </span>
                        ))}
                        {(!job.tags || job.tags.length === 0) && <span className="text-zinc-500">-</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm">{formatNumber(job.interval)}</td>
                    <td className="px-4 py-3 text-sm">{job.unit || '-'}</td>
                    <td className="px-4 py-3 text-sm">{job.at_time || '-'}</td>
                    <td className="px-4 py-3 text-sm">{formatTimestamp(job.next_run)}</td>
                    <td className="px-4 py-3 text-sm">{formatTimestamp(job.last_run)}</td>
                  </tr>
                ))}
                {snapshot.scheduler.jobs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                      현재 프로세스에 등록된 스케줄 잡이 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
