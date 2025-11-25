import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import './MacroDashboard.css';
import './MacroMonitoring.css';

const MacroDashboard = () => {
  const [subTab, setSubTab] = useState('fred'); // 'fred' or 'news'
  const [overviewData, setOverviewData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Overview 데이터 로드 (API는 추후 구현)
  useEffect(() => {
    // TODO: LLM 분석 결과 API 호출
    // const fetchOverview = async () => {
    //   setLoading(true);
    //   try {
    //     const response = await fetch('/api/macro-trading/overview');
    //     if (response.ok) {
    //       const data = await response.json();
    //       setOverviewData(data);
    //     }
    //   } catch (err) {
    //     setError(err.message);
    //   } finally {
    //     setLoading(false);
    //   }
    // };
    // fetchOverview();
  }, []);

  return (
    <div className="macro-dashboard">
      {/* Overview 섹션 (항상 표시) */}
      <div className="overview-section">
        <h2>overview</h2>
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
              <div className="analysis-result">
                {/* LLM 분석 결과 표시 */}
                <pre>{JSON.stringify(overviewData, null, 2)}</pre>
              </div>
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
      try {
        setLoading(true);
        const response = await fetch('/api/macro-trading/yield-curve-spread?days=365');
        if (!response.ok) {
          throw new Error('데이터를 불러오는데 실패했습니다.');
        }
        const data = await response.json();
        
        if (data.error) {
          const errorMsg = data.error.message || '데이터를 불러오는 중 오류가 발생했습니다.';
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
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/macro-trading/economic-news?hours=${hours}`);
        if (!response.ok) {
          throw new Error('뉴스를 불러오는데 실패했습니다.');
        }
        const data = await response.json();
        setNews(data.news || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, [hours]);

  // 필터링된 뉴스
  const filteredNews = news.filter(item => {
    if (filterCountry && item.country !== filterCountry) return false;
    if (filterCategory && item.category !== filterCategory) return false;
    return true;
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

export default MacroDashboard;

