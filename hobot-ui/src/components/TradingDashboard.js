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
          editing[assetClass] = [...(data.data[assetClass] || [])];
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
    const newItem = { ticker: '', name: '', weight: 0 };
    setEditingItems(prev => ({
      ...prev,
      [assetClass]: [...(prev[assetClass] || []), newItem]
    }));
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
            ticker: item.ticker,
            name: item.name,
            weight: parseFloat(item.weight)
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
                    + 종목 추가
                  </button>
                </div>
                
                <div className="items-list">
                  {(editingItems[assetClass] || []).map((item, index) => {
                    const searchKey = `${assetClass}-${index}`;
                    const results = searchResults[searchKey] || [];
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

