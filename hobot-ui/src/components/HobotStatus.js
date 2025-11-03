import React, { useState, useEffect } from 'react';

const HobotStatus = ({ platform = 'upbit' }) => {
  const [status, setStatus] = useState('Loading...');
  const [isHealthy, setIsHealthy] = useState(false);

  const platformNames = {
    upbit: 'Upbit',
    binance: 'Binance',
    kis: '한국투자증권'
  };

  const checkHealth = async () => {
    try {
      // 플랫폼별 헬스체크 API 호출
      let healthEndpoint = '/api/health';
      
      if (platform === 'kis') {
        healthEndpoint = '/api/kis/health';
      } else if (platform === 'binance') {
        // Binance 헬스체크는 추후 구현
        healthEndpoint = '/api/binance/health';
      }
      
      const response = await fetch(healthEndpoint);
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setStatus('Healthy');
          setIsHealthy(true);
        } else {
          setStatus('Error');
          setIsHealthy(false);
        }
      } else {
        setStatus('Error');
        setIsHealthy(false);
      }
    } catch (error) {
      console.error('Health check failed:', error);
      setStatus('Error');
      setIsHealthy(false);
    }
  };

  useEffect(() => {
    checkHealth();
    // 30초마다 헬스체크 실행
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [platform]);

  return (
    <div className="card">
      <h3>{platformNames[platform]} Status</h3>
      <p className={isHealthy ? 'status-healthy' : 'status-error'}>
        {status}
      </p>
    </div>
  );
};

export default HobotStatus;
