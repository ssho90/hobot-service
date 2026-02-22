import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Activity, RefreshCw, Route, Users, Bot, Layers, ChevronDown, ChevronUp } from 'lucide-react';

interface FlowRun {
  flow_run_id: string;
  flow_type: string;
  user_id: string;
  started_at: string;
  ended_at: string;
  flow_duration_ms: number;
  call_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  llm_duration_ms: number;
  services: string;
  models: string;
}

interface FlowCall {
  id: number;
  flow_run_id: string;
  flow_type: string;
  user_id: string;
  service_name: string;
  agent_name?: string;
  model_name: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms: number;
  trace_order?: number;
  created_at: string;
  request_prompt?: string;
  response_prompt?: string;
}

interface OptionsResponse {
  flow_types: string[];
  users: string[];
}

interface MonitoringFilters {
  flow_type: string;
  user_id: string;
  start_date: string;
  end_date: string;
}

const formatNumber = (value?: number) => (value ?? 0).toLocaleString('ko-KR');

const formatDateTime = (value?: string) => {
  if (!value) return '-';
  const date = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ko-KR');
};

const toLocalDateTime = (date: Date) => {
  const pad = (num: number) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

export const AdminMultiAgentMonitoring: React.FC = () => {
  const { getAuthHeaders } = useAuth();
  const [loading, setLoading] = useState(false);
  const [callsLoading, setCallsLoading] = useState(false);
  const [error, setError] = useState('');
  const [flowRuns, setFlowRuns] = useState<FlowRun[]>([]);
  const [flowCalls, setFlowCalls] = useState<FlowCall[]>([]);
  const [expandedCallIds, setExpandedCallIds] = useState<Set<number>>(new Set());
  const [selectedFlowRunId, setSelectedFlowRunId] = useState<string>('');
  const [options, setOptions] = useState<OptionsResponse>({ flow_types: [], users: [] });
  const [filters, setFilters] = useState<MonitoringFilters>({
    flow_type: 'All',
    user_id: 'All',
    start_date: toLocalDateTime(new Date(Date.now() - 24 * 60 * 60 * 1000)),
    end_date: '',
  });

  const fetchOptions = useCallback(async (forceRefresh: boolean = false) => {
    try {
      const endpoint = forceRefresh
        ? `/api/admin/multi-agent-monitoring/options?_ts=${Date.now()}`
        : '/api/admin/multi-agent-monitoring/options';
      const response = await fetch(endpoint, {
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (!response.ok) return;
      const data = await response.json();
      setOptions({
        flow_types: data.flow_types || [],
        users: data.users || [],
      });
    } catch (err) {
      console.error('multi-agent options fetch failed', err);
    }
  }, [getAuthHeaders]);

  const fetchFlowRuns = useCallback(async (
    forceRefresh: boolean = false,
    activeFilters: MonitoringFilters = filters,
  ): Promise<FlowRun[]> => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        limit: '100',
        offset: '0',
      });
      if (activeFilters.flow_type !== 'All') params.append('flow_type', activeFilters.flow_type);
      if (activeFilters.user_id !== 'All') params.append('user_id', activeFilters.user_id);
      if (activeFilters.start_date) params.append('start_date', activeFilters.start_date);
      if (activeFilters.end_date) params.append('end_date', activeFilters.end_date);
      if (forceRefresh) params.append('_ts', String(Date.now()));

      const response = await fetch(`/api/admin/multi-agent-monitoring/flows?${params.toString()}`, {
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error('멀티에이전트 run 목록 조회 실패');
      }
      const data = await response.json();
      const runs: FlowRun[] = data.flows || data.data || [];
      setFlowRuns(runs);
      if (runs.length > 0) {
        const stillExists = runs.some((run) => run.flow_run_id === selectedFlowRunId);
        if (!selectedFlowRunId || !stillExists) {
          setSelectedFlowRunId(runs[0].flow_run_id);
        }
      } else {
        setSelectedFlowRunId('');
        setFlowCalls([]);
      }
      return runs;
    } catch (err) {
      console.error(err);
      setError('멀티에이전트 run 목록을 불러오지 못했습니다.');
      setFlowRuns([]);
      setSelectedFlowRunId('');
      setFlowCalls([]);
      return [];
    } finally {
      setLoading(false);
    }
  }, [filters, getAuthHeaders, selectedFlowRunId]);

  const fetchFlowCalls = useCallback(async (flowRunId: string, forceRefresh: boolean = false) => {
    if (!flowRunId) {
      setFlowCalls([]);
      setExpandedCallIds(new Set());
      return;
    }
    setCallsLoading(true);
    try {
      const params = new URLSearchParams({ flow_run_id: flowRunId });
      if (forceRefresh) params.append('_ts', String(Date.now()));
      const response = await fetch(`/api/admin/multi-agent-monitoring/calls?${params.toString()}`, {
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error('멀티에이전트 호출 상세 조회 실패');
      }
      const data = await response.json();
      setFlowCalls(data.calls || data.data || []);
      setExpandedCallIds(new Set());
    } catch (err) {
      console.error(err);
      setFlowCalls([]);
      setExpandedCallIds(new Set());
    } finally {
      setCallsLoading(false);
    }
  }, [getAuthHeaders]);

  const handleRefresh = useCallback(async () => {
    await fetchOptions(true);
    const runs = await fetchFlowRuns(true);
    const nextFlowRunId = runs.some((run) => run.flow_run_id === selectedFlowRunId)
      ? selectedFlowRunId
      : (runs[0]?.flow_run_id || '');
    if (nextFlowRunId) {
      await fetchFlowCalls(nextFlowRunId, true);
    }
  }, [fetchFlowCalls, fetchFlowRuns, fetchOptions, selectedFlowRunId]);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  useEffect(() => {
    fetchFlowRuns();
  }, [fetchFlowRuns]);

  useEffect(() => {
    fetchFlowCalls(selectedFlowRunId);
  }, [selectedFlowRunId, fetchFlowCalls]);

  const selectedRun = useMemo(
    () => flowRuns.find((run) => run.flow_run_id === selectedFlowRunId) || null,
    [flowRuns, selectedFlowRunId]
  );

  const toggleCallDetail = useCallback((callId: number) => {
    setExpandedCallIds((prev) => {
      const next = new Set(prev);
      if (next.has(callId)) {
        next.delete(callId);
      } else {
        next.add(callId);
      }
      return next;
    });
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-zinc-900">
      <div className="flex items-center gap-3 mb-6">
        <Layers className="w-8 h-8 text-indigo-600" />
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Multi-Agent 모니터링</h1>
          <p className="text-zinc-500">플로우 단위 실행 현황과 호출별 토큰 사용량을 추적합니다.</p>
          {error && <p className="text-sm text-rose-600 mt-1">{error}</p>}
        </div>
      </div>

      <div className="bg-white border border-zinc-200 rounded-xl p-4 mb-6 shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div>
            <p className="text-xs text-zinc-500 mb-1">Flow 타입</p>
            <select
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm"
              value={filters.flow_type}
              onChange={(event) => setFilters((prev) => ({ ...prev, flow_type: event.target.value }))}
            >
              <option value="All">All</option>
              {options.flow_types.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
          <div>
            <p className="text-xs text-zinc-500 mb-1">사용자</p>
            <select
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm"
              value={filters.user_id}
              onChange={(event) => setFilters((prev) => ({ ...prev, user_id: event.target.value }))}
            >
              <option value="All">All</option>
              {options.users.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
          <div>
            <p className="text-xs text-zinc-500 mb-1">시작 시각</p>
            <input
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm"
              value={filters.start_date}
              onChange={(event) => setFilters((prev) => ({ ...prev, start_date: event.target.value }))}
              placeholder="YYYY-MM-DD HH:MM:SS"
            />
          </div>
          <div>
            <p className="text-xs text-zinc-500 mb-1">종료 시각 (비우면 현재까지)</p>
            <input
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm"
              value={filters.end_date}
              onChange={(event) => setFilters((prev) => ({ ...prev, end_date: event.target.value }))}
              placeholder="YYYY-MM-DD HH:MM:SS"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleRefresh}
              className="w-full px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors inline-flex items-center justify-center gap-2"
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              새로고침
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="xl:col-span-2 bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-2">
            <Route className="w-4 h-4 text-indigo-600" />
            <h2 className="font-semibold">Flow Run 목록</h2>
          </div>
          <div className="overflow-auto max-h-[560px]">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left text-zinc-500">Flow</th>
                  <th className="px-3 py-2 text-left text-zinc-500">사용자</th>
                  <th className="px-3 py-2 text-left text-zinc-500">시작</th>
                  <th className="px-3 py-2 text-right text-zinc-500">호출수</th>
                  <th className="px-3 py-2 text-right text-zinc-500">총 토큰</th>
                </tr>
              </thead>
              <tbody>
                {!loading && flowRuns.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-zinc-500">조회된 run이 없습니다.</td>
                  </tr>
                )}
                {flowRuns.map((run) => (
                  <tr
                    key={run.flow_run_id}
                    onClick={() => setSelectedFlowRunId(run.flow_run_id)}
                    className={`cursor-pointer border-t border-zinc-100 hover:bg-indigo-50/40 ${selectedFlowRunId === run.flow_run_id ? 'bg-indigo-50/60' : ''}`}
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium text-zinc-800">{run.flow_type}</div>
                      <div className="text-[11px] text-zinc-500">{run.flow_run_id}</div>
                    </td>
                    <td className="px-3 py-2 text-zinc-600">{run.user_id || 'system'}</td>
                    <td className="px-3 py-2 text-zinc-600">{formatDateTime(run.started_at)}</td>
                    <td className="px-3 py-2 text-right text-zinc-700">{formatNumber(run.call_count)}</td>
                    <td className="px-3 py-2 text-right font-semibold text-emerald-600">{formatNumber(run.total_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="bg-white border border-zinc-200 rounded-xl shadow-sm p-4 space-y-4">
          <h2 className="font-semibold">선택 Flow 요약</h2>
          {selectedRun ? (
            <>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2 text-zinc-700">
                  <Bot className="w-4 h-4 text-indigo-600" />
                  <span className="font-medium">{selectedRun.flow_type}</span>
                </div>
                <div className="flex items-center gap-2 text-zinc-700">
                  <Users className="w-4 h-4 text-zinc-500" />
                  <span>{selectedRun.user_id || 'system'}</span>
                </div>
                <div className="text-xs text-zinc-500 break-all">{selectedRun.flow_run_id}</div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="p-3 border border-zinc-200 rounded-lg">
                  <p className="text-zinc-500 text-xs">총 호출 수</p>
                  <p className="text-lg font-semibold">{formatNumber(selectedRun.call_count)}</p>
                </div>
                <div className="p-3 border border-zinc-200 rounded-lg">
                  <p className="text-zinc-500 text-xs">총 토큰</p>
                  <p className="text-lg font-semibold text-emerald-600">{formatNumber(selectedRun.total_tokens)}</p>
                </div>
                <div className="p-3 border border-zinc-200 rounded-lg col-span-2">
                  <p className="text-zinc-500 text-xs">LLM 총 지연</p>
                  <p className="text-lg font-semibold">{formatNumber(selectedRun.llm_duration_ms)} ms</p>
                </div>
              </div>
              <div className="text-xs text-zinc-500 space-y-1">
                <p>시작: {formatDateTime(selectedRun.started_at)}</p>
                <p>종료: {formatDateTime(selectedRun.ended_at)}</p>
                <p>모델: {selectedRun.models || '-'}</p>
              </div>
            </>
          ) : (
            <p className="text-sm text-zinc-500">좌측에서 run을 선택하세요.</p>
          )}
        </section>
      </div>

      <section className="bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden mt-6">
        <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-2">
          <Activity className="w-4 h-4 text-indigo-600" />
          <h2 className="font-semibold">호출 상세</h2>
        </div>
        <div className="overflow-auto max-h-[500px]">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 sticky top-0">
              <tr>
                <th className="px-3 py-2 text-left text-zinc-500">시각</th>
                <th className="px-3 py-2 text-left text-zinc-500">Service / Agent</th>
                <th className="px-3 py-2 text-left text-zinc-500">Model</th>
                <th className="px-3 py-2 text-left text-zinc-500">User</th>
                <th className="px-3 py-2 text-right text-zinc-500">Prompt</th>
                <th className="px-3 py-2 text-right text-zinc-500">Completion</th>
                <th className="px-3 py-2 text-right text-zinc-500">Total</th>
                <th className="px-3 py-2 text-right text-zinc-500">지연</th>
                <th className="px-3 py-2 text-right text-zinc-500">상세</th>
              </tr>
            </thead>
            <tbody>
              {!callsLoading && flowCalls.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-zinc-500">호출 상세가 없습니다.</td>
                </tr>
              )}
              {flowCalls.map((call) => {
                const isExpanded = expandedCallIds.has(call.id);
                return (
                  <React.Fragment key={call.id}>
                    <tr className="border-t border-zinc-100 hover:bg-zinc-50/80">
                      <td className="px-3 py-2 text-zinc-600">{formatDateTime(call.created_at)}</td>
                      <td className="px-3 py-2">
                        <div className="font-medium text-zinc-800">{call.service_name || '-'}</div>
                        <div className="text-[11px] text-zinc-500">{call.agent_name || '-'}</div>
                      </td>
                      <td className="px-3 py-2 text-zinc-700">{call.model_name}</td>
                      <td className="px-3 py-2 text-zinc-600">{call.user_id || 'system'}</td>
                      <td className="px-3 py-2 text-right text-zinc-600">{formatNumber(call.prompt_tokens)}</td>
                      <td className="px-3 py-2 text-right text-zinc-600">{formatNumber(call.completion_tokens)}</td>
                      <td className="px-3 py-2 text-right font-semibold text-emerald-600">{formatNumber(call.total_tokens)}</td>
                      <td className="px-3 py-2 text-right text-zinc-600">{formatNumber(call.duration_ms)}ms</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            className="h-7 w-7 rounded-md border border-zinc-300 bg-white hover:bg-zinc-100 text-zinc-700 inline-flex items-center justify-center"
                            onClick={() => toggleCallDetail(call.id)}
                            title={isExpanded ? '상세 접기' : '상세 펼치기'}
                          >
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                          <button
                            type="button"
                            className="px-2 py-1 rounded-md border border-zinc-300 bg-white hover:bg-zinc-100 text-[11px] font-medium text-zinc-700"
                            onClick={() => toggleCallDetail(call.id)}
                          >
                            Detail
                          </button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-t border-zinc-100 bg-zinc-50/70">
                        <td colSpan={9} className="px-4 py-4">
                          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                            <div className="rounded-lg border border-zinc-200 bg-white">
                              <div className="px-3 py-2 border-b border-zinc-200 text-xs font-semibold text-zinc-700">LLM Request</div>
                              <pre className="px-3 py-2 text-xs text-zinc-700 whitespace-pre-wrap break-words max-h-64 overflow-auto">
                                {call.request_prompt || '-'}
                              </pre>
                            </div>
                            <div className="rounded-lg border border-zinc-200 bg-white">
                              <div className="px-3 py-2 border-b border-zinc-200 text-xs font-semibold text-zinc-700">LLM Response</div>
                              <pre className="px-3 py-2 text-xs text-zinc-700 whitespace-pre-wrap break-words max-h-64 overflow-auto">
                                {call.response_prompt || '-'}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
