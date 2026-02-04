import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './News.css';

const News = () => {
  const [news, setNews] = useState('');
  const [newsDate, setNewsDate] = useState('');
  const [isToday, setIsToday] = useState(false);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState(null);

  const fetchNews = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/news');
      if (response.ok) {
        const data = await response.json();
        setNews(data.news);
        setNewsDate(data.date);
        setIsToday(data.is_today);
      } else {
        setError(`Failed to fetch news: ${response.status}`);
      }
    } catch (err) {
      setError(`Error fetching news: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const updateNews = async () => {
    setUpdating(true);
    setError(null);
    try {
      // 타임아웃을 3분(180초)으로 설정
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 180000); // 3분
      
      const response = await fetch('/api/news-update?force=true', {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) {
        const data = await response.json().catch(() => null);
        if (data && data.status === 'success') {
          // 업데이트 성공 후 새 뉴스 불러오기
          await fetchNews();
        } else {
          setError(`Failed to update news: ${data?.message || 'Unknown response format'}`);
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
        setError(`Failed to update news: ${errorData.detail || response.status}`);
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        setError('News update timed out. Please try again.');
      } else {
        setError(`Error updating news: ${err.message}`);
      }
    } finally {
      setUpdating(false);
    }
  };

  // 컴포넌트 마운트 시 자동으로 뉴스 로드
  useEffect(() => {
    fetchNews();
  }, []);

  return (
    <div className="news-container">
      <div className="news-header">
        <div>
          <h2>Daily News</h2>
          {newsDate && (
            <p className="news-date">
              {newsDate} {isToday ? '(Today)' : ''}
            </p>
          )}
        </div>
        <div className="news-buttons">
          <button 
            className="btn btn-update" 
            onClick={updateNews}
            disabled={updating || loading}
          >
            {updating ? 'Updating...' : 'Update News'}
          </button>
          <button 
            className="btn btn-refresh" 
            onClick={fetchNews}
            disabled={loading || updating}
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {loading && !news && (
        <div className="loading-message">
          Loading news...
        </div>
      )}

      {!loading && !error && !news && (
        <div className="card news-content-card">
          <div className="news-content" style={{ textAlign: 'center', padding: '2rem' }}>
            <p style={{ fontSize: '1.2rem', color: '#666' }}>
              업데이트가 필요합니다.
            </p>
            <p style={{ fontSize: '0.9rem', color: '#999', marginTop: '0.5rem' }}>
              오늘자 뉴스가 없습니다. 'Update News' 버튼을 클릭하여 뉴스를 업데이트하세요.
            </p>
          </div>
        </div>
      )}

      {!loading && !error && news && !isToday && (
        <div className="card news-content-card">
          <div className="news-content" style={{ textAlign: 'center', padding: '1rem', marginBottom: '1rem', backgroundColor: '#fff3cd', borderRadius: '4px' }}>
            <p style={{ fontSize: '1rem', color: '#856404', margin: 0 }}>
              ⚠️ 업데이트가 필요합니다. 오늘자 뉴스가 아닙니다.
            </p>
          </div>
          <div className="news-content">
            <ReactMarkdown 
              remarkPlugins={[remarkGfm]}
              components={{
                h3: ({node, children, ...props}) => <h3 className="news-header-text" {...props}>{children}</h3>,
                p: ({node, ...props}) => <p className="news-text" {...props} />,
                strong: ({node, ...props}) => <strong className="news-bold" {...props} />,
                ul: ({node, ...props}) => <ul className="news-list" {...props} />,
                li: ({node, ...props}) => <li className="news-item" {...props} />,
              }}
            >
              {news}
            </ReactMarkdown>
          </div>
        </div>
      )}

      {!loading && !error && news && isToday && (
        <div className="card news-content-card">
          <div className="news-content">
            <ReactMarkdown 
              remarkPlugins={[remarkGfm]}
              components={{
                h3: ({node, children, ...props}) => <h3 className="news-header-text" {...props}>{children}</h3>,
                p: ({node, ...props}) => <p className="news-text" {...props} />,
                strong: ({node, ...props}) => <strong className="news-bold" {...props} />,
                ul: ({node, ...props}) => <ul className="news-list" {...props} />,
                li: ({node, ...props}) => <li className="news-item" {...props} />,
              }}
            >
              {news}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
};

export default News;

