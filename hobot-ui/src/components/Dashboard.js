import React, { useState, useEffect } from 'react';
import HobotStatus from './HobotStatus';
import CurrentPosition from './CurrentPosition';
import Tools from './Tools';
import News from './News';
import './Dashboard.css';

const Dashboard = () => {
  const [currentStrategy, setCurrentStrategy] = useState('');
  const [activeTab, setActiveTab] = useState('trading');

  // CurrentStrategy.txt 파일을 읽어서 상태 업데이트
  const fetchCurrentStrategy = async () => {
    try {
      const response = await fetch('/api/current-strategy');
      if (response.ok) {
        const data = await response.text();
        setCurrentStrategy(data.trim());
      } else {
        console.error('Failed to fetch current strategy:', response.status);
      }
    } catch (error) {
      console.error('Failed to fetch current strategy:', error);
    }
  };

  useEffect(() => {
    fetchCurrentStrategy();
    // 1분마다 상태 업데이트
    const interval = setInterval(fetchCurrentStrategy, 60000);
    return () => clearInterval(interval);
  }, []);

  const handleStrategyChange = (newStrategy) => {
    setCurrentStrategy(newStrategy);
  };

  return (
    <div className="container">
      <div className="dashboard-header">
        <h1>Hobot Panel</h1>
      </div>

      <div className="tabs">
        <button 
          className={`tab ${activeTab === 'trading' ? 'active' : ''}`}
          onClick={() => setActiveTab('trading')}
        >
          Trading
        </button>
        <button 
          className={`tab ${activeTab === 'news' ? 'active' : ''}`}
          onClick={() => setActiveTab('news')}
        >
          News
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'trading' && (
          <>
            <div className="status-section">
              <div className="status-item">
                <HobotStatus />
              </div>
              <div className="status-item">
                <CurrentPosition currentStrategy={currentStrategy} />
              </div>
            </div>

            <div className="tools-section">
              <Tools 
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
  );
};

export default Dashboard;
