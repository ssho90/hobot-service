import React from 'react';

const Tools = ({ platform = 'upbit', currentStrategy, onStrategyChange }) => {
  const platformNames = {
    upbit: 'Upbit',
    binance: 'Binance',
    kis: '한국투자증권'
  };

  const handlePauseStart = async () => {
    try {
      const newStrategy = currentStrategy === 'STRATEGY_NULL' ? 'STRATEGY_PAUSE' : 'STRATEGY_NULL';
      
      // 플랫폼별 API 엔드포인트 (JSON 기반)
      const strategyEndpoint = `/api/current-strategy/${platform}`;
      
      const response = await fetch(strategyEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ strategy: newStrategy }),
      });

      if (response.ok) {
        onStrategyChange(newStrategy);
      } else {
        console.error('Failed to update strategy');
      }
    } catch (error) {
      console.error('Error updating strategy:', error);
    }
  };

  const handleChangePosition = () => {
    // Change Position 기능은 추후 구현
    alert(`${platformNames[platform]}의 Change Position 기능은 추후 구현 예정입니다.`);
  };

  const isPauseStartEnabled = currentStrategy === 'STRATEGY_NULL' || currentStrategy === 'STRATEGY_PAUSE';
  const buttonText = currentStrategy === 'STRATEGY_PAUSE' ? 'Start' : 'Pause';

  return (
    <div className="card">
      <h3>{platformNames[platform]} Tools</h3>
      <div className="tools-buttons">
        <button 
          className="btn" 
          onClick={handlePauseStart}
          disabled={!isPauseStartEnabled}
        >
          {buttonText}
        </button>
        <button 
          className="btn btn-secondary" 
          onClick={handleChangePosition}
        >
          Change Position
        </button>
      </div>
    </div>
  );
};

export default Tools;
