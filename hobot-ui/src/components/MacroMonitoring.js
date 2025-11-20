import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { useAuth } from '../context/AuthContext';
import './MacroMonitoring.css';

const MacroMonitoring = () => {
  const { isSystemAdmin, getAuthHeaders } = useAuth();
  const [activeTab, setActiveTab] = useState('macro-indicators');
  const [yieldSpreadData, setYieldSpreadData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const resizeHandlerRef = useRef(null);

  // 장단기 금리차 데이터 로드
  useEffect(() => {
    const fetchYieldSpreadData = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/macro-trading/yield-curve-spread?days=365');
        if (!response.ok) {
          throw new Error('데이터를 불러오는데 실패했습니다.');
        }
        const data = await response.json();
        
        // 에러가 있으면 표시
        if (data.error) {
          const errorMsg = data.error.message || '데이터를 불러오는 중 오류가 발생했습니다.';
          setError(errorMsg);
          // 에러가 있어도 데이터가 있으면 표시
          if (data.spread_data && data.spread_data.length > 0) {
            setYieldSpreadData(data);
          } else {
            setYieldSpreadData(null);
          }
        } else {
          setYieldSpreadData(data);
          setError(null);
        }
      } catch (err) {
        setError(err.message || '데이터를 불러오는데 실패했습니다.');
        console.error('Error fetching yield spread data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchYieldSpreadData();
  }, []);

  // Tradingview Lightweight Charts로 장단기 금리차 차트 렌더링
  useEffect(() => {
    // 거시경제 지표 탭이 활성화되고 데이터가 있을 때만 차트 렌더링
    if (activeTab !== 'macro-indicators' || !yieldSpreadData || !chartContainerRef.current) {
      // 다른 탭으로 전환 시 차트 정리
      if (activeTab !== 'macro-indicators' && chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      return;
    }

    // 기존 차트 제거
    if (chartRef.current) {
      chartRef.current.remove();
    }

    // DOM이 준비될 때까지 약간의 지연
    const timer = setTimeout(() => {
      if (!chartContainerRef.current) return;

      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: 'white' },
          textColor: 'black',
        },
        width: chartContainerRef.current.clientWidth,
        height: 500,
        grid: {
          vertLines: { color: '#e0e0e0' },
          horzLines: { color: '#e0e0e0' },
        },
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
        },
      });

      // 스프레드 라인
      const spreadSeries = chart.addLineSeries({
        title: '장단기 금리차',
        color: '#2196F3',
        lineWidth: 2,
      });

      // 20일 이동평균
      const ma20Series = chart.addLineSeries({
        title: '20일 이동평균',
        color: '#FF9800',
        lineWidth: 1,
      });

      // 120일 이동평균
      const ma120Series = chart.addLineSeries({
        title: '120일 이동평균',
        color: '#4CAF50',
        lineWidth: 1,
      });

      // 데이터 포맷팅 및 추가 (lightweight-charts는 YYYY-MM-DD 형식 필요)
      const spreadData = yieldSpreadData.spread_data.map(item => ({
        time: item.date, // 이미 YYYY-MM-DD 형식
        value: item.value,
      }));

      const ma20Data = yieldSpreadData.ma20
        .filter(item => item.value !== null)
        .map(item => ({
          time: item.date, // 이미 YYYY-MM-DD 형식
          value: item.value,
        }));

      const ma120Data = yieldSpreadData.ma120
        .filter(item => item.value !== null)
        .map(item => ({
          time: item.date, // 이미 YYYY-MM-DD 형식
          value: item.value,
        }));

      spreadSeries.setData(spreadData);
      ma20Series.setData(ma20Data);
      ma120Series.setData(ma120Data);

      chartRef.current = chart;

      // 리사이즈 핸들러
      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: chartContainerRef.current.clientWidth,
          });
        }
      };

      resizeHandlerRef.current = handleResize;
      window.addEventListener('resize', handleResize);
    }, 100);

    return () => {
      clearTimeout(timer);
      if (resizeHandlerRef.current) {
        window.removeEventListener('resize', resizeHandlerRef.current);
        resizeHandlerRef.current = null;
      }
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [yieldSpreadData, activeTab]);

  if (loading && activeTab === 'macro-indicators') {
    return <div className="macro-monitoring-loading">데이터를 불러오는 중...</div>;
  }

  if (error && activeTab === 'macro-indicators') {
    return <div className="macro-monitoring-error">오류: {error}</div>;
  }

  return (
    <div className="macro-monitoring">
      <h1>모니터링</h1>
      
      {/* 탭 메뉴 */}
      <div className="monitoring-tabs">
        <button
          className={`monitoring-tab ${activeTab === 'macro-indicators' ? 'active' : ''}`}
          onClick={() => setActiveTab('macro-indicators')}
        >
          거시경제 지표
        </button>
        {isSystemAdmin() && (
          <button
            className={`monitoring-tab ${activeTab === 'rebalancing' ? 'active' : ''}`}
            onClick={() => setActiveTab('rebalancing')}
          >
            리밸런싱 현황
          </button>
        )}
      </div>

      {/* 거시경제 지표 탭 */}
      {activeTab === 'macro-indicators' && (
        <div className="tab-content">
          {/* 에러 메시지 표시 */}
          {error && (
            <div className="macro-monitoring-error-banner">
              <strong>⚠️ 경고:</strong> {error}
            </div>
          )}
          
          {/* 장단기 금리차 차트 */}
          <div className="chart-section">
            <h2>장단기 금리차 (DGS10 - DGS2) - 지난 1년</h2>
            {yieldSpreadData && yieldSpreadData.error && (
              <div className="data-quality-warning">
                <strong>⚠️ 데이터 품질 경고:</strong> {yieldSpreadData.error.message}
                {yieldSpreadData.error.details && (
                  <ul>
                    {yieldSpreadData.error.details.map((detail, idx) => (
                      <li key={idx}>{detail}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <div ref={chartContainerRef} className="yield-spread-chart" />
          </div>

          {/* 기타 지표 차트 */}
          <OtherIndicatorsCharts />
        </div>
      )}

      {/* 리밸런싱 현황 탭 */}
      {activeTab === 'rebalancing' && isSystemAdmin() && (
        <RebalancingStatus getAuthHeaders={getAuthHeaders} />
      )}
    </div>
  );
};

// 기타 지표 차트 컴포넌트
const OtherIndicatorsCharts = () => {
  const [indicators, setIndicators] = useState({
    FEDFUNDS: null,
    CPIAUCSL: null,
    PCEPI: null,
    GDP: null,
    UNRATE: null,
    PAYEMS: null,
    WALCL: null,
    WTREGEN: null,
    RRPONTSYD: null,
    BAMLH0A0HYM2: null,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAllIndicators = async () => {
      try {
        const indicatorCodes = Object.keys(indicators);
        const promises = indicatorCodes.map(async (code) => {
          try {
            const response = await fetch(`/api/macro-trading/fred-data?indicator_code=${code}&days=365`);
            if (response.ok) {
              const data = await response.json();
              return { code, data: data.data };
            }
            return { code, data: null };
          } catch (err) {
            console.error(`Error fetching ${code}:`, err);
            return { code, data: null };
          }
        });

        const results = await Promise.all(promises);
        const newIndicators = {};
        results.forEach(({ code, data }) => {
          newIndicators[code] = data;
        });
        setIndicators(newIndicators);
      } catch (err) {
        console.error('Error fetching indicators:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchAllIndicators();
  }, []);

  if (loading) {
    return <div className="indicators-loading">지표 데이터를 불러오는 중...</div>;
  }

  // 지표별 이름 및 단위
  const indicatorInfo = {
    FEDFUNDS: { name: '연준 금리', unit: '%' },
    CPIAUCSL: { name: 'CPI (소비자물가지수)', unit: 'Index' },
    PCEPI: { name: 'PCE (개인소비지출)', unit: 'Index' },
    GDP: { name: 'GDP', unit: 'Billions of $' },
    UNRATE: { name: '실업률', unit: '%' },
    PAYEMS: { name: '비농업 고용', unit: 'Thousands' },
    WALCL: { name: '연준 총자산', unit: 'Millions of $' },
    WTREGEN: { name: '연준 총유동성', unit: 'Millions of $' },
    RRPONTSYD: { name: '역RP 잔액', unit: 'Billions of $' },
    BAMLH0A0HYM2: { name: '하이일드 스프레드', unit: '%' },
  };

  return (
      <div className="other-indicators">
        <h2>기타 거시경제 지표</h2>
        <div className="indicators-grid">
          {Object.entries(indicators).map(([code, indicatorData]) => {
            const data = indicatorData?.data || indicatorData; // 하위 호환성
            if (!data || data.length === 0) {
              // 에러가 있으면 표시
              if (indicatorData?.error) {
                const info = indicatorInfo[code];
                return (
                  <div key={code} className="indicator-chart indicator-error">
                    <h3>{info?.name || code} ({code})</h3>
                    <div className="indicator-error-message">
                      <strong>⚠️ 오류:</strong> {indicatorData.error.message}
                    </div>
                  </div>
                );
              }
              return null;
            }

            const info = indicatorInfo[code];
            if (!info) return null;

            return (
              <div key={code} className="indicator-chart">
                <h3>{info.name} ({code})</h3>
                {indicatorData?.error && (
                  <div className="indicator-warning">
                    <strong>⚠️ 경고:</strong> {indicatorData.error.message}
                  </div>
                )}
                {indicatorData?.warning && (
                  <div className="indicator-warning">
                    <strong>⚠️ 데이터 품질 경고:</strong> {indicatorData.warning.message}
                  </div>
                )}
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={data}>
                    <defs>
                      <linearGradient id={`color${code}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#2196F3" stopOpacity={0.8} />
                        <stop offset="95%" stopColor="#2196F3" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="date" 
                      tick={{ fontSize: 12 }}
                      angle={-45}
                      textAnchor="end"
                      height={80}
                    />
                    <YAxis 
                      tick={{ fontSize: 12 }}
                      label={{ value: info.unit, angle: -90, position: 'insideLeft' }}
                    />
                    <Tooltip 
                      formatter={(value) => [`${value} ${info.unit}`, info.name]}
                      labelFormatter={(label) => `날짜: ${label}`}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="#2196F3"
                      fillOpacity={1}
                      fill={`url(#color${code})`}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            );
          })}
        </div>
      </div>
  );
};

// 리밸런싱 현황 컴포넌트
const RebalancingStatus = ({ getAuthHeaders }) => {
  const [accountSnapshots, setAccountSnapshots] = useState([]);
  const [rebalancingHistory, setRebalancingHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const headers = getAuthHeaders();
        
        // 계좌 스냅샷 조회
        const snapshotsResponse = await fetch('/api/macro-trading/account-snapshots?days=30', {
          headers: {
            ...headers,
            'Content-Type': 'application/json'
          }
        });
        
        if (!snapshotsResponse.ok) {
          throw new Error('계좌 스냅샷 데이터를 불러오는데 실패했습니다.');
        }
        
        const snapshotsData = await snapshotsResponse.json();
        setAccountSnapshots(snapshotsData.data || []);
        
        // 리밸런싱 이력 조회
        const historyResponse = await fetch('/api/macro-trading/rebalancing-history?days=30', {
          headers: {
            ...headers,
            'Content-Type': 'application/json'
          }
        });
        
        if (!historyResponse.ok) {
          throw new Error('리밸런싱 이력 데이터를 불러오는데 실패했습니다.');
        }
        
        const historyData = await historyResponse.json();
        setRebalancingHistory(historyData.data || []);
        
        setError(null);
      } catch (err) {
        setError(err.message);
        console.error('Error fetching rebalancing data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [getAuthHeaders]);

  if (loading) {
    return <div className="macro-monitoring-loading">데이터를 불러오는 중...</div>;
  }

  if (error) {
    return <div className="macro-monitoring-error">오류: {error}</div>;
  }

  // 최신 계좌 스냅샷
  const latestSnapshot = accountSnapshots.length > 0 ? accountSnapshots[0] : null;

  return (
    <div className="tab-content">
      <div className="rebalancing-status">
        {/* 최신 계좌 현황 */}
        {latestSnapshot && (
          <div className="chart-section">
            <h2>최신 계좌 현황</h2>
            <div className="account-summary">
              <div className="summary-item">
                <span className="summary-label">총 자산 가치:</span>
                <span className="summary-value">{latestSnapshot.total_value?.toLocaleString('ko-KR')} 원</span>
              </div>
              <div className="summary-item">
                <span className="summary-label">현금 잔액:</span>
                <span className="summary-value">{latestSnapshot.cash_balance?.toLocaleString('ko-KR')} 원</span>
              </div>
              <div className="summary-item">
                <span className="summary-label">총 손익률:</span>
                <span className={`summary-value ${latestSnapshot.pnl_total >= 0 ? 'positive' : 'negative'}`}>
                  {latestSnapshot.pnl_total?.toFixed(2)}%
                </span>
              </div>
              <div className="summary-item">
                <span className="summary-label">스냅샷 날짜:</span>
                <span className="summary-value">{latestSnapshot.snapshot_date}</span>
              </div>
            </div>
            
            {/* 자산 배분 */}
            {latestSnapshot.allocation_actual && (
              <div className="allocation-section">
                <h3>자산 배분</h3>
                <div className="allocation-grid">
                  {Object.entries(latestSnapshot.allocation_actual).map(([asset, value]) => (
                    <div key={asset} className="allocation-item">
                      <span className="allocation-label">{asset}:</span>
                      <span className="allocation-value">{typeof value === 'number' ? value.toFixed(2) : value}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* 자산군별 손익 */}
            {latestSnapshot.pnl_by_asset && (
              <div className="pnl-section">
                <h3>자산군별 손익률</h3>
                <div className="pnl-grid">
                  {Object.entries(latestSnapshot.pnl_by_asset).map(([asset, pnl]) => (
                    <div key={asset} className="pnl-item">
                      <span className="pnl-label">{asset}:</span>
                      <span className={`pnl-value ${pnl >= 0 ? 'positive' : 'negative'}`}>
                        {typeof pnl === 'number' ? pnl.toFixed(2) : pnl}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 계좌 스냅샷 히스토리 차트 */}
        {accountSnapshots.length > 0 && (
          <div className="chart-section">
            <h2>계좌 가치 추이 (최근 30일)</h2>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={accountSnapshots.map(s => ({
                date: s.snapshot_date,
                value: s.total_value,
                pnl: s.pnl_total
              }))}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4CAF50" stopOpacity={0.8} />
                    <stop offset="95%" stopColor="#4CAF50" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="date" 
                  tick={{ fontSize: 12 }}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis 
                  tick={{ fontSize: 12 }}
                  label={{ value: '자산 가치 (원)', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip 
                  formatter={(value) => [`${value.toLocaleString('ko-KR')} 원`, '총 자산 가치']}
                  labelFormatter={(label) => `날짜: ${label}`}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#4CAF50"
                  fillOpacity={1}
                  fill="url(#colorValue)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* 리밸런싱 이력 */}
        <div className="chart-section">
          <h2>리밸런싱 실행 이력 (최근 30일)</h2>
          {rebalancingHistory.length === 0 ? (
            <div className="no-data">리밸런싱 실행 이력이 없습니다.</div>
          ) : (
            <div className="history-table">
              <table>
                <thead>
                  <tr>
                    <th>실행 일시</th>
                    <th>임계값</th>
                    <th>상태</th>
                    <th>거래 비용</th>
                    <th>실행 전 편차</th>
                    <th>실행 후 편차</th>
                  </tr>
                </thead>
                <tbody>
                  {rebalancingHistory.map((item) => (
                    <tr key={item.id}>
                      <td>{item.execution_date}</td>
                      <td>{item.threshold_used}%</td>
                      <td>
                        <span className={`status-badge status-${item.status?.toLowerCase()}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>{item.total_cost?.toLocaleString('ko-KR')} 원</td>
                      <td>
                        {item.drift_before && typeof item.drift_before === 'object' 
                          ? Object.entries(item.drift_before).map(([k, v]) => `${k}: ${v}%`).join(', ')
                          : '-'}
                      </td>
                      <td>
                        {item.drift_after && typeof item.drift_after === 'object'
                          ? Object.entries(item.drift_after).map(([k, v]) => `${k}: ${v}%`).join(', ')
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MacroMonitoring;

