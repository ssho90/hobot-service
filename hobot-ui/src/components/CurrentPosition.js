import React from 'react';

const CurrentPosition = ({ currentStrategy }) => {
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
      <h3>Current Position</h3>
      <p>{getPositionText(currentStrategy)}</p>
    </div>
  );
};

export default CurrentPosition;
