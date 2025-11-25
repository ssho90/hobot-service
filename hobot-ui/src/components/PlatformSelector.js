import React from 'react';
import './PlatformSelector.css';

const PlatformSelector = ({ activePlatform, setActivePlatform }) => {
  const platforms = [
    { id: 'upbit', label: 'Upbit', icon: '💰', color: '#3b82f6' },
    { id: 'binance', label: 'Binance', icon: '🌐', color: '#f59e0b', disabled: true },
  ];

  return (
    <div className="platform-selector">
      <div className="platform-selector-header">
        <h2>Trading Platforms</h2>
        <p className="platform-subtitle">Select a platform to monitor and control</p>
      </div>
      <div className="platform-cards">
        {platforms.map((platform) => (
          <div
            key={platform.id}
            className={`platform-card ${activePlatform === platform.id ? 'active' : ''} ${platform.disabled ? 'disabled' : ''}`}
            onClick={() => !platform.disabled && setActivePlatform(platform.id)}
          >
            <div className="platform-icon" style={{ color: platform.color }}>
              {platform.icon}
            </div>
            <div className="platform-info">
              <h3>{platform.label}</h3>
              {platform.disabled && (
                <span className="platform-badge">Coming Soon</span>
              )}
            </div>
            {activePlatform === platform.id && (
              <div className="platform-active-indicator">
                <span>✓</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default PlatformSelector;

