import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import './Sidebar.css';

const Sidebar = ({ activeTab, setActiveTab }) => {
  const { isAdmin, isSystemAdmin } = useAuth();
  const [expandedMenus, setExpandedMenus] = useState({});
  
  // 시스템 어드민만 Trading 메뉴 접근 가능
  const menuItems = [];
  if (isSystemAdmin()) {
    menuItems.push({ id: 'trading', label: 'Trading', icon: '📊' });
  }
  menuItems.push({ id: 'news', label: 'News', icon: '📰' });

  // Admin 메뉴와 하위 메뉴
  const adminMenu = {
    id: 'admin',
    label: 'Admin',
    icon: '⚙️',
    subItems: [
      { id: 'admin-users', label: '사용자 관리', icon: '👥' },
      { id: 'admin-logs', label: '로그 관리', icon: '📋' },
      { id: 'admin-llm-monitoring', label: 'LLM 모니터링', icon: '🤖' },
      { id: 'admin-sector-management', label: '종목 관리', icon: '📊' }
    ]
  };

  const toggleMenu = (menuId) => {
    setExpandedMenus(prev => ({
      ...prev,
      [menuId]: !prev[menuId]
    }));
  };

  const handleMenuClick = (itemId) => {
    setActiveTab(itemId);
    // Admin 메뉴 클릭 시 하위 메뉴 펼치기
    if (itemId === 'admin' || itemId.startsWith('admin-')) {
      if (!expandedMenus['admin']) {
        setExpandedMenus(prev => ({ ...prev, admin: true }));
      }
    }
  };

  const isMenuExpanded = (menuId) => {
    return expandedMenus[menuId] || false;
  };

  const isActiveMenu = (itemId) => {
    if (itemId === 'admin') {
      return activeTab === 'admin-users' || activeTab === 'admin-logs' || activeTab === 'admin-llm-monitoring' || activeTab === 'admin-sector-management';
    }
    return activeTab === itemId;
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <img src="/banner.png" alt="Stockoverflow" className="logo-image" />
        </div>
      </div>

      <nav className="sidebar-nav">
        {menuItems.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => handleMenuClick(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </button>
        ))}

        {isSystemAdmin() && (
          <div className="nav-menu-group">
            <button
              className={`nav-item ${isActiveMenu('admin') ? 'active' : ''}`}
              onClick={() => toggleMenu('admin')}
            >
              <span className="nav-icon">{adminMenu.icon}</span>
              <span className="nav-label">{adminMenu.label}</span>
              <span className="nav-arrow" style={{ 
                marginLeft: 'auto',
                transform: isMenuExpanded('admin') ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s ease'
              }}>
                ▶
              </span>
            </button>
            {isMenuExpanded('admin') && (
              <div className="nav-submenu">
                {adminMenu.subItems.map((subItem) => (
                  <button
                    key={subItem.id}
                    className={`nav-item nav-subitem ${activeTab === subItem.id ? 'active' : ''}`}
                    onClick={() => handleMenuClick(subItem.id)}
                  >
                    <span className="nav-icon">{subItem.icon}</span>
                    <span className="nav-label">{subItem.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </nav>
    </div>
  );
};

export default Sidebar;

