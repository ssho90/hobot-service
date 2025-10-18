import React, { useState, useEffect } from 'react';

const HobotStatus = () => {
  const [status, setStatus] = useState('Loading...');
  const [isHealthy, setIsHealthy] = useState(false);

  const checkHealth = async () => {
    try {
      const response = await fetch('/api/health');
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
  }, []);

  return (
    <div className="card">
      <h3>Hobot Status</h3>
      <p className={isHealthy ? 'status-healthy' : 'status-error'}>
        {status}
      </p>
    </div>
  );
};

export default HobotStatus;
