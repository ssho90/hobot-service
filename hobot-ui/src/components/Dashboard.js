import React, { useState, useEffect } from 'react';
import HobotStatus from './HobotStatus';
import CurrentPosition from './CurrentPosition';
import Tools from './Tools';
import News from './News';
import Sidebar from './Sidebar';
import Header from './Header';
import PlatformSelector from './PlatformSelector';
import './Dashboard.css';

const Dashboard = () => {
  const [currentStrategy, setCurrentStrategy] = useState('');
  const [activeTab, setActiveTab] = useState('trading');
  const [activePlatform, setActivePlatform] = useState('upbit');

  // CurrentStrategy.json 파일을 읽어서 상태 업데이트
  const fetchCurrentStrategy = async (platform) => {
    try {
      const response = await fetch(`/api/current-strategy/${platform}`);
      if (response.ok) {
        const data = await response.text();
        setCurrentStrategy(data.trim());
      } else {
        // JSON 형식으로 재시도
        const jsonResponse = await fetch(`/api/current-strategy?platform=${platform}`);
        if (jsonResponse.ok) {
          const jsonData = await jsonResponse.json();
          setCurrentStrategy(jsonData.strategy);
        }
      }
    } catch (error) {
      console.error('Failed to fetch current strategy:', error);
    }
  };

  useEffect(() => {
    fetchCurrentStrategy(activePlatform);
    // 1분마다 상태 업데이트
    const interval = setInterval(() => fetchCurrentStrategy(activePlatform), 60000);
    return () => clearInterval(interval);
  }, [activePlatform]);

  const handleStrategyChange = (newStrategy) => {
    setCurrentStrategy(newStrategy);
    // API 호출도 업데이트
    fetchCurrentStrategy(activePlatform);
  };

  return (
    <div className="dashboard-layout">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <Header />
      <div className="main-content">
        <div className="dashboard-header">
          <h1>Welcome back</h1>
          <p className="dashboard-subtitle">Monitor your trading and stay updated with the latest news</p>
        </div>

        <div className="content-area">
          {activeTab === 'trading' && (
            <>
              <PlatformSelector 
                activePlatform={activePlatform} 
                setActivePlatform={setActivePlatform}
              />
              
              <div className="status-section">
                <div className="status-item">
                  <HobotStatus platform={activePlatform} />
                </div>
                <div className="status-item">
                  <CurrentPosition 
                    platform={activePlatform}
                    currentStrategy={currentStrategy} 
                  />
                </div>
              </div>

              <div className="tools-section">
                <Tools 
                  platform={activePlatform}
                  currentStrategy={currentStrategy} 
                  onStrategyChange={handleStrategyChange}
                />
              </div>
            </>
          )}

          {activeTab === 'news' && (
            <News />
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
