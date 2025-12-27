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

// 리밸런싱 현황 카드 (MP / Sub-MP 목표 vs 실제)
const RebalancingStatusCard = ({ data, loading, error }) => {
  const assetClassLabels = {
    stocks: '주식',
    bonds: '채권',
    alternatives: '대체',
    cash: '현금'
  };

  const renderRow = (title, allocations) => {
    if (!allocations) return null;
    const ordered = ['stocks', 'bonds', 'alternatives', 'cash'];
    return (
      <div className="mp-row">
        <div className="mp-row-title">{title}</div>
        <div className="mp-row-items">
          {ordered.map((key) => (
            <div key={key} className="mp-item">
              <span className="mp-item-label">{assetClassLabels[key]}</span>
              <span className="mp-item-value">{(allocations[key] ?? 0).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderSubMpBlock = (sub) => {
    const target = sub?.target || [];
    const actual = sub?.actual || [];
    return (
      <div className="submp-asset-block" key={sub.asset_class}>
        <div className="submp-asset-title">{assetClassLabels[sub.asset_class] || sub.asset_class}</div>
        <div className="submp-row">
          <div className="submp-row-title">목표</div>
          <div className="submp-row-items">
            {target.length === 0 && <div className="submp-empty">-</div>}
            {target.map((item, idx) => (
              <div key={idx} className="submp-chip">
                <span className="submp-chip-name">{item.name}</span>
                <span className="submp-chip-meta">
                  {item.ticker ? `${item.ticker} · ` : ''}{(item.weight_percent ?? 0).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="submp-row">
          <div className="submp-row-title">실제</div>
          <div className="submp-row-items">
            {actual.length === 0 && <div className="submp-empty">-</div>}
            {actual.map((item, idx) => (
              <div key={idx} className="submp-chip actual">
                <span className="submp-chip-name">{item.name}</span>
                <span className="submp-chip-meta">
                  {item.ticker ? `${item.ticker} · ` : ''}{(item.weight_percent ?? 0).toFixed(1)}%
                </span>
              </div>
            ))}
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
        <div className="rebalance-sections">
          <div className="mp-section">
            <div className="section-title">MP</div>
            {renderRow('목표', data.mp?.target_allocation)}
            {renderRow('실제', data.mp?.actual_allocation)}
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

