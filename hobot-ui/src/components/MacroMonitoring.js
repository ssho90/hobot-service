import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area } from 'recharts';
import './MacroMonitoring.css';

const MacroMonitoring = () => {
  const [yieldSpreadData, setYieldSpreadData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);

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
        setYieldSpreadData(data);
        setError(null);
      } catch (err) {
        setError(err.message);
        console.error('Error fetching yield spread data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchYieldSpreadData();
  }, []);

  // Tradingview Lightweight Charts로 장단기 금리차 차트 렌더링
  useEffect(() => {
    if (!yieldSpreadData || !chartContainerRef.current) return;

    // 기존 차트 제거
    if (chartRef.current) {
      chartRef.current.remove();
    }

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

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
      }
    };
  }, [yieldSpreadData]);

  if (loading) {
    return <div className="macro-monitoring-loading">데이터를 불러오는 중...</div>;
  }

  if (error) {
    return <div className="macro-monitoring-error">오류: {error}</div>;
  }

  return (
    <div className="macro-monitoring">
      <h1>거시경제 지표 모니터링</h1>
      
      {/* 장단기 금리차 차트 */}
      <div className="chart-section">
        <h2>장단기 금리차 (DGS10 - DGS2) - 지난 1년</h2>
        <div ref={chartContainerRef} className="yield-spread-chart" />
      </div>

      {/* 기타 지표 차트 */}
      <OtherIndicatorsCharts />
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
        {Object.entries(indicators).map(([code, data]) => {
          if (!data || data.length === 0) return null;

          const info = indicatorInfo[code];
          if (!info) return null;

          return (
            <div key={code} className="indicator-chart">
              <h3>{info.name} ({code})</h3>
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

export default MacroMonitoring;

