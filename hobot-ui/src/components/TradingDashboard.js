import React, { useState, useEffect } from 'react';
import HobotStatus from './HobotStatus';
import './TradingDashboard.css';

const TradingDashboard = () => {
  const [kisBalance, setKisBalance] = useState(null);
  const [kisLoading, setKisLoading] = useState(false);
  const [kisError, setKisError] = useState(null);

  // KIS 계좌 잔액 조회
  useEffect(() => {
    const fetchKisBalance = async () => {
      setKisLoading(true);
      setKisError(null);
      try {
        const response = await fetch('/api/kis/balance');
        if (response.ok) {
          const data = await response.json();
          setKisBalance(data);
        } else {
          throw new Error('계좌 정보를 불러오는데 실패했습니다.');
        }
      } catch (err) {
        setKisError(err.message);
      } finally {
        setKisLoading(false);
      }
    };
    fetchKisBalance();
  }, []);

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
      {/* API 연동 상태 */}
      <div className="status-section">
        <HobotStatus platform="kis" />
      </div>

      {/* 계좌 정보 */}
      <div className="card">
        <h2>계좌 정보</h2>
        {loading && <div className="loading">계좌 정보를 불러오는 중...</div>}
        {error && <div className="error">오류: {error}</div>}
        {!loading && !error && balance && balance.status === 'success' && (
          <div className="account-info">
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
            {balance.target_ticker_current_price && (
              <div className="info-row">
                <span className="info-label">대상 종목 현재가 ({balance.target_ticker_name}):</span>
                <span className="info-value">
                  {balance.target_ticker_current_price?.toLocaleString('ko-KR')} 원
                </span>
              </div>
            )}
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

      {/* 리밸런싱 상태 */}
      <div className="card">
        <h2>리밸런싱 상태</h2>
        <div className="rebalancing-status">
          <p className="info-note">
            리밸런싱 상태는 "모니터링" 탭의 "리밸런싱 현황"에서 확인할 수 있습니다.
          </p>
        </div>
      </div>
    </div>
  );
};

export default TradingDashboard;

