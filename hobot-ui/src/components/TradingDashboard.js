import React, { useState, useEffect } from 'react';
import HobotStatus from './HobotStatus';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
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

      {/* 계좌 정보 및 리밸런싱 차트 */}
      <div className="account-rebalancing-container">
        {/* 계좌 정보 (왼쪽 반) */}
        <div className="card account-info-card">
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

        {/* 리밸런싱 차트 (오른쪽 반) */}
        <div className="card rebalancing-chart-card">
          <h2>리밸런싱 상태</h2>
          {loading && <div className="loading">데이터를 불러오는 중...</div>}
          {error && <div className="error">오류: {error}</div>}
          {!loading && !error && balance && balance.status === 'success' && (
            <RebalancingChart balance={balance} />
          )}
          {!loading && !error && (!balance || balance.status !== 'success') && (
            <div className="no-data">데이터를 불러올 수 없습니다.</div>
          )}
        </div>
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

// 리밸런싱 차트 컴포넌트
const RebalancingChart = ({ balance }) => {
  // 자산 비율 계산
  const cashAmount = balance.cash_balance || 0;
  const stockAmount = balance.holdings?.reduce((sum, holding) => sum + (holding.eval_amount || 0), 0) || 0;
  const bondAmount = 0; // 채권 데이터는 현재 없음
  const goldAmount = 0; // 금 데이터는 현재 없음

  const totalAmount = cashAmount + stockAmount + bondAmount + goldAmount;

  const chartData = [
    { name: '현금', value: cashAmount, color: '#4CAF50' },
    { name: '주식', value: stockAmount, color: '#2196F3' },
    { name: '채권', value: bondAmount, color: '#FF9800' },
    { name: '금', value: goldAmount, color: '#FFC107' }
  ].filter(item => item.value > 0); // 0인 항목은 제외

  const renderCustomLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
    const RADIAN = Math.PI / 180;
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);

    if (percent < 0.05) return null; // 5% 미만은 레이블 숨김

    return (
      <text
        x={x}
        y={y}
        fill="white"
        textAnchor={x > cx ? 'start' : 'end'}
        dominantBaseline="central"
        fontSize={12}
        fontWeight="bold"
      >
        {`${(percent * 100).toFixed(1)}%`}
      </text>
    );
  };

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const data = payload[0];
      return (
        <div className="chart-tooltip">
          <p className="tooltip-label">{data.name}</p>
          <p className="tooltip-value">
            {data.value.toLocaleString('ko-KR')} 원
          </p>
          <p className="tooltip-percent">
            {((data.value / totalAmount) * 100).toFixed(2)}%
          </p>
        </div>
      );
    }
    return null;
  };

  if (totalAmount === 0) {
    return (
      <div className="no-data">
        자산 데이터가 없습니다.
      </div>
    );
  }

  return (
    <div className="rebalancing-chart-container">
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={renderCustomLabel}
            outerRadius={100}
            fill="#8884d8"
            dataKey="value"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value, entry) => (
              <span style={{ color: entry.color }}>
                {value}: {((entry.payload.value / totalAmount) * 100).toFixed(2)}%
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="chart-summary">
        <div className="summary-item">
          <span className="summary-label">총 자산:</span>
          <span className="summary-value">
            {totalAmount.toLocaleString('ko-KR')} 원
          </span>
        </div>
      </div>
    </div>
  );
};

export default TradingDashboard;

