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
  const [mfaStatus, setMfaStatus] = useState({ mfa_enabled: false, backup_codes_count: 0 });
  const [mfaSetup, setMfaSetup] = useState({ secret: '', qr_code: '', showQR: false });
  const [mfaVerificationCode, setMfaVerificationCode] = useState('');
  const [mfaBackupCodes, setMfaBackupCodes] = useState([]);
  const [showBackupCodes, setShowBackupCodes] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [mfaLoading, setMfaLoading] = useState(false);

  useEffect(() => {
    fetchCredentials();
    fetchMfaStatus();
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

  const fetchMfaStatus = async () => {
    try {
      const headers = getAuthHeaders();
      const response = await fetch('/api/user/mfa/status', {
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setMfaStatus(data.data || { mfa_enabled: false, backup_codes_count: 0 });
      }
    } catch (err) {
      console.error('Error fetching MFA status:', err);
    }
  };

  const handleMfaSetup = async () => {
    try {
      setMfaLoading(true);
      setError('');
      const headers = getAuthHeaders();
      const response = await fetch('/api/user/mfa/setup', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setMfaSetup({
          secret: data.data.secret,
          qr_code: data.data.qr_code,
          showQR: true
        });
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'MFA 설정을 시작하는데 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
      console.error('Error setting up MFA:', err);
    } finally {
      setMfaLoading(false);
    }
  };

  const handleMfaVerifySetup = async (e) => {
    e.preventDefault();
    try {
      setMfaLoading(true);
      setError('');
      const headers = getAuthHeaders();
      const response = await fetch('/api/user/mfa/verify-setup', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          secret: mfaSetup.secret,
          code: mfaVerificationCode
        })
      });

      if (response.ok) {
        const data = await response.json();
        setMfaBackupCodes(data.data.backup_codes || []);
        setShowBackupCodes(true);
        setMfaSetup({ secret: '', qr_code: '', showQR: false });
        setMfaVerificationCode('');
        await fetchMfaStatus();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'MFA 코드 검증에 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
      console.error('Error verifying MFA setup:', err);
    } finally {
      setMfaLoading(false);
    }
  };

  const handleMfaDisable = async (e) => {
    e.preventDefault();
    if (!window.confirm('MFA를 비활성화하시겠습니까? 계정 보안이 약화됩니다.')) {
      return;
    }

    try {
      setMfaLoading(true);
      setError('');
      const headers = getAuthHeaders();
      const response = await fetch('/api/user/mfa/disable', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          password: disablePassword
        })
      });

      if (response.ok) {
        setSuccess('MFA가 비활성화되었습니다.');
        setDisablePassword('');
        setMfaStatus({ mfa_enabled: false, backup_codes_count: 0 });
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'MFA 비활성화에 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
      console.error('Error disabling MFA:', err);
    } finally {
      setMfaLoading(false);
    }
  };

  const handleRegenerateBackupCodes = async (e) => {
    e.preventDefault();
    if (!window.confirm('백업 코드를 재생성하시겠습니까? 기존 백업 코드는 더 이상 사용할 수 없습니다.')) {
      return;
    }

    try {
      setMfaLoading(true);
      setError('');
      const headers = getAuthHeaders();
      const response = await fetch('/api/user/mfa/regenerate-backup-codes', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          password: disablePassword
        })
      });

      if (response.ok) {
        const data = await response.json();
        setMfaBackupCodes(data.data.backup_codes || []);
        setShowBackupCodes(true);
        setDisablePassword('');
        await fetchMfaStatus();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || '백업 코드 재생성에 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
      console.error('Error regenerating backup codes:', err);
    } finally {
      setMfaLoading(false);
    }
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

      <div className="profile-section">
        <h2>2단계 인증 (MFA)</h2>
        
        {mfaStatus.mfa_enabled ? (
          <div>
            <div className="credentials-status">
              <span className="status-badge status-active">MFA가 활성화되어 있습니다</span>
              <p className="status-note">
                남은 백업 코드: {mfaStatus.backup_codes_count}개
              </p>
            </div>

            {showBackupCodes && mfaBackupCodes.length > 0 && (
              <div className="backup-codes-section">
                <h3>백업 코드</h3>
                <p className="backup-codes-warning">
                  ⚠️ 이 코드들은 한 번만 표시됩니다. 안전한 곳에 저장하세요.
                </p>
                <div className="backup-codes-list">
                  {mfaBackupCodes.map((code, index) => (
                    <div key={index} className="backup-code-item">{code}</div>
                  ))}
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowBackupCodes(false)}
                >
                  닫기
                </button>
              </div>
            )}

            <div className="mfa-actions">
              <form onSubmit={handleRegenerateBackupCodes} className="mfa-form">
                <h3>백업 코드 재생성</h3>
                <div className="form-group">
                  <label htmlFor="disable-password">비밀번호 확인 *</label>
                  <input
                    type="password"
                    id="disable-password"
                    value={disablePassword}
                    onChange={(e) => setDisablePassword(e.target.value)}
                    required
                    placeholder="비밀번호를 입력하세요"
                  />
                </div>
                <button
                  type="submit"
                  className="btn btn-secondary"
                  disabled={mfaLoading}
                >
                  {mfaLoading ? '처리 중...' : '백업 코드 재생성'}
                </button>
              </form>

              <form onSubmit={handleMfaDisable} className="mfa-form">
                <h3>MFA 비활성화</h3>
                <div className="form-group">
                  <label htmlFor="disable-password-2">비밀번호 확인 *</label>
                  <input
                    type="password"
                    id="disable-password-2"
                    value={disablePassword}
                    onChange={(e) => setDisablePassword(e.target.value)}
                    required
                    placeholder="비밀번호를 입력하세요"
                  />
                </div>
                <button
                  type="submit"
                  className="btn btn-danger"
                  disabled={mfaLoading}
                >
                  {mfaLoading ? '처리 중...' : 'MFA 비활성화'}
                </button>
              </form>
            </div>
          </div>
        ) : (
          <div>
            {!mfaSetup.showQR ? (
              <div>
                <p>2단계 인증을 활성화하여 계정 보안을 강화하세요.</p>
                <button
                  className="btn btn-primary"
                  onClick={handleMfaSetup}
                  disabled={mfaLoading}
                >
                  {mfaLoading ? '설정 중...' : 'MFA 활성화'}
                </button>
              </div>
            ) : (
              <div className="mfa-setup-section">
                <h3>MFA 설정</h3>
                <ol className="mfa-setup-steps">
                  <li>Google Authenticator 또는 Microsoft Authenticator 앱을 설치하세요.</li>
                  <li>아래 QR 코드를 스캔하세요.</li>
                  <li>앱에 표시된 6자리 코드를 입력하세요.</li>
                </ol>
                
                <div className="qr-code-container">
                  <img src={mfaSetup.qr_code} alt="MFA QR Code" />
                </div>

                <form onSubmit={handleMfaVerifySetup} className="mfa-verify-form">
                  <div className="form-group">
                    <label htmlFor="mfa-verification-code">인증 코드 (6자리) *</label>
                    <input
                      type="text"
                      id="mfa-verification-code"
                      value={mfaVerificationCode}
                      onChange={(e) => setMfaVerificationCode(e.target.value)}
                      required
                      maxLength={6}
                      placeholder="000000"
                      pattern="[0-9]{6}"
                    />
                  </div>
                  <div className="form-actions">
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={mfaLoading || mfaVerificationCode.length !== 6}
                    >
                      {mfaLoading ? '검증 중...' : '설정 완료'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setMfaSetup({ secret: '', qr_code: '', showQR: false })}
                      disabled={mfaLoading}
                    >
                      취소
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        )}

        <div className="credentials-info">
          <h3>MFA 안내</h3>
          <ul>
            <li>2단계 인증을 활성화하면 로그인 시 추가 인증 코드가 필요합니다.</li>
            <li>Google Authenticator, Microsoft Authenticator 등 TOTP 앱을 사용할 수 있습니다.</li>
            <li>백업 코드는 앱에 접근할 수 없을 때 사용할 수 있는 일회용 코드입니다.</li>
            <li>백업 코드는 안전한 곳에 보관하세요.</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;


