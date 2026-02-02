import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link } from 'react-router-dom';
import { X, AlertCircle } from 'lucide-react';

interface LoginModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose }) => {
    const { login } = useAuth();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        const result = await login(username, password);
        if (!result.success) {
            setError(result.error || '로그인에 실패했습니다.');
        } else {
            onClose(); // Close modal on success
            window.location.reload();
        }
        setLoading(false);
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
                onClick={onClose}
            />

            {/* Modal */}
            <div className="relative bg-[#09090b] border border-zinc-800 rounded-2xl p-8 w-full max-w-md shadow-2xl animate-in fade-in zoom-in-95 duration-200 mx-4">
                {/* Close Button */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-zinc-500 hover:text-white transition-colors"
                >
                    <X className="h-6 w-6" />
                </button>

                <h1 className="text-2xl font-bold text-white mb-2 text-center">로그인</h1>
                <p className="text-zinc-400 text-center mb-8 text-sm">StockOverflow에 오신 것을 환영합니다.</p>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm text-zinc-400 mb-2">아이디</label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full bg-black/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all outline-none placeholder:text-zinc-600"
                            placeholder="사용자 이름"
                            autoFocus
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-zinc-400 mb-2">비밀번호</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full bg-black/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all outline-none placeholder:text-zinc-600"
                            placeholder="비밀번호"
                        />
                    </div>

                    {error && (
                        <div className="flex items-center gap-2 text-rose-400 text-sm bg-rose-900/10 p-3 rounded-lg border border-rose-900/20">
                            <AlertCircle className="h-4 w-4 flex-shrink-0" />
                            <p>{error}</p>
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full mt-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3 px-4 rounded-xl transition-all disabled:opacity-50 flex items-center justify-center shadow-lg shadow-blue-900/20"
                    >
                        {loading ? (
                            <div className="h-5 w-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        ) : '로그인'}
                    </button>
                </form>

                <div className="mt-6 pt-6 border-t border-zinc-800/50 text-center">
                    <p className="text-zinc-500 text-sm">
                        계정이 없으신가요?{' '}
                        <Link
                            to="/register"
                            onClick={onClose}
                            className="text-blue-400 hover:text-blue-300 font-medium hover:underline transition-colors"
                        >
                            회원가입
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
};
