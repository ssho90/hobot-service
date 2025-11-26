import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  }, []);

  const verifyToken = useCallback(async (tokenToVerify) => {
    try {
      const response = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${tokenToVerify}`
        }
      });
      
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        setToken(tokenToVerify);
      } else {
        // 토큰이 유효하지 않음
        logout();
      }
    } catch (error) {
      console.error('Token verification failed:', error);
      logout();
    } finally {
      setLoading(false);
    }
  }, [logout]);

  useEffect(() => {
    // localStorage에서 토큰과 사용자 정보 복원
    const savedToken = localStorage.getItem('token');
    const savedUser = localStorage.getItem('user');
    
    if (savedToken && savedUser) {
      setToken(savedToken);
      setUser(JSON.parse(savedUser));
      // 토큰 유효성 확인
      verifyToken(savedToken);
    } else {
      setLoading(false);
    }
  }, [verifyToken]);

  const login = async (username, password) => {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorData;
        try {
          errorData = JSON.parse(errorText);
        } catch {
          errorData = { detail: `서버 오류 (${response.status})` };
        }
        return { success: false, error: errorData.detail || '로그인에 실패했습니다.' };
      }

      const data = await response.json();

      if (response.ok) {
        setToken(data.token);
        setUser(data.user);
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        return { success: true };
      } else {
        return { success: false, error: data.detail || '로그인에 실패했습니다.' };
      }
    } catch (error) {
      // 네트워크 에러인 경우
      if (error.name === 'TypeError' && error.message.includes('fetch')) {
        return { success: false, error: '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요.' };
      }
      console.error('Login error:', error);
      return { success: false, error: '서버 연결에 실패했습니다.' };
    }
  };

  const register = async (username, email, password) => {
    try {
      const requestBody = { username, password };
      if (email) {
        requestBody.email = email;
      }
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorData;
        try {
          errorData = JSON.parse(errorText);
        } catch {
          errorData = { detail: `서버 오류 (${response.status})` };
        }
        return { success: false, error: errorData.detail || '회원가입에 실패했습니다.' };
      }

      const data = await response.json();

      if (response.ok) {
        return { success: true, message: '회원가입이 완료되었습니다.' };
      } else {
        return { success: false, error: data.detail || '회원가입에 실패했습니다.' };
      }
    } catch (error) {
      // 네트워크 에러인 경우
      if (error.name === 'TypeError' && error.message.includes('fetch')) {
        return { success: false, error: '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요.' };
      }
      console.error('Register error:', error);
      return { success: false, error: '서버 연결에 실패했습니다.' };
    }
  };

  const isAdmin = () => {
    return user && user.role === 'admin';
  };

  const isSystemAdmin = () => {
    // 시스템 어드민: admin role을 가진 사용자
    if (!user) return false;
    return user.role === 'admin';
  };

  const getAuthHeaders = () => {
    if (!token) return {};
    return {
      'Authorization': `Bearer ${token}`
    };
  };

  const value = {
    user,
    token,
    loading,
    login,
    register,
    logout,
    isAdmin,
    isSystemAdmin,
    getAuthHeaders
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

