import React from 'react';

const CurrentPosition = ({ platform = 'upbit', currentStrategy }) => {
  const platformNames = {
    upbit: 'Upbit',
    binance: 'Binance',
    kis: '한국투자증권'
  };

  const getPositionText = (strategy) => {
    switch (strategy) {
      case 'STRATEGY_NULL':
        return 'No Position';
      case 'STRATEGY_PAUSE':
        return 'Paused';
      case 'STRATEGY_EMA':
        return 'EMA Strategy';
      default:
        return strategy || 'Unknown';
    }
  };

  return (
    <div className="card">
      <h3>{platformNames[platform]} Current Position</h3>
      <p>{getPositionText(currentStrategy)}</p>
    </div>
  );
};

export default CurrentPosition;
