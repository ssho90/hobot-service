import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import './AdminPage.css';

const LogManagementPage = () => {
  const [selectedLogType, setSelectedLogType] = useState('backend');
  const [selectedBackendLogFile, setSelectedBackendLogFile] = useState('log.txt');
  const [logContent, setLogContent] = useState('');
  const [logFile, setLogFile] = useState('');
  const [lines, setLines] = useState(100);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [useTimeFilter, setUseTimeFilter] = useState(false);
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const { getAuthHeaders } = useAuth();

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      
      // 시간 필터 파라미터 구성
      let url = `/api/admin/logs?log_type=${selectedLogType}&lines=${lines}`;
      
      // 백엔드 로그인 경우 특정 파일 선택
      if (selectedLogType === 'backend') {
        url += `&log_file=${encodeURIComponent(selectedBackendLogFile)}`;
      }
      
      if (useTimeFilter && startTime && endTime) {
        url += `&start_time=${encodeURIComponent(startTime)}&end_time=${encodeURIComponent(endTime)}`;
      }
      
      const response = await fetch(url, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setLogContent(data.content || 'No log content available');
          setLogFile(data.file || '');
        } else {
          setError(data.message || 'Failed to fetch logs');
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch logs' }));
        setError(errorData.detail || 'Failed to fetch logs');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }, [selectedLogType, selectedBackendLogFile, lines, useTimeFilter, startTime, endTime, getAuthHeaders]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    let interval = null;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchLogs();
      }, 5000); // 5초마다 자동 새로고침
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, fetchLogs]);

  const logTypes = [
    { value: 'backend', label: '백엔드 로그', icon: '🔧' },
    { value: 'frontend', label: '프론트엔드 로그', icon: '⚛️' },
    { value: 'nginx', label: 'Nginx 로그', icon: '🌐' }
  ];

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h1>로그 관리</h1>
        <p>시스템 로그를 확인하고 모니터링할 수 있습니다.</p>
      </div>

      <div className="log-controls" style={{ marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <label htmlFor="log-type" style={{ fontWeight: 600 }}>로그 타입:</label>
          <select
            id="log-type"
            value={selectedLogType}
            onChange={(e) => setSelectedLogType(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px' }}
          >
            {logTypes.map(type => (
              <option key={type.value} value={type.value}>
                {type.icon} {type.label}
              </option>
            ))}
          </select>
        </div>

        {selectedLogType === 'backend' && (
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <label htmlFor="backend-log-file" style={{ fontWeight: 600 }}>로그 파일:</label>
            <select
              id="backend-log-file"
              value={selectedBackendLogFile}
              onChange={(e) => setSelectedBackendLogFile(e.target.value)}
              style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px' }}
            >
              <option value="log.txt">📝 log.txt (애플리케이션 로그)</option>
              <option value="error.log">❌ error.log (에러 로그)</option>
              <option value="access.log">📊 access.log (접근 로그)</option>
            </select>
          </div>
        )}

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <label htmlFor="lines" style={{ fontWeight: 600 }}>줄 수:</label>
          <input
            id="lines"
            type="number"
            value={lines}
            onChange={(e) => setLines(parseInt(e.target.value) || 100)}
            min="10"
            max="1000"
            style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px', width: '100px' }}
          />
        </div>

        <button
          onClick={fetchLogs}
          disabled={loading}
          className="btn"
          style={{ minWidth: '100px' }}
        >
          {loading ? '로딩 중...' : '새로고침'}
        </button>

        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          <span>자동 새로고침 (5초)</span>
        </label>
      </div>

      <div className="time-filter-section" style={{ 
        marginBottom: '20px', 
        padding: '16px', 
        backgroundColor: '#f9fafb', 
        borderRadius: '8px',
        border: '1px solid #e5e7eb'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600 }}>
            <input
              type="checkbox"
              checked={useTimeFilter}
              onChange={(e) => {
                setUseTimeFilter(e.target.checked);
                if (!e.target.checked) {
                  setStartTime('');
                  setEndTime('');
                }
              }}
            />
            <span>시간대 필터 사용</span>
          </label>
        </div>
        
        {useTimeFilter && (
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <label htmlFor="start-time" style={{ fontWeight: 600, minWidth: '80px' }}>시작 시간:</label>
              <input
                id="start-time"
                type="datetime-local"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                style={{ 
                  padding: '8px 12px', 
                  borderRadius: '8px', 
                  border: '1px solid #d1d5db', 
                  fontSize: '14px',
                  backgroundColor: '#ffffff'
                }}
              />
            </div>
            
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <label htmlFor="end-time" style={{ fontWeight: 600, minWidth: '80px' }}>종료 시간:</label>
              <input
                id="end-time"
                type="datetime-local"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                style={{ 
                  padding: '8px 12px', 
                  borderRadius: '8px', 
                  border: '1px solid #d1d5db', 
                  fontSize: '14px',
                  backgroundColor: '#ffffff'
                }}
              />
            </div>
            
            {/* UTC+9 시간대를 datetime-local 형식으로 변환하는 헬퍼 함수 */}
            {(() => {
              const formatDateTimeLocal = (date) => {
                const year = date.getUTCFullYear();
                const month = String(date.getUTCMonth() + 1).padStart(2, '0');
                const day = String(date.getUTCDate()).padStart(2, '0');
                const hours = String(date.getUTCHours()).padStart(2, '0');
                const minutes = String(date.getUTCMinutes()).padStart(2, '0');
                return `${year}-${month}-${day}T${hours}:${minutes}`;
              };
              
              const setTimeRange = (minutesAgo) => {
                const now = new Date();
                const kstTime = new Date(now.getTime() + (9 * 60 * 60 * 1000)); // UTC+9
                const pastTime = new Date(kstTime.getTime() - minutesAgo * 60 * 1000);
                setEndTime(formatDateTimeLocal(kstTime));
                setStartTime(formatDateTimeLocal(pastTime));
              };
              
              return (
                <>
                  <button
                    onClick={() => setTimeRange(5)}
                    style={{
                      padding: '8px 16px',
                      borderRadius: '8px',
                      border: '1px solid #d1d5db',
                      backgroundColor: '#ffffff',
                      cursor: 'pointer',
                      fontSize: '14px'
                    }}
                  >
                    최근 5분
                  </button>
                  
                  <button
                    onClick={() => setTimeRange(15)}
                    style={{
                      padding: '8px 16px',
                      borderRadius: '8px',
                      border: '1px solid #d1d5db',
                      backgroundColor: '#ffffff',
                      cursor: 'pointer',
                      fontSize: '14px'
                    }}
                  >
                    최근 15분
                  </button>
                  
                  <button
                    onClick={() => setTimeRange(30)}
                    style={{
                      padding: '8px 16px',
                      borderRadius: '8px',
                      border: '1px solid #d1d5db',
                      backgroundColor: '#ffffff',
                      cursor: 'pointer',
                      fontSize: '14px'
                    }}
                  >
                    최근 30분
                  </button>
                  
                  <button
                    onClick={() => setTimeRange(60)}
                    style={{
                      padding: '8px 16px',
                      borderRadius: '8px',
                      border: '1px solid #d1d5db',
                      backgroundColor: '#ffffff',
                      cursor: 'pointer',
                      fontSize: '14px'
                    }}
                  >
                    최근 1시간
                  </button>
                  
                  <button
                    onClick={() => setTimeRange(24 * 60)}
                    style={{
                      padding: '8px 16px',
                      borderRadius: '8px',
                      border: '1px solid #d1d5db',
                      backgroundColor: '#ffffff',
                      cursor: 'pointer',
                      fontSize: '14px'
                    }}
                  >
                    최근 24시간
                  </button>
                </>
              );
            })()}
          </div>
        )}
      </div>

      {error && (
        <div className="error-message" style={{ color: 'red', marginBottom: '20px', padding: '12px', backgroundColor: '#fee', borderRadius: '8px' }}>
          {error}
        </div>
      )}

      {logFile && (
        <div style={{ marginBottom: '10px', color: '#6b7280', fontSize: '14px' }}>
          📁 파일: <code style={{ backgroundColor: '#f3f4f6', padding: '2px 6px', borderRadius: '4px' }}>{logFile}</code>
        </div>
      )}

      <div className="log-viewer" style={{
        backgroundColor: '#1e1e1e',
        color: '#d4d4d4',
        padding: '20px',
        borderRadius: '8px',
        fontFamily: 'Monaco, "Courier New", monospace',
        fontSize: '13px',
        lineHeight: '1.6',
        maxHeight: '600px',
        overflowY: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word'
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', color: '#9ca3af' }}>로딩 중...</div>
        ) : logContent ? (
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{logContent}</pre>
        ) : (
          <div style={{ textAlign: 'center', color: '#9ca3af' }}>로그 내용이 없습니다.</div>
        )}
      </div>
    </div>
  );
};

export default LogManagementPage;

