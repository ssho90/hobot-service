import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import './TradingDashboard.css';

const TradingDashboard = () => {
  const { getAuthHeaders } = useAuth();
  const [kisBalance, setKisBalance] = useState(null);
  const [kisLoading, setKisLoading] = useState(false);
  const [kisError, setKisError] = useState(null);

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

  return (
    <div className="trading-dashboard">
      <MacroQuantTradingTab 
        balance={kisBalance}
        loading={kisLoading}
        error={kisError}
      />
    </div>
  );
};

// Macro Quant Trading 탭 컴포넌트
const MacroQuantTradingTab = ({ balance, loading, error }) => {
  return (
    <div className="tab-content">
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

      {/* 자산군별 수익률 */}
      {balance && balance.status === 'success' && balance.asset_class_info && (
        <div className="card">
          <h2>자산군별 수익률</h2>
          <AssetClassPerformance assetClassInfo={balance.asset_class_info} />
        </div>
      )}

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

// 자산군별 수익률 컴포넌트
const AssetClassPerformance = ({ assetClassInfo }) => {
  const assetClassLabels = {
    stocks: '주식',
    bonds: '채권',
    alternatives: '대체투자',
    cash: '현금'
  };

  const assetClassOrder = ['stocks', 'bonds', 'alternatives', 'cash'];

  return (
    <div className="asset-class-performance">
      {assetClassOrder.map((assetClass) => {
        const info = assetClassInfo[assetClass];
        if (!info || (info.count === 0 && assetClass !== 'cash')) {
          return null;
        }

        return (
          <div key={assetClass} className="asset-class-group">
            <div className="asset-class-header">
              <h3>{assetClassLabels[assetClass] || assetClass}</h3>
              <div className="asset-class-summary">
                <span className="summary-label">평가금액:</span>
                <span className="summary-value">
                  {info.total_eval_amount?.toLocaleString('ko-KR')} 원
                </span>
                <span className="summary-label">손익:</span>
                <span className={`summary-value ${info.total_profit_loss >= 0 ? 'positive' : 'negative'}`}>
                  {info.total_profit_loss?.toLocaleString('ko-KR')} 원
                </span>
                <span className="summary-label">수익률:</span>
                <span className={`summary-value ${info.profit_loss_rate >= 0 ? 'positive' : 'negative'}`}>
                  {info.profit_loss_rate?.toFixed(2)}%
                </span>
              </div>
            </div>
            
            {/* 그룹 내 종목별 수익률 */}
            {info.holdings && info.holdings.length > 0 && (
              <div className="asset-class-holdings">
                <table className="holdings-table">
                  <thead>
                    <tr>
                      <th>종목명</th>
                      <th>종목코드</th>
                      <th>평가금액</th>
                      <th>손익</th>
                      <th>손익률</th>
                    </tr>
                  </thead>
                  <tbody>
                    {info.holdings.map((holding, idx) => (
                      <tr key={idx}>
                        <td>{holding.stock_name}</td>
                        <td>{holding.stock_code}</td>
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
            )}
          </div>
        );
      })}
    </div>
  );
};

export default TradingDashboard;

