import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { BarChart3, Filter, Search, Check, Copy, X, BrainCircuit, Activity, Users } from 'lucide-react';

interface LLMLog {
  id: string;
  created_at: string;
  model_name: string;
  provider: string;
  service_name?: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms: number;
  request_prompt?: string;
  response_prompt?: string;
  user_id?: string;
}

interface TokenUsage {
  date?: string;
  model_name?: string;
  provider?: string;
  service_name?: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  request_count: number;
  avg_duration_ms?: number;
}

interface UserUsage {
  user_id: string;
  request_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  avg_duration_ms: number;
  last_used_at: string;
  first_used_at: string;
}

interface UserUsageSummary {
  total_users: number;
  total_requests: number;
  total_tokens_used: number;
}

export const AdminLLMMonitoring: React.FC = () => {
  const [logs, setLogs] = useState<LLMLog[]>([]);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);
  const [userUsage, setUserUsage] = useState<UserUsage[]>([]);
  const [userUsageSummary, setUserUsageSummary] = useState<UserUsageSummary | null>(null);
  const [llmUsers, setLlmUsers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedLog, setSelectedLog] = useState<LLMLog | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [services, setServices] = useState<string[]>([]);
  const [filters, setFilters] = useState({
    model_name: 'All',
    service_name: 'All',
    user_id: 'All',
    start_date: '',
    end_date: ''
  });
  const [timeRange, setTimeRange] = useState('1hour');
  const [groupBy, setGroupBy] = useState('day');
  const [activeTab, setActiveTab] = useState<'overview' | 'users'>('overview');
  const [copyFeedback, setCopyFeedback] = useState('');
  const { getAuthHeaders } = useAuth();
  const [isInitialized, setIsInitialized] = useState(false);

  // --- Helpers ---
  const formatLocalDateTime = (date: Date) => {
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
      `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  };

  const calculateDateRange = useCallback((range: string) => {
    const now = new Date();
    let start = new Date();
    switch (range) {
      case '5min': start = new Date(now.getTime() - 5 * 60000); break;
      case '10min': start = new Date(now.getTime() - 10 * 60000); break;
      case '15min': start = new Date(now.getTime() - 15 * 60000); break;
      case '30min': start = new Date(now.getTime() - 30 * 60000); break;
      case '1hour': start = new Date(now.getTime() - 60 * 60000); break;
      case '1day': start = new Date(now.getTime() - 24 * 3600000); break;
      case '1week': start = new Date(now.getTime() - 7 * 24 * 3600000); break;
      case '1month': start = new Date(now.getTime() - 30 * 24 * 3600000); break;
      default: start = new Date(now.getTime() - 60 * 60000);
    }
    return {
      start_date: formatLocalDateTime(start),
      end_date: formatLocalDateTime(now)
    };
  }, []);

  const formatNumber = (num?: number) => num?.toLocaleString('ko-KR') ?? '-';

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ko-KR', {
      year: 'numeric', month: 'numeric', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  };

  const handleCopy = (text?: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopyFeedback('복사되었습니다.');
      setTimeout(() => setCopyFeedback(''), 2000);
    });
  };

  // --- Data Fetching ---
  const fetchOptions = useCallback(async () => {
    try {
      const response = await fetch('/api/llm-monitoring/options', { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        setModels(data.models || []);
        setServices(data.services || []);
      }
    } catch (err) {
      console.error('Failed to fetch options', err);
    }
  }, [getAuthHeaders]);

  const fetchLlmUsers = useCallback(async () => {
    try {
      const response = await fetch('/api/llm-monitoring/users', { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        setLlmUsers(data.users || []);
      }
    } catch (err) {
      console.error('Failed to fetch LLM users', err);
    }
  }, [getAuthHeaders]);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ limit: '100', offset: '0' });
      if (filters.model_name !== 'All') params.append('model_name', filters.model_name);
      if (filters.service_name !== 'All') params.append('service_name', filters.service_name);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);

      const response = await fetch(`/api/llm-monitoring/logs?${params}`, { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        setLogs(data.logs || []);
        setError('');
      } else {
        setError('Failed to fetch LLM logs');
      }
    } catch {
      setError('Server connection failed');
    } finally {
      setLoading(false);
    }
  }, [filters, getAuthHeaders]);

  const fetchTokenUsage = useCallback(async () => {
    try {
      const params = new URLSearchParams({ group_by: groupBy });
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
      if (filters.model_name !== 'All') params.append('model_name', filters.model_name);
      if (filters.service_name !== 'All') params.append('service_name', filters.service_name);

      const response = await fetch(`/api/llm-monitoring/token-usage?${params}`, { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        setTokenUsage(data.data || []);
      }
    } catch {
      console.error('Failed to fetch token usage');
    }
  }, [groupBy, filters, getAuthHeaders]);

  const fetchUserUsage = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
      if (filters.user_id !== 'All') params.append('user_id', filters.user_id);

      const response = await fetch(`/api/llm-monitoring/user-usage?${params}`, { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        setUserUsage(data.data || []);
        setUserUsageSummary(data.summary || null);
      }
    } catch {
      console.error('Failed to fetch user usage');
    }
  }, [filters, getAuthHeaders]);

  // --- Effects ---
  useEffect(() => {
    fetchOptions();
    fetchLlmUsers();
    const range = calculateDateRange('1hour');
    setFilters(prev => ({ ...prev, ...range }));
  }, [fetchOptions, fetchLlmUsers, calculateDateRange]);

  useEffect(() => {
    if (filters.start_date && filters.end_date) {
      if (activeTab === 'overview') {
        fetchLogs();
        fetchTokenUsage();
      } else {
        fetchUserUsage();
      }
      if (!isInitialized) setIsInitialized(true);
    }
  }, [filters.model_name, filters.service_name, filters.user_id, filters.start_date, filters.end_date, groupBy, activeTab, fetchLogs, fetchTokenUsage, fetchUserUsage, isInitialized]);

  const handleTimeRangeChange = (range: string) => {
    setTimeRange(range);
    setFilters(prev => ({ ...prev, ...calculateDateRange(range) }));
  };

  const handleTabChange = (tab: 'overview' | 'users') => {
    setActiveTab(tab);
  };

  // Safe check for logs before mapping
  const renderLogRows = () => {
    if (!logs || logs.length === 0) {
      return <tr><td colSpan={7} className="px-4 py-8 text-center text-zinc-600">로그가 없습니다.</td></tr>;
    }
    return logs.map(log => (
      <tr key={log.id} className="hover:bg-slate-50 transition-colors">
        <td className="px-4 py-3 text-zinc-500 text-xs">{formatDate(log.created_at)}</td>
        <td className="px-4 py-3">
          <div className="font-medium text-zinc-800">{log.model_name}</div>
          <div className="text-xs text-zinc-500">{log.provider}</div>
        </td>
        <td className="px-4 py-3 text-zinc-500">{log.service_name || '-'}</td>
        <td className="px-4 py-3 text-zinc-600">{log.user_id || '-'}</td>
        <td className="px-4 py-3 text-right font-mono text-xs">
          <span className="text-zinc-500">{log.prompt_tokens}</span> /
          <span className="text-zinc-500"> {log.completion_tokens}</span> /
          <span className="text-emerald-600 font-bold"> {log.total_tokens}</span>
        </td>
        <td className="px-4 py-3 text-right text-xs text-zinc-500">{log.duration_ms}ms</td>
        <td className="px-4 py-3 text-center">
          <button
            onClick={() => setSelectedLog(log)}
            className="px-3 py-1 bg-white hover:bg-slate-100 border border-zinc-200 rounded text-xs transition-colors text-zinc-700"
          >
            상세보기
          </button>
        </td>
      </tr>
    ));
  };

  const renderTokenUsageRows = () => {
    if (!tokenUsage || tokenUsage.length === 0) {
      return <tr><td colSpan={7} className="px-4 py-8 text-center text-zinc-600">데이터가 없습니다.</td></tr>;
    }
    return tokenUsage.map((item, i) => (
      <tr key={i} className="hover:bg-slate-50 transition-colors">
        <td className="px-4 py-3 font-medium text-zinc-800">
          {groupBy === 'day' ? item.date : groupBy === 'model' ? item.model_name : item.service_name || '-'}
        </td>
        {groupBy === 'model' && <td className="px-4 py-3 text-zinc-500">{item.provider}</td>}
        <td className="px-4 py-3 text-right text-zinc-600">{formatNumber(item.total_prompt_tokens)}</td>
        <td className="px-4 py-3 text-right text-zinc-600">{formatNumber(item.total_completion_tokens)}</td>
        <td className="px-4 py-3 text-right font-bold text-emerald-600">{formatNumber(item.total_tokens)}</td>
        <td className="px-4 py-3 text-right text-zinc-600">{formatNumber(item.request_count)}</td>
        {groupBy !== 'day' && <td className="px-4 py-3 text-right text-zinc-600">{item.avg_duration_ms ? Math.round(item.avg_duration_ms) + 'ms' : '-'}</td>}
      </tr>
    ));
  };

  const renderUserUsageRows = () => {
    if (!userUsage || userUsage.length === 0) {
      return <tr><td colSpan={7} className="px-4 py-8 text-center text-zinc-600">사용자별 데이터가 없습니다.</td></tr>;
    }
    return userUsage.map((item, i) => (
      <tr key={i} className="hover:bg-slate-50 transition-colors">
        <td className="px-4 py-3 font-medium text-zinc-800">{item.user_id}</td>
        <td className="px-4 py-3 text-right text-zinc-600">{formatNumber(item.request_count)}</td>
        <td className="px-4 py-3 text-right text-zinc-600">{formatNumber(item.total_prompt_tokens)}</td>
        <td className="px-4 py-3 text-right text-zinc-600">{formatNumber(item.total_completion_tokens)}</td>
        <td className="px-4 py-3 text-right font-bold text-emerald-600">{formatNumber(item.total_tokens)}</td>
        <td className="px-4 py-3 text-right text-zinc-500">{item.avg_duration_ms ? Math.round(item.avg_duration_ms) + 'ms' : '-'}</td>
        <td className="px-4 py-3 text-xs text-zinc-500">{formatDate(item.last_used_at)}</td>
      </tr>
    ));
  };


  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-zinc-900">
      <div className="flex items-center gap-3 mb-8">
        <BrainCircuit className="w-8 h-8 text-blue-600" />
        <div>
          <h1 className="text-3xl font-bold tracking-tight">LLM 모니터링</h1>
          <p className="text-zinc-500">LLM 토큰 사용량 및 로그 분석</p>
          {error && <span className="text-red-500 text-sm ml-2">{error}</span>}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => handleTabChange('overview')}
          className={`px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2 ${
            activeTab === 'overview'
              ? 'bg-blue-600 text-white shadow-md'
              : 'bg-white text-zinc-600 border border-zinc-200 hover:bg-zinc-50'
          }`}
        >
          <Activity className="w-4 h-4" />
          전체 현황
        </button>
        <button
          onClick={() => handleTabChange('users')}
          className={`px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2 ${
            activeTab === 'users'
              ? 'bg-blue-600 text-white shadow-md'
              : 'bg-white text-zinc-600 border border-zinc-200 hover:bg-zinc-50'
          }`}
        >
          <Users className="w-4 h-4" />
          사용자별 현황
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-zinc-200 p-6 mb-8 shadow-sm">
        <div className="flex items-center gap-2 mb-4 text-sm font-semibold text-zinc-700">
          <Filter className="w-4 h-4" /> 검색 필터
        </div>

        <div className="flex flex-wrap gap-4 mb-6">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-zinc-500 mb-1.5 uppercase tracking-wider">Time Range</label>
            <div className="flex bg-slate-50 rounded-lg border border-zinc-200 p-1 overflow-x-auto custom-scrollbar">
              {['5min', '15min', '30min', '1hour', '1day', '1week', '1month'].map(range => (
                <button
                  key={range}
                  onClick={() => handleTimeRangeChange(range)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-all ${timeRange === range
                    ? 'bg-white text-blue-600 shadow-sm border border-zinc-200'
                    : 'text-zinc-500 hover:text-zinc-900 hover:bg-slate-200'
                    }`}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>

          {activeTab === 'overview' && (
            <>
              <div className="min-w-[150px]">
                <label className="block text-xs font-medium text-zinc-500 mb-1.5 uppercase tracking-wider">Model</label>
                <select
                  value={filters.model_name}
                  onChange={(e) => setFilters({ ...filters, model_name: e.target.value })}
                  className="w-full bg-white border border-zinc-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none text-zinc-900"
                >
                  <option value="All">All Models</option>
                  {models.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>

              <div className="min-w-[150px]">
                <label className="block text-xs font-medium text-zinc-500 mb-1.5 uppercase tracking-wider">Service</label>
                <select
                  value={filters.service_name}
                  onChange={(e) => setFilters({ ...filters, service_name: e.target.value })}
                  className="w-full bg-white border border-zinc-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none text-zinc-900"
                >
                  <option value="All">All Services</option>
                  {services.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </>
          )}

          {activeTab === 'users' && (
            <div className="min-w-[150px]">
              <label className="block text-xs font-medium text-zinc-500 mb-1.5 uppercase tracking-wider">User</label>
              <select
                value={filters.user_id}
                onChange={(e) => setFilters({ ...filters, user_id: e.target.value })}
                className="w-full bg-white border border-zinc-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none text-zinc-900"
              >
                <option value="All">All Users</option>
                {llmUsers.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3">
          <button
            onClick={() => {
              const range = calculateDateRange('1hour');
              setTimeRange('1hour');
              setFilters({ model_name: 'All', service_name: 'All', user_id: 'All', ...range });
            }}
            className="px-4 py-2 text-sm text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 rounded-lg transition-all"
          >
            초기화
          </button>
          <button
            onClick={() => { 
              if (activeTab === 'overview') {
                fetchLogs(); 
                fetchTokenUsage(); 
              } else {
                fetchUserUsage();
              }
            }}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-all shadow-sm"
          >
            조회 적용
          </button>
        </div>
      </div>

      {activeTab === 'overview' ? (
        <>
          {/* Token Usage Stats */}
          <div className="bg-white rounded-xl border border-zinc-200 p-6 mb-8 shadow-sm">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold flex items-center gap-2 text-zinc-900">
                <BarChart3 className="w-5 h-5 text-emerald-600" /> 토큰 사용량 통계
              </h2>
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value)}
                className="bg-white border border-zinc-200 rounded-lg px-3 py-1.5 text-xs focus:ring-1 focus:ring-emerald-500 outline-none text-zinc-700"
              >
                <option value="day">일자별</option>
                <option value="model">모델별</option>
                <option value="service">서비스별</option>
              </select>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-zinc-500 uppercase bg-slate-50 border-b border-zinc-200">
                  <tr>
                    <th className="px-4 py-3 font-medium">{groupBy === 'day' ? 'Date' : groupBy === 'model' ? 'Model' : 'Service'}</th>
                    {groupBy === 'model' && <th className="px-4 py-3 font-medium">Provider</th>}
                    <th className="px-4 py-3 font-medium text-right">Prompt Tokens</th>
                    <th className="px-4 py-3 font-medium text-right">Completion Tokens</th>
                    <th className="px-4 py-3 font-medium text-right text-zinc-900">Total Tokens</th>
                    <th className="px-4 py-3 font-medium text-right">Requests</th>
                    {groupBy !== 'day' && <th className="px-4 py-3 font-medium text-right">Avg Latency</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {renderTokenUsageRows()}
                </tbody>
              </table>
            </div>
          </div>

          {/* Logs Table */}
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <h2 className="text-lg font-bold flex items-center gap-2 mb-6 text-zinc-900">
              <Activity className="w-5 h-5 text-blue-600" /> 상세 로그
            </h2>

            {loading ? (
              <div className="text-center py-12 text-zinc-500 animate-pulse">데이터를 불러오는 중...</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-zinc-500 uppercase bg-slate-50 border-b border-zinc-200">
                    <tr>
                      <th className="px-4 py-3">Time</th>
                      <th className="px-4 py-3">Model</th>
                      <th className="px-4 py-3">Service</th>
                      <th className="px-4 py-3">User</th>
                      <th className="px-4 py-3 text-right">Tokens (P/C/T)</th>
                      <th className="px-4 py-3 text-right">Latency</th>
                      <th className="px-4 py-3 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100">
                    {renderLogRows()}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : (
        /* User Usage Tab */
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
          <h2 className="text-lg font-bold flex items-center gap-2 mb-6 text-zinc-900">
            <Users className="w-5 h-5 text-purple-600" /> 사용자별 LLM 사용량
          </h2>

          {/* Summary Cards */}
          {userUsageSummary && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4 border border-blue-200">
                <div className="text-xs text-blue-600 font-medium uppercase tracking-wider mb-1">전체 사용자</div>
                <div className="text-2xl font-bold text-blue-800">{formatNumber(userUsageSummary.total_users)}</div>
              </div>
              <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-xl p-4 border border-emerald-200">
                <div className="text-xs text-emerald-600 font-medium uppercase tracking-wider mb-1">전체 요청 수</div>
                <div className="text-2xl font-bold text-emerald-800">{formatNumber(userUsageSummary.total_requests)}</div>
              </div>
              <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4 border border-purple-200">
                <div className="text-xs text-purple-600 font-medium uppercase tracking-wider mb-1">전체 토큰</div>
                <div className="text-2xl font-bold text-purple-800">{formatNumber(userUsageSummary.total_tokens_used)}</div>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-zinc-500 uppercase bg-slate-50 border-b border-zinc-200">
                <tr>
                  <th className="px-4 py-3 font-medium">User ID</th>
                  <th className="px-4 py-3 font-medium text-right">요청 횟수</th>
                  <th className="px-4 py-3 font-medium text-right">Prompt Tokens</th>
                  <th className="px-4 py-3 font-medium text-right">Completion Tokens</th>
                  <th className="px-4 py-3 font-medium text-right text-zinc-900">Total Tokens</th>
                  <th className="px-4 py-3 font-medium text-right">Avg Latency</th>
                  <th className="px-4 py-3 font-medium">마지막 사용</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {renderUserUsageRows()}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setSelectedLog(null)}>
          <div className="bg-white border border-zinc-200 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-zinc-200 bg-slate-50 rounded-t-xl">
              <h3 className="text-xl font-bold flex items-center gap-2 text-zinc-900">
                <Search className="w-5 h-5 text-blue-600" /> 로그 상세 정보
              </h3>
              <button onClick={() => setSelectedLog(null)} className="p-2 hover:bg-zinc-100 rounded-lg transition-colors text-zinc-500">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-6">
              {/* Log metadata */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-zinc-500">Model:</span>
                  <span className="ml-2 font-medium">{selectedLog.model_name}</span>
                </div>
                <div>
                  <span className="text-zinc-500">Service:</span>
                  <span className="ml-2 font-medium">{selectedLog.service_name || '-'}</span>
                </div>
                <div>
                  <span className="text-zinc-500">User:</span>
                  <span className="ml-2 font-medium">{selectedLog.user_id || '-'}</span>
                </div>
                <div>
                  <span className="text-zinc-500">Tokens:</span>
                  <span className="ml-2 font-medium">{selectedLog.total_tokens}</span>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-semibold text-zinc-700 uppercase tracking-wider">Request Prompt</h4>
                  <button onClick={() => handleCopy(selectedLog.request_prompt)} className="p-1.5 hover:bg-zinc-100 rounded text-zinc-500 hover:text-zinc-900 transition-colors">
                    <Copy className="w-4 h-4" />
                  </button>
                </div>
                <div className="bg-slate-50 border border-zinc-200 rounded-lg p-4 font-mono text-sm text-zinc-600 whitespace-pre-wrap leading-relaxed max-h-[300px] overflow-auto custom-scrollbar">
                  {selectedLog.request_prompt || '-'}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-semibold text-zinc-700 uppercase tracking-wider">Response</h4>
                  <button onClick={() => handleCopy(selectedLog.response_prompt)} className="p-1.5 hover:bg-zinc-100 rounded text-zinc-500 hover:text-zinc-900 transition-colors">
                    <Copy className="w-4 h-4" />
                  </button>
                </div>
                <div className="bg-slate-50 border border-zinc-200 rounded-lg p-4 font-mono text-sm text-zinc-600 whitespace-pre-wrap leading-relaxed max-h-[300px] overflow-auto custom-scrollbar">
                  {selectedLog.response_prompt || '-'}
                </div>
              </div>
            </div>

            <div className="p-6 border-t border-zinc-200 bg-slate-50 rounded-b-xl flex justify-end">
              <button onClick={() => setSelectedLog(null)} className="px-6 py-2 bg-white hover:bg-zinc-50 border border-zinc-300 text-zinc-700 rounded-lg transition-colors font-medium">
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Copy Feeddback */}
      {copyFeedback && (
        <div className="fixed bottom-8 left-1/2 transform -translate-x-1/2 bg-zinc-800 text-white px-4 py-2 rounded-full shadow-lg flex items-center gap-2 z-[60] animate-in fade-in slide-in-from-bottom-2">
          <Check className="w-4 h-4 text-emerald-400" /> {copyFeedback}
        </div>
      )}
    </div>
  );
};
