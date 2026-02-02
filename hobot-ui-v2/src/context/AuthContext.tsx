import React, { createContext, useState, useContext, useEffect, useCallback, useMemo, type ReactNode } from 'react';
import type { User, AuthContextType, LoginResult, RegisterResult } from '../types';

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = (): AuthContextType => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
};

interface AuthProviderProps {
    children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    const logout = useCallback(() => {
        setToken(null);
        setUser(null);
        localStorage.removeItem('token');
        localStorage.removeItem('user');
    }, []);

    const verifyToken = useCallback(async (tokenToVerify: string) => {
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
        const savedToken = localStorage.getItem('token');
        const savedUser = localStorage.getItem('user');

        if (savedToken && savedUser) {
            setToken(savedToken);
            setUser(JSON.parse(savedUser));
            verifyToken(savedToken);
        } else {
            setLoading(false);
        }
    }, [verifyToken]);

    const login = async (username: string, password: string, mfaCode: string | null = null): Promise<LoginResult> => {
        const url = '/api/auth/login';

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password, mfa_code: mfaCode })
            });

            if (!response.ok) {
                const errorText = await response.text();
                let errorData;
                try {
                    errorData = JSON.parse(errorText);
                } catch {
                    errorData = { detail: `서버 오류 (${response.status} ${response.statusText})` };
                }
                return { success: false, error: errorData.detail || '로그인에 실패했습니다.' };
            }

            const data = await response.json();

            if (data.status === 'mfa_required') {
                return { success: false, mfa_required: true, message: data.message || 'MFA 코드가 필요합니다.' };
            }

            if (response.ok && data.status === 'success') {
                setToken(data.token);
                setUser(data.user);
                localStorage.setItem('token', data.token);
                localStorage.setItem('user', JSON.stringify(data.user));
                return { success: true };
            } else {
                return { success: false, error: data.detail || '로그인에 실패했습니다.' };
            }
        } catch (error) {
            if (error instanceof TypeError && error.message.includes('fetch')) {
                return { success: false, error: '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요.' };
            }
            return { success: false, error: '서버 연결에 실패했습니다.' };
        }
    };

    const register = async (username: string, password: string): Promise<RegisterResult> => {
        try {
            const response = await fetch('/api/auth/register', {
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
                return { success: false, error: errorData.detail || '회원가입에 실패했습니다.' };
            }

            return { success: true, message: '회원가입이 완료되었습니다.' };
        } catch (error) {
            if (error instanceof TypeError && error.message.includes('fetch')) {
                return { success: false, error: '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요.' };
            }
            console.error('Register error:', error);
            return { success: false, error: '서버 연결에 실패했습니다.' };
        }
    };

    const isAdmin = useCallback(() => {
        return user?.role === 'admin';
    }, [user]);

    const isSystemAdmin = useCallback(() => {
        return user?.role === 'admin';
    }, [user]);

    const getAuthHeaders = useCallback((): Record<string, string> => {
        if (!token) return {};
        return {
            'Authorization': `Bearer ${token}`
        } as Record<string, string>;
    }, [token]);

    const isAuthenticated = !!user && !!token;

    const value = useMemo(() => ({
        user,
        token,
        loading,
        isAuthenticated,
        login,
        register,
        logout,
        isAdmin,
        isSystemAdmin,
        getAuthHeaders
    }), [user, token, loading, isAuthenticated, logout, isAdmin, isSystemAdmin, getAuthHeaders]);

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
