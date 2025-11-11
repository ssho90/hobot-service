import React, { useEffect } from 'react';
import News from './News';
import Header from './Header';
import './MainPage.css';

const MainPage = () => {
  // MainPage가 마운트될 때 News 탭 활성화 알림
  useEffect(() => {
    const event = new CustomEvent('dashboardTabChange', { detail: { tab: 'news' } });
    window.dispatchEvent(event);
  }, []);

  return (
    <div className="main-page-layout">
      <Header />
      <div className="main-content">
        <div className="content-area">
          <News />
        </div>
      </div>
    </div>
  );
};

export default MainPage;

