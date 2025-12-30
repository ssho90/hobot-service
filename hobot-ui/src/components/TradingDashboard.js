import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import './TradingDashboard.css';

const TradingDashboard = () => {
  const { getAuthHeaders } = useAuth();
  const [kisBalance, setKisBalance] = useState(null);
  const [kisLoading, setKisLoading] = useState(false);
  const [kisError, setKisError] = useState(null);
  const [rebalanceStatus, setRebalanceStatus] = useState(null);
  const [rebalanceLoading, setRebalanceLoading] = useState(false);
  const [rebalanceError, setRebalanceError] = useState(null);

  // KIS 계좌 잔액 조회
  useEffect(() => {
    const fetchKisBalance = async () => {
      setKisLoading(true);
      setKisError(null);
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
          throw new Error(errorData.message || '계좌 정보를 불러오는데 실패했습니다.');
        }
      } catch (err) {
        setKisError(err.message);
      } finally {
        setKisLoading(false);
      }
    };
    fetchKisBalance();
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
      />
    </div>
  );
};

// Macro Quant Trading 탭 컴포넌트
const MacroQuantTradingTab = ({ balance, loading, error, rebalanceStatus, rebalanceLoading, rebalanceError }) => {
  return (
    <div className="tab-content">
      <RebalancingStatusCard
        data={rebalanceStatus}
        loading={rebalanceLoading}
        error={rebalanceError}
      />

      <div className="card account-info-card">
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
              <span className="info-label">현금 잔액:</span>
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

      {/* 보유 자산 */}
      {balance && balance.status === 'success' && balance.holdings && balance.holdings.length > 0 && (
        <div className="card">
          <h2>보유 자산</h2>
          <div className="holdings-table">
            <table>
              <thead>
                <tr>
                  <th>종목명</th>
                  <th>종목코드</th>
                  <th>보유수량</th>
                  <th>평균매수가</th>
                  <th>현재가</th>
                  <th>평가금액</th>
                  <th>손익</th>
                  <th>손익률</th>
                </tr>
              </thead>
              <tbody>
                {balance.holdings.map((holding, idx) => (
                  <tr key={idx}>
                    <td>{holding.stock_name}</td>
                    <td>{holding.stock_code}</td>
                    <td>{holding.quantity?.toLocaleString('ko-KR')} 주</td>
                    <td>{holding.avg_buy_price?.toLocaleString('ko-KR')} 원</td>
                    <td>{holding.current_price?.toLocaleString('ko-KR')} 원</td>
                    <td>{holding.eval_amount?.toLocaleString('ko-KR')} 원</td>
                    <td className={holding.profit_loss >= 0 ? 'positive' : 'negative'}>
                      {holding.profit_loss?.toLocaleString('ko-KR')} 원
                    </td>
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
        color: colors[key] || '#888'
      }));
  };

  const renderSubMpBlock = (sub) => {
    const target = sub?.target || [];
    const actual = sub?.actual || [];
    const { needed, reasons } = getSubMpStatus(sub.asset_class);

    const buildBarSegments = (items, tone = 'target') => {
      const palette = barPalette[tone] || barPalette.target;
      const list = [...items];
      if (sub.asset_class === 'cash' && list.length === 0) {
        list.push({ name: '현금', ticker: 'CASH', weight_percent: 100 });
      }
      return list.map((item, idx) => ({
        label: item.name || item.ticker || '',
        value: item.weight_percent ?? 0,
        color: palette[idx % palette.length],
      }));
    };

    return (
      <div className="submp-asset-block" key={sub.asset_class}>
        <div className="submp-asset-title">
          {assetClassLabels[sub.asset_class] || sub.asset_class}
          <TrafficLight needed={needed} reasons={reasons} />
        </div>
        <div className="submp-row">
          <div className="submp-row-title">목표</div>
          <div className="submp-bar-area">
            {target.length === 0 ? (
              <StackedBar segments={[]} tone="target" />
            ) : (
              <StackedBar segments={buildBarSegments(target, 'target')} />
            )}
          </div>
        </div>
        <div className="submp-row">
          <div className="submp-row-title">실제</div>
          <div className="submp-bar-area">
            {actual.length === 0 ? (
              <StackedBar segments={[]} tone="actual" />
            ) : (
              <StackedBar segments={buildBarSegments(actual, 'actual')} tone="actual" />
            )}
          </div>
        </div>
      </div>
    );
  };

  const mpStatus = getMpStatus();

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
          // 0인 세그먼트는 표시하지 않음 (하지만 전체 바는 표시됨)
          if ((seg.value || 0) === 0) return null;
          return (
            <div
              key={`${seg.label}-${idx}`}
              className="stacked-bar-segment"
              style={{ width: `${width}%`, background: seg.color }}
              title={`${seg.label}: ${(seg.value ?? 0).toFixed(1)}%`}
            >
              <span className="stacked-bar-label">
                {seg.label} {(seg.value ?? 0).toFixed(1)}%
              </span>
            </div>
          );
        })
      )}
    </div>
  );
};

