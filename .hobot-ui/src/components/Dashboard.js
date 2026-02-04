import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import UpbitAccountSummary from './UpbitAccountSummary';
import UserManagementPage from './UserManagementPage';
import LogManagementPage from './LogManagementPage';
import LLMMonitoringPage from './LLMMonitoringPage';
import PortfolioManagementPage from './PortfolioManagementPage';
import MacroDashboard from './MacroDashboard';
import TradingDashboard from './TradingDashboard';
import ProfilePage from './ProfilePage';
import FileUploadPage from './FileUploadPage';
import Header from './Header';
import PlatformSelector from './PlatformSelector';
import './Dashboard.css';

const Dashboard = () => {
  const { isSystemAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState('macro-dashboard');
  const [activePlatform, setActivePlatform] = useState('upbit');

  // trading-crypto는 admin만 접근 가능, trading-macro는 전체 사용자 접근 가능
  useEffect(() => {
    if (activeTab === 'trading-crypto' && !isSystemAdmin()) {
      setActiveTab('macro-dashboard');
    }
  }, [activeTab, isSystemAdmin]);

  // 시스템 어드민이 아니면 admin 탭 접근 불가
  useEffect(() => {
    if ((activeTab === 'admin-users' || activeTab === 'admin-logs' || activeTab === 'admin-llm-monitoring' || activeTab === 'admin-portfolio-management' || activeTab === 'admin-files') && !isSystemAdmin()) {
      setActiveTab('news');
    }
  }, [activeTab, isSystemAdmin]);

  // Header 탭 클릭에 따라 초기 탭 설정
  useEffect(() => {
    // URL에서 탭 정보 확인 (예: /dashboard?tab=trading-macro)
    const urlParams = new URLSearchParams(window.location.search);
    const tabParam = urlParams.get('tab');
    if (tabParam === 'trading-macro') {
      setActiveTab('trading-macro');
    } else if (tabParam === 'trading-crypto' && isSystemAdmin()) {
      setActiveTab('trading-crypto');
    } else if (tabParam === 'admin' && isSystemAdmin()) {
      setActiveTab('admin-users');
    } else if (tabParam === 'macro-dashboard') {
      setActiveTab('macro-dashboard');
    } else if (tabParam === 'profile') {
      setActiveTab('profile');
    }
  }, [isSystemAdmin]);

  // Header에서 사용자 관리 클릭 시 admin 탭으로 전환
  useEffect(() => {
    const handleSwitchToAdmin = (event) => {
      const tab = event.detail?.tab || 'admin-users';
      setActiveTab(tab);
    };

    const handleSwitchToTab = (event) => {
      const tab = event.detail?.tab || 'macro-dashboard';
      setActiveTab(tab);
    };

    window.addEventListener('switchToAdmin', handleSwitchToAdmin);
    window.addEventListener('switchToTab', handleSwitchToTab);
    return () => {
      window.removeEventListener('switchToAdmin', handleSwitchToAdmin);
      window.removeEventListener('switchToTab', handleSwitchToTab);
    };
  }, []);

  // activeTab 변경 시 Header에 알림
  useEffect(() => {
    const event = new CustomEvent('dashboardTabChange', { detail: { tab: activeTab } });
    window.dispatchEvent(event);
  }, [activeTab]);

  return (
    <div className="dashboard-layout">
      <Header />
      <div className="main-content">
        <div className="content-area">
          {/* Macro Quant Trading */}
          {activeTab === 'trading-macro' && (
            <TradingDashboard />
          )}

          {/* Crypto Auto Trading */}
          {activeTab === 'trading-crypto' && (
            <>
              <PlatformSelector
                activePlatform={activePlatform}
                setActivePlatform={setActivePlatform}
              />

              {/* Upbit 선택 시에만 Status, Position, Tools 표시 */}
              {activePlatform === 'upbit' && (
                <>
                  <UpbitAccountSummary platform={activePlatform} />

                </>
              )}

              {/* Binance 선택 시 (추후 구현) */}
              {activePlatform === 'binance' && (
                <div className="card">
                  <h2>Binance Auto Trading</h2>
                  <p className="info-note">Binance 자동매매 기능은 추후 구현 예정입니다.</p>
                </div>
              )}
            </>
          )}

          {activeTab === 'macro-dashboard' && (
            <MacroDashboard />
          )}

          {activeTab === 'admin-users' && (
            <UserManagementPage />
          )}

          {activeTab === 'admin-logs' && (
            <LogManagementPage />
          )}

          {activeTab === 'admin-llm-monitoring' && (
            <LLMMonitoringPage />
          )}

          {activeTab === 'admin-portfolio-management' && (
            <PortfolioManagementPage />
          )}

          {activeTab === 'admin-files' && (
            <FileUploadPage />
          )}

          {activeTab === 'profile' && (
            <ProfilePage />
          )}

        </div>
      </div>
    </div>
  );
};

export default Dashboard;
