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
        balance={balance}
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

// 리밸런싱 현황 카드 (MP / Sub-MP 목표 vs 실제)
const RebalancingStatusCard = ({ data, loading, error, balance }) => {
  const assetClassLabels = {
    stocks: '주식',
    bonds: '채권',
    alternatives: '대체',
    cash: '현금'
  };

  const DRIFT_THRESHOLD = 3.0; // 임계값 3%

  // 총 자산 평가액 계산
  const totalEvalAmount = balance?.total_eval_amount || 0;

  // 괴리율 계산 함수
  const calculateDrift = (target, actual) => {
    return actual - target; // 실제 - 목표
  };

  // 신호등 상태 결정 함수
  const getDriftStatus = (drift) => {
    const absDrift = Math.abs(drift);
    if (absDrift <= DRIFT_THRESHOLD * 0.8) {
      return 'green'; // 정상 (임계값의 80% 이내)
    } else if (absDrift < DRIFT_THRESHOLD) {
      return 'yellow'; // 주의 (임계값 근접)
    } else {
      return 'red'; // 리밸런싱 필요 (임계값 초과)
    }
  };

  // 신호등 아이콘 컴포넌트
  const StatusIndicator = ({ status, drift }) => {
    const absDrift = Math.abs(drift);
    const sign = drift >= 0 ? '+' : '';
    const statusLabels = {
      green: '정상',
      yellow: '주의',
      red: '리밸런싱 필요'
    };
    const statusEmojis = {
      green: '🟢',
      yellow: '🟡',
      red: '🔴'
    };
    
    return (
      <span className={`drift-indicator drift-${status}`} title={statusLabels[status]}>
        {statusEmojis[status]} {sign}{absDrift.toFixed(1)}%p
      </span>
    );
  };

  const barPalette = {
    target: ['#4F81BD', '#9BBB59', '#C0504D', '#8064A2', '#46b5d1', '#f4b400'],
    actual: ['#3b6aa3', '#7da444', '#a33f3a', '#684f88', '#2e9bc0', '#d49a00'],
  };

  const buildBarSegmentsFromAlloc = (allocations, isActual = false) => {
    const ordered = ['stocks', 'bonds', 'alternatives', 'cash'];
    const colors = {
      stocks: '#4F81BD',
      bonds: '#9BBB59',
      alternatives: '#C0504D',
      cash: '#8064A2'
    };
    return ordered
      .map((key) => {
        const value = allocations?.[key] ?? 0;
        const amount = totalEvalAmount * (value / 100);
        return {
          key,
          label: assetClassLabels[key],
          value,
          amount,
          color: colors[key] || '#888'
        };
      })
      .filter((seg) => seg.value > 0 || (isActual && seg.value === 0 && allocations?.[seg.key] === 0));
  };

  // 매매 시뮬레이션 계산
  const calculateTradeSimulation = () => {
    if (!data || !data.mp || totalEvalAmount === 0) return null;

    const target = data.mp.target_allocation || {};
    const actual = data.mp.actual_allocation || {};
    const trades = [];

    // MP 레벨 매매 계산
    const assetOrder = ['stocks', 'bonds', 'alternatives', 'cash'];
    assetOrder.forEach((assetKey) => {
      const targetPercent = target[assetKey] || 0;
      const actualPercent = actual[assetKey] || 0;
      const targetAmount = totalEvalAmount * (targetPercent / 100);
      const actualAmount = totalEvalAmount * (actualPercent / 100);
      const diffAmount = targetAmount - actualAmount;
      const diffPercent = targetPercent - actualPercent;

      if (Math.abs(diffPercent) >= DRIFT_THRESHOLD) {
        trades.push({
          assetClass: assetClassLabels[assetKey],
          action: diffAmount > 0 ? '매수' : '매도',
          amount: Math.abs(diffAmount),
          percent: Math.abs(diffPercent)
        });
      }
    });

    // Sub-MP 레벨 매매 계산
    const subMpTrades = [];
    (data.sub_mp || []).forEach((sub) => {
      const assetKey = sub.asset_class;
      const classTargetPercent = target[assetKey] || 0;
      const classActualPercent = actual[assetKey] || 0;
      const classTotalAmount = totalEvalAmount * (classActualPercent / 100 || classTargetPercent / 100);

      // 목표 종목별 금액 계산
      const targetItems = sub.target || [];
      const actualItems = sub.actual || [];
      
      const targetMap = new Map();
      targetItems.forEach(item => {
        const itemPercent = item.weight_percent || 0;
        const itemAmount = classTotalAmount * (itemPercent / 100);
        targetMap.set(item.ticker || item.name, { percent: itemPercent, amount: itemAmount });
      });

      const actualMap = new Map();
      actualItems.forEach(item => {
        const itemPercent = item.weight_percent || 0;
        const itemAmount = classTotalAmount * (itemPercent / 100);
        actualMap.set(item.ticker || item.name, { percent: itemPercent, amount: itemAmount });
      });

      // 매매 계산
      targetMap.forEach((targetData, ticker) => {
        const actualData = actualMap.get(ticker) || { percent: 0, amount: 0 };
        const diffAmount = targetData.amount - actualData.amount;
        const diffPercent = targetData.percent - actualData.percent;

        if (Math.abs(diffPercent) >= 1.0) { // Sub-MP는 1% 이상 차이
          subMpTrades.push({
            assetClass: assetClassLabels[assetKey],
            ticker: ticker,
            name: targetItems.find(t => (t.ticker || t.name) === ticker)?.name || ticker,
            action: diffAmount > 0 ? '매수' : '매도',
            amount: Math.abs(diffAmount),
            percent: Math.abs(diffPercent)
          });
        }
      });

      // 실제에만 있고 목표에 없는 종목 (전량 매도)
      actualMap.forEach((actualData, ticker) => {
        if (!targetMap.has(ticker) && actualData.amount > 0) {
          subMpTrades.push({
            assetClass: assetClassLabels[assetKey],
            ticker: ticker,
            name: actualItems.find(t => (t.ticker || t.name) === ticker)?.name || ticker,
            action: '매도',
            amount: actualData.amount,
            percent: actualData.percent
          });
        }
      });
    });

    return { mpTrades: trades, subMpTrades };
  };

  const tradeSimulation = calculateTradeSimulation();

  const renderSubMpBlock = (sub) => {
    const target = sub?.target || [];
    const actual = sub?.actual || [];
    const assetKey = sub.asset_class;
    const classTargetPercent = data?.mp?.target_allocation?.[assetKey] || 0;
    const classActualPercent = data?.mp?.actual_allocation?.[assetKey] || 0;
    const classTotalAmount = totalEvalAmount * (classActualPercent / 100 || classTargetPercent / 100);
    
    // 전체 포트폴리오가 현금 100%인지 확인
    const isAllCash = data?.mp?.actual_allocation?.cash === 100 && 
                      (data?.mp?.actual_allocation?.stocks === 0 || !data?.mp?.actual_allocation?.stocks) &&
                      (data?.mp?.actual_allocation?.bonds === 0 || !data?.mp?.actual_allocation?.bonds) &&
                      (data?.mp?.actual_allocation?.alternatives === 0 || !data?.mp?.actual_allocation?.alternatives);
    
    const buildBarSegments = (items, tone = 'target') => {
      const palette = barPalette[tone] || barPalette.target;
      const list = [...items];
      
      // 현금 자산군이고 목표가 비어있으면 100% 현금으로 표시
      if (sub.asset_class === 'cash' && list.length === 0 && tone === 'target') {
        list.push({ name: '현금', ticker: 'CASH', weight_percent: 100 });
      }
      
      // 실제가 비어있고 전체 포트폴리오가 현금 100%인 경우, 현금 섹션에 100% 표시
      if (tone === 'actual' && list.length === 0 && sub.asset_class === 'cash' && isAllCash) {
        list.push({ name: '현금', ticker: 'CASH', weight_percent: 100 });
      }
      
      return list.map((item, idx) => {
        const percent = item.weight_percent ?? 0;
        const amount = classTotalAmount * (percent / 100);
        return {
          label: item.name || item.ticker || '',
          value: percent,
          amount,
          color: palette[idx % palette.length],
        };
      });
    };

    // 실제가 비어있어도 빈 바 표시
    const targetSegments = buildBarSegments(target, 'target');
    const actualSegments = buildBarSegments(actual, 'actual');
    
    // 실제가 비어있고 목표가 있으면 빈 회색 바 표시 (단, 현금 100% 상태가 아닌 경우)
    const showEmptyBar = actual.length === 0 && target.length > 0 && !(sub.asset_class === 'cash' && isAllCash);

    return (
      <div className="submp-asset-block" key={sub.asset_class}>
        <div className="submp-asset-title">
          {assetClassLabels[sub.asset_class] || sub.asset_class}
          {actual.length > 0 && target.length > 0 && actualSegments.map((seg, idx) => {
            const targetSeg = targetSegments.find(t => t.label === seg.label);
            if (targetSeg) {
              const drift = calculateDrift(targetSeg.value, seg.value);
              const status = getDriftStatus(drift);
              return (
                <StatusIndicator key={idx} status={status} drift={drift} />
              );
            }
            return null;
          })}
        </div>
        <div className="submp-row">
          <div className="submp-row-title">목표</div>
          <div className="submp-bar-area">
            {target.length === 0 ? (
              <div className="submp-empty">-</div>
            ) : (
              <StackedBar segments={targetSegments} totalAmount={classTotalAmount} />
            )}
          </div>
        </div>
        <div className="submp-row">
          <div className="submp-row-title">실제</div>
          <div className="submp-bar-area">
            {showEmptyBar ? (
              <div className="stacked-bar tone-actual empty-bar">
                <div className="empty-bar-indicator">0%</div>
              </div>
            ) : actual.length === 0 ? (
              <div className="submp-empty">-</div>
            ) : (
              <StackedBar segments={actualSegments} tone="actual" totalAmount={classTotalAmount} />
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="card rebalancing-status-card">
      <h2>Rebalancing Status</h2>
      {loading && <div className="loading">리밸런싱 현황을 불러오는 중...</div>}
      {error && <div className="error">오류: {error}</div>}
      {!loading && !error && !data && <div className="no-data">데이터가 없습니다.</div>}
      {!loading && !error && data && (
        <>
          {/* 총 자산 평가액 표시 */}
          {totalEvalAmount > 0 && (
            <div className="total-asset-display">
              <span className="total-asset-label">총 자산 평가액:</span>
              <span className="total-asset-value">{totalEvalAmount.toLocaleString('ko-KR')} 원</span>
            </div>
          )}

          <div className="rebalance-sections">
            <div className="mp-section">
              <div className="section-title">
                MP
                {data.mp && (() => {
                  const target = data.mp.target_allocation || {};
                  const actual = data.mp.actual_allocation || {};
                  const assetOrder = ['stocks', 'bonds', 'alternatives', 'cash'];
                  const maxDrift = Math.max(...assetOrder.map(key => {
                    const drift = calculateDrift(target[key] || 0, actual[key] || 0);
                    return Math.abs(drift);
                  }));
                  const maxDriftKey = assetOrder.find(key => {
                    const drift = calculateDrift(target[key] || 0, actual[key] || 0);
                    return Math.abs(drift) === maxDrift;
                  });
                  if (maxDriftKey) {
                    const drift = calculateDrift(target[maxDriftKey] || 0, actual[maxDriftKey] || 0);
                    const status = getDriftStatus(drift);
                    if (status !== 'green') {
                      return <StatusIndicator key={maxDriftKey} status={status} drift={drift} />;
                    }
                  }
                  return null;
                })()}
              </div>
              <div className="mp-row">
                <div className="mp-row-title">목표</div>
                <div className="mp-row-bar">
                  <StackedBar segments={buildBarSegmentsFromAlloc(data.mp?.target_allocation)} totalAmount={totalEvalAmount} />
                </div>
              </div>
              <div className="mp-row">
                <div className="mp-row-title">실제</div>
                <div className="mp-row-bar">
                  <StackedBar segments={buildBarSegmentsFromAlloc(data.mp?.actual_allocation, true)} tone="actual" totalAmount={totalEvalAmount} />
                  {/* 괴리율 표시 */}
                  {data.mp && (() => {
                    const target = data.mp.target_allocation || {};
                    const actual = data.mp.actual_allocation || {};
                    const assetOrder = ['stocks', 'bonds', 'alternatives', 'cash'];
                    return assetOrder.map(key => {
                      const targetVal = target[key] || 0;
                      const actualVal = actual[key] || 0;
                      if (targetVal === 0 && actualVal === 0) return null;
                      const drift = calculateDrift(targetVal, actualVal);
                      const status = getDriftStatus(drift);
                      if (status === 'green' && Math.abs(drift) < 0.1) return null; // 거의 차이 없으면 표시 안함
                      return (
                        <div key={key} className="mp-drift-info">
                          <span className="drift-label">{assetClassLabels[key]}:</span>
                          <StatusIndicator status={status} drift={drift} />
                        </div>
                      );
                    }).filter(Boolean);
                  })()}
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

          {/* 매매 시뮬레이션 패널 */}
          {tradeSimulation && (tradeSimulation.mpTrades.length > 0 || tradeSimulation.subMpTrades.length > 0) && (
            <div className="trade-simulation-panel">
              <h3>예상 주문 (Expected Trades)</h3>
              {tradeSimulation.mpTrades.length > 0 && (
                <div className="trade-group">
                  <h4>MP 레벨</h4>
                  <div className="trade-list">
                    {tradeSimulation.mpTrades.map((trade, idx) => (
                      <div key={idx} className={`trade-item trade-${trade.action === '매수' ? 'buy' : 'sell'}`}>
                        <span className="trade-action">{trade.action}</span>
                        <span className="trade-asset">{trade.assetClass}</span>
                        <span className="trade-amount">{trade.amount.toLocaleString('ko-KR')} 원</span>
                        <span className="trade-percent">({trade.percent.toFixed(1)}%)</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {tradeSimulation.subMpTrades.length > 0 && (
                <div className="trade-group">
                  <h4>Sub-MP 레벨</h4>
                  <div className="trade-list">
                    {tradeSimulation.subMpTrades.map((trade, idx) => (
                      <div key={idx} className={`trade-item trade-${trade.action === '매수' ? 'buy' : 'sell'}`}>
                        <span className="trade-action">{trade.action}</span>
                        <span className="trade-asset">{trade.name || trade.ticker}</span>
                        <span className="trade-asset-class">({trade.assetClass})</span>
                        <span className="trade-amount">{trade.amount.toLocaleString('ko-KR')} 원</span>
                        <span className="trade-percent">({trade.percent.toFixed(1)}%)</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

const StackedBar = ({ segments, tone = 'target', totalAmount = 0 }) => {
  const total = segments.reduce((sum, s) => sum + (s.value || 0), 0) || 1;
  return (
    <div className={`stacked-bar ${tone === 'actual' ? 'tone-actual' : 'tone-target'}`}>
      {segments.map((seg, idx) => {
        const width = Math.max(0, (seg.value || 0) / total * 100);
        const amount = seg.amount || (totalAmount * (seg.value || 0) / 100);
        const tooltip = totalAmount > 0 
          ? `${seg.label}: ${(seg.value ?? 0).toFixed(1)}% / ${amount.toLocaleString('ko-KR')} 원`
          : `${seg.label}: ${(seg.value ?? 0).toFixed(1)}%`;
        return (
          <div
            key={`${seg.label}-${idx}`}
            className="stacked-bar-segment"
            style={{ width: `${width}%`, background: seg.color }}
            title={tooltip}
          >
            <span className="stacked-bar-label">
              {seg.label} {(seg.value ?? 0).toFixed(1)}%
              {totalAmount > 0 && (
                <span className="stacked-bar-amount">
                  {' '}({amount.toLocaleString('ko-KR')} 원)
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
};

