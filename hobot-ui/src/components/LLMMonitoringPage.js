import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import './AdminPage.css';

const LLMMonitoringPage = () => {
  const [logs, setLogs] = useState([]);
  const [tokenUsage, setTokenUsage] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedLog, setSelectedLog] = useState(null);
  const [filters, setFilters] = useState({
    model_name: '',
    service_name: '',
    start_date: '',
    end_date: ''
  });
  const [groupBy, setGroupBy] = useState('day');
  const { getAuthHeaders } = useAuth();

  // 로그 조회
  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        limit: '100',
        offset: '0'
      });
      
      if (filters.model_name) params.append('model_name', filters.model_name);
      if (filters.service_name) params.append('service_name', filters.service_name);
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

  useEffect(() => {
    fetchLogs();
    fetchTokenUsage();
  }, [fetchLogs, fetchTokenUsage]);

  const handleFilterChange = (field, value) => {
    setFilters(prev => ({ ...prev, [field]: value }));
  };

  const handleApplyFilters = () => {
    fetchLogs();
    fetchTokenUsage();
  };

  const handleResetFilters = () => {
    setFilters({
      model_name: '',
      service_name: '',
      start_date: '',
      end_date: ''
    });
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ko-KR');
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

  const chartData = prepareChartData();

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
        <div className="filter-grid">
          <div className="filter-item">
            <label>모델명</label>
            <input
              type="text"
              value={filters.model_name}
              onChange={(e) => handleFilterChange('model_name', e.target.value)}
              placeholder="예: gemini-2.5-pro"
            />
          </div>
          <div className="filter-item">
            <label>서비스명</label>
            <input
              type="text"
              value={filters.service_name}
              onChange={(e) => handleFilterChange('service_name', e.target.value)}
              placeholder="예: ai_strategist"
            />
          </div>
          <div className="filter-item">
            <label>시작 날짜</label>
            <input
              type="date"
              value={filters.start_date}
              onChange={(e) => handleFilterChange('start_date', e.target.value)}
            />
          </div>
          <div className="filter-item">
            <label>종료 날짜</label>
            <input
              type="date"
              value={filters.end_date}
              onChange={(e) => handleFilterChange('end_date', e.target.value)}
            />
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
                <h3>기본 정보</h3>
                <p><strong>모델:</strong> {selectedLog.model_name}</p>
                <p><strong>제공자:</strong> {selectedLog.provider}</p>
                <p><strong>서비스:</strong> {selectedLog.service_name || '-'}</p>
                <p><strong>시간:</strong> {formatDate(selectedLog.created_at)}</p>
                <p><strong>응답 시간:</strong> {selectedLog.duration_ms ? `${selectedLog.duration_ms}ms` : '-'}</p>
              </div>
              <div className="detail-section">
                <h3>토큰 사용량</h3>
                <p><strong>프롬프트 토큰:</strong> {formatNumber(selectedLog.prompt_tokens)}</p>
                <p><strong>완료 토큰:</strong> {formatNumber(selectedLog.completion_tokens)}</p>
                <p><strong>총 토큰:</strong> {formatNumber(selectedLog.total_tokens)}</p>
              </div>
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

