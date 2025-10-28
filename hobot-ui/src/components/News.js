import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './News.css';

const News = () => {
  const [news, setNews] = useState('');
  const [newsDate, setNewsDate] = useState('');
  const [isToday, setIsToday] = useState(false);
  const [loading, setLoading] = useState(false);
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
        <button 
          className="btn btn-refresh" 
          onClick={fetchNews}
          disabled={loading}
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
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

      {news && (
        <div className="news-content">
          <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            components={{
              h3: ({node, ...props}) => <h3 className="news-header-text" {...props} />,
              p: ({node, ...props}) => <p className="news-text" {...props} />,
              strong: ({node, ...props}) => <strong className="news-bold" {...props} />,
              ul: ({node, ...props}) => <ul className="news-list" {...props} />,
              li: ({node, ...props}) => <li className="news-item" {...props} />,
            }}
          >
            {news}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
};

export default News;

