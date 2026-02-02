import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const RegisterPage: React.FC = () => {
  const { register } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('비밀번호가 일치하지 않습니다.');
      return;
    }
    setLoading(true);
    setError('');

    const result = await register(username, password);
    if (result.success) {
      setSuccess(result.message || '회원가입이 완료되었습니다.');
    } else {
      setError(result.error || '회원가입에 실패했습니다.');
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <div className="bg-zinc-900/40 rounded-2xl border border-zinc-800 p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold text-white mb-6 text-center">회원가입</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-zinc-400 mb-2">아이디</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              placeholder="사용자 이름"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-2">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              placeholder="비밀번호"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-2">비밀번호 확인</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              placeholder="비밀번호 확인"
            />
          </div>
          {error && <p className="text-rose-400 text-sm">{error}</p>}
          {success && <p className="text-emerald-400 text-sm">{success}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg transition-all disabled:opacity-50"
          >
            {loading ? '가입 중...' : '회원가입'}
          </button>
        </form>
        <p className="text-zinc-500 text-sm text-center mt-4">
          이미 계정이 있으신가요? <Link to="/login" className="text-blue-400 hover:underline">로그인</Link>
        </p>
      </div>
    </div>
  );
};

export default RegisterPage;
