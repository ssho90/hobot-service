import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './LoginPage.css';

const LoginPage = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await login(username, password);
      
      if (result.success) {
        navigate('/dashboard');
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError('로그인 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-form">
        <h2>Stockoverflow</h2>
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
          
          <button 
            type="submit" 
            className="btn" 
            style={{ width: '100%' }}
            disabled={loading}
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>
        
        <div style={{ marginTop: '24px', textAlign: 'center' }}>
          <div style={{ marginBottom: '16px', color: '#6b7280', fontSize: '14px' }}>
            계정이 없으신가요?
          </div>
          <Link to="/register">
            <button 
              type="button"
              className="btn btn-secondary"
              style={{ 
                width: '100%',
                backgroundColor: '#f3f4f6',
                color: '#1f2937',
                border: '1px solid #e5e7eb'
              }}
            >
              회원가입
            </button>
          </Link>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
