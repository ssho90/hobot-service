import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import './AdminPage.css';

const UserManagementPage = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState({ role: '' });
  const { getAuthHeaders } = useAuth();

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/admin/users', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setUsers(data.users);
      } else {
        setError('사용자 목록을 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleEdit = (user) => {
    setEditingUser(user.id);
    setEditForm({
      role: user.role
    });
  };

  const handleCancelEdit = () => {
    setEditingUser(null);
    setEditForm({ role: '' });
  };

  const handleSaveEdit = async (userId) => {
    try {
      const response = await fetch(`/api/admin/users/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify(editForm)
      });

      if (response.ok) {
        await fetchUsers();
        setEditingUser(null);
        setEditForm({ role: '' });
      } else {
        const data = await response.json();
        alert(data.detail || '사용자 정보 업데이트에 실패했습니다.');
      }
    } catch (err) {
      alert('서버 연결에 실패했습니다.');
    }
  };

  const handleDelete = async (userId) => {
    if (!window.confirm('정말 이 사용자를 삭제하시겠습니까?')) {
      return;
    }

    try {
      const response = await fetch(`/api/admin/users/${userId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        await fetchUsers();
      } else {
        const data = await response.json();
        alert(data.detail || '사용자 삭제에 실패했습니다.');
      }
    } catch (err) {
      alert('서버 연결에 실패했습니다.');
    }
  };

  if (loading) {
    return (
      <div className="admin-page">
        <div className="admin-header">
          <h1>사용자 관리</h1>
        </div>
        <div style={{ textAlign: 'center', padding: '40px' }}>로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h1>사용자 관리</h1>
        <p>시스템에 등록된 모든 사용자를 관리할 수 있습니다.</p>
      </div>

      {error && (
        <div className="error-message" style={{ color: 'red', marginBottom: '20px' }}>
          {error}
        </div>
      )}

      <div className="users-table-container">
        <table className="users-table">
          <thead>
            <tr>
              <th>사용자명 (ID)</th>
              <th>역할</th>
              <th>생성일</th>
              <th>작업</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.id}</td>
                <td>
                  {editingUser === user.id ? (
                    <select
                      value={editForm.role}
                      onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                      className="edit-input"
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  ) : (
                    <span className={`role-badge ${user.role}`}>
                      {user.role}
                    </span>
                  )}
                </td>
                <td>{new Date(user.created_at).toLocaleDateString('ko-KR')}</td>
                <td>
                  {editingUser === user.id ? (
                    <div className="action-buttons">
                      <button
                        className="btn-save"
                        onClick={() => handleSaveEdit(user.id)}
                      >
                        저장
                      </button>
                      <button
                        className="btn-cancel"
                        onClick={handleCancelEdit}
                      >
                        취소
                      </button>
                    </div>
                  ) : (
                    <div className="action-buttons">
                      <button
                        className="btn-edit"
                        onClick={() => handleEdit(user)}
                      >
                        수정
                      </button>
                      <button
                        className="btn-delete"
                        onClick={() => handleDelete(user.id)}
                      >
                        삭제
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default UserManagementPage;

