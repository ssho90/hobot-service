import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import './ProfilePage.css';

const ProfilePage = () => {
  const { user, getAuthHeaders } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [credentials, setCredentials] = useState({
    kis_id: '',
    account_no: '',
    app_key: '',
    app_secret: ''
  });
  const [hasCredentials, setHasCredentials] = useState(false);

  useEffect(() => {
    fetchCredentials();
  }, []);

  const fetchCredentials = async () => {
    try {
      setLoading(true);
      setError('');
      const headers = getAuthHeaders();
      const response = await fetch('/api/user/kis-credentials', {
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.has_credentials && data.data) {
          setCredentials({
            kis_id: data.data.kis_id || '',
            account_no: data.data.account_no || '',
            app_key: data.data.app_key || '',
            app_secret: data.data.app_secret || ''
          });
          setHasCredentials(true);
        } else {
          setHasCredentials(false);
        }
      } else {
        const errorData = await response.json();
        setError(errorData.detail || '인증 정보를 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
      console.error('Error fetching credentials:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    try {
      const headers = getAuthHeaders();
      const response = await fetch('/api/user/kis-credentials', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(credentials)
      });

      if (response.ok) {
        const data = await response.json();
        setSuccess(data.message || '인증 정보가 저장되었습니다.');
        setHasCredentials(true);
        // 비밀번호 필드는 보안을 위해 초기화
        setCredentials(prev => ({
          ...prev,
          app_key: '',
          app_secret: ''
        }));
      } else {
        const errorData = await response.json();
        setError(errorData.detail || '인증 정보 저장에 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
      console.error('Error saving credentials:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setCredentials(prev => ({
      ...prev,
      [name]: value
    }));
  };

  if (loading) {
    return <div className="profile-page-loading">로딩 중...</div>;
  }

  return (
    <div className="profile-page">
      <h1>프로필 설정</h1>
      
      <div className="profile-section">
        <h2>사용자 정보</h2>
        <div className="user-info">
          <div className="info-item">
            <span className="info-label">사용자명:</span>
            <span className="info-value">{user?.username}</span>
          </div>
          <div className="info-item">
            <span className="info-label">이메일:</span>
            <span className="info-value">{user?.email || '-'}</span>
          </div>
          <div className="info-item">
            <span className="info-label">권한:</span>
            <span className="info-value">{user?.role === 'admin' ? '관리자' : '사용자'}</span>
          </div>
        </div>
      </div>

      <div className="profile-section">
        <h2>한국투자증권 API 인증 정보</h2>
        {hasCredentials && (
          <div className="credentials-status">
            <span className="status-badge status-active">인증 정보가 등록되어 있습니다</span>
            <p className="status-note">
              보안을 위해 기존 인증 정보는 표시되지 않습니다. 
              수정하려면 아래 필드에 새로운 값을 입력하세요.
            </p>
          </div>
        )}
        
        {error && (
          <div className="error-message">{error}</div>
        )}
        
        {success && (
          <div className="success-message">{success}</div>
        )}

        <form onSubmit={handleSubmit} className="credentials-form">
          <div className="form-group">
            <label htmlFor="kis_id">한국투자증권 ID *</label>
            <input
              type="text"
              id="kis_id"
              name="kis_id"
              value={credentials.kis_id}
              onChange={handleChange}
              required
              placeholder="한국투자증권 ID를 입력하세요"
            />
          </div>

          <div className="form-group">
            <label htmlFor="account_no">계좌번호 *</label>
            <input
              type="text"
              id="account_no"
              name="account_no"
              value={credentials.account_no}
              onChange={handleChange}
              required
              placeholder="계좌번호를 입력하세요 (예: 12345678-01)"
            />
          </div>

          <div className="form-group">
            <label htmlFor="app_key">App Key *</label>
            <input
              type="password"
              id="app_key"
              name="app_key"
              value={credentials.app_key}
              onChange={handleChange}
              required
              placeholder={hasCredentials ? "새로운 App Key를 입력하세요" : "App Key를 입력하세요"}
            />
          </div>

          <div className="form-group">
            <label htmlFor="app_secret">App Secret *</label>
            <input
              type="password"
              id="app_secret"
              name="app_secret"
              value={credentials.app_secret}
              onChange={handleChange}
              required
              placeholder={hasCredentials ? "새로운 App Secret을 입력하세요" : "App Secret을 입력하세요"}
            />
          </div>

          <div className="form-actions">
            <button 
              type="submit" 
              className="btn btn-primary"
              disabled={saving}
            >
              {saving ? '저장 중...' : hasCredentials ? '인증 정보 업데이트' : '인증 정보 저장'}
            </button>
          </div>
        </form>

        <div className="credentials-info">
          <h3>인증 정보 안내</h3>
          <ul>
            <li>한국투자증권 Open API에서 발급받은 인증 정보를 입력하세요.</li>
            <li>모든 인증 정보는 암호화되어 안전하게 저장됩니다.</li>
            <li>인증 정보는 본인만 확인할 수 있으며, 다른 사용자에게 공유되지 않습니다.</li>
            <li>Macro-trading 화면에서 본인의 계좌 정보를 확인할 수 있습니다.</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;

