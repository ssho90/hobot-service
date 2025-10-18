import React, { useState } from 'react';

const LoginPage = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    
    // 간단한 인증 로직 (실제 환경에서는 서버 인증을 사용해야 함)
    if (username === 'admin' && password === 'admin') {
      onLogin();
    } else {
      setError('잘못된 사용자명 또는 비밀번호입니다.');
    }
  };

  return (
    <div className="login-container">
      <div className="login-form">
        <h2>Hobot Dashboard</h2>
        <p>로그인하여 계속하세요</p>
        
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">사용자명</label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          
          <div className="form-group">
            <label htmlFor="password">비밀번호</label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          
          {error && (
            <div style={{ color: 'red', marginBottom: '20px' }}>
              {error}
            </div>
          )}
          
          <button type="submit" className="btn" style={{ width: '100%' }}>
            로그인
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
