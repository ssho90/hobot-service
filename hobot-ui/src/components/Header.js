import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Header.css';

const Header = () => {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef(null);

  // 외부 클릭 시 메뉴 닫기
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowMenu(false);
      }
    };

    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showMenu]);

  const handleLogout = () => {
    logout();
    navigate('/login');
    setShowMenu(false);
  };

  const handleUserManagement = () => {
    navigate('/dashboard');
    // Dashboard에서 admin 탭으로 전환
    setTimeout(() => {
      const event = new CustomEvent('switchToAdmin');
      window.dispatchEvent(event);
    }, 100);
    setShowMenu(false);
  };

  const getInitials = (username) => {
    if (!username) return 'U';
    return username.substring(0, 2).toUpperCase();
  };

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
      </div>
    </header>
  );
};

export default Header;

