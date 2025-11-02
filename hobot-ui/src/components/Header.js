import React from 'react';
import './Header.css';

const Header = () => {
  return (
    <header className="top-header">
      <div className="header-search">
        <span className="search-icon">🔍</span>
      </div>
      <div className="header-actions">
        <button className="header-icon-btn">
          <span>🌐</span>
        </button>
        <button className="header-icon-btn">
          <span>🌙</span>
        </button>
        <button className="header-icon-btn notification-btn">
          <span>🔔</span>
          <span className="notification-badge">3</span>
        </button>
        <div className="user-avatar">
          <span>JC</span>
        </div>
      </div>
    </header>
  );
};

export default Header;

