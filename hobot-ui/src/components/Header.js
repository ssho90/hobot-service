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
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [mobileShowAdminSubmenu, setMobileShowAdminSubmenu] = useState(false);
  const [mobileShowTradingSubmenu, setMobileShowTradingSubmenu] = useState(false);
  const menuRef = useRef(null);
  const adminMenuRef = useRef(null);
  const tradingMenuRef = useRef(null);
  const sidebarRef = useRef(null);

  // Dashboard의 activeTab 변경 추적
  useEffect(() => {
    const handleTabChange = (event) => {
      const tab = event.detail?.tab || null;
      setDashboardActiveTab(tab);
      // Admin 하위 탭이 활성화되면 하위 메뉴 열기
      if (tab === 'admin-users' || tab === 'admin-logs' || tab === 'admin-llm-monitoring' || tab === 'admin-portfolio-management' || tab === 'admin-files') {
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
      // Admin 탭 클릭 시 하위 메뉴 토글 (admin만)
      if (isSystemAdmin()) {
        setShowAdminSubmenu(!showAdminSubmenu);
      }
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
      if (dashboardActiveTab === 'trading-macro' || (dashboardActiveTab === 'trading-crypto' && isSystemAdmin())) return 'trading';
      if (dashboardActiveTab === 'admin-users' || dashboardActiveTab === 'admin-logs' || dashboardActiveTab === 'admin-llm-monitoring' || dashboardActiveTab === 'admin-portfolio-management' || dashboardActiveTab === 'admin-files') return 'admin';
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
      // 사이드바 외부 클릭 시 닫기
      if (sidebarRef.current && !sidebarRef.current.contains(event.target) &&
        !event.target.closest('.mobile-menu-btn')) {
        setIsSidebarOpen(false);
      }
    };

    if (showMenu || showAdminSubmenu || showTradingSubmenu || isSidebarOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showMenu, showAdminSubmenu, showTradingSubmenu, isSidebarOpen]);

  // 사이드바 열릴 때 body 스크롤 방지
  useEffect(() => {
    if (isSidebarOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isSidebarOpen]);

  const handleLogout = () => {
    logout();
    navigate('/');
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

  const getInitials = (userId) => {
    if (!userId) return 'U';
    return userId.substring(0, 2).toUpperCase();
  };

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
  };

  const handleMobileTabClick = (tab) => {
    if (tab === 'trading') {
      setMobileShowTradingSubmenu(!mobileShowTradingSubmenu);
    } else if (tab === 'admin') {
      setMobileShowAdminSubmenu(!mobileShowAdminSubmenu);
    }
  };

  const handleMobileNavClick = (path, tab) => {
    navigate(path);
    setIsSidebarOpen(false);
    setMobileShowAdminSubmenu(false);
    setMobileShowTradingSubmenu(false);
    setTimeout(() => {
      if (tab) {
        const event = new CustomEvent('switchToTab', { detail: { tab } });
        window.dispatchEvent(event);
      }
    }, 100);
  };

  const handleMobileAdminSubmenuClick = (subTab) => {
    navigate('/dashboard?tab=admin');
    setIsSidebarOpen(false);
    setMobileShowAdminSubmenu(false);
    setTimeout(() => {
      const event = new CustomEvent('switchToAdmin', { detail: { tab: subTab } });
      window.dispatchEvent(event);
    }, 100);
  };

  const activeTab = getActiveTab();

  return (
    <>
      <header className="top-header">
        <div className="header-left">
          <button
            className="mobile-menu-btn"
            onClick={toggleSidebar}
            aria-label="메뉴 열기"
          >
            <span>☰</span>
          </button>
          <div
            className="header-logo"
            onClick={() => navigate('/')}
            style={{ cursor: 'pointer' }}
          >
            <img src="/banner.png" alt="Stockoverflow" className="logo-image" />
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
                  {isSystemAdmin() && (
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
                  )}
                </div>
              )}
            </div>
            {isSystemAdmin() && (
              <>
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
                      <button
                        className={`admin-submenu-item ${dashboardActiveTab === 'admin-llm-monitoring' ? 'active' : ''}`}
                        onClick={() => handleAdminSubmenuClick('admin-llm-monitoring')}
                      >
                        LLM 모니터링
                      </button>
                      <button
                        className={`admin-submenu-item ${dashboardActiveTab === 'admin-portfolio-management' ? 'active' : ''}`}
                        onClick={() => handleAdminSubmenuClick('admin-portfolio-management')}
                      >
                        리밸런싱 관리
                      </button>
                      <button
                        className={`admin-submenu-item ${dashboardActiveTab === 'admin-files' ? 'active' : ''}`}
                        onClick={() => handleAdminSubmenuClick('admin-files')}
                      >
                        파일 업로드
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
              <div className="user-menu-container" ref={menuRef}>
                <div
                  className="user-menu"
                  onClick={() => setShowMenu(!showMenu)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="user-avatar">
                    <span>{getInitials(user?.id)}</span>
                  </div>
                  <div className="user-info">
                    <span className="user-name">{user?.id}</span>
                    {user?.role === 'admin' && (
                      <span className="user-role">Admin</span>
                    )}
                  </div>
                  <span className="dropdown-arrow">▼</span>
                </div>

                {showMenu && (
                  <div className="user-dropdown-menu">
                    <button
                      className="dropdown-item"
                      onClick={() => {
                        navigate('/dashboard?tab=profile');
                        setShowMenu(false);
                        setTimeout(() => {
                          const event = new CustomEvent('switchToTab', { detail: { tab: 'profile' } });
                          window.dispatchEvent(event);
                        }, 100);
                      }}
                    >
                      <span className="dropdown-icon">👤</span>
                      <span>프로필</span>
                    </button>
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

      {/* 모바일 사이드바 오버레이 */}
      <div
        className={`sidebar-overlay ${isSidebarOpen ? 'show' : ''}`}
        onClick={() => setIsSidebarOpen(false)}
      />

      {/* 모바일 사이드바 */}
      <aside
        ref={sidebarRef}
        className={`mobile-sidebar ${isSidebarOpen ? 'open' : ''}`}
      >
        <div className="mobile-sidebar-header">
          <div
            className="mobile-sidebar-logo"
            onClick={() => {
              navigate('/');
              setIsSidebarOpen(false);
            }}
            style={{ cursor: 'pointer' }}
          >
            <img src="/banner.png" alt="Stockoverflow" className="logo-image" />
          </div>
          <button
            className="mobile-sidebar-close"
            onClick={() => setIsSidebarOpen(false)}
            aria-label="메뉴 닫기"
          >
            ✕
          </button>
        </div>

        <nav className="mobile-sidebar-nav">
          <button
            className={`mobile-nav-item ${activeTab === 'macro-dashboard' ? 'active' : ''}`}
            onClick={() => handleMobileNavClick('/dashboard?tab=macro-dashboard', 'macro-dashboard')}
          >
            <span className="mobile-nav-icon">📊</span>
            <span>Macro Dashboard</span>
          </button>

          <div className="mobile-nav-group">
            <button
              className={`mobile-nav-item ${activeTab === 'trading' ? 'active' : ''}`}
              onClick={() => handleMobileTabClick('trading')}
            >
              <span className="mobile-nav-icon">💹</span>
              <span>Trading</span>
              <span className="mobile-nav-arrow" style={{
                marginLeft: 'auto',
                transform: mobileShowTradingSubmenu ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s ease'
              }}>
                ▶
              </span>
            </button>
            {mobileShowTradingSubmenu && (
              <div className="mobile-nav-submenu">
                <button
                  className={`mobile-nav-item mobile-nav-subitem ${dashboardActiveTab === 'trading-macro' ? 'active' : ''}`}
                  onClick={() => handleMobileNavClick('/dashboard?tab=trading-macro', 'trading-macro')}
                >
                  <span className="mobile-nav-icon">📈</span>
                  <span>Macro Quant</span>
                </button>
                {isSystemAdmin() && (
                  <button
                    className={`mobile-nav-item mobile-nav-subitem ${dashboardActiveTab === 'trading-crypto' ? 'active' : ''}`}
                    onClick={() => handleMobileNavClick('/dashboard?tab=trading-crypto', 'trading-crypto')}
                  >
                    <span className="mobile-nav-icon">₿</span>
                    <span>Crypto</span>
                  </button>
                )}
              </div>
            )}
          </div>

          {isSystemAdmin() && (
            <>
              <div className="mobile-nav-group">
                <button
                  className={`mobile-nav-item ${activeTab === 'admin' ? 'active' : ''}`}
                  onClick={() => handleMobileTabClick('admin')}
                >
                  <span className="mobile-nav-icon">⚙️</span>
                  <span>Admin</span>
                  <span className="mobile-nav-arrow" style={{
                    marginLeft: 'auto',
                    transform: mobileShowAdminSubmenu ? 'rotate(90deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s ease'
                  }}>
                    ▶
                  </span>
                </button>
                {mobileShowAdminSubmenu && (
                  <div className="mobile-nav-submenu">
                    <button
                      className={`mobile-nav-item mobile-nav-subitem ${dashboardActiveTab === 'admin-users' ? 'active' : ''}`}
                      onClick={() => handleMobileAdminSubmenuClick('admin-users')}
                    >
                      <span className="mobile-nav-icon">👥</span>
                      <span>사용자 관리</span>
                    </button>
                    <button
                      className={`mobile-nav-item mobile-nav-subitem ${dashboardActiveTab === 'admin-logs' ? 'active' : ''}`}
                      onClick={() => handleMobileAdminSubmenuClick('admin-logs')}
                    >
                      <span className="mobile-nav-icon">📋</span>
                      <span>로그 관리</span>
                    </button>
                    <button
                      className={`mobile-nav-item mobile-nav-subitem ${dashboardActiveTab === 'admin-llm-monitoring' ? 'active' : ''}`}
                      onClick={() => handleMobileAdminSubmenuClick('admin-llm-monitoring')}
                    >
                      <span className="mobile-nav-icon">🤖</span>
                      <span>LLM 모니터링</span>
                    </button>
                    <button
                      className={`mobile-nav-item mobile-nav-subitem ${dashboardActiveTab === 'admin-portfolio-management' ? 'active' : ''}`}
                      onClick={() => handleMobileAdminSubmenuClick('admin-portfolio-management')}
                    >
                      <span className="mobile-nav-icon">💼</span>
                      <span>리밸런싱 관리</span>
                    </button>
                    <button
                      className={`mobile-nav-item mobile-nav-subitem ${dashboardActiveTab === 'admin-files' ? 'active' : ''}`}
                      onClick={() => handleMobileAdminSubmenuClick('admin-files')}
                    >
                      <span className="mobile-nav-icon">📁</span>
                      <span>파일 업로드</span>
                    </button>
                  </div>
                )}
              </div>
            </>
          )}

          {user && (
            <div className="mobile-sidebar-user">
              <div className="mobile-user-avatar">
                <span>{getInitials(user?.id)}</span>
              </div>
              <div className="mobile-user-info">
                <span className="mobile-user-name">{user?.id}</span>
                {user?.role === 'admin' && (
                  <span className="mobile-user-role">Admin</span>
                )}
              </div>
            </div>
          )}

          {user && (
            <div className="mobile-sidebar-actions">
              <button
                className="mobile-action-btn"
                onClick={() => {
                  navigate('/dashboard?tab=profile');
                  setIsSidebarOpen(false);
                  setTimeout(() => {
                    const event = new CustomEvent('switchToTab', { detail: { tab: 'profile' } });
                    window.dispatchEvent(event);
                  }, 100);
                }}
              >
                <span className="mobile-action-icon">👤</span>
                <span>프로필</span>
              </button>
              {isAdmin() && (
                <button
                  className="mobile-action-btn"
                  onClick={() => {
                    handleUserManagement();
                    setIsSidebarOpen(false);
                  }}
                >
                  <span className="mobile-action-icon">👥</span>
                  <span>사용자 관리</span>
                </button>
              )}
              <button
                className="mobile-action-btn"
                onClick={() => {
                  handleLogout();
                  setIsSidebarOpen(false);
                }}
              >
                <span className="mobile-action-icon">🚪</span>
                <span>로그아웃</span>
              </button>
            </div>
          )}

          {!user && (
            <button
              className="mobile-login-btn"
              onClick={() => {
                handleLogin();
                setIsSidebarOpen(false);
              }}
            >
              로그인
            </button>
          )}
        </nav>
      </aside>
    </>
  );
};

export default Header;

