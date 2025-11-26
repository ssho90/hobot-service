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
  const [showAssetClassModal, setShowAssetClassModal] = useState(false);
  const [showRebalanceConfirm, setShowRebalanceConfirm] = useState(false);
  const [isRebalancing, setIsRebalancing] = useState(false);
  const [targetAllocation, setTargetAllocation] = useState(null);
  const [rebalancingChanges, setRebalancingChanges] = useState(null);
  const [assetClassDetails, setAssetClassDetails] = useState(null);

  // AI 목표 비중 및 자산군 상세 설정 조회
  useEffect(() => {
    const fetchData = async () => {
      try {
        // AI 목표 비중 조회
        let targetAllocData = null;
        const targetResponse = await fetch('/api/macro-trading/latest-strategy-decision');
        if (targetResponse.ok) {
          const result = await targetResponse.json();
          if (result.data) {
            setTargetAllocation(result.data);
            targetAllocData = result.data.target_allocation;
          }
        }

        // 자산군 상세 설정 조회
        let assetClassDetailsData = null;
        const detailsResponse = await fetch('/api/macro-trading/asset-class-details');
        if (detailsResponse.ok) {
          const detailsResult = await detailsResponse.json();
          if (detailsResult.data) {
            setAssetClassDetails(detailsResult.data);
            assetClassDetailsData = detailsResult.data;
          }
        }

        // 다음 리밸런싱 변경 사항 계산
        if (balance && balance.status === 'success' && targetAllocData) {
          calculateRebalancingChanges(balance, targetAllocData, assetClassDetailsData);
        }
      } catch (err) {
        console.error('Error fetching data:', err);
      }
    };
    
    if (balance && balance.status === 'success') {
      fetchData();
    }
  }, [balance]);

  // 리밸런싱 변경 사항 계산
  const calculateRebalancingChanges = (currentBalance, targetAlloc, assetClassDetailsData) => {
    if (!currentBalance.asset_class_info) return;
    
    const totalAmount = currentBalance.total_eval_amount || 0;
    const changes = [];
    
    // 자산군별 목표 비중과 현재 비중 비교
    const assetClassLabels = {
      stocks: '주식',
      bonds: '채권',
      alternatives: '대체투자',
      cash: '현금'
    };
    
    Object.keys(assetClassLabels).forEach(assetClass => {
      const currentInfo = currentBalance.asset_class_info[assetClass];
      const currentAmount = currentInfo?.total_eval_amount || 0;
      const currentWeight = totalAmount > 0 ? (currentAmount / totalAmount) * 100 : 0;
      
      // 목표 비중 (AI 결정 또는 기본값)
      // AI 결정은 Stocks, Bonds_US_Long, Bonds_KR_Short, Alternatives, Cash 형식일 수 있음
      let targetWeight = 0;
      if (targetAlloc[assetClass]) {
        targetWeight = targetAlloc[assetClass];
      } else if (assetClass === 'stocks' && targetAlloc['Stocks']) {
        targetWeight = targetAlloc['Stocks'];
      } else if (assetClass === 'bonds') {
        // 채권은 US_Long과 KR_Short의 합
        targetWeight = (targetAlloc['Bonds_US_Long'] || 0) + (targetAlloc['Bonds_KR_Short'] || 0);
      } else if (assetClass === 'alternatives' && targetAlloc['Alternatives']) {
        targetWeight = targetAlloc['Alternatives'];
      } else if (assetClass === 'cash' && targetAlloc['Cash']) {
        targetWeight = targetAlloc['Cash'];
      }
      const targetAmount = (totalAmount * targetWeight) / 100;
      const diff = targetAmount - currentAmount;
      const diffWeight = targetWeight - currentWeight;
      
      // 자산군 상세 설정에서 해당 자산군의 종목 목록 가져오기
      const assetClassItems = assetClassDetailsData && assetClassDetailsData[assetClass] ? assetClassDetailsData[assetClass] : [];
      
      changes.push({
        assetClass: assetClassLabels[assetClass],
        currentWeight: currentWeight.toFixed(2),
        targetWeight: targetWeight.toFixed(2),
        diffWeight: diffWeight > 0 ? `+${diffWeight.toFixed(2)}` : diffWeight.toFixed(2),
        diffAmount: diff,
        action: diff > 0 ? '매수' : '매도',
        items: assetClassItems // 자산군 상세 설정 종목 목록
      });
    });
    
    setRebalancingChanges(changes);
  };

  return (
    <div className="tab-content">
      {/* API 연동 상태 */}
      <div className="status-section">
        <HobotStatus platform="kis" />
      </div>

      {/* 계좌 정보 및 리밸런싱 차트 (나란히 배치) */}
      <div className="account-rebalancing-container">
        {/* 계좌 정보 (왼쪽 반) */}
        <div className="card account-info-card">
          <div className="card-header-with-actions">
            <h2>계좌 정보</h2>
            <div className="card-actions">
              <button 
                className="btn btn-secondary"
                onClick={() => setShowAssetClassModal(true)}
              >
                자산군 상세 설정
              </button>
              <button 
                className="btn btn-primary"
                onClick={() => setShowRebalanceConfirm(true)}
                disabled={isRebalancing}
              >
                {isRebalancing ? '리밸런싱 중...' : '수동 리밸런싱'}
              </button>
            </div>
          </div>
          
          {loading && <div className="loading">계좌 정보를 불러오는 중...</div>}
          {error && <div className="error">오류: {error}</div>}
          
          {!loading && !error && balance && balance.status === 'success' && (
            <>
              {/* 기본 계좌 정보 */}
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

              {/* 현재 리밸런싱 대상 자산 테이블 */}
              <div className="rebalancing-target-assets">
                <h3>현재 리밸런싱 대상 자산</h3>
                <RebalancingTargetAssetsTable balance={balance} />
              </div>
            </>
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

      {/* 다음 리밸런싱 시 변경될 자산 목록 (전체 너비) */}
      {!loading && !error && balance && balance.status === 'success' && (
        <div className="card next-rebalancing-changes-card">
          <h2>다음 리밸런싱 시 변경될 자산 목록</h2>
          <RebalancingChangesList 
            changes={rebalancingChanges}
            targetAllocation={targetAllocation}
            assetClassDetails={assetClassDetails}
          />
        </div>
      )}

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

      {/* 자산군 상세 설정 모달 */}
      {showAssetClassModal && (
        <AssetClassDetailsModal
          onClose={() => setShowAssetClassModal(false)}
        />
      )}

      {/* 수동 리밸런싱 확인 모달 */}
      {showRebalanceConfirm && (
        <RebalanceConfirmModal
          onConfirm={async () => {
            setIsRebalancing(true);
            try {
              const token = localStorage.getItem('token');
              const response = await fetch('/api/macro-trading/rebalance', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${token}`
                }
              });
              
              if (response.ok) {
                const data = await response.json();
                alert('리밸런싱이 요청되었습니다.');
                setShowRebalanceConfirm(false);
              } else {
                const error = await response.json();
                alert(`리밸런싱 실패: ${error.detail || '알 수 없는 오류'}`);
              }
            } catch (err) {
              alert(`리밸런싱 실패: ${err.message}`);
            } finally {
              setIsRebalancing(false);
            }
          }}
          onCancel={() => setShowRebalanceConfirm(false)}
        />
      )}

    </div>
  );
};

// 현재 리밸런싱 대상 자산 테이블 컴포넌트
const RebalancingTargetAssetsTable = ({ balance }) => {
  const assetClassLabels = {
    stocks: '주식',
    bonds: '채권',
    alternatives: '대체투자',
    cash: '현금'
  };

  // 자산군별로 보유 종목 그룹화
  const groupedHoldings = {};
  
  if (balance.asset_class_info) {
    Object.keys(assetClassLabels).forEach(assetClass => {
      const info = balance.asset_class_info[assetClass];
      if (info && info.holdings && info.holdings.length > 0) {
        groupedHoldings[assetClass] = info.holdings.map(holding => ({
          ...holding,
          group: assetClassLabels[assetClass]
        }));
      }
    });
  }

  // 현금 자산군 처리
  if (balance.asset_class_info && balance.asset_class_info.cash) {
    const cashInfo = balance.asset_class_info.cash;
    if (cashInfo.total_eval_amount > 0) {
      if (!groupedHoldings.cash) {
        groupedHoldings.cash = [];
      }
      // 현금은 별도 항목으로 추가
      if (balance.cash_balance > 0) {
        groupedHoldings.cash.push({
          stock_name: '원화 현금',
          stock_code: 'CASH',
          current_price: 1,
          avg_buy_price: 1,
          profit_loss_rate: 0,
          eval_amount: balance.cash_balance,
          quantity: balance.cash_balance,
          group: '현금'
        });
      }
    }
  }

  // 모든 종목을 평탄화하여 테이블에 표시
  const allHoldings = [];
  Object.keys(groupedHoldings).forEach(assetClass => {
    allHoldings.push(...groupedHoldings[assetClass]);
  });

  if (allHoldings.length === 0) {
    return <div className="no-data">보유 자산이 없습니다.</div>;
  }

  return (
    <div className="rebalancing-target-table">
      <table>
        <thead>
          <tr>
            <th>그룹</th>
            <th>종목명</th>
            <th>현재가</th>
            <th>매수가</th>
            <th>수익률</th>
            <th>수익금 (매수한 총 금액)</th>
          </tr>
        </thead>
        <tbody>
          {allHoldings.map((holding, idx) => {
            // 매수한 총 금액 = 평균매수가 * 수량
            const totalBuyAmount = (holding.avg_buy_price || 0) * (holding.quantity || 0);
            
            return (
              <tr key={idx}>
                <td>{holding.group}</td>
                <td>{holding.stock_name}</td>
                <td>
                  {holding.current_price ? `${holding.current_price.toLocaleString('ko-KR')} 원` : '-'}
                </td>
                <td>
                  {holding.avg_buy_price ? `${holding.avg_buy_price.toLocaleString('ko-KR')} 원` : '-'}
                </td>
                <td className={holding.profit_loss_rate >= 0 ? 'positive' : 'negative'}>
                  {holding.profit_loss_rate !== undefined ? `${holding.profit_loss_rate.toFixed(2)}%` : '-'}
                </td>
                <td>
                  {totalBuyAmount > 0 ? `${totalBuyAmount.toLocaleString('ko-KR')} 원` : '-'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// 다음 리밸런싱 변경 사항 목록 컴포넌트
const RebalancingChangesList = ({ changes, targetAllocation, assetClassDetails }) => {
  if (!changes || changes.length === 0) {
    return (
      <div className="rebalancing-changes-empty">
        <p>현재 목표 비중과 일치합니다. 변경 사항이 없습니다.</p>
        {(targetAllocation || assetClassDetails) && (
          <div className="target-allocation-info">
            {targetAllocation && targetAllocation.target_allocation && (
              <div className="ai-allocation-section">
                <p><strong>AI 분석 목표 비중:</strong></p>
                <ul>
                  {Object.entries(targetAllocation.target_allocation).map(([key, value]) => (
                    <li key={key}>
                      {key}: {typeof value === 'number' ? `${value.toFixed(2)}%` : value}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {assetClassDetails && (
              <div className="user-settings-section">
                <p><strong>사용자 설정 (자산군 상세 설정):</strong></p>
                {Object.keys(assetClassDetails).map(assetClass => {
                  const items = assetClassDetails[assetClass] || [];
                  if (items.length === 0) return null;
                  
                  const assetClassLabels = {
                    stocks: '주식',
                    bonds: '채권',
                    alternatives: '대체투자',
                    cash: '현금'
                  };
                  
                  return (
                    <div key={assetClass} className="asset-class-detail">
                      <p><strong>{assetClassLabels[assetClass]}:</strong></p>
                      <ul>
                        {items.map((item, idx) => (
                          <li key={idx}>
                            {item.name} ({item.ticker}) - 비중: {(item.weight * 100).toFixed(2)}%
                            {item.currency && ` [${item.currency}]`}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rebalancing-changes-list">
      {/* AI 목표 비중 및 사용자 설정 정보 */}
      <div className="rebalancing-info-sections">
        {targetAllocation && targetAllocation.target_allocation && (
          <div className="info-section">
            <h4>AI 분석 목표 비중</h4>
            <div className="allocation-grid">
              {Object.entries(targetAllocation.target_allocation).map(([key, value]) => (
                <div key={key} className="allocation-item">
                  <span className="allocation-label">{key}:</span>
                  <span className="allocation-value">{typeof value === 'number' ? `${value.toFixed(2)}%` : value}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {assetClassDetails && (
          <div className="info-section">
            <h4>사용자 설정 (자산군 상세 설정)</h4>
            {Object.keys(assetClassDetails).map(assetClass => {
              const items = assetClassDetails[assetClass] || [];
              if (items.length === 0) return null;
              
              const assetClassLabels = {
                stocks: '주식',
                bonds: '채권',
                alternatives: '대체투자',
                cash: '현금'
              };
              
              return (
                <div key={assetClass} className="asset-class-detail">
                  <strong>{assetClassLabels[assetClass]}:</strong>
                  <ul>
                    {items.map((item, idx) => (
                      <li key={idx}>
                        {item.name} ({item.ticker}) - {(item.weight * 100).toFixed(2)}%
                        {item.currency && ` [${item.currency}]`}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 변경 사항 테이블 */}
      <table>
        <thead>
          <tr>
            <th>자산군</th>
            <th>현재 비중</th>
            <th>목표 비중</th>
            <th>변경 비중</th>
            <th>변경 금액</th>
            <th>조치</th>
            <th>설정된 종목</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change, idx) => (
            <tr key={idx}>
              <td>{change.assetClass}</td>
              <td>{change.currentWeight}%</td>
              <td>{change.targetWeight}%</td>
              <td className={parseFloat(change.diffWeight) >= 0 ? 'positive' : 'negative'}>
                {change.diffWeight}%
              </td>
              <td className={change.diffAmount >= 0 ? 'positive' : 'negative'}>
                {change.diffAmount >= 0 ? '+' : ''}{change.diffAmount.toLocaleString('ko-KR')} 원
              </td>
              <td>
                <span className={`action-badge ${change.action === '매수' ? 'buy' : 'sell'}`}>
                  {change.action}
                </span>
              </td>
              <td>
                {change.items && change.items.length > 0 ? (
                  <div className="configured-items">
                    {change.items.map((item, itemIdx) => (
                      <span key={itemIdx} className="item-badge">
                        {item.name} ({(item.weight * 100).toFixed(0)}%)
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="no-items">설정 없음</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
        if (!info || info.count === 0 && assetClass !== 'cash') {
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

// 리밸런싱 차트 컴포넌트
const RebalancingChart = ({ balance }) => {
  // 자산군별 정보에서 데이터 추출
  const assetClassInfo = balance.asset_class_info || {};
  
  const stockAmount = assetClassInfo.stocks?.total_eval_amount || 0;
  const bondAmount = assetClassInfo.bonds?.total_eval_amount || 0;
  const alternativesAmount = assetClassInfo.alternatives?.total_eval_amount || 0;
  const cashAmount = assetClassInfo.cash?.total_eval_amount || balance.cash_balance || 0;

  const totalAmount = cashAmount + stockAmount + bondAmount + alternativesAmount;

  const chartData = [
    { name: '현금', value: cashAmount, color: '#4CAF50' },
    { name: '주식', value: stockAmount, color: '#2196F3' },
    { name: '채권', value: bondAmount, color: '#FF9800' },
    { name: '대체투자', value: alternativesAmount, color: '#FFC107' }
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

// 자산군 상세 설정 모달 컴포넌트
const AssetClassDetailsModal = ({ onClose }) => {
  const [assetClassDetails, setAssetClassDetails] = useState({
    stocks: [],
    bonds: [],
    alternatives: [],
    cash: []
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('stocks');
  const [editingItems, setEditingItems] = useState({});

  const assetClassLabels = {
    stocks: '주식',
    bonds: '채권',
    alternatives: '대체투자',
    cash: '현금'
  };

  useEffect(() => {
    fetchAssetClassDetails();
  }, []);

  const fetchAssetClassDetails = async () => {
    try {
      const response = await fetch('/api/macro-trading/asset-class-details');
      if (response.ok) {
        const data = await response.json();
        setAssetClassDetails(data.data || {
          stocks: [],
          bonds: [],
          alternatives: [],
          cash: []
        });
        // 각 자산군별로 편집 가능한 상태 초기화
        const editing = {};
        Object.keys(data.data || {}).forEach(assetClass => {
          editing[assetClass] = (data.data[assetClass] || []).map(item => ({
            ...item,
            currency: item.currency || (assetClass === 'cash' ? 'KRW' : undefined)
          }));
        });
        setEditingItems(editing);
      }
    } catch (err) {
      console.error('Error fetching asset class details:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddItem = (assetClass) => {
    // 현금 자산군은 통화 선택이 필요
    if (assetClass === 'cash') {
      const newItem = { 
        currency: 'KRW', 
        ticker: '', 
        name: '원화 현금', 
        weight: 0 
      };
      setEditingItems(prev => ({
        ...prev,
        [assetClass]: [...(prev[assetClass] || []), newItem]
      }));
    } else {
      const newItem = { ticker: '', name: '', weight: 0 };
      setEditingItems(prev => ({
        ...prev,
        [assetClass]: [...(prev[assetClass] || []), newItem]
      }));
    }
  };

  const handleRemoveItem = (assetClass, index) => {
    setEditingItems(prev => ({
      ...prev,
      [assetClass]: prev[assetClass].filter((_, i) => i !== index)
    }));
  };

  const handleItemChange = (assetClass, index, field, value) => {
    setEditingItems(prev => {
      const newItems = [...prev[assetClass]];
      newItems[index] = { ...newItems[index], [field]: value };
      return { ...prev, [assetClass]: newItems };
    });
  };

  const [searchResults, setSearchResults] = useState({});
  const [searchTimeouts, setSearchTimeouts] = useState({});

  const handleNameSearch = async (assetClass, index, searchValue) => {
    // 기존 타이머 취소
    const key = `${assetClass}-${index}`;
    if (searchTimeouts[key]) {
      clearTimeout(searchTimeouts[key]);
    }

    // 입력값 업데이트
    handleItemChange(assetClass, index, 'name', searchValue);

    // 검색어가 2글자 이상일 때만 검색
    if (searchValue.length < 2) {
      setSearchResults(prev => ({ ...prev, [key]: [] }));
      return;
    }

    // 디바운싱: 300ms 후 검색
    const timeout = setTimeout(async () => {
      try {
        const response = await fetch(`/api/macro-trading/search-stocks?keyword=${encodeURIComponent(searchValue)}&limit=10`);
        if (response.ok) {
          const data = await response.json();
          setSearchResults(prev => ({ ...prev, [key]: data.data || [] }));
        }
      } catch (err) {
        console.error('Error searching stocks:', err);
        setSearchResults(prev => ({ ...prev, [key]: [] }));
      }
    }, 300);

    setSearchTimeouts(prev => ({ ...prev, [key]: timeout }));
  };

  const handleSelectStock = (assetClass, index, stock) => {
    const key = `${assetClass}-${index}`;
    handleItemChange(assetClass, index, 'ticker', stock.ticker);
    handleItemChange(assetClass, index, 'name', stock.stock_name);
    setSearchResults(prev => ({ ...prev, [key]: [] }));
  };

  const handleSave = async (assetClass) => {
    const items = editingItems[assetClass] || [];
    
    // 유효성 검사
    if (items.length === 0) {
      alert('최소 1개 이상의 종목이 필요합니다.');
      return;
    }

    const totalWeight = items.reduce((sum, item) => sum + parseFloat(item.weight || 0), 0);
    if (Math.abs(totalWeight - 1.0) > 0.01) {
      alert(`비중 합계가 1.0이어야 합니다. (현재: ${totalWeight.toFixed(4)})`);
      return;
    }

    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/macro-trading/asset-class-details', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          asset_class: assetClass,
          items: items.map(item => ({
            ticker: item.ticker || '',
            name: item.name || (assetClass === 'cash' ? `${item.currency || 'KRW'} 현금` : ''),
            weight: parseFloat(item.weight),
            currency: assetClass === 'cash' ? (item.currency || 'KRW') : undefined
          }))
        })
      });

      if (response.ok) {
        alert('저장되었습니다. 다음 리밸런싱 시 반영됩니다.');
        await fetchAssetClassDetails();
      } else {
        const error = await response.json();
        alert(`저장 실패: ${error.detail || '알 수 없는 오류'}`);
      }
    } catch (err) {
      alert(`저장 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="loading">로딩 중...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content asset-class-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>자산군 상세 설정</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        
        <div className="modal-tabs">
          {Object.keys(assetClassLabels).map(assetClass => (
            <button
              key={assetClass}
              className={`modal-tab ${activeTab === assetClass ? 'active' : ''}`}
              onClick={() => setActiveTab(assetClass)}
            >
              {assetClassLabels[assetClass]}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {Object.keys(assetClassLabels).map(assetClass => (
            activeTab === assetClass && (
              <div key={assetClass} className="asset-class-editor">
                <div className="editor-header">
                  <h3>{assetClassLabels[assetClass]} 자산군 설정</h3>
                  <button
                    className="btn btn-small"
                    onClick={() => handleAddItem(assetClass)}
                  >
                    + {assetClass === 'cash' ? '통화 추가' : '종목 추가'}
                  </button>
                </div>
                
                <div className="items-list">
                  {(editingItems[assetClass] || []).map((item, index) => {
                    const searchKey = `${assetClass}-${index}`;
                    const results = searchResults[searchKey] || [];
                    
                    // 현금 자산군은 통화 선택 UI
                    if (assetClass === 'cash') {
                      const handleCurrencyChange = (newCurrency) => {
                        handleItemChange(assetClass, index, 'currency', newCurrency);
                        // 통화 변경 시 자동으로 티커와 이름 설정
                        if (newCurrency === 'USD') {
                          // 달러 선택 시: KODEX 미국달러선물 ETF (138230) 자동 설정
                          handleItemChange(assetClass, index, 'ticker', '138230');
                          handleItemChange(assetClass, index, 'name', 'KODEX 미국달러선물');
                        } else if (newCurrency === 'KRW') {
                          // 원화 선택 시: 티커는 선택사항, 이름만 설정
                          if (!item.ticker) {
                            handleItemChange(assetClass, index, 'ticker', '');
                          }
                          if (!item.name) {
                            handleItemChange(assetClass, index, 'name', '원화 현금');
                          }
                        }
                      };
                      
                      return (
                        <div key={index} className="item-row cash-item-row">
                          <select
                            className="input-currency"
                            value={item.currency || 'KRW'}
                            onChange={(e) => handleCurrencyChange(e.target.value)}
                          >
                            <option value="KRW">KRW (원화)</option>
                            <option value="USD">USD (달러)</option>
                          </select>
                          <input
                            type="text"
                            placeholder={item.currency === 'USD' ? '티커 (자동: 138230)' : '티커 (선택사항)'}
                            value={item.ticker || ''}
                            onChange={(e) => handleItemChange(assetClass, index, 'ticker', e.target.value)}
                            className="input-ticker"
                            disabled={item.currency === 'USD'} // 달러 선택 시 티커 자동 설정으로 비활성화
                          />
                          <input
                            type="text"
                            placeholder={item.currency === 'USD' ? '이름 (자동: KODEX 미국달러선물)' : '이름 (예: 원화 현금)'}
                            value={item.name || ''}
                            onChange={(e) => handleItemChange(assetClass, index, 'name', e.target.value)}
                            className="input-name"
                            disabled={item.currency === 'USD'} // 달러 선택 시 이름 자동 설정으로 비활성화
                          />
                          <input
                            type="number"
                            placeholder="비중 (0-1)"
                            min="0"
                            max="1"
                            step="0.01"
                            value={item.weight || ''}
                            onChange={(e) => handleItemChange(assetClass, index, 'weight', e.target.value)}
                            className="input-weight"
                          />
                          <button
                            className="btn btn-danger btn-small"
                            onClick={() => handleRemoveItem(assetClass, index)}
                          >
                            삭제
                          </button>
                        </div>
                      );
                    }
                    
                    // 다른 자산군은 기존 UI
                    return (
                      <div key={index} className="item-row">
                        <input
                          type="text"
                          placeholder="티커 (예: 360750)"
                          value={item.ticker || ''}
                          onChange={(e) => handleItemChange(assetClass, index, 'ticker', e.target.value)}
                          className="input-ticker"
                        />
                        <div className="input-name-wrapper">
                          <input
                            type="text"
                            placeholder="종목명 검색 (예: TIGER)"
                            value={item.name || ''}
                            onChange={(e) => handleNameSearch(assetClass, index, e.target.value)}
                            className="input-name"
                            autoComplete="off"
                          />
                          {results.length > 0 && (
                            <div className="search-results-dropdown">
                              {results.map((stock, idx) => (
                                <div
                                  key={idx}
                                  className="search-result-item"
                                  onClick={() => handleSelectStock(assetClass, index, stock)}
                                >
                                  <span className="result-ticker">{stock.ticker}</span>
                                  <span className="result-name">{stock.stock_name}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                        <input
                          type="number"
                          placeholder="비중 (0-1)"
                          min="0"
                          max="1"
                          step="0.01"
                          value={item.weight || ''}
                          onChange={(e) => handleItemChange(assetClass, index, 'weight', e.target.value)}
                          className="input-weight"
                        />
                        <button
                          className="btn btn-danger btn-small"
                          onClick={() => handleRemoveItem(assetClass, index)}
                        >
                          삭제
                        </button>
                      </div>
                    );
                  })}
                </div>

                <div className="editor-footer">
                  <div className="weight-summary">
                    총 비중: {((editingItems[assetClass] || []).reduce((sum, item) => sum + parseFloat(item.weight || 0), 0)).toFixed(4)}
                  </div>
                  <button
                    className="btn btn-primary"
                    onClick={() => handleSave(assetClass)}
                    disabled={saving}
                  >
                    {saving ? '저장 중...' : '저장'}
                  </button>
                </div>
              </div>
            )
          ))}
        </div>
      </div>
    </div>
  );
};

// 수동 리밸런싱 확인 모달 컴포넌트
const RebalanceConfirmModal = ({ onConfirm, onCancel }) => {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content confirm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>리밸런싱 확인</h2>
        </div>
        <div className="modal-body">
          <p>정말 리밸런싱을 실행하시겠습니까?</p>
          <p className="warning-text">
            리밸런싱은 현재 포트폴리오를 AI가 결정한 목표 비중에 맞춰 자동으로 조정합니다.
            실제 매매가 발생할 수 있습니다.
          </p>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>
            취소
          </button>
          <button className="btn btn-primary" onClick={onConfirm}>
            확인
          </button>
        </div>
      </div>
    </div>
  );
};

export default TradingDashboard;

