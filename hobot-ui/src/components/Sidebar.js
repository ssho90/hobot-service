import React from 'react';
import { useAuth } from '../context/AuthContext';
import './Sidebar.css';

const Sidebar = ({ activeTab, setActiveTab }) => {
  const { isAdmin } = useAuth();
  
  const menuItems = [
    { id: 'trading', label: 'Trading', icon: '📊' },
    { id: 'news', label: 'News', icon: '📰' },
  ];

  // Admin 메뉴 추가
  if (isAdmin()) {
    menuItems.push({ id: 'admin', label: 'Admin', icon: '⚙️' });
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <span className="logo-icon">🤖</span>
          <span className="logo-text">Hobot</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {menuItems.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => setActiveTab(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
};

export default Sidebar;

