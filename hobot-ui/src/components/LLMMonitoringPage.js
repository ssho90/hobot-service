import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import './AdminPage.css';

const LLMMonitoringPage = () => {
  const [logs, setLogs] = useState([]);
  const [tokenUsage, setTokenUsage] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedLog, setSelectedLog] = useState(null);
  const [models, setModels] = useState([]);
  const [services, setServices] = useState([]);
  const [filters, setFilters] = useState({
    model_name: 'All',
    service_name: 'All',
    start_date: '',
    end_date: ''
  });
  const [timeRange, setTimeRange] = useState('1hour'); // 기본값: 1시간
  const [groupBy, setGroupBy] = useState('day');
  const { getAuthHeaders } = useAuth();

  // 필터 옵션 조회 (모델명, 서비스명 목록)
  const fetchOptions = useCallback(async () => {
    try {
      const response = await fetch('/api/llm-monitoring/options', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setModels(data.models || []);
        setServices(data.services || []);
      }
    } catch (err) {
      console.error('필터 옵션 조회 실패:', err);
    }
  }, [getAuthHeaders]);

  // 로컬 시간대(UTC+9) 기준으로 날짜 문자열 생성
  const formatLocalDateTime = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  };

  // 날짜 범위 계산 함수
  const calculateDateRange = (range) => {
    const now = new Date();
    let startDate, endDate;

    switch (range) {
      case '5min':
        startDate = new Date(now.getTime() - 5 * 60 * 1000);
        break;
      case '10min':
        startDate = new Date(now.getTime() - 10 * 60 * 1000);
        break;
      case '15min':
        startDate = new Date(now.getTime() - 15 * 60 * 1000);
        break;
      case '30min':
        startDate = new Date(now.getTime() - 30 * 60 * 1000);
        break;
      case '1hour':
        startDate = new Date(now.getTime() - 60 * 60 * 1000);
        break;
      case '1day':
        startDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        break;
      case '1week':
        startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        break;
      case '1month':
        startDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        break;
      default:
        startDate = new Date(now.getTime() - 60 * 60 * 1000);
    }

    endDate = now;

    // 로컬 시간대(UTC+9) 기준으로 포맷팅 (toISOString()은 UTC로 변환하므로 사용하지 않음)
    return {
      start_date: formatLocalDateTime(startDate),
      end_date: formatLocalDateTime(endDate)
    };
  };

  // 초기화: 필터 옵션 조회 및 기본 날짜 범위 설정
  useEffect(() => {
    fetchOptions();
    const dateRange = calculateDateRange('1hour');
    setFilters(prev => ({
      ...prev,
      start_date: dateRange.start_date,
      end_date: dateRange.end_date
    }));
  }, [fetchOptions]);

  // 로그 조회
  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        limit: '100',
        offset: '0'
      });
      
      if (filters.model_name && filters.model_name !== 'All') {
        params.append('model_name', filters.model_name);
      }
      if (filters.service_name && filters.service_name !== 'All') {
        params.append('service_name', filters.service_name);
      }
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);

      const response = await fetch(`/api/llm-monitoring/logs?${params}`, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setLogs(data.logs || []);
      } else {
        setError('LLM 로그를 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }, [filters, getAuthHeaders]);

  // 토큰 사용량 조회
  const fetchTokenUsage = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        group_by: groupBy
      });
      
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
      if (filters.model_name && filters.model_name !== 'All') {
        params.append('model_name', filters.model_name);
      }
      if (filters.service_name && filters.service_name !== 'All') {
        params.append('service_name', filters.service_name);
      }

      const response = await fetch(`/api/llm-monitoring/token-usage?${params}`, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setTokenUsage(data.data || []);
      }
    } catch (err) {
      console.error('토큰 사용량 조회 실패:', err);
    }
  }, [groupBy, filters, getAuthHeaders]);

  // 필터 변경 시 자동 조회 (초기 로드 후)
  const [isInitialized, setIsInitialized] = useState(false);
  
  useEffect(() => {
    if (isInitialized && filters.start_date && filters.end_date) {
      fetchLogs();
      fetchTokenUsage();
    }
  }, [filters.model_name, filters.service_name, filters.start_date, filters.end_date, groupBy, isInitialized, fetchLogs, fetchTokenUsage]);

  // 초기 로드
  useEffect(() => {
    if (filters.start_date && filters.end_date && !isInitialized) {
      fetchLogs();
      fetchTokenUsage();
      setIsInitialized(true);
    }
  }, [filters.start_date, filters.end_date, isInitialized, fetchLogs, fetchTokenUsage]);

  const handleFilterChange = (field, value) => {
    setFilters(prev => ({ ...prev, [field]: value }));
  };

  const handleApplyFilters = () => {
    fetchLogs();
    fetchTokenUsage();
  };

  const handleResetFilters = () => {
    const dateRange = calculateDateRange('1hour');
    setTimeRange('1hour');
    setFilters({
      model_name: 'All',
      service_name: 'All',
      start_date: dateRange.start_date,
      end_date: dateRange.end_date
    });
  };

  const handleTimeRangeChange = (range) => {
    setTimeRange(range);
    const dateRange = calculateDateRange(range);
    const newFilters = {
      ...filters,
      start_date: dateRange.start_date,
      end_date: dateRange.end_date
    };
    setFilters(newFilters);
    // 날짜 범위 변경 시 즉시 조회
    setTimeout(() => {
      fetchLogs();
      fetchTokenUsage();
    }, 100);
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    // UTC 시간을 KST(UTC+9)로 변환
    const kstDate = new Date(date.getTime() + (9 * 60 * 60 * 1000));
    // KST 시간을 한국어 형식으로 포맷팅 (예: 2025. 12. 1. 오후 11:31:22)
    const year = kstDate.getUTCFullYear();
    const month = String(kstDate.getUTCMonth() + 1).padStart(2, '0');
    const day = String(kstDate.getUTCDate()).padStart(2, '0');
    const hours24 = kstDate.getUTCHours();
    const hours12 = hours24 > 12 ? hours24 - 12 : (hours24 === 0 ? 12 : hours24);
    const ampm = hours24 >= 12 ? '오후' : '오전';
    const minutes = String(kstDate.getUTCMinutes()).padStart(2, '0');
    const seconds = String(kstDate.getUTCSeconds()).padStart(2, '0');
    return `${year}. ${month}. ${day}. ${ampm} ${hours12}:${minutes}:${seconds}`;
  };

  const formatNumber = (num) => {
    if (num === null || num === undefined) return '-';
    return num.toLocaleString('ko-KR');
  };

  // 그래프 데이터 준비 (일자별 토큰 사용량)
  const prepareChartData = () => {
    if (groupBy !== 'day') return null;

    const chartData = tokenUsage.map(item => ({
      date: item.date,
      model: item.model_name,
      tokens: item.total_tokens || 0
    }));

    // 모델별로 그룹화
    const models = [...new Set(chartData.map(d => d.model))];
    const dates = [...new Set(chartData.map(d => d.date))].sort();

    return {
      labels: dates,
      datasets: models.map((model, index) => ({
        label: model,
        data: dates.map(date => {
          const item = chartData.find(d => d.date === date && d.model === model);
          return item ? item.tokens : 0;
        }),
        borderColor: `hsl(${(index * 360) / models.length}, 70%, 50%)`,
        backgroundColor: `hsla(${(index * 360) / models.length}, 70%, 50%, 0.1)`,
        tension: 0.4
      }))
    };
  };

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h1>LLM 모니터링</h1>
        <p>LLM 사용 로그 및 토큰 사용량을 모니터링합니다.</p>
      </div>

      {error && (
        <div className="error-message" style={{ marginBottom: '20px' }}>
          {error}
        </div>
      )}

      {/* 필터 섹션 */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <h2>필터</h2>
        
        {/* 날짜 범위 버튼 */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, color: '#374151' }}>
            날짜 범위
          </label>
          <div className="time-range-buttons">
            <button
              className={`time-range-btn ${timeRange === '5min' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('5min')}
            >
              5분
            </button>
            <button
              className={`time-range-btn ${timeRange === '10min' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('10min')}
            >
              10분
            </button>
            <button
              className={`time-range-btn ${timeRange === '15min' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('15min')}
            >
              15분
            </button>
            <button
              className={`time-range-btn ${timeRange === '30min' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('30min')}
            >
              30분
            </button>
            <button
              className={`time-range-btn ${timeRange === '1hour' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('1hour')}
            >
              1시간
            </button>
            <button
              className={`time-range-btn ${timeRange === '1day' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('1day')}
            >
              1일
            </button>
            <button
              className={`time-range-btn ${timeRange === '1week' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('1week')}
            >
              1주일
            </button>
            <button
              className={`time-range-btn ${timeRange === '1month' ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange('1month')}
            >
              1달
            </button>
          </div>
        </div>

        <div className="filter-grid">
          <div className="filter-item">
            <label>모델명</label>
            <select
              value={filters.model_name}
              onChange={(e) => handleFilterChange('model_name', e.target.value)}
            >
              <option value="All">All</option>
              {models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>
          <div className="filter-item">
            <label>서비스명</label>
            <select
              value={filters.service_name}
              onChange={(e) => handleFilterChange('service_name', e.target.value)}
            >
              <option value="All">All</option>
              {services.map((service) => (
                <option key={service} value={service}>
                  {service}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="filter-actions">
          <button className="btn btn-primary" onClick={handleApplyFilters}>
            적용
          </button>
          <button className="btn btn-secondary" onClick={handleResetFilters}>
            초기화
          </button>
        </div>
      </div>

      {/* 토큰 사용량 통계 */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <h2>토큰 사용량 통계</h2>
        <div className="filter-actions" style={{ marginBottom: '15px' }}>
          <label>그룹화 기준: </label>
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
            <option value="day">일자별</option>
            <option value="model">모델별</option>
            <option value="service">서비스별</option>
          </select>
        </div>

        {groupBy === 'day' && (
          <div style={{ marginBottom: '20px', padding: '16px', backgroundColor: '#f9fafb', borderRadius: '6px' }}>
            <h3>일자별 토큰 사용량 추이</h3>
            <p style={{ color: '#6b7280', fontSize: '14px' }}>
              일자별 토큰 사용량은 아래 표에서 확인할 수 있습니다. 
              그래프 기능은 추후 Chart.js를 통해 추가될 예정입니다.
            </p>
          </div>
        )}

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                {groupBy === 'day' && <th>날짜</th>}
                {groupBy === 'model' && <th>모델명</th>}
                {groupBy === 'model' && <th>제공자</th>}
                {groupBy === 'service' && <th>서비스명</th>}
                <th>프롬프트 토큰</th>
                <th>완료 토큰</th>
                <th>총 토큰</th>
                <th>요청 수</th>
                {groupBy !== 'day' && <th>평균 응답 시간 (ms)</th>}
              </tr>
            </thead>
            <tbody>
              {tokenUsage.length === 0 ? (
                <tr>
                  <td colSpan={groupBy === 'day' ? 6 : groupBy === 'model' ? 7 : 6}>
                    데이터가 없습니다.
                  </td>
                </tr>
              ) : (
                tokenUsage.map((item, index) => (
                  <tr key={index}>
                    {groupBy === 'day' && <td>{item.date}</td>}
                    {groupBy === 'model' && <td>{item.model_name}</td>}
                    {groupBy === 'model' && <td>{item.provider}</td>}
                    {groupBy === 'service' && <td>{item.service_name || '-'}</td>}
                    <td>{formatNumber(item.total_prompt_tokens)}</td>
                    <td>{formatNumber(item.total_completion_tokens)}</td>
                    <td><strong>{formatNumber(item.total_tokens)}</strong></td>
                    <td>{formatNumber(item.request_count)}</td>
                    {groupBy !== 'day' && (
                      <td>{item.avg_duration_ms ? Math.round(item.avg_duration_ms) : '-'}</td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* LLM 사용 로그 */}
      <div className="card">
        <h2>LLM 사용 로그</h2>
        {loading ? (
          <div className="loading">로딩 중...</div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>시간</th>
                  <th>모델</th>
                  <th>제공자</th>
                  <th>서비스</th>
                  <th>프롬프트 토큰</th>
                  <th>완료 토큰</th>
                  <th>총 토큰</th>
                  <th>응답 시간</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan="9">로그가 없습니다.</td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.created_at)}</td>
                      <td>{log.model_name}</td>
                      <td>{log.provider}</td>
                      <td>{log.service_name || '-'}</td>
                      <td>{formatNumber(log.prompt_tokens)}</td>
                      <td>{formatNumber(log.completion_tokens)}</td>
                      <td><strong>{formatNumber(log.total_tokens)}</strong></td>
                      <td>{log.duration_ms ? `${log.duration_ms}ms` : '-'}</td>
                      <td>
                        <button
                          className="btn btn-sm btn-secondary"
                          onClick={() => setSelectedLog(log)}
                        >
                          상세보기
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 로그 상세 모달 */}
      {selectedLog && (
        <div className="modal-overlay" onClick={() => setSelectedLog(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>LLM 사용 로그 상세</h2>
              <button
                className="modal-close"
                onClick={() => setSelectedLog(null)}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="detail-section">
                <h3>요청 프롬프트</h3>
                <pre className="prompt-box">
                  {selectedLog.request_prompt || '-'}
                </pre>
              </div>
              <div className="detail-section">
                <h3>응답 프롬프트</h3>
                <pre className="prompt-box">
                  {selectedLog.response_prompt || '-'}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LLMMonitoringPage;

