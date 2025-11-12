import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import './LoginModal.css';

const LoginModal = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState('login'); // 'login' or 'register'
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  // Login state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  
  // Register state
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [registerError, setRegisterError] = useState('');
  const [registerSuccess, setRegisterSuccess] = useState('');
  const [registerLoading, setRegisterLoading] = useState(false);
  
  const { login, register } = useAuth();

  if (!isOpen) return null;

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    setLoginLoading(true);

    try {
      const result = await login(username, password);
      
      if (result.success) {
        onClose();
        // 페이지 새로고침하여 로그인 상태 반영
        window.location.reload();
      } else {
        setLoginError(result.error || '로그인에 실패했습니다.');
      }
    } catch (err) {
      setLoginError('로그인 중 오류가 발생했습니다.');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setRegisterError('');
    setRegisterSuccess('');

    // 유효성 검사
    if (regPassword !== confirmPassword) {
      setRegisterError('비밀번호가 일치하지 않습니다.');
      return;
    }

    if (regPassword.length < 6) {
      setRegisterError('비밀번호는 최소 6자 이상이어야 합니다.');
      return;
    }

    setRegisterLoading(true);

    try {
      const result = await register(regUsername, null, regPassword);
      
      if (result.success) {
        setRegisterSuccess('회원가입이 완료되었습니다. 로그인해주세요.');
        // 회원가입 성공 후 자동 로그인
        setTimeout(async () => {
          const loginResult = await login(regUsername, regPassword);
          if (loginResult.success) {
            onClose();
            window.location.reload();
          } else {
            setActiveTab('login');
            setUsername(regUsername);
          }
        }, 1000);
      } else {
        setRegisterError(result.error || '회원가입에 실패했습니다.');
      }
    } catch (err) {
      setRegisterError('회원가입 중 오류가 발생했습니다.');
    } finally {
      setRegisterLoading(false);
    }
  };

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="login-modal-overlay" onClick={handleOverlayClick}>
      <div className="login-modal">
        <button className="login-modal-close" onClick={onClose}>
          ✕
        </button>
        
        <div className="login-modal-logo">
          <span className="logo-icon">🤖</span>
          <span className="logo-text">Hobot</span>
        </div>

        {activeTab === 'login' ? (
          <form onSubmit={handleLogin} className="login-modal-form">
            <div className="form-group">
              <input
                type="text"
                placeholder="사용자명"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="form-input"
              />
            </div>
            
            <div className="form-group password-group">
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="비밀번호"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="form-input"
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
              >
                {showPassword ? '👁️' : '👁️‍🗨️'}
              </button>
            </div>
            
            {loginError && (
              <div className="error-message">
                {loginError}
              </div>
            )}
            
            <button 
              type="submit" 
              className="login-modal-btn"
              disabled={loginLoading}
            >
              {loginLoading ? '로그인 중...' : '로그인'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister} className="login-modal-form">
            <div className="form-group">
              <input
                type="text"
                placeholder="사용자명"
                value={regUsername}
                onChange={(e) => setRegUsername(e.target.value)}
                required
                minLength={3}
                className="form-input"
              />
            </div>
            
            <div className="form-group password-group">
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="비밀번호"
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
                required
                minLength={6}
                className="form-input"
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
              >
                {showPassword ? '👁️' : '👁️‍🗨️'}
              </button>
            </div>
            
            <div className="form-group password-group">
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                placeholder="비밀번호 확인"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={6}
                className="form-input"
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                aria-label={showConfirmPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
              >
                {showConfirmPassword ? '👁️' : '👁️‍🗨️'}
              </button>
            </div>
            
            {registerError && (
              <div className="error-message">
                {registerError}
              </div>
            )}
            
            {registerSuccess && (
              <div className="success-message">
                {registerSuccess}
              </div>
            )}
            
            <button 
              type="submit" 
              className="login-modal-btn"
              disabled={registerLoading}
            >
              {registerLoading ? '처리 중...' : '회원가입'}
            </button>
          </form>
        )}

        <div className="login-modal-links">
          {activeTab === 'login' ? (
            <>
              <span>비밀번호 찾기</span>
              <span className="link-divider">|</span>
              <span 
                className="link-clickable" 
                onClick={() => {
                  setActiveTab('register');
                  setLoginError('');
                }}
              >
                회원가입
              </span>
              <span className="link-divider">|</span>
              <span>아이디 찾기</span>
            </>
          ) : (
            <span 
              className="link-clickable" 
              onClick={() => {
                setActiveTab('login');
                setRegisterError('');
                setRegisterSuccess('');
              }}
            >
              로그인으로 돌아가기
            </span>
          )}
        </div>

        <div className="login-modal-social">
          <div className="social-label">간편 로그인</div>
          <div className="social-icons">
            <button className="social-icon" type="button" title="카카오">
              💬
            </button>
            <button className="social-icon" type="button" title="구글">
              G
            </button>
            <button className="social-icon" type="button" title="깃허브">
              🐙
            </button>
            <button className="social-icon" type="button" title="애플">
              🍎
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginModal;

