import React, { useState, useEffect } from 'react';
import './MacroDashboard.css';

const MacroDashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [overviewData, setOverviewData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Overview 데이터 로드 (API는 추후 구현)
  useEffect(() => {
    if (activeTab === 'overview') {
      // TODO: LLM 분석 결과 API 호출
      // const fetchOverview = async () => {
      //   setLoading(true);
      //   try {
      //     const response = await fetch('/api/macro-trading/overview');
      //     if (response.ok) {
      //       const data = await response.json();
      //       setOverviewData(data);
      //     }
      //   } catch (err) {
      //     setError(err.message);
      //   } finally {
      //     setLoading(false);
      //   }
      // };
      // fetchOverview();
    }
  }, [activeTab]);

  return (
    <div className="macro-dashboard">
      <h1>Macro Dashboard</h1>
      
      {/* 탭 메뉴 */}
      <div className="dashboard-tabs">
        <button
          className={`dashboard-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`dashboard-tab ${activeTab === 'fred' ? 'active' : ''}`}
          onClick={() => setActiveTab('fred')}
        >
          FRED 지표
        </button>
        <button
          className={`dashboard-tab ${activeTab === 'news' ? 'active' : ''}`}
          onClick={() => setActiveTab('news')}
        >
          Economic News
        </button>
      </div>

      {/* Overview 탭 */}
      {activeTab === 'overview' && (
        <div className="tab-content">
          {loading && <div className="loading">분석 중...</div>}
          {error && <div className="error">오류: {error}</div>}
          {!loading && !error && !overviewData && (
            <div className="card">
              <div className="overview-placeholder">
                <h2>거시경제 상황 분석</h2>
                <p>FRED 지표와 Economic News를 조합하여 LLM으로 분석한 결과가 여기에 표시됩니다.</p>
                <p className="note">※ API 구현 예정</p>
              </div>
            </div>
          )}
          {overviewData && (
            <div className="card">
              <div className="overview-content">
                <h2>거시경제 상황 분석</h2>
                <div className="analysis-result">
                  {/* LLM 분석 결과 표시 */}
                  <pre>{JSON.stringify(overviewData, null, 2)}</pre>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* FRED 지표 탭 */}
      {activeTab === 'fred' && (
        <div className="tab-content">
          <p className="info-note">
            FRED 지표는 "모니터링" 탭에서 확인할 수 있습니다.
          </p>
        </div>
      )}

      {/* Economic News 탭 */}
      {activeTab === 'news' && (
        <EconomicNewsTab />
      )}
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

  useEffect(() => {
    const fetchNews = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/macro-trading/economic-news?hours=${hours}`);
        if (!response.ok) {
          throw new Error('뉴스를 불러오는데 실패했습니다.');
        }
        const data = await response.json();
        setNews(data.news || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, [hours]);

  // 필터링된 뉴스
  const filteredNews = news.filter(item => {
    if (filterCountry && item.country !== filterCountry) return false;
    if (filterCategory && item.category !== filterCategory) return false;
    return true;
  });

  // 국가 및 카테고리 목록
  const countries = [...new Set(news.map(item => item.country).filter(Boolean))].sort();
  const categories = [...new Set(news.map(item => item.category).filter(Boolean))].sort();

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
            filteredNews.map(item => (
              <div key={item.id} className="news-item">
                <div className="news-header">
                  <h3 className="news-title">
                    {item.link ? (
                      <a href={item.link} target="_blank" rel="noopener noreferrer">
                        {item.title}
                      </a>
                    ) : (
                      item.title
                    )}
                  </h3>
                  <div className="news-meta">
                    {item.country && <span className="news-country">{item.country}</span>}
                    {item.category && <span className="news-category">{item.category}</span>}
                    {item.published_at && (
                      <span className="news-date">
                        {new Date(item.published_at).toLocaleString('ko-KR')}
                      </span>
                    )}
                  </div>
                </div>
                {item.description && (
                  <div className="news-description">{item.description}</div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default MacroDashboard;

