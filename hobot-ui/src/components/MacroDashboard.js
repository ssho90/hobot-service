import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useAuth } from '../context/AuthContext';
import './MacroDashboard.css';
import './MacroMonitoring.css';

const MacroDashboard = () => {
  const [subTab, setSubTab] = useState('fred'); // 'fred' or 'news'
  const [overviewData, setOverviewData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [historyData, setHistoryData] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotalPages, setHistoryTotalPages] = useState(1);
  const { isAdmin, getAuthHeaders } = useAuth();

  // Overview 데이터 로드
  const fetchOverview = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/macro-trading/overview');
      if (response.ok) {
        const result = await response.json();
        if (result.status === 'success' && result.data) {
          setOverviewData(result.data);
        } else {
          setOverviewData(null);
        }
      } else {
        throw new Error('AI 분석 데이터를 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError(err.message);
      console.error('Error fetching overview:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isMounted = true;
    
    const loadData = async () => {
      if (isMounted) {
        await fetchOverview();
      }
    };
    
    loadData();
    
    return () => {
      isMounted = false;
    };
  }, []);

  // 이전 분석 데이터 조회
  const fetchHistoryData = async (page = 1) => {
    setHistoryLoading(true);
    try {
      const response = await fetch(`/api/macro-trading/strategy-decisions-history?page=${page}&limit=1`);
      if (response.ok) {
        const result = await response.json();
        if (result.status === 'success' && result.data) {
          setHistoryData(Array.isArray(result.data) ? result.data : [result.data]);
          setHistoryTotalPages(result.total_pages || 1);
          setHistoryPage(result.page || 1);
        } else {
          setHistoryData([]);
        }
      } else {
        throw new Error('이전 분석 데이터를 불러오는데 실패했습니다.');
      }
    } catch (err) {
      console.error('Error fetching history:', err);
      setHistoryData([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  // 이전 분석 모달 열기
  useEffect(() => {
    if (showHistoryModal) {
      fetchHistoryData(1);
    }
  }, [showHistoryModal]);

  // 수동 AI 분석 실행
  const handleManualUpdate = async () => {
    if (!isAdmin()) {
      alert('관리자만 사용할 수 있는 기능입니다.');
      return;
    }

    setUpdating(true);
    setError(null);
    
    try {
      const response = await fetch('/api/macro-trading/run-ai-analysis', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        }
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === 'success') {
          alert('AI 분석이 완료되었습니다. 결과를 불러오는 중...');
          // 분석 완료 후 데이터 다시 로드
          await fetchOverview();
        } else {
          throw new Error(result.message || 'AI 분석 실행에 실패했습니다.');
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: '알 수 없는 오류' }));
        throw new Error(errorData.detail || 'AI 분석 실행에 실패했습니다.');
      }
    } catch (err) {
      setError(err.message);
      alert(`오류: ${err.message}`);
      console.error('Error running AI analysis:', err);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="macro-dashboard">
      {/* Overview 섹션 (항상 표시) */}
      <div className="overview-section">
        <div className="overview-header-section">
          <div className="overview-title-wrapper">
            <h2>
              <span className="ai-badge">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/>
                </svg>
                <span className="ai-badge-text">AI 분석</span>
              </span>
              overview
            </h2>
            {overviewData && (
              <button
                className="info-button"
                onClick={() => setShowInfoModal(true)}
                title="AI 분석 방법 알아보기"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" fill="none"/>
                  <path d="M12 16v-4M12 8h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              </button>
            )}
          </div>
          <div className="overview-buttons">
            <button
              className="btn-history"
              onClick={() => setShowHistoryModal(true)}
              title="이전 분석 검색"
            >
              이전 분석 검색
            </button>
            {isAdmin() && (
              <button
                className="btn btn-primary btn-update"
                onClick={handleManualUpdate}
                disabled={updating || loading}
              >
                {updating ? '분석 중...' : '수동 업데이트'}
              </button>
            )}
          </div>
        </div>
        <div className="card overview-card">
          {loading && <div className="loading">분석 중...</div>}
          {error && <div className="error">오류: {error}</div>}
          {!loading && !error && !overviewData && (
            <div className="overview-placeholder">
              <p>Overview 관련 내용 출력</p>
            </div>
          )}
          {overviewData && (
            <div className="overview-content">
              <div className="overview-header">
                <div className="overview-date">
                  <span className="ai-badge-small">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/>
                    </svg>
                    AI 생성
                  </span>
                  분석 일시: {overviewData.decision_date || overviewData.created_at}
                </div>
              </div>
              
              <div className="analysis-summary">
                <h3>
                  <span className="ai-icon-inline">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/>
                    </svg>
                  </span>
                  분석 요약
                </h3>
                <p>{overviewData.analysis_summary}</p>
              </div>
              
              {overviewData.reasoning && (
                <div className="analysis-reasoning">
                  <h3>판단 근거</h3>
                  <p>{overviewData.reasoning}</p>
                </div>
              )}
              
              {overviewData.target_allocation && (
                <div className="target-allocation">
                  <h3>목표 자산 배분</h3>
                  <div className="allocation-grid">
                    <div className="allocation-item">
                      <span className="allocation-label">주식</span>
                      <span className="allocation-value">{overviewData.target_allocation.Stocks?.toFixed(1) || 0}%</span>
                    </div>
                    <div className="allocation-item">
                      <span className="allocation-label">채권</span>
                      <span className="allocation-value">{overviewData.target_allocation.Bonds?.toFixed(1) || 0}%</span>
                    </div>
                    <div className="allocation-item">
                      <span className="allocation-label">대체투자</span>
                      <span className="allocation-value">{overviewData.target_allocation.Alternatives?.toFixed(1) || 0}%</span>
                    </div>
                    <div className="allocation-item">
                      <span className="allocation-label">현금</span>
                      <span className="allocation-value">{overviewData.target_allocation.Cash?.toFixed(1) || 0}%</span>
                    </div>
                  </div>
                </div>
              )}

          {overviewData.recommended_stocks && (
            <div className="recommended-stocks">
              <h3>
                <span className="ai-icon-inline">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/>
                  </svg>
                </span>
                AI 추천 섹터/그룹
              </h3>
              
              {/* 세부 전략 근거 표시 */}
              {overviewData.recommended_stocks.reasoning && (
                <div className="sub-reasoning-box">
                  <h4>💡 세부 전략 근거</h4>
                  <p>{overviewData.recommended_stocks.reasoning}</p>
                </div>
              )}
              
              <div className="recommended-stocks-content">
                    {overviewData.recommended_stocks.Stocks && Array.isArray(overviewData.recommended_stocks.Stocks) && overviewData.recommended_stocks.Stocks.length > 0 && (
                      <div className="recommended-category">
                        <h4>
                          <span className="category-icon">📈</span>
                          주식 ({overviewData.target_allocation?.Stocks?.toFixed(1) || 0}%)
                        </h4>
                        <ul className="recommended-list">
                          {overviewData.recommended_stocks.Stocks.map((item, idx) => (
                            <li key={idx}>
                              <span className="category-name">{item.category || 'N/A'}</span>
                              <span className="category-weight">{(item.weight ? (item.weight * 100).toFixed(0) : 0)}%</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {overviewData.recommended_stocks.Bonds && Array.isArray(overviewData.recommended_stocks.Bonds) && overviewData.recommended_stocks.Bonds.length > 0 && (
                      <div className="recommended-category">
                        <h4>
                          <span className="category-icon">📊</span>
                          채권 ({overviewData.target_allocation?.Bonds?.toFixed(1) || 0}%)
                        </h4>
                        <ul className="recommended-list">
                          {overviewData.recommended_stocks.Bonds.map((item, idx) => (
                            <li key={idx}>
                              <span className="category-name">{item.category || 'N/A'}</span>
                              <span className="category-weight">{(item.weight ? (item.weight * 100).toFixed(0) : 0)}%</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {overviewData.recommended_stocks.Alternatives && Array.isArray(overviewData.recommended_stocks.Alternatives) && overviewData.recommended_stocks.Alternatives.length > 0 && (
                      <div className="recommended-category">
                        <h4>
                          <span className="category-icon">💎</span>
                          대체투자 ({overviewData.target_allocation?.Alternatives?.toFixed(1) || 0}%)
                        </h4>
                        <ul className="recommended-list">
                          {overviewData.recommended_stocks.Alternatives.map((item, idx) => (
                            <li key={idx}>
                              <span className="category-name">{item.category || 'N/A'}</span>
                              <span className="category-weight">{(item.weight ? (item.weight * 100).toFixed(0) : 0)}%</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {overviewData.recommended_stocks.Cash && Array.isArray(overviewData.recommended_stocks.Cash) && overviewData.recommended_stocks.Cash.length > 0 && (
                      <div className="recommended-category">
                        <h4>
                          <span className="category-icon">💰</span>
                          현금 ({overviewData.target_allocation?.Cash?.toFixed(1) || 0}%)
                        </h4>
                        <ul className="recommended-list">
                          {overviewData.recommended_stocks.Cash.map((item, idx) => (
                            <li key={idx}>
                              <span className="category-name">{item.category || 'N/A'}</span>
                              <span className="category-weight">{(item.weight ? (item.weight * 100).toFixed(0) : 0)}%</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 구분선 */}
      <div className="divider"></div>

      {/* 서브 탭 메뉴 (Fred 지표, Economic News) */}
      <div className="sub-tabs">
        <button
          className={`sub-tab ${subTab === 'fred' ? 'active' : ''}`}
          onClick={() => setSubTab('fred')}
        >
          Fred 지표
        </button>
        <button
          className={`sub-tab ${subTab === 'news' ? 'active' : ''}`}
          onClick={() => setSubTab('news')}
        >
          Economic News
        </button>
      </div>

      {/* 서브 탭 컨텐츠 */}
      <div className="sub-tab-content">
        {subTab === 'fred' && <FredIndicatorsTab />}
        {subTab === 'news' && <EconomicNewsTab />}
      </div>

      {/* AI 분석 정보 모달 */}
      {showInfoModal && (
        <div className="modal-overlay" onClick={() => setShowInfoModal(false)}>
          <div className="modal-content ai-info-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <span className="ai-badge">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/>
                  </svg>
                  <span className="ai-badge-text">AI 분석 방법</span>
                </span>
              </h2>
              <button className="modal-close" onClick={() => setShowInfoModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="ai-info-content">
                <section className="info-section">
                  <h3>📊 분석 개요</h3>
                  <p>
                    이 분석은 AI 모델을 사용하여 매일 오전 8시 30분에 자동으로 실행됩니다.
                    거시경제 데이터와 뉴스를 종합적으로 분석하여 최적의 자산 배분 전략을 제시합니다.
                  </p>
                </section>

                <section className="info-section">
                  <h3>📈 사용 데이터</h3>
                  <div className="data-sources">
                    <div className="data-source-item">
                      <h4>1. FRED 정량 시그널 (가장 신뢰도 높음)</h4>
                      <ul>
                        <li><strong>장단기 금리차 추세</strong>: 10년-2년 국채 금리차의 20일/120일 이동평균 분석</li>
                        <li><strong>실질 금리</strong>: 명목 금리에서 인플레이션을 차감한 실질 금리</li>
                        <li><strong>테일러 룰 시그널</strong>: 연준의 정책 금리 적정성 평가</li>
                        <li><strong>순유동성</strong>: 연준 총자산에서 역RP 잔액을 차감한 순유동성 (4주 이동평균)</li>
                        <li><strong>하이일드 스프레드</strong>: 고수익 채권과 국채 간 금리차</li>
                        <li><strong>기타 지표</strong>: CPI, PCE, GDP, 실업률, 고용 데이터 등</li>
                      </ul>
                    </div>

                    <div className="data-source-item">
                      <h4>2. 경제 뉴스 (정성적 감정 분석)</h4>
                      <ul>
                        <li>최근 <strong>1주일</strong> 이내의 주요 경제 뉴스 수집</li>
                        <li>특정 국가 필터링: Crypto, Commodity, Euro Area, China, United States</li>
                        <li>뉴스의 내용과 톤을 분석하여 시장 심리 파악</li>
                        <li>정량 시그널에 비해 낮은 비중으로 참고</li>
                      </ul>
                    </div>

                  </div>
                </section>

                <section className="info-section">
                  <h3>🤖 분석 프로세스</h3>
                  <ol className="process-steps">
                    <li>
                      <strong>데이터 수집</strong>
                      <p>FRED API에서 최신 거시경제 지표와 물가 지표를 수집하고, TradingEconomics에서 경제 뉴스를 수집합니다.</p>
                    </li>
                    <li>
                      <strong>시그널 계산</strong>
                      <p>정량적 지표들을 분석하여 투자 시그널을 계산합니다 (예: 금리차 추세, 유동성 상태, 하이일드 스프레드 등).</p>
                    </li>
                    <li>
                      <strong>AI 종합 분석</strong>
                      <p>수집된 모든 데이터를 Gemini 2.5 Pro AI 모델에 제공하여 종합적인 시장 분석과 투자 전략을 생성합니다.</p>
                    </li>
                    <li>
                      <strong>자산 배분 결정</strong>
                      <p>AI가 분석 결과를 바탕으로 주식, 채권, 대체투자, 현금의 최적 비중을 제시합니다.</p>
                    </li>
                    <li>
                      <strong>판단 근거 제공</strong>
                      <p>각 결정에 대한 상세한 판단 근거를 한국어로 제공하여 투자자가 이해할 수 있도록 합니다.</p>
                    </li>
                  </ol>
                </section>

                <section className="info-section">
                  <h3>⚙️ 실행 주기</h3>
                  <p>
                    AI 분석은 <strong>매일 오전 8시 30분</strong>에 자동으로 실행됩니다.
                    관리자는 필요시 "수동 업데이트" 버튼을 통해 언제든지 분석을 실행할 수 있습니다.
                  </p>
                </section>

                <section className="info-section">
                  <h3>⚠️ 주의사항</h3>
                  <ul>
                    <li>이 분석은 AI가 생성한 것으로, 투자 결정의 참고 자료로만 사용해야 합니다.</li>
                    <li>실제 투자 결정은 개인의 위험 성향과 재무 상황을 고려하여 신중하게 내려야 합니다.</li>
                    <li>시장 상황은 빠르게 변할 수 있으므로, 분석 결과를 맹신하지 마세요.</li>
                  </ul>
                </section>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 이전 분석 검색 모달 */}
      {showHistoryModal && (
        <div className="modal-overlay" onClick={() => setShowHistoryModal(false)}>
          <div className="modal-content history-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>이전 분석 검색</h2>
              <button className="modal-close" onClick={() => setShowHistoryModal(false)}>×</button>
            </div>
            <div className="history-modal-body">
              {historyLoading ? (
                <div className="loading">로딩 중...</div>
              ) : historyData && historyData.length > 0 ? (
                <div className="history-content">
                  {historyData.map((item, index) => (
                    <div key={item.id || index} className="history-item">
                      <div className="history-header">
                        <div className="history-date">
                          분석 일시: {item.decision_date || item.created_at}
                        </div>
                      </div>
                      
                      <div className="history-section">
                        <h3>분석 요약</h3>
                        <p>{item.analysis_summary}</p>
                      </div>
                      
                      {item.reasoning && (
                        <div className="history-section">
                          <h3>판단 근거</h3>
                          <p>{item.reasoning}</p>
                        </div>
                      )}
                      
                      {item.target_allocation && (
                        <div className="history-section">
                          <h3>목표 자산 배분</h3>
                          <div className="allocation-grid">
                            <div className="allocation-item">
                              <span className="allocation-label">주식</span>
                              <span className="allocation-value">{item.target_allocation.Stocks?.toFixed(1) || 0}%</span>
                            </div>
                            <div className="allocation-item">
                              <span className="allocation-label">채권</span>
                              <span className="allocation-value">{item.target_allocation.Bonds?.toFixed(1) || 0}%</span>
                            </div>
                            <div className="allocation-item">
                              <span className="allocation-label">대체투자</span>
                              <span className="allocation-value">{item.target_allocation.Alternatives?.toFixed(1) || 0}%</span>
                            </div>
                            <div className="allocation-item">
                              <span className="allocation-label">현금</span>
                              <span className="allocation-value">{item.target_allocation.Cash?.toFixed(1) || 0}%</span>
                            </div>
                          </div>
                        </div>
                      )}

                      {item.recommended_stocks && (
                        <div className="history-section">
                          <h3>AI 추천 섹터/그룹</h3>
                          
                          {/* 세부 전략 근거 표시 (이전 분석 내역) */}
                          {item.recommended_stocks.reasoning && (
                            <div className="sub-reasoning-box history-sub-reasoning">
                              <h4>💡 세부 전략 근거</h4>
                              <p>{item.recommended_stocks.reasoning}</p>
                            </div>
                          )}
                          
                          <div className="recommended-stocks-content">
                            {item.recommended_stocks.Stocks && Array.isArray(item.recommended_stocks.Stocks) && item.recommended_stocks.Stocks.length > 0 && (
                              <div className="recommended-category">
                                <h4>주식 ({item.target_allocation?.Stocks?.toFixed(1) || 0}%)</h4>
                                <ul className="recommended-list">
                                  {item.recommended_stocks.Stocks.map((stock, idx) => (
                                    <li key={idx}>
                                      <span className="category-name">{stock.category}</span>
                                      <span className="category-weight">{(stock.weight ? (stock.weight * 100).toFixed(0) : 0)}%</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {item.recommended_stocks.Bonds && Array.isArray(item.recommended_stocks.Bonds) && item.recommended_stocks.Bonds.length > 0 && (
                              <div className="recommended-category">
                                <h4>채권 ({item.target_allocation?.Bonds?.toFixed(1) || 0}%)</h4>
                                <ul className="recommended-list">
                                  {item.recommended_stocks.Bonds.map((bond, idx) => (
                                    <li key={idx}>
                                      <span className="category-name">{bond.category}</span>
                                      <span className="category-weight">{(bond.weight ? (bond.weight * 100).toFixed(0) : 0)}%</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {item.recommended_stocks.Alternatives && Array.isArray(item.recommended_stocks.Alternatives) && item.recommended_stocks.Alternatives.length > 0 && (
                              <div className="recommended-category">
                                <h4>대체투자 ({item.target_allocation?.Alternatives?.toFixed(1) || 0}%)</h4>
                                <ul className="recommended-list">
                                  {item.recommended_stocks.Alternatives.map((alt, idx) => (
                                    <li key={idx}>
                                      <span className="category-name">{alt.category}</span>
                                      <span className="category-weight">{(alt.weight ? (alt.weight * 100).toFixed(0) : 0)}%</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {item.recommended_stocks.Cash && Array.isArray(item.recommended_stocks.Cash) && item.recommended_stocks.Cash.length > 0 && (
                              <div className="recommended-category">
                                <h4>현금 ({item.target_allocation?.Cash?.toFixed(1) || 0}%)</h4>
                                <ul className="recommended-list">
                                  {item.recommended_stocks.Cash.map((cash, idx) => (
                                    <li key={idx}>
                                      <span className="category-name">{cash.category}</span>
                                      <span className="category-weight">{(cash.weight ? (cash.weight * 100).toFixed(0) : 0)}%</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">분석 데이터가 없습니다.</div>
              )}
            </div>
            {/* 페이징 - 모달 body 밖으로 이동 */}
            {historyTotalPages > 1 && (
              <div className="pagination">
                <button
                  className="pagination-btn"
                  onClick={() => {
                    const newPage = Math.max(1, historyPage - 1);
                    setHistoryPage(newPage);
                    fetchHistoryData(newPage);
                  }}
                  disabled={historyPage === 1}
                >
                  이전
                </button>
                <span className="pagination-info">
                  {historyPage} / {historyTotalPages}
                </span>
                <button
                  className="pagination-btn"
                  onClick={() => {
                    const newPage = Math.min(historyTotalPages, historyPage + 1);
                    setHistoryPage(newPage);
                    fetchHistoryData(newPage);
                  }}
                  disabled={historyPage === historyTotalPages}
                >
                  다음
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// FRED 지표 탭 컴포넌트
const FredIndicatorsTab = () => {
  const [yieldSpreadData, setYieldSpreadData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const chartContainerRef = useRef(null);

  // 장단기 금리차 데이터 로드
  useEffect(() => {
    const fetchYieldSpreadData = async () => {
      const url = '/api/macro-trading/yield-curve-spread?days=365';
      console.log('[MacroDashboard] Fetching yield spread data from:', url);
      
      try {
        setLoading(true);
        setError(null);
        
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }).catch((fetchError) => {
          console.error('[MacroDashboard] Fetch error details:', {
            name: fetchError.name,
            message: fetchError.message,
            stack: fetchError.stack,
            cause: fetchError.cause,
            type: fetchError.constructor.name,
          });
          throw fetchError;
        });
        
        console.log('[MacroDashboard] Response received:', {
          status: response.status,
          statusText: response.statusText,
          ok: response.ok,
          headers: Object.fromEntries(response.headers.entries()),
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error('[MacroDashboard] Error response body:', errorText);
          let errorData;
          try {
            errorData = JSON.parse(errorText);
          } catch {
            errorData = { detail: `서버 오류 (${response.status} ${response.statusText})` };
          }
          throw new Error(errorData.detail || '데이터를 불러오는데 실패했습니다.');
        }
        
        const data = await response.json();
        console.log('[MacroDashboard] Data received:', { hasError: !!data.error, dataKeys: Object.keys(data) });
        
        if (data.error) {
          const errorMsg = data.error.message || '데이터를 불러오는 중 오류가 발생했습니다.';
          console.error('[MacroDashboard] Data contains error:', data.error);
          setError(errorMsg);
          if (data.spread_data && data.spread_data.length > 0) {
            setYieldSpreadData(data);
          } else {
            setYieldSpreadData(null);
          }
        } else {
          setYieldSpreadData(data);
          setError(null);
        }
      } catch (err) {
        console.error('[MacroDashboard] Full error object:', {
          name: err.name,
          message: err.message,
          stack: err.stack,
          cause: err.cause,
          type: err.constructor.name,
          toString: err.toString(),
        });
        
        // 네트워크 에러인 경우
        if (err.name === 'TypeError' && (err.message.includes('fetch') || err.message.includes('Failed to fetch'))) {
          const errorMsg = '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요. (프록시 설정: http://localhost:8991)';
          console.error('[MacroDashboard] Network error - 프록시 또는 백엔드 서버 연결 실패');
          setError(errorMsg);
        } else {
          setError(err.message || '데이터를 불러오는데 실패했습니다.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchYieldSpreadData();
  }, []);

  return (
    <div className="fred-indicators-tab">
      {loading && <div className="macro-monitoring-loading">데이터를 불러오는 중...</div>}
      {error && (
        <div className="macro-monitoring-error-banner">
          <strong>⚠️ 경고:</strong> {error}
        </div>
      )}
      
      {!loading && yieldSpreadData && (
        <>
          {/* 기타 지표 차트 (장단기 금리차 포함) */}
          <OtherIndicatorsCharts yieldSpreadData={yieldSpreadData} chartContainerRef={chartContainerRef} />
        </>
      )}
    </div>
  );
};

// 기타 지표 차트 컴포넌트
const OtherIndicatorsCharts = ({ yieldSpreadData, chartContainerRef }) => {
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
  const [realInterestRateData, setRealInterestRateData] = useState(null);
  const [netLiquidityData, setNetLiquidityData] = useState(null);
  const [loading, setLoading] = useState(true);
  const chartRef = useRef(null);
  const resizeHandlerRef = useRef(null);
  const internalChartContainerRef = useRef(null);

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
            // 네트워크 에러는 조용히 처리 (개별 지표 실패는 전체를 막지 않음)
            if (err.name === 'TypeError' && err.message.includes('fetch')) {
              console.error(`Network error fetching ${code}: 서버에 연결할 수 없습니다.`);
            } else {
              console.error(`Error fetching ${code}:`, err);
            }
            return { code, data: null };
          }
        });

        // 실질 금리와 순 유동성 데이터도 함께 가져오기
        const realRatePromise = fetch('/api/macro-trading/real-interest-rate?days=365')
          .then(res => res.ok ? res.json() : null)
          .catch(err => {
            console.error('Error fetching real interest rate:', err);
            return null;
          });

        const netLiquidityPromise = fetch('/api/macro-trading/net-liquidity?days=365')
          .then(res => res.ok ? res.json() : null)
          .catch(err => {
            console.error('Error fetching net liquidity:', err);
            return null;
          });

        const [results, realRateResult, netLiquidityResult] = await Promise.all([
          Promise.all(promises),
          realRatePromise,
          netLiquidityPromise
        ]);

        const newIndicators = {};
        results.forEach(({ code, data }) => {
          newIndicators[code] = data;
        });
        setIndicators(newIndicators);
        
        if (realRateResult && realRateResult.data) {
          setRealInterestRateData(realRateResult.data);
        }
        
        if (netLiquidityResult && netLiquidityResult.data) {
          setNetLiquidityData(netLiquidityResult.data);
        }
      } catch (err) {
        console.error('Error fetching indicators:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchAllIndicators();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 차트 생성 함수
  const createChartInstance = (containerElement) => {
    if (!containerElement) {
      console.warn('[OtherIndicatorsCharts] Chart container is null');
      return;
    }

    if (!yieldSpreadData || !yieldSpreadData.spread_data || yieldSpreadData.spread_data.length === 0) {
      console.warn('[OtherIndicatorsCharts] No valid spread data');
      return;
    }

    if (chartRef.current) {
      chartRef.current.remove();
    }

    console.log('[OtherIndicatorsCharts] Creating chart', {
      containerWidth: containerElement.clientWidth,
      spreadDataCount: yieldSpreadData.spread_data.length,
    });

    const chart = createChart(containerElement, {
        layout: {
          background: { type: ColorType.Solid, color: 'white' },
          textColor: 'black',
        },
        width: containerElement.clientWidth,
        height: 300,
        grid: {
          vertLines: { color: '#e0e0e0' },
          horzLines: { color: '#e0e0e0' },
        },
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
        },
        rightPriceScale: {
          borderVisible: false,
        },
        leftPriceScale: {
          borderVisible: false,
        },
      });

      const spreadSeries = chart.addLineSeries({
        title: '장단기 금리차',
        color: '#2196F3',
        lineWidth: 2,
      });

      const ma20Series = chart.addLineSeries({
        title: '20일 이동평균',
        color: '#FF9800',
        lineWidth: 1,
      });

      const ma120Series = chart.addLineSeries({
        title: '120일 이동평균',
        color: '#4CAF50',
        lineWidth: 1,
      });

      const spreadData = yieldSpreadData.spread_data
        .filter(item => item && item.date && item.value !== null && item.value !== undefined)
        .map(item => ({
          time: item.date,
          value: parseFloat(item.value),
        }));

      const ma20Data = (yieldSpreadData.ma20 || [])
        .filter(item => item && item.value !== null && item.value !== undefined && item.date)
        .map(item => ({
          time: item.date,
          value: parseFloat(item.value),
        }));

      const ma120Data = (yieldSpreadData.ma120 || [])
        .filter(item => item && item.value !== null && item.value !== undefined && item.date)
        .map(item => ({
          time: item.date,
          value: parseFloat(item.value),
        }));

      console.log('[OtherIndicatorsCharts] Chart data prepared', {
        spreadDataCount: spreadData.length,
        ma20Count: ma20Data.length,
        ma120Count: ma120Data.length,
        firstSpreadItem: spreadData[0],
        lastSpreadItem: spreadData[spreadData.length - 1],
      });

      if (spreadData.length > 0) {
        spreadSeries.setData(spreadData);
      }
      if (ma20Data.length > 0) {
        ma20Series.setData(ma20Data);
      }
      if (ma120Data.length > 0) {
        ma120Series.setData(ma120Data);
      }

      chartRef.current = chart;

    const handleResize = () => {
      if (containerElement && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerElement.clientWidth,
        });
      }
    };

    resizeHandlerRef.current = handleResize;
    window.addEventListener('resize', handleResize);
  };

  // ref callback을 사용하여 ref가 설정될 때 차트 생성
  const handleChartContainerRef = (element) => {
    internalChartContainerRef.current = element;
    
    // 부모 컴포넌트의 ref도 업데이트
    if (chartContainerRef) {
      if (typeof chartContainerRef === 'function') {
        chartContainerRef(element);
      } else if (chartContainerRef.current !== undefined) {
        chartContainerRef.current = element;
      }
    }

    // ref가 설정되면 차트 생성
    if (element && yieldSpreadData) {
      // DOM이 완전히 렌더링될 때까지 약간의 지연
      setTimeout(() => {
        createChartInstance(element);
      }, 0);
    }
  };

  // yieldSpreadData가 변경될 때 차트 업데이트
  useEffect(() => {
    if (internalChartContainerRef.current && yieldSpreadData) {
      createChartInstance(internalChartContainerRef.current);
    }

    return () => {
      if (resizeHandlerRef.current) {
        window.removeEventListener('resize', resizeHandlerRef.current);
        resizeHandlerRef.current = null;
      }
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yieldSpreadData]);

  if (loading) {
    return <div className="indicators-loading">지표 데이터를 불러오는 중...</div>;
  }

  const indicatorInfo = {
    FEDFUNDS: { 
      name: '연준 금리', 
      unit: '%',
      description: '연방준비제도가 설정하는 기준금리로, 통화정책의 핵심 지표입니다.'
    },
    CPIAUCSL: { 
      name: 'CPI (소비자물가지수)', 
      unit: 'Index',
      description: '소비자가 구매하는 상품과 서비스의 가격 변화를 측정하는 물가 지표입니다.'
    },
    PCEPI: { 
      name: 'PCE (개인소비지출)', 
      unit: 'Index',
      description: '연준이 선호하는 물가 지표로, CPI보다 소비 패턴 변화를 더 잘 반영합니다.'
    },
    GDP: { 
      name: 'GDP', 
      unit: 'Billions of $',
      description: '국내총생산으로, 한 국가의 경제 성장을 측정하는 핵심 지표입니다.'
    },
    UNRATE: { 
      name: '실업률', 
      unit: '%',
      description: '노동력 중 실업자 비율로, 노동 시장의 건강도를 나타냅니다.'
    },
    PAYEMS: { 
      name: '비농업 고용', 
      unit: 'Thousands',
      description: '농업을 제외한 모든 산업의 고용자 수로, 경제 활동의 강도를 나타냅니다.'
    },
    WALCL: { 
      name: '연준 총자산', 
      unit: 'Millions of $',
      description: '연준의 총 자산 규모로, 양적완화(QE)나 긴축 정책의 규모를 나타냅니다.'
    },
    WTREGEN: { 
      name: '재무부 일반계정', 
      unit: 'Millions of $',
      description: '미국 재무부의 일반계정 잔액으로, 정부의 현금 보유량을 나타냅니다.'
    },
    RRPONTSYD: { 
      name: '역RP 잔액', 
      unit: 'Billions of $',
      description: '역레포 거래 잔액으로, 금융 시장의 유동성 흡수 규모를 나타냅니다.'
    },
    BAMLH0A0HYM2: { 
      name: '하이일드 스프레드', 
      unit: '%',
      description: '고수익 채권과 국채 간 금리차로, 시장의 위험 선호도를 나타냅니다.'
    },
  };

  // 그룹별 지표 분류
  const indicatorGroups = {
    liquidity: {
      title: '유동성',
      codes: ['WALCL', 'WTREGEN', 'RRPONTSYD'],
      description: '시장 유동성과 연준의 통화정책 규모를 나타내는 지표들입니다.'
    },
    employment: {
      title: '고용',
      codes: ['UNRATE', 'PAYEMS'],
      description: '노동 시장의 건강도와 경제 활동 강도를 나타내는 지표들입니다.'
    },
    inflation: {
      title: '물가 및 통화정책',
      codes: ['FEDFUNDS', 'CPIAUCSL', 'PCEPI'],
      description: '물가 수준과 통화정책 방향을 나타내는 지표들입니다.'
    },
    growth: {
      title: '경기 성장 및 리스크 신호',
      codes: ['GDP', 'BAMLH0A0HYM2'],
      description: '경제 성장과 시장 리스크를 나타내는 지표들입니다.'
    }
  };

  const renderIndicatorChart = (code, indicatorData) => {
    const data = indicatorData?.data || indicatorData;
    if (!data || data.length === 0) {
      if (indicatorData?.error) {
        const info = indicatorInfo[code];
        return (
          <div key={code} className="indicator-chart indicator-error">
            <h3>{info?.name || code} ({code})</h3>
            <div className="indicator-error-message">
              <strong>⚠️ 오류:</strong> {indicatorData.error.message}
            </div>
          </div>
        );
      }
      return null;
    }

    const info = indicatorInfo[code];
    if (!info) return null;

    return (
      <div key={code} className="indicator-chart">
        <h3>{info.name} ({code})</h3>
        <p className="indicator-description">{info.description}</p>
        {indicatorData?.error && (
          <div className="indicator-warning">
            <strong>⚠️ 경고:</strong> {indicatorData.error.message}
          </div>
        )}
        {indicatorData?.warning && (
          <div className="indicator-warning">
            <strong>⚠️ 데이터 품질 경고:</strong> {indicatorData.warning.message}
          </div>
        )}
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
  };

  return (
    <div className="other-indicators">
      {/* 유동성 그룹 */}
      <div className="indicator-group">
        <div className="indicator-group-header">
          <h2>💧 유동성</h2>
          <p className="group-description">{indicatorGroups.liquidity.description}</p>
        </div>
        <div className="indicators-grid">
          {indicatorGroups.liquidity.codes.map(code => renderIndicatorChart(code, indicators[code]))}
        </div>
      </div>

      {/* 고용 그룹 */}
      <div className="indicator-group">
        <div className="indicator-group-header">
          <h2>👥 고용</h2>
          <p className="group-description">{indicatorGroups.employment.description}</p>
        </div>
        <div className="indicators-grid">
          {indicatorGroups.employment.codes.map(code => renderIndicatorChart(code, indicators[code]))}
        </div>
      </div>

      {/* 물가 및 통화정책 그룹 */}
      <div className="indicator-group">
        <div className="indicator-group-header">
          <h2>💰 물가 및 통화정책</h2>
          <p className="group-description">{indicatorGroups.inflation.description}</p>
        </div>
        <div className="indicators-grid">
          {indicatorGroups.inflation.codes.map(code => renderIndicatorChart(code, indicators[code]))}
          {/* 실질 금리 차트 */}
          {realInterestRateData && realInterestRateData.length > 0 && (
            <div className="indicator-chart">
              <h3>실질 금리</h3>
              <p className="indicator-description">
                명목 금리에서 인플레이션을 차감한 실질 금리입니다. 
                양수면 통화 정책이 경기 과열 억제 효과가 있고, 음수면 통화 완화적이며 자산 가격 상승 압력이 있습니다.
              </p>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={realInterestRateData}>
                  <defs>
                    <linearGradient id="colorRealRate" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#FF9800" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#FF9800" stopOpacity={0} />
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
                    label={{ value: '%', angle: -90, position: 'insideLeft' }}
                  />
                  <Tooltip 
                    formatter={(value) => [`${value}%`, '실질 금리']}
                    labelFormatter={(label) => `날짜: ${label}`}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#FF9800"
                    fillOpacity={1}
                    fill="url(#colorRealRate)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* 경기 성장 및 리스크 신호 그룹 */}
      <div className="indicator-group">
        <div className="indicator-group-header">
          <h2>📈 경기 성장 및 리스크 신호</h2>
          <p className="group-description">{indicatorGroups.growth.description}</p>
        </div>
        <div className="indicators-grid">
          {indicatorGroups.growth.codes.map(code => renderIndicatorChart(code, indicators[code]))}
          {/* 장단기 금리차 차트 */}
          {yieldSpreadData && (
            <div className="indicator-chart">
              <h3>장단기 금리차 (DGS10 - DGS2)</h3>
              <p className="indicator-description">
                10년 국채와 2년 국채의 금리차로, 경기 사이클과 금리 곡선의 변화를 나타냅니다. 양수면 정상 곡선, 음수면 역전을 의미합니다.
              </p>
              {yieldSpreadData.error && (
                <div className="data-quality-warning">
                  <strong>⚠️ 데이터 품질 경고:</strong> {yieldSpreadData.error.message}
                  {yieldSpreadData.error.details && (
                    <ul>
                      {yieldSpreadData.error.details.map((detail, idx) => (
                        <li key={idx}>{detail}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {(!yieldSpreadData.spread_data || yieldSpreadData.spread_data.length === 0) ? (
                <div className="indicator-error-message">
                  차트 데이터가 없습니다. API 응답을 확인해주세요.
                </div>
              ) : (
                <div ref={handleChartContainerRef} className="yield-spread-chart" style={{ minHeight: '300px' }} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Economic News 탭 컴포넌트
const EconomicNewsTab = () => {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [hours, setHours] = useState(24);
  const [filterCountry, setFilterCountry] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [translationLang, setTranslationLang] = useState('en'); // 'en' or 'ko'
  const [translatedData, setTranslatedData] = useState({}); // {field_id: translated_text}
  const [translating, setTranslating] = useState({}); // {field_id: true/false}

  useEffect(() => {
    const fetchNews = async () => {
      const url = `/api/macro-trading/economic-news?hours=${hours}`;
      console.log('[EconomicNewsTab] Fetching news from:', url);
      
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }).catch((fetchError) => {
          console.error('[EconomicNewsTab] Fetch error details:', {
            name: fetchError.name,
            message: fetchError.message,
            stack: fetchError.stack,
            cause: fetchError.cause,
            type: fetchError.constructor.name,
          });
          throw fetchError;
        });
        
        console.log('[EconomicNewsTab] Response received:', {
          status: response.status,
          statusText: response.statusText,
          ok: response.ok,
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error('[EconomicNewsTab] Error response body:', errorText);
          let errorData;
          try {
            errorData = JSON.parse(errorText);
          } catch {
            errorData = { detail: `서버 오류 (${response.status} ${response.statusText})` };
          }
          throw new Error(errorData.detail || '뉴스를 불러오는데 실패했습니다.');
        }
        const data = await response.json();
        console.log('[EconomicNewsTab] Data received:', { newsCount: data.news?.length || 0 });
        setNews(data.news || []);
      } catch (err) {
        console.error('[EconomicNewsTab] Full error object:', {
          name: err.name,
          message: err.message,
          stack: err.stack,
          cause: err.cause,
          type: err.constructor.name,
          toString: err.toString(),
        });
        
        // 네트워크 에러인 경우
        if (err.name === 'TypeError' && (err.message.includes('fetch') || err.message.includes('Failed to fetch'))) {
          console.error('[EconomicNewsTab] Network error - 프록시 또는 백엔드 서버 연결 실패');
          setError('서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요. (프록시 설정: http://localhost:8991)');
        } else {
          setError(err.message || '뉴스를 불러오는데 실패했습니다.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, [hours]);

  // 필터링된 뉴스 (published_at 기준 최신순 정렬)
  const filteredNews = news
    .filter(item => {
      if (filterCountry && item.country !== filterCountry) return false;
      if (filterCategory && item.category !== filterCategory) return false;
      return true;
    })
    .sort((a, b) => {
      // published_at 기준 최신순 정렬 (내림차순)
      if (!a.published_at && !b.published_at) return 0;
      if (!a.published_at) return 1;
      if (!b.published_at) return -1;
      return new Date(b.published_at) - new Date(a.published_at);
    });

  // 국가 및 카테고리 목록
  const countries = [...new Set(news.map(item => item.country).filter(Boolean))].sort();
  const categories = [...new Set(news.map(item => item.category).filter(Boolean))].sort();

  // 번역 함수
  const translateText = async (text, fieldId, newsId, fieldType) => {
    if (!text || translationLang === 'en') {
      // 영어 모드이거나 텍스트가 없으면 번역하지 않음
      const newTranslatedData = { ...translatedData };
      delete newTranslatedData[fieldId];
      setTranslatedData(newTranslatedData);
      return;
    }

    // 이미 번역된 데이터가 있으면 사용
    if (translatedData[fieldId]) {
      return;
    }

    setTranslating({ ...translating, [fieldId]: true });

    try {
      const response = await fetch('/api/macro-trading/translate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: text,
          target_lang: 'ko',
          news_id: newsId,
          field_type: fieldType
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setTranslatedData({
            ...translatedData,
            [fieldId]: data.translated_text
          });
        }
      }
    } catch (err) {
      console.error('Translation error:', err);
    } finally {
      setTranslating({ ...translating, [fieldId]: false });
    }
  };

  // 번역 언어 변경 시 번역 데이터 초기화
  useEffect(() => {
    if (translationLang === 'en') {
      setTranslatedData({});
      setTranslating({});
    }
  }, [translationLang]);

  // 한글 모드일 때 뉴스가 로드되면 번역 요청 (DB에서 먼저 확인)
  useEffect(() => {
    if (translationLang === 'ko' && filteredNews.length > 0) {
      // DB에서 이미 번역된 내용이 있으면 먼저 사용 (title, description만)
      filteredNews.forEach((item) => {
        const titleKey = `title_${item.id}`;
        const descKey = `desc_${item.id}`;
        
        // DB에서 가져온 번역 데이터가 있으면 사용
        if (item.title_ko && !translatedData[titleKey]) {
          setTranslatedData(prev => ({ ...prev, [titleKey]: item.title_ko }));
        }
        if (item.description_ko && !translatedData[descKey]) {
          setTranslatedData(prev => ({ ...prev, [descKey]: item.description_ko }));
        }
        
        // DB에 번역이 없으면 번역 요청 (title, description만)
        if (item.title && !item.title_ko && !translatedData[titleKey] && !translating[titleKey]) {
          translateText(item.title, titleKey, item.id, 'title');
        }
        if (item.description && !item.description_ko && !translatedData[descKey] && !translating[descKey]) {
          translateText(item.description, descKey, item.id, 'description');
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translationLang, news]);

  return (
    <div className="tab-content">
      <div className="news-controls">
        <div className="control-group">
          <label>시간 범위:</label>
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={24}>24시간</option>
            <option value={48}>48시간</option>
            <option value={72}>72시간</option>
            <option value={168}>1주일</option>
          </select>
        </div>
        <div className="control-group">
          <label>국가:</label>
          <select value={filterCountry} onChange={(e) => setFilterCountry(e.target.value)}>
            <option value="">전체</option>
            {countries.map(country => (
              <option key={country} value={country}>{country}</option>
            ))}
          </select>
        </div>
        <div className="control-group">
          <label>카테고리:</label>
          <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}>
            <option value="">전체</option>
            {categories.map(category => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>
        </div>
        <div className="control-group">
          <label>번역:</label>
          <div className="lang-toggle">
            <button
              className={translationLang === 'en' ? 'active' : ''}
              onClick={() => setTranslationLang('en')}
            >
              EN
            </button>
            <button
              className={translationLang === 'ko' ? 'active' : ''}
              onClick={() => setTranslationLang('ko')}
            >
              KO
            </button>
          </div>
        </div>
      </div>

      {loading && <div className="loading">뉴스를 불러오는 중...</div>}
      {error && <div className="error">오류: {error}</div>}
      {!loading && !error && (
        <div className="news-list">
          <div className="news-summary">
            총 {filteredNews.length}개의 뉴스가 있습니다.
          </div>
          {filteredNews.length === 0 ? (
            <div className="no-news">뉴스가 없습니다.</div>
          ) : (
            filteredNews.map(item => {
              const titleKey = `title_${item.id}`;
              const descKey = `desc_${item.id}`;
              
              const displayTitle = translationLang === 'ko' && translatedData[titleKey] 
                ? translatedData[titleKey] 
                : item.title;
              const displayDesc = translationLang === 'ko' && translatedData[descKey] 
                ? translatedData[descKey] 
                : item.description;

              return (
                <div key={item.id} className="news-item">
                  <div className="news-header">
                    <h3 className="news-title">
                      {item.link ? (
                        <a href={item.link} target="_blank" rel="noopener noreferrer">
                          {translating[titleKey] ? '번역 중...' : displayTitle}
                        </a>
                      ) : (
                        translating[titleKey] ? '번역 중...' : displayTitle
                      )}
                    </h3>
                    <div className="news-meta">
                      {item.country && (
                        <span className="news-country">
                          {item.country}
                        </span>
                      )}
                      {item.category && (
                        <span className="news-category">
                          {item.category}
                        </span>
                      )}
                      {item.published_at && (
                        <span className="news-date">
                          {new Date(item.published_at).toLocaleString('ko-KR')}
                        </span>
                      )}
                    </div>
                  </div>
                  {displayDesc && (
                    <div className="news-description">
                      {translating[descKey] ? '번역 중...' : displayDesc}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};

export default MacroDashboard;

