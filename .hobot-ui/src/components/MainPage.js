import React from 'react';
import MacroDashboard from './MacroDashboard';
import Header from './Header';
import './MainPage.css';

const MainPage = () => {
  return (
    <div className="main-page-layout">
      <Header />
      <div className="main-content">
        <div className="content-area">
          <MacroDashboard />
        </div>
      </div>
    </div>
  );
};

export default MainPage;

