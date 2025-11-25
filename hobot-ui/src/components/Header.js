import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import LoginModal from './LoginModal';
import './Header.css';

const Header = () => {
  const { user, logout, isAdmin, isSystemAdmin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showMenu, setShowMenu] = useState(false);
  const [showAdminSubmenu, setShowAdminSubmenu] = useState(false);
  const [showTradingSubmenu, setShowTradingSubmenu] = useState(false);
  const [dashboardActiveTab, setDashboardActiveTab] = useState(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const menuRef = useRef(null);
  const adminMenuRef = useRef(null);
  const tradingMenuRef = useRef(null);
  
  // Dashboard의 activeTab 변경 추적
  useEffect(() => {
    const handleTabChange = (event) => {
      const tab = event.detail?.tab || null;
      setDashboardActiveTab(tab);
      // Admin 하위 탭이 활성화되면 하위 메뉴 열기
      if (tab === 'admin-users' || tab === 'admin-logs') {
        setShowAdminSubmenu(true);
      }
      // Trading 하위 탭이 활성화되면 하위 메뉴 열기
      if (tab === 'trading-macro' || tab === 'trading-crypto') {
        setShowTradingSubmenu(true);
      }
    };
    
    window.addEventListener('dashboardTabChange', handleTabChange);
    return () => {
      window.removeEventListener('dashboardTabChange', handleTabChange);
    };
  }, []);
  
  const handleLogin = () => {
    setShowLoginModal(true);
  };

  const handleTabClick = (tab) => {
    if (tab === 'trading') {
      // Trading 탭 클릭 시 하위 메뉴 토글
      setShowTradingSubmenu(!showTradingSubmenu);
    } else if (tab === 'admin') {
      // Admin 탭 클릭 시 하위 메뉴 토글
      setShowAdminSubmenu(!showAdminSubmenu);
    }
  };
  
  const handleAdminSubmenuClick = (subTab) => {
    navigate('/dashboard?tab=admin');
    setShowAdminSubmenu(false);
    setTimeout(() => {
      const event = new CustomEvent('switchToAdmin', { detail: { tab: subTab } });
      window.dispatchEvent(event);
    }, 100);
  };
  
  // 현재 활성 탭 확인
  const getActiveTab = () => {
    if (location.pathname === '/dashboard') {
      if (dashboardActiveTab === 'trading-macro' || dashboardActiveTab === 'trading-crypto') return 'trading';
      if (dashboardActiveTab === 'admin-users' || dashboardActiveTab === 'admin-logs') return 'admin';
      if (dashboardActiveTab === 'macro-dashboard') return 'macro-dashboard';
      return 'macro-dashboard'; // 기본값
    }
    // 기본 화면(/)에서는 Macro Dashboard가 활성화
    if (location.pathname === '/') {
      return 'macro-dashboard';
    }
    return 'macro-dashboard';
  };

  // 외부 클릭 시 메뉴 닫기
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowMenu(false);
      }
      if (adminMenuRef.current && !adminMenuRef.current.contains(event.target)) {
        setShowAdminSubmenu(false);
      }
      if (tradingMenuRef.current && !tradingMenuRef.current.contains(event.target)) {
        setShowTradingSubmenu(false);
      }
    };

    if (showMenu || showAdminSubmenu || showTradingSubmenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showMenu, showAdminSubmenu, showTradingSubmenu]);

  const handleLogout = () => {
    logout();
    navigate('/login');
    setShowMenu(false);
  };

  const handleUserManagement = () => {
    navigate('/dashboard');
    // Dashboard에서 admin-users 탭으로 전환
    setTimeout(() => {
      const event = new CustomEvent('switchToAdmin', { detail: { tab: 'admin-users' } });
      window.dispatchEvent(event);
    }, 100);
    setShowMenu(false);
  };

  const getInitials = (username) => {
    if (!username) return 'U';
    return username.substring(0, 2).toUpperCase();
  };

  const activeTab = getActiveTab();
  
  return (
    <header className="top-header">
      <div className="header-left">
        <div className="header-logo">
          <span className="logo-icon">🤖</span>
          <span className="logo-text">Hobot</span>
        </div>
        <nav className="header-tabs">
          <button
            className={`header-tab ${activeTab === 'macro-dashboard' ? 'active' : ''}`}
            onClick={() => {
              navigate('/dashboard?tab=macro-dashboard');
              setTimeout(() => {
                const event = new CustomEvent('switchToTab', { detail: { tab: 'macro-dashboard' } });
                window.dispatchEvent(event);
              }, 100);
            }}
          >
            Macro Dashboard
          </button>
          {isSystemAdmin() && (
            <>
              <div className="header-tab-container" ref={tradingMenuRef}>
                <button
                  className={`header-tab ${activeTab === 'trading' ? 'active' : ''}`}
                  onClick={() => handleTabClick('trading')}
                >
                  Trading
                  <span className="tab-arrow">▼</span>
                </button>
                {showTradingSubmenu && (
                  <div className="admin-submenu">
                    <button
                      className={`admin-submenu-item ${dashboardActiveTab === 'trading-macro' ? 'active' : ''}`}
                      onClick={() => {
                        navigate('/dashboard?tab=trading-macro');
                        setShowTradingSubmenu(false);
                        setTimeout(() => {
                          const event = new CustomEvent('switchToTab', { detail: { tab: 'trading-macro' } });
                          window.dispatchEvent(event);
                        }, 100);
                      }}
                    >
                      Macro Quant
                    </button>
                    <button
                      className={`admin-submenu-item ${dashboardActiveTab === 'trading-crypto' ? 'active' : ''}`}
                      onClick={() => {
                        navigate('/dashboard?tab=trading-crypto');
                        setShowTradingSubmenu(false);
                        setTimeout(() => {
                          const event = new CustomEvent('switchToTab', { detail: { tab: 'trading-crypto' } });
                          window.dispatchEvent(event);
                        }, 100);
                      }}
                    >
                      Crypto
                    </button>
                  </div>
                )}
              </div>
              <div className="header-tab-container" ref={adminMenuRef}>
                <button
                  className={`header-tab ${activeTab === 'admin' ? 'active' : ''}`}
                  onClick={() => handleTabClick('admin')}
                >
                  Admin
                  <span className="tab-arrow">▼</span>
                </button>
                {showAdminSubmenu && (
                  <div className="admin-submenu">
                    <button
                      className={`admin-submenu-item ${dashboardActiveTab === 'admin-users' ? 'active' : ''}`}
                      onClick={() => handleAdminSubmenuClick('admin-users')}
                    >
                      사용자 관리
                    </button>
                    <button
                      className={`admin-submenu-item ${dashboardActiveTab === 'admin-logs' ? 'active' : ''}`}
                      onClick={() => handleAdminSubmenuClick('admin-logs')}
                    >
                      로그 관리
                    </button>
                  </div>
                )}
              </div>
            </>
          )}
        </nav>
      </div>
      <div className="header-actions">
        {user ? (
          <>
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
            <div className="user-menu-container" ref={menuRef}>
              <div 
                className="user-menu" 
                onClick={() => setShowMenu(!showMenu)}
                style={{ cursor: 'pointer' }}
              >
                <div className="user-avatar">
                  <span>{getInitials(user?.username)}</span>
                </div>
                <div className="user-info">
                  <span className="user-name">{user?.username}</span>
                  {user?.role === 'admin' && (
                    <span className="user-role">Admin</span>
                  )}
                </div>
                <span className="dropdown-arrow">▼</span>
              </div>
              
              {showMenu && (
                <div className="user-dropdown-menu">
                  {isAdmin() && (
                    <button 
                      className="dropdown-item"
                      onClick={handleUserManagement}
                    >
                      <span className="dropdown-icon">👥</span>
                      <span>사용자 관리</span>
                    </button>
                  )}
                  <button 
                    className="dropdown-item"
                    onClick={handleLogout}
                  >
                    <span className="dropdown-icon">🚪</span>
                    <span>로그아웃</span>
                  </button>
                </div>
              )}
            </div>
          </>
        ) : (
            <button 
              className="btn btn-secondary"
              onClick={handleLogin}
              style={{ padding: '8px 16px' }}
            >
              로그인
            </button>
          )}
      </div>
      
      <LoginModal 
        isOpen={showLoginModal} 
        onClose={() => setShowLoginModal(false)} 
      />
    </header>
  );
};

export default Header;

