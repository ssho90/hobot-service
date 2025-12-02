import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useAuth } from '../context/AuthContext';
import './MacroDashboard.css';
import './MacroMonitoring.css';

const MacroDashboard = () => {
  const [subTab, setSubTab] = useState('fred'); // 'fred' or 'news'
  const [overviewData, setOverviewData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const { isAdmin, getAuthHeaders } = useAuth();

  // Overview 데이터 로드
  const fetchOverview = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/macro-trading/overview');
      if (response.ok) {
        const result = await response.json();
        if (result.status === 'success' && result.data) {
          setOverviewData(result.data);
        } else {
          setOverviewData(null);
        }
      } else {
        throw new Error('AI 분석 데이터를 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError(err.message);
      console.error('Error fetching overview:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, []);

  // 수동 AI 분석 실행
  const handleManualUpdate = async () => {
    if (!isAdmin()) {
      alert('관리자만 사용할 수 있는 기능입니다.');
      return;
    }

    setUpdating(true);
    setError(null);
    
    try {
      const response = await fetch('/api/macro-trading/run-ai-analysis', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        }
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === 'success') {
          alert('AI 분석이 완료되었습니다. 결과를 불러오는 중...');
          // 분석 완료 후 데이터 다시 로드
          await fetchOverview();
        } else {
          throw new Error(result.message || 'AI 분석 실행에 실패했습니다.');
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: '알 수 없는 오류' }));
        throw new Error(errorData.detail || 'AI 분석 실행에 실패했습니다.');
      }
    } catch (err) {
      setError(err.message);
      alert(`오류: ${err.message}`);
      console.error('Error running AI analysis:', err);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="macro-dashboard">
      {/* Overview 섹션 (항상 표시) */}
      <div className="overview-section">
        <div className="overview-header-section">
          <h2>overview</h2>
          <div className="overview-buttons">
            <button
              className="btn btn-secondary btn-history"
              onClick={() => setShowHistoryModal(true)}
            >
              지난 분석 보기
            </button>
            {isAdmin() && (
              <button
                className="btn btn-primary btn-update"
                onClick={handleManualUpdate}
                disabled={updating || loading}
              >
                {updating ? '분석 중...' : '수동 업데이트'}
              </button>
            )}
          </div>
        </div>
        <div className="card overview-card">
          {loading && <div className="loading">분석 중...</div>}
          {error && <div className="error">오류: {error}</div>}
          {!loading && !error && !overviewData && (
            <div className="overview-placeholder">
              <p>Overview 관련 내용 출력</p>
            </div>
          )}
          {overviewData && (
            <div className="overview-content">
              <div className="overview-header">
                <div className="overview-date">
                  분석 일시: {overviewData.decision_date || overviewData.created_at}
                </div>
              </div>
              
              <div className="analysis-summary">
                <h3>분석 요약</h3>
                <p>{overviewData.analysis_summary}</p>
              </div>
              
              {overviewData.reasoning && (
                <div className="analysis-reasoning">
                  <h3>판단 근거</h3>
                  <p>{overviewData.reasoning}</p>
                </div>
              )}
              
              {overviewData.target_allocation && (
                <div className="target-allocation">
                  <h3>목표 자산 배분</h3>
                  <div className="allocation-grid">
                    <div className="allocation-item">
                      <span className="allocation-label">주식</span>
                      <span className="allocation-value">{overviewData.target_allocation.Stocks?.toFixed(1) || 0}%</span>
                    </div>
                    <div className="allocation-item">
                      <span className="allocation-label">채권</span>
                      <span className="allocation-value">{overviewData.target_allocation.Bonds?.toFixed(1) || 0}%</span>
                    </div>
                    <div className="allocation-item">
                      <span className="allocation-label">대체투자</span>
                      <span className="allocation-value">{overviewData.target_allocation.Alternatives?.toFixed(1) || 0}%</span>
                    </div>
                    <div className="allocation-item">
                      <span className="allocation-label">현금</span>
                      <span className="allocation-value">{overviewData.target_allocation.Cash?.toFixed(1) || 0}%</span>
                    </div>
                  </div>
                </div>
              )}
              
              {overviewData.recommended_stocks && (
                <div className="recommended-stocks">
                  <h3>추천 섹터/카테고리</h3>
                  {overviewData.recommended_stocks.Stocks && overviewData.recommended_stocks.Stocks.length > 0 && (
                    <div className="recommended-stocks-section">
                      <h4>주식 (Stocks)</h4>
                      <div className="recommended-stocks-list">
                        {overviewData.recommended_stocks.Stocks.map((stock, idx) => (
                          <div key={idx} className="recommended-stock-item">
                            <span className="stock-category">{stock.category || stock.name || 'N/A'}</span>
                            {stock.ticker && (
                              <span className="stock-ticker">({stock.ticker})</span>
                            )}
                            {stock.name && stock.name !== stock.category && (
                              <span className="stock-name"> - {stock.name}</span>
                            )}
                            <span className="stock-weight">{((stock.weight || 0) * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {overviewData.recommended_stocks.Bonds && overviewData.recommended_stocks.Bonds.length > 0 && (
                    <div className="recommended-stocks-section">
                      <h4>채권 (Bonds)</h4>
                      <div className="recommended-stocks-list">
                        {overviewData.recommended_stocks.Bonds.map((stock, idx) => (
                          <div key={idx} className="recommended-stock-item">
                            <span className="stock-category">{stock.category || stock.name || 'N/A'}</span>
                            {stock.ticker && (
                              <span className="stock-ticker">({stock.ticker})</span>
                            )}
                            {stock.name && stock.name !== stock.category && (
                              <span className="stock-name"> - {stock.name}</span>
                            )}
                            <span className="stock-weight">{((stock.weight || 0) * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {overviewData.recommended_stocks.Alternatives && overviewData.recommended_stocks.Alternatives.length > 0 && (
                    <div className="recommended-stocks-section">
                      <h4>대체투자 (Alternatives)</h4>
                      <div className="recommended-stocks-list">
                        {overviewData.recommended_stocks.Alternatives.map((stock, idx) => (
                          <div key={idx} className="recommended-stock-item">
                            <span className="stock-category">{stock.category || stock.name || 'N/A'}</span>
                            {stock.ticker && (
                              <span className="stock-ticker">({stock.ticker})</span>
                            )}
                            {stock.name && stock.name !== stock.category && (
                              <span className="stock-name"> - {stock.name}</span>
                            )}
                            <span className="stock-weight">{((stock.weight || 0) * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {overviewData.recommended_stocks.Cash && overviewData.recommended_stocks.Cash.length > 0 && (
                    <div className="recommended-stocks-section">
                      <h4>현금 (Cash)</h4>
                      <div className="recommended-stocks-list">
                        {overviewData.recommended_stocks.Cash.map((stock, idx) => (
                          <div key={idx} className="recommended-stock-item">
                            <span className="stock-category">{stock.category || stock.name || 'N/A'}</span>
                            {stock.ticker && (
                              <span className="stock-ticker">({stock.ticker})</span>
                            )}
                            {stock.name && stock.name !== stock.category && (
                              <span className="stock-name"> - {stock.name}</span>
                            )}
                            <span className="stock-weight">{((stock.weight || 0) * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 구분선 */}
      <div className="divider"></div>

      {/* 서브 탭 메뉴 (Fred 지표, Economic News) */}
      <div className="sub-tabs">
        <button
          className={`sub-tab ${subTab === 'fred' ? 'active' : ''}`}
          onClick={() => setSubTab('fred')}
        >
          Fred 지표
        </button>
        <button
          className={`sub-tab ${subTab === 'news' ? 'active' : ''}`}
          onClick={() => setSubTab('news')}
        >
          Economic News
        </button>
      </div>

      {/* 서브 탭 컨텐츠 */}
      <div className="sub-tab-content">
        {subTab === 'fred' && <FredIndicatorsTab />}
        {subTab === 'news' && <EconomicNewsTab />}
      </div>

      {/* 지난 분석 보기 모달 */}
      {showHistoryModal && (
        <AnalysisHistoryModal
          onClose={() => setShowHistoryModal(false)}
        />
      )}
    </div>
  );
};

// FRED 지표 탭 컴포넌트
const FredIndicatorsTab = () => {
  const [yieldSpreadData, setYieldSpreadData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const resizeHandlerRef = useRef(null);

  // 장단기 금리차 데이터 로드
  useEffect(() => {
    const fetchYieldSpreadData = async () => {
      const url = '/api/macro-trading/yield-curve-spread?days=365';
      console.log('[MacroDashboard] Fetching yield spread data from:', url);
      
      try {
        setLoading(true);
        setError(null);
        
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }).catch((fetchError) => {
          console.error('[MacroDashboard] Fetch error details:', {
            name: fetchError.name,
            message: fetchError.message,
            stack: fetchError.stack,
            cause: fetchError.cause,
            type: fetchError.constructor.name,
          });
          throw fetchError;
        });
        
        console.log('[MacroDashboard] Response received:', {
          status: response.status,
          statusText: response.statusText,
          ok: response.ok,
          headers: Object.fromEntries(response.headers.entries()),
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error('[MacroDashboard] Error response body:', errorText);
          let errorData;
          try {
            errorData = JSON.parse(errorText);
          } catch {
            errorData = { detail: `서버 오류 (${response.status} ${response.statusText})` };
          }
          throw new Error(errorData.detail || '데이터를 불러오는데 실패했습니다.');
        }
        
        const data = await response.json();
        console.log('[MacroDashboard] Data received:', { hasError: !!data.error, dataKeys: Object.keys(data) });
        
        if (data.error) {
          const errorMsg = data.error.message || '데이터를 불러오는 중 오류가 발생했습니다.';
          console.error('[MacroDashboard] Data contains error:', data.error);
          setError(errorMsg);
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
        console.error('[MacroDashboard] Full error object:', {
          name: err.name,
          message: err.message,
          stack: err.stack,
          cause: err.cause,
          type: err.constructor.name,
          toString: err.toString(),
        });
        
        // 네트워크 에러인 경우
        if (err.name === 'TypeError' && (err.message.includes('fetch') || err.message.includes('Failed to fetch'))) {
          const errorMsg = '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요. (프록시 설정: http://localhost:8991)';
          console.error('[MacroDashboard] Network error - 프록시 또는 백엔드 서버 연결 실패');
          setError(errorMsg);
        } else {
          setError(err.message || '데이터를 불러오는데 실패했습니다.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchYieldSpreadData();
  }, []);

  // Tradingview Lightweight Charts로 장단기 금리차 차트 렌더링
  useEffect(() => {
    if (!yieldSpreadData || !chartContainerRef.current) {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      return;
    }

    if (chartRef.current) {
      chartRef.current.remove();
    }

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

      const spreadSeries = chart.addLineSeries({
        title: '장단기 금리차',
        color: '#2196F3',
        lineWidth: 2,
      });

      const ma20Series = chart.addLineSeries({
        title: '20일 이동평균',
        color: '#FF9800',
        lineWidth: 1,
      });

      const ma120Series = chart.addLineSeries({
        title: '120일 이동평균',
        color: '#4CAF50',
        lineWidth: 1,
      });

      const spreadData = yieldSpreadData.spread_data.map(item => ({
        time: item.date,
        value: item.value,
      }));

      const ma20Data = yieldSpreadData.ma20
        .filter(item => item.value !== null)
        .map(item => ({
          time: item.date,
          value: item.value,
        }));

      const ma120Data = yieldSpreadData.ma120
        .filter(item => item.value !== null)
        .map(item => ({
          time: item.date,
          value: item.value,
        }));

      spreadSeries.setData(spreadData);
      ma20Series.setData(ma20Data);
      ma120Series.setData(ma120Data);

      chartRef.current = chart;

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
  }, [yieldSpreadData]);

  return (
    <div className="fred-indicators-tab">
      {loading && <div className="macro-monitoring-loading">데이터를 불러오는 중...</div>}
      {error && (
        <div className="macro-monitoring-error-banner">
          <strong>⚠️ 경고:</strong> {error}
        </div>
      )}
      
      {!loading && yieldSpreadData && (
        <>
          {/* 장단기 금리차 차트 */}
          <div className="chart-section">
            <h2>장단기 금리차 (DGS10 - DGS2) - 지난 1년</h2>
            {yieldSpreadData.error && (
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
        </>
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
            // 네트워크 에러는 조용히 처리 (개별 지표 실패는 전체를 막지 않음)
            if (err.name === 'TypeError' && err.message.includes('fetch')) {
              console.error(`Network error fetching ${code}: 서버에 연결할 수 없습니다.`);
            } else {
              console.error(`Error fetching ${code}:`, err);
            }
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
          const data = indicatorData?.data || indicatorData;
          if (!data || data.length === 0) {
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

// Economic News 탭 컴포넌트
const EconomicNewsTab = () => {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [hours, setHours] = useState(24);
  const [filterCountry, setFilterCountry] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [translationLang, setTranslationLang] = useState('en'); // 'en' or 'ko'
  const [translatedData, setTranslatedData] = useState({}); // {field_id: translated_text}
  const [translating, setTranslating] = useState({}); // {field_id: true/false}

  useEffect(() => {
    const fetchNews = async () => {
      const url = `/api/macro-trading/economic-news?hours=${hours}`;
      console.log('[EconomicNewsTab] Fetching news from:', url);
      
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }).catch((fetchError) => {
          console.error('[EconomicNewsTab] Fetch error details:', {
            name: fetchError.name,
            message: fetchError.message,
            stack: fetchError.stack,
            cause: fetchError.cause,
            type: fetchError.constructor.name,
          });
          throw fetchError;
        });
        
        console.log('[EconomicNewsTab] Response received:', {
          status: response.status,
          statusText: response.statusText,
          ok: response.ok,
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error('[EconomicNewsTab] Error response body:', errorText);
          let errorData;
          try {
            errorData = JSON.parse(errorText);
          } catch {
            errorData = { detail: `서버 오류 (${response.status} ${response.statusText})` };
          }
          throw new Error(errorData.detail || '뉴스를 불러오는데 실패했습니다.');
        }
        const data = await response.json();
        console.log('[EconomicNewsTab] Data received:', { newsCount: data.news?.length || 0 });
        setNews(data.news || []);
      } catch (err) {
        console.error('[EconomicNewsTab] Full error object:', {
          name: err.name,
          message: err.message,
          stack: err.stack,
          cause: err.cause,
          type: err.constructor.name,
          toString: err.toString(),
        });
        
        // 네트워크 에러인 경우
        if (err.name === 'TypeError' && (err.message.includes('fetch') || err.message.includes('Failed to fetch'))) {
          console.error('[EconomicNewsTab] Network error - 프록시 또는 백엔드 서버 연결 실패');
          setError('서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요. (프록시 설정: http://localhost:8991)');
        } else {
          setError(err.message || '뉴스를 불러오는데 실패했습니다.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, [hours]);

  // 필터링된 뉴스 (published_at 기준 최신순 정렬)
  const filteredNews = news
    .filter(item => {
      if (filterCountry && item.country !== filterCountry) return false;
      if (filterCategory && item.category !== filterCategory) return false;
      return true;
    })
    .sort((a, b) => {
      // published_at 기준 최신순 정렬 (내림차순)
      if (!a.published_at && !b.published_at) return 0;
      if (!a.published_at) return 1;
      if (!b.published_at) return -1;
      return new Date(b.published_at) - new Date(a.published_at);
    });

  // 국가 및 카테고리 목록
  const countries = [...new Set(news.map(item => item.country).filter(Boolean))].sort();
  const categories = [...new Set(news.map(item => item.category).filter(Boolean))].sort();

  // 번역 함수
  const translateText = async (text, fieldId, newsId, fieldType) => {
    if (!text || translationLang === 'en') {
      // 영어 모드이거나 텍스트가 없으면 번역하지 않음
      const newTranslatedData = { ...translatedData };
      delete newTranslatedData[fieldId];
      setTranslatedData(newTranslatedData);
      return;
    }

    // 이미 번역된 데이터가 있으면 사용
    if (translatedData[fieldId]) {
      return;
    }

    setTranslating({ ...translating, [fieldId]: true });

    try {
      const response = await fetch('/api/macro-trading/translate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: text,
          target_lang: 'ko',
          news_id: newsId,
          field_type: fieldType
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setTranslatedData({
            ...translatedData,
            [fieldId]: data.translated_text
          });
        }
      }
    } catch (err) {
      console.error('Translation error:', err);
    } finally {
      setTranslating({ ...translating, [fieldId]: false });
    }
  };

  // 번역 언어 변경 시 번역 데이터 초기화
  useEffect(() => {
    if (translationLang === 'en') {
      setTranslatedData({});
      setTranslating({});
    }
  }, [translationLang]);

  // 한글 모드일 때 뉴스가 로드되면 번역 요청 (DB에서 먼저 확인)
  useEffect(() => {
    if (translationLang === 'ko' && filteredNews.length > 0) {
      // DB에서 이미 번역된 내용이 있으면 먼저 사용 (title, description만)
      filteredNews.forEach((item) => {
        const titleKey = `title_${item.id}`;
        const descKey = `desc_${item.id}`;
        
        // DB에서 가져온 번역 데이터가 있으면 사용
        if (item.title_ko && !translatedData[titleKey]) {
          setTranslatedData(prev => ({ ...prev, [titleKey]: item.title_ko }));
        }
        if (item.description_ko && !translatedData[descKey]) {
          setTranslatedData(prev => ({ ...prev, [descKey]: item.description_ko }));
        }
        
        // DB에 번역이 없으면 번역 요청 (title, description만)
        if (item.title && !item.title_ko && !translatedData[titleKey] && !translating[titleKey]) {
          translateText(item.title, titleKey, item.id, 'title');
        }
        if (item.description && !item.description_ko && !translatedData[descKey] && !translating[descKey]) {
          translateText(item.description, descKey, item.id, 'description');
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translationLang, news]);

  return (
    <div className="tab-content">
      <div className="news-controls">
        <div className="control-group">
          <label>시간 범위:</label>
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={24}>24시간</option>
            <option value={48}>48시간</option>
            <option value={72}>72시간</option>
            <option value={168}>1주일</option>
          </select>
        </div>
        <div className="control-group">
          <label>국가:</label>
          <select value={filterCountry} onChange={(e) => setFilterCountry(e.target.value)}>
            <option value="">전체</option>
            {countries.map(country => (
              <option key={country} value={country}>{country}</option>
            ))}
          </select>
        </div>
        <div className="control-group">
          <label>카테고리:</label>
          <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}>
            <option value="">전체</option>
            {categories.map(category => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>
        </div>
        <div className="control-group">
          <label>번역:</label>
          <div className="lang-toggle">
            <button
              className={translationLang === 'en' ? 'active' : ''}
              onClick={() => setTranslationLang('en')}
            >
              EN
            </button>
            <button
              className={translationLang === 'ko' ? 'active' : ''}
              onClick={() => setTranslationLang('ko')}
            >
              KO
            </button>
          </div>
        </div>
      </div>

      {loading && <div className="loading">뉴스를 불러오는 중...</div>}
      {error && <div className="error">오류: {error}</div>}
      {!loading && !error && (
        <div className="news-list">
          <div className="news-summary">
            총 {filteredNews.length}개의 뉴스가 있습니다.
          </div>
          {filteredNews.length === 0 ? (
            <div className="no-news">뉴스가 없습니다.</div>
          ) : (
            filteredNews.map(item => {
              const titleKey = `title_${item.id}`;
              const descKey = `desc_${item.id}`;
              
              const displayTitle = translationLang === 'ko' && translatedData[titleKey] 
                ? translatedData[titleKey] 
                : item.title;
              const displayDesc = translationLang === 'ko' && translatedData[descKey] 
                ? translatedData[descKey] 
                : item.description;

              return (
                <div key={item.id} className="news-item">
                  <div className="news-header">
                    <h3 className="news-title">
                      {item.link ? (
                        <a href={item.link} target="_blank" rel="noopener noreferrer">
                          {translating[titleKey] ? '번역 중...' : displayTitle}
                        </a>
                      ) : (
                        translating[titleKey] ? '번역 중...' : displayTitle
                      )}
                    </h3>
                    <div className="news-meta">
                      {item.country && (
                        <span className="news-country">
                          {item.country}
                        </span>
                      )}
                      {item.category && (
                        <span className="news-category">
                          {item.category}
                        </span>
                      )}
                      {item.published_at && (
                        <span className="news-date">
                          {new Date(item.published_at).toLocaleString('ko-KR')}
                        </span>
                      )}
                    </div>
                  </div>
                  {displayDesc && (
                    <div className="news-description">
                      {translating[descKey] ? '번역 중...' : displayDesc}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};

// 지난 분석 보기 모달 컴포넌트
const AnalysisHistoryModal = ({ onClose }) => {
  const [decision, setDecision] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // 분석 이력 로드
  const fetchHistory = async (pageNum) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/macro-trading/strategy-decisions-history?page=${pageNum}`);
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setDecision(data.data);
          setTotalPages(data.total_pages || 1);
        } else {
          throw new Error(data.message || '분석 이력을 불러오는데 실패했습니다.');
        }
      } else {
        throw new Error('분석 이력을 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError(err.message);
      console.error('Error fetching analysis history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory(page);
  }, [page]);

  const handlePrevPage = () => {
    if (page > 1) {
      setPage(page - 1);
    }
  };

  const handleNextPage = () => {
    if (page < totalPages) {
      setPage(page + 1);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content history-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>지난 AI 분석 내용</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        
        <div className="modal-body history-modal-body">
          {loading && <div className="loading">로딩 중...</div>}
          {error && <div className="error">오류: {error}</div>}
          
          {!loading && !error && !decision && (
            <div className="no-data">분석 이력이 없습니다.</div>
          )}
          
          {!loading && !error && decision && (
            <div className="history-content">
              <div className="history-item">
                <div className="history-header">
                  <div className="history-date">
                    {decision.decision_date || decision.created_at}
                  </div>
                </div>
                
                {decision.analysis_summary && (
                  <div className="history-section">
                    <h3>분석 요약</h3>
                    <p>{decision.analysis_summary}</p>
                  </div>
                )}
                
                {decision.reasoning && (
                  <div className="history-section">
                    <h3>판단 근거</h3>
                    <p>{decision.reasoning}</p>
                  </div>
                )}
                
                {decision.target_allocation && (
                  <div className="history-section">
                    <h3>목표 자산 배분</h3>
                    <div className="allocation-grid">
                      {decision.target_allocation.Stocks !== undefined && (
                        <div className="allocation-item">
                          <span className="allocation-label">주식</span>
                          <span className="allocation-value">
                            {decision.target_allocation.Stocks?.toFixed(1) || 0}%
                          </span>
                        </div>
                      )}
                      {decision.target_allocation.Bonds !== undefined && (
                        <div className="allocation-item">
                          <span className="allocation-label">채권</span>
                          <span className="allocation-value">
                            {decision.target_allocation.Bonds?.toFixed(1) || 0}%
                          </span>
                        </div>
                      )}
                      {decision.target_allocation.Alternatives !== undefined && (
                        <div className="allocation-item">
                          <span className="allocation-label">대체투자</span>
                          <span className="allocation-value">
                            {decision.target_allocation.Alternatives?.toFixed(1) || 0}%
                          </span>
                        </div>
                      )}
                      {decision.target_allocation.Cash !== undefined && (
                        <div className="allocation-item">
                          <span className="allocation-label">현금</span>
                          <span className="allocation-value">
                            {decision.target_allocation.Cash?.toFixed(1) || 0}%
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              {/* 페이징 버튼을 내용 아래에 배치 */}
              <div className="pagination">
                <button
                  className="pagination-btn"
                  onClick={handlePrevPage}
                  disabled={page === 1 || loading}
                >
                  이전
                </button>
                <span className="pagination-info">
                  {page} / {totalPages}
                </span>
                <button
                  className="pagination-btn"
                  onClick={handleNextPage}
                  disabled={page >= totalPages || loading}
                >
                  다음
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MacroDashboard;

