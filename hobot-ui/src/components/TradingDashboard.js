import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { createChart, ColorType } from 'lightweight-charts';
import './TradingDashboard.css';

const TradingDashboard = () => {
  const { getAuthHeaders } = useAuth();
  const [kisBalance, setKisBalance] = useState(null);
  const [kisLoading, setKisLoading] = useState(false);
  const [kisError, setKisError] = useState(null);
  const [rebalanceStatus, setRebalanceStatus] = useState(null);
  const [rebalanceLoading, setRebalanceLoading] = useState(false);
  const [rebalanceError, setRebalanceError] = useState(null);
  const [historyData, setHistoryData] = useState([]);
  const [testModalOpen, setTestModalOpen] = useState(false);

  // KIS 계좌 잔액 조회
  useEffect(() => {
    const fetchKisBalance = async (isBackground = false) => {
      if (!isBackground) {
        setKisLoading(true);
        setKisError(null);
      }
      try {
        const headers = getAuthHeaders();
        const response = await fetch('/api/kis/balance', {
          headers: {
            ...headers,
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          const data = await response.json();
          setKisBalance(data);
        } else {
          const errorData = await response.json();
          // 백그라운드 갱신 중 에러는 조용히 로그만 남기거나 에러 상태 업데이트 (선택사항)
          // 여기서는 에러 상태를 업데이트하되, 화면 전체가 에러로 바뀌는 UX 고려
          if (!isBackground) {
            throw new Error(errorData.message || '계좌 정보를 불러오는데 실패했습니다.');
          } else {
            console.error('Background fetch failed:', errorData.message);
          }
        }
      } catch (err) {
        if (!isBackground) {
          setKisError(err.message);
        } else {
          console.error('Background fetch error:', err.message);
        }
      } finally {
        if (!isBackground) {
          setKisLoading(false);
        }
      }
    };

    fetchKisBalance(false); // 초기 로딩

    const intervalId = setInterval(() => {
      fetchKisBalance(true); // 백그라운드 갱신
    }, 10000); // 10초마다

    return () => clearInterval(intervalId);
  }, [getAuthHeaders]);

  // 리밸런싱 현황 조회 (MP / Sub-MP 목표 vs 실제)
  useEffect(() => {
    const fetchRebalanceStatus = async () => {
      setRebalanceLoading(true);
      setRebalanceError(null);
      try {
        const headers = getAuthHeaders();
        const response = await fetch('/api/macro-trading/rebalancing-status', {
          headers: {
            ...headers,
            'Content-Type': 'application/json'
          }
        });
        const data = await response.json();
        if (!response.ok || data.status === 'error') {
          throw new Error(data.message || '리밸런싱 현황을 불러오는데 실패했습니다.');
        }
        setRebalanceStatus(data.data);
      } catch (err) {
        setRebalanceError(err.message);
      } finally {
        setRebalanceLoading(false);
      }
    };
    fetchRebalanceStatus();
    fetchRebalanceStatus();
  }, [getAuthHeaders]);

  // 자산 히스토리 조회
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const headers = getAuthHeaders();
        const response = await fetch('/api/macro-trading/account-snapshots?days=30', {
          headers: { ...headers, 'Content-Type': 'application/json' }
        });
        if (response.ok) {
          const data = await response.json();
          // 날짜 오름차순 정렬
          const sorted = data.sort((a, b) => new Date(a.snapshot_date) - new Date(b.snapshot_date));
          setHistoryData(sorted);
        }
      } catch (err) {
        console.error("Failed to fetch history:", err);
      }
    };
    fetchHistory();
  }, [getAuthHeaders]);

  return (
    <div className="trading-dashboard">
      <MacroQuantTradingTab
        balance={kisBalance}
        loading={kisLoading}
        error={kisError}
        rebalanceStatus={rebalanceStatus}
        rebalanceLoading={rebalanceLoading}
        rebalanceError={rebalanceError}
        historyData={historyData}
        onOpenTestModal={() => setTestModalOpen(true)}
      />
      {testModalOpen && (
        <RebalancingTestModal
          onClose={() => setTestModalOpen(false)}
          getAuthHeaders={getAuthHeaders}
        />
      )}
    </div>
  );
};

// Macro Quant Trading 탭 컴포넌트
const MacroQuantTradingTab = ({ balance, loading, error, rebalanceStatus, rebalanceLoading, rebalanceError, historyData, onOpenTestModal }) => {
  const [activeTab, setActiveTab] = useState('account');
  const chartContainerRef = useRef(null);

  useEffect(() => {
    if (activeTab === 'account' && chartContainerRef.current && historyData.length > 0) {
      const chart = createChart(chartContainerRef.current, {
        layout: { background: { type: ColorType.Solid, color: 'white' } },
        width: chartContainerRef.current.clientWidth,
        height: 200,
        rightPriceScale: { borderVisible: false },
        timeScale: { borderVisible: false, timeVisible: false, secondsVisible: false },
        grid: { horzLines: { visible: false }, vertLines: { visible: false } }
      });

      const lineSeries = chart.addLineSeries({ color: '#2962FF' });
      const data = historyData.map(d => ({ time: d.snapshot_date, value: d.total_value }));
      lineSeries.setData(data);
      chart.timeScale().fitContent();

      const handleResize = () => {
        if (chartContainerRef.current) {
          chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        }
      };
      window.addEventListener('resize', handleResize);
      return () => {
        window.removeEventListener('resize', handleResize);
        chart.remove();
      };
    }
  }, [activeTab, historyData]);

  return (
    <div className="tab-content">
      <div className="dashboard-tabs" style={{ marginBottom: '15px', borderBottom: '1px solid #e0e0e0', justifyContent: 'flex-start' }}>
        <button
          className={`dashboard-tab ${activeTab === 'account' ? 'active' : ''}`}
          onClick={() => setActiveTab('account')}
        >
          계좌/자산
        </button>
        <button
          className={`dashboard-tab ${activeTab === 'rebalance' ? 'active' : ''}`}
          onClick={() => setActiveTab('rebalance')}
        >
          리밸런싱 현황
        </button>
        {activeTab === 'rebalance' && (
          <div style={{ marginLeft: 'auto', alignSelf: 'center' }}>
            <button className="btn btn-primary" onClick={onOpenTestModal} style={{ padding: '6px 12px', fontSize: '13px' }}>
              Rebalancing Test
            </button>
          </div>
        )}
      </div>

      {activeTab === 'rebalance' && (
        <RebalancingStatusCard
          data={rebalanceStatus}
          loading={rebalanceLoading}
          error={rebalanceError}
        />
      )}

      {activeTab === 'account' && (
        <div className="account-assets-container">
          <div className="account-holdings-row">
            {/* Left: Account Info */}
            <div className="card account-info-card" style={{ flex: '0 0 350px' }}>
              <h2>계좌 정보</h2>
              {loading && <div className="loading">계좌 정보를 불러오는 중...</div>}
              {error && <div className="error">오류: {error}</div>}
              {!loading && !error && balance && balance.status === 'success' && (
                <div className="account-info-summary">
                  <div className="info-row">
                    <span className="info-label">계좌번호:</span>
                    <span className="info-value">{balance.account_no}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">총 평가금액:</span>
                    <span className="info-value">
                      {balance.total_eval_amount?.toLocaleString('ko-KR')} 원
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">총 손익:</span>
                    <span className={`info-value ${balance.total_profit_loss >= 0 ? 'positive' : 'negative'}`}
                      style={{ color: balance.total_profit_loss >= 0 ? '#d32f2f' : '#1976D2' }}>
                      {balance.total_profit_loss > 0 ? '+' : ''}{balance.total_profit_loss?.toLocaleString('ko-KR')}원 ( {balance.total_return_rate > 0 ? '+' : ''}{balance.total_return_rate}% )
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">가수도정산(D+2):</span>
                    <span className="info-value">
                      {balance.cash_balance?.toLocaleString('ko-KR')} 원
                    </span>
                  </div>
                </div>
              )}
              {!loading && !error && (!balance || balance.status !== 'success') && (
                <div className="no-data">계좌 정보를 불러올 수 없습니다.</div>
              )}
            </div>

            {/* Right: Holdings */}
            {balance && balance.status === 'success' && balance.holdings && (
              <div className="card holdings-card" style={{ flex: 1, minWidth: 0 }}>
                <h2>보유 자산</h2>
                <div className="holdings-table">
                  <table>
                    <thead>
                      <tr>
                        <th>종목명</th>
                        <th>보유수량</th>
                        <th>평가금액</th>
                        <th>손익률</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...balance.holdings]
                        .sort((a, b) => b.eval_amount - a.eval_amount)
                        .map((holding, idx) => (
                          <tr key={idx}>
                            <td>
                              <div style={{ fontWeight: 500 }}>{holding.stock_name}</div>
                              <div style={{ fontSize: '11px', color: '#888' }}>{holding.stock_code}</div>
                            </td>
                            <td>{holding.quantity?.toLocaleString('ko-KR')}</td>
                            <td>{holding.eval_amount?.toLocaleString('ko-KR')}</td>
                            <td className={holding.profit_loss_rate >= 0 ? 'positive' : 'negative'}>
                              {holding.profit_loss_rate?.toFixed(2)}%
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* Chart Section (Bottom) */}
          <div className="card account-chart-card">
            <h2>총 자산 추이 (일별)</h2>
            {historyData.length > 0 ? (
              <div ref={chartContainerRef} style={{ width: '100%', height: '250px' }} />
            ) : (
              <div className="no-data">데이터가 없습니다 (최근 30일)</div>
            )}
          </div>
        </div>
      )}

    </div>
  );
};

export default TradingDashboard;

// ... (TrafficLight component definition)
const TrafficLight = ({ needed, reasons = [] }) => {
  const status = needed ? 'red' : 'green';
  const tooltip = reasons.length > 0 ? reasons.join('\n') : (needed ? '리밸런싱 필요' : '정상');
  return (
    <span
      className={`traffic-light ${status}`}
      title={tooltip}
    />
  );
};

const RebalancingStatusCard = ({ data, loading, error }) => {
  const assetClassLabels = {
    stocks: '주식',
    bonds: '채권',
    alternatives: '대체',
    cash: '현금'
  };

  const barPalette = {
    target: ['#4F81BD', '#9BBB59', '#C0504D', '#8064A2', '#46b5d1', '#f4b400'],
    actual: ['#3b6aa3', '#7da444', '#a33f3a', '#684f88', '#2e9bc0', '#d49a00'],
  };

  // 화면 크기에 따른 라벨 표시 모드 관리
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);


  // Drift Analysis Logic
  const getMpStatus = () => {
    if (!data?.rebalancing_status) return { needed: false, reasons: [] };
    const { drift_details, thresholds } = data.rebalancing_status;
    const mpDrifts = drift_details?.mp_drifts || {};
    const threshold = thresholds?.mp || 3.0;

    let needed = false;
    let reasons = [];

    Object.entries(mpDrifts).forEach(([asset, drift]) => {
      if (Math.abs(drift) >= threshold) {
        needed = true;
        reasons.push(`${assetClassLabels[asset] || asset}: ${drift}% (임계값 ${threshold}%)`);
      }
    });
    return { needed, reasons };
  };

  const getSubMpStatus = (assetClass) => {
    if (!data?.rebalancing_status) return { needed: false, reasons: [] };
    const { drift_details, thresholds } = data.rebalancing_status;
    const subMpDrifts = drift_details?.sub_mp_drifts || {};
    // sub_mp_drifts: { "stocks": [{"ticker":..., "drift":...}] }

    const items = subMpDrifts[assetClass] || [];
    const threshold = thresholds?.sub_mp || 5.0;

    let needed = false;
    let reasons = [];

    items.forEach(item => {
      if (Math.abs(item.drift) >= threshold) {
        needed = true;
        reasons.push(`${item.name || item.ticker}: ${item.drift}% (임계값 ${threshold}%)`);
      }
    });

    return { needed, reasons };
  };

  const buildBarSegmentsFromAlloc = (allocations) => {
    const ordered = ['stocks', 'bonds', 'alternatives', 'cash'];
    const colors = {
      stocks: '#4F81BD',
      bonds: '#9BBB59',
      alternatives: '#C0504D',
      cash: '#8064A2'
    };
    return ordered
      .map((key) => ({
        key,
        label: assetClassLabels[key],
        value: allocations?.[key] ?? 0,
        color: colors[key] || '#888',
        isMobile: isMobile // Closure access
      }));
  };

  const mpColors = {
    stocks: '#4F81BD',
    bonds: '#9BBB59',
    alternatives: '#C0504D',
    cash: '#8064A2'
  };

  const renderSubMpBlock = (sub) => {
    const target = sub?.target || [];
    const actual = sub?.actual || [];
    const { needed, reasons } = getSubMpStatus(sub.asset_class);

    // 1. 모든 고유 티커 수집 및 색상 매핑 생성
    const targetTickers = target.map(item => item.ticker);
    const actualTickers = actual.map(item => item.ticker);
    const allTickers = Array.from(new Set([...targetTickers, ...actualTickers]));

    // 정렬 로직
    allTickers.sort((a, b) => {
      const idxA = targetTickers.indexOf(a);
      const idxB = targetTickers.indexOf(b);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      return a.localeCompare(b);
    });

    // 색상 매핑 및 범례 아이템 생성
    const palette = barPalette.target;
    const colorMap = {};
    const legendItems = [];

    allTickers.forEach((ticker, idx) => {
      const color = palette[idx % palette.length];
      colorMap[ticker] = color;

      const itemInfo = [...target, ...actual].find(t => t.ticker === ticker);
      const name = itemInfo?.name || ticker;
      if (name !== '현금' && ticker !== 'CASH') {
        legendItems.push({ label: name, color: color });
      }
    });

    if (sub.asset_class === 'cash' || [...target, ...actual].some(t => t.name === '현금' || t.ticker === 'CASH')) {
      const cashColor = '#8064A2';
      if (!legendItems.some(i => i.label === '현금')) {
        legendItems.push({ label: '현금', color: cashColor });
      }
    }

    const buildBarSegments = (items) => {
      const sortedItems = [...items].sort((a, b) => {
        const tickerA = a.ticker || (a.name === '현금' ? 'CASH' : '');
        const tickerB = b.ticker || (b.name === '현금' ? 'CASH' : '');
        return allTickers.indexOf(tickerA) - allTickers.indexOf(tickerB);
      });

      if (sub.asset_class === 'cash' && sortedItems.length === 0) {
        const cashColor = colorMap['CASH'] || '#8064A2';
        return [{ label: '현금', value: 100, color: cashColor, isMobile: isMobile }];
      }

      return sortedItems.map((item) => {
        const ticker = item.ticker || (item.name === '현금' ? 'CASH' : '');
        return {
          label: item.name || item.ticker || '',
          value: item.weight_percent ?? 0,
          color: colorMap[ticker] || '#888',
          isMobile: isMobile
        };
      });
    };

    return (
      <div className="submp-asset-block" key={sub.asset_class}>
        <div className="submp-asset-title">
          {assetClassLabels[sub.asset_class] || sub.asset_class}
          <TrafficLight needed={needed} reasons={reasons} />
        </div>

        {/* 범례 (Legend) 표시 - 모바일일 때만 표시 */}
        {isMobile && legendItems.length > 0 && (
          <div className="chart-legend">
            {legendItems.map((item, idx) => (
              <div key={idx} className="legend-item">
                <div className="legend-color" style={{ background: item.color }}></div>
                <span className="legend-label">{item.label}</span>
              </div>
            ))}
          </div>
        )}

        <div className="submp-row">
          <div className="submp-row-title">목표</div>
          <div className="submp-bar-area">
            {target.length === 0 ? (
              <StackedBar segments={[]} tone="target" />
            ) : (
              <StackedBar segments={buildBarSegments(target)} />
            )}
          </div>
        </div>
        <div className="submp-row">
          <div className="submp-row-title">실제</div>
          <div className="submp-bar-area">
            {actual.length === 0 ? (
              <StackedBar segments={[]} tone="actual" />
            ) : (
              <StackedBar segments={buildBarSegments(actual)} tone="actual" />
            )}
          </div>
        </div>
      </div>
    );
  };

  const mpStatus = getMpStatus();
  // MP 범례 아이템 생성
  const mpLegendItems = isMobile ? Object.entries(mpColors).map(([key, color]) => ({
    label: assetClassLabels[key],
    color: color
  })) : [];

  return (
    <div className="card rebalancing-status-card">
      <h2>Rebalancing Status</h2>
      {loading && <div className="loading">리밸런싱 현황을 불러오는 중...</div>}
      {error && <div className="error">오류: {error}</div>}
      {!loading && !error && !data && <div className="no-data">데이터가 없습니다.</div>}
      {!loading && !error && data && (
        <div className="rebalance-sections">
          <div className="mp-section">
            <div className="section-title">
              MP
              <TrafficLight needed={mpStatus.needed} reasons={mpStatus.reasons} />
            </div>
            {/* MP 범례 - 모바일일 때만 표시 */}
            {isMobile && mpLegendItems.length > 0 && (
              <div className="chart-legend">
                {mpLegendItems.map((item, idx) => (
                  <div key={idx} className="legend-item">
                    <div className="legend-color" style={{ background: item.color }}></div>
                    <span className="legend-label">{item.label}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="mp-row">
              <div className="mp-row-title">목표</div>
              <div className="mp-row-bar">
                <StackedBar segments={buildBarSegmentsFromAlloc(data.mp?.target_allocation)} />
              </div>
            </div>
            <div className="mp-row">
              <div className="mp-row-title">실제</div>
              <div className="mp-row-bar">
                <StackedBar segments={buildBarSegmentsFromAlloc(data.mp?.actual_allocation)} tone="actual" />
              </div>
            </div>
          </div>

          <div className="submp-section">
            <div className="section-title">Sub-MP</div>
            <div className="submp-grid">
              {(data.sub_mp || []).map(renderSubMpBlock)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};


const StackedBar = ({ segments, tone = 'target' }) => {
  const total = segments.reduce((sum, s) => sum + (s.value || 0), 0) || 1;
  const hasVisibleSegments = segments.some(s => (s.value || 0) > 0);

  return (
    <div className={`stacked-bar ${tone === 'actual' ? 'tone-actual' : 'tone-target'}`}>
      {segments.length === 0 || !hasVisibleSegments ? (
        // 빈 회색 바 표시
        <div
          className="stacked-bar-segment empty-bar"
          style={{ width: '100%', background: '#e0e0e0' }}
        />
      ) : (
        segments.map((seg, idx) => {
          const width = Math.max(0, (seg.value || 0) / total * 100);
          // 0.5% 미만은 공간 문제로 렌더링 하지 않거나 아주 작게 표시
          if (width < 0.5) return null;

          // 모바일이면 라벨 숨기고 %만 표시 or 짧은 라벨
          const displayText = seg.isMobile
            ? `${(seg.value ?? 0).toFixed(1)}%`
            : `${seg.label} ${(seg.value ?? 0).toFixed(1)}%`;

          // Narrow width handling: reduce font size to prevent truncation
          let segmentStyle = { width: `${width}%`, background: seg.color };
          if (seg.isMobile && width < 15) {
            segmentStyle.fontSize = width < 10 ? '9px' : '10px';
            if (width < 8) {
              segmentStyle.fontSize = '8px';
              segmentStyle.letterSpacing = '-0.5px';
            }
          }

          const segmentClass = `stacked-bar-segment ${seg.isMobile && width < 15 ? 'compact' : ''}`;

          return (
            <div
              key={`${seg.label}-${idx}`}
              className={segmentClass}
              style={segmentStyle}
              title={`${seg.label}: ${(seg.value ?? 0).toFixed(1)}%`}
            >
              <span className="stacked-bar-label">
                {displayText}
              </span>
            </div>
          );
        })
      )}
    </div >
  );
};

const RebalancingTestModal = ({ onClose, getAuthHeaders }) => {
  const [maxPhase, setMaxPhase] = useState(5);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const runTest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const headers = getAuthHeaders();
      const response = await fetch('/api/macro-trading/rebalance/test', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ max_phase: maxPhase })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.message || '테스트 실행 실패');
      }
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '800px', width: '90%' }}>
        <div className="modal-header">
          <h3>Rebalancing Process Test</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>Test Scope (Max Phase):</label>
            <select value={maxPhase} onChange={(e) => setMaxPhase(Number(e.target.value))}>
              <option value={2}>Phase 2: Drift Check (Analysis Only)</option>
              <option value={4}>Phase 3 & 4: Plan & Validate (Python Algorithm)</option>
              <option value={5}>Phase 5: Full Execution (Trade)</option>
            </select>
          </div>

          <div className="action-row" style={{ marginTop: '10px' }}>
            <button className="btn btn-primary" onClick={runTest} disabled={loading}>
              {loading ? 'Running...' : 'Run Test'}
            </button>
          </div>

          {error && <div className="error-message" style={{ marginTop: '10px', color: 'red' }}>{error}</div>}

          {result && (
            <div className="test-result" style={{ marginTop: '20px', background: '#f5f5f5', padding: '10px', borderRadius: '4px' }}>
              <h4>Test Result</h4>
              <div style={{ maxHeight: '400px', overflow: 'auto' }}>
                <pre style={{ fontSize: '12px' }}>{JSON.stringify(result, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

