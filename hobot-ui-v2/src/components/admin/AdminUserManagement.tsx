import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Users, Trash2, Edit2, Save, X, Shield, Loader2, AlertCircle, Crown, User } from 'lucide-react';

interface UserData {
    id: number;
    username: string;
    role: string;
    created_at: string;
    is_active: boolean;
}

export const AdminUserManagement: React.FC = () => {
    const { getAuthHeaders, user, isAuthenticated } = useAuth();
    const [users, setUsers] = useState<UserData[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editForm, setEditForm] = useState<{ role: string }>({ role: '' });
    const [saving, setSaving] = useState(false);

    const isAdmin = user?.role === 'admin';

    const fetchUsers = useCallback(async () => {
        if (!isAuthenticated || !isAdmin) {
            setLoading(false);
            return;
        }

        try {
            setError(null);
            const response = await fetch('/api/admin/users', {
                headers: getAuthHeaders()
            });

            if (response.ok) {
                const data = await response.json();
                setUsers(data.users || data);
            } else if (response.status === 403) {
                setError('관리자 권한이 필요합니다.');
            } else {
                setError('사용자 목록을 불러오는데 실패했습니다.');
            }
        } catch (err) {
            console.error('Error fetching users:', err);
            setError('서버 연결에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    }, [getAuthHeaders, isAuthenticated, isAdmin]);

    useEffect(() => {
        fetchUsers();
    }, [fetchUsers]);

    const handleEdit = (userData: UserData) => {
        setEditingId(userData.id);
        setEditForm({ role: userData.role });
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setEditForm({ role: '' });
    };

    const handleSave = async (userId: number) => {
        try {
            setSaving(true);
            const response = await fetch(`/api/admin/users/${userId}`, {
                method: 'PUT',
                headers: {
                    ...getAuthHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(editForm)
            });

            if (response.ok) {
                await fetchUsers();
                setEditingId(null);
            } else {
                const errorData = await response.json();
                setError(errorData.detail || '수정에 실패했습니다.');
            }
        } catch (err) {
            console.error('Error saving user:', err);
            setError('서버 연결에 실패했습니다.');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (userId: number, username: string) => {
        if (!window.confirm(`정말 "${username}" 사용자를 삭제하시겠습니까?`)) {
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
                const errorData = await response.json();
                setError(errorData.detail || '삭제에 실패했습니다.');
            }
        } catch (err) {
            console.error('Error deleting user:', err);
            setError('서버 연결에 실패했습니다.');
        }
    };

    if (!isAuthenticated) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center">
                <div className="text-center">
                    <AlertCircle className="h-12 w-12 text-yellow-400 mx-auto mb-4" />
                    <h2 className="text-xl font-bold text-white mb-2">로그인이 필요합니다</h2>
                    <p className="text-zinc-400">Admin 페이지에 접근하려면 먼저 로그인해주세요.</p>
                </div>
            </div>
        );
    }

    if (!isAdmin) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center">
                <div className="text-center">
                    <Shield className="h-12 w-12 text-red-400 mx-auto mb-4" />
                    <h2 className="text-xl font-bold text-white mb-2">접근 권한이 없습니다</h2>
                    <p className="text-zinc-400">관리자만 이 페이지에 접근할 수 있습니다.</p>
                </div>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center">
                <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8">
            <div className="max-w-6xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-zinc-900 flex items-center gap-3">
                        <Users className="h-8 w-8 text-blue-600" />
                        사용자 관리
                    </h1>
                    <p className="text-zinc-500 mt-1">사용자 권한 및 계정 관리</p>
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-xl flex items-center gap-3">
                        <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
                        <p className="text-red-300">{error}</p>
                        <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                )}

                <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm">
                    <div className="px-6 py-4 border-b border-zinc-200 flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-zinc-900 flex items-center gap-2">
                            <Users className="h-5 w-5 text-blue-600" />
                            User List
                        </h3>
                        <span className="text-sm text-zinc-500">{users.length} Users</span>
                    </div>

                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-slate-50">
                                <tr className="text-left text-xs text-zinc-500 uppercase tracking-wider">
                                    <th className="px-6 py-3">User</th>
                                    <th className="px-6 py-3">Role</th>
                                    <th className="px-6 py-3">Joined</th>
                                    <th className="px-6 py-3">Status</th>
                                    <th className="px-6 py-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-200">
                                {users.map((userData) => (
                                    <tr key={userData.id} className="hover:bg-slate-50 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className={`h-10 w-10 rounded-full flex items-center justify-center ${userData.role === 'admin' ? 'bg-amber-100' : 'bg-slate-100'}`}>
                                                    {userData.role === 'admin' ? (
                                                        <Crown className="h-5 w-5 text-amber-600" />
                                                    ) : (
                                                        <User className="h-5 w-5 text-zinc-500" />
                                                    )}
                                                </div>
                                                <div>
                                                    <p className="text-sm font-medium text-zinc-900">{userData.username}</p>
                                                    <p className="text-xs text-zinc-500">ID: {userData.id}</p>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            {editingId === userData.id ? (
                                                <select
                                                    value={editForm.role}
                                                    onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                                                    className="bg-white border border-zinc-200 rounded px-3 py-1 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                                >
                                                    <option value="user">User</option>
                                                    <option value="admin">Admin</option>
                                                </select>
                                            ) : (
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${userData.role === 'admin' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-zinc-600'
                                                    }`}>
                                                    {userData.role}
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 text-sm text-zinc-600">
                                            {new Date(userData.created_at).toLocaleDateString('ko-KR')}
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${userData.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                                                }`}>
                                                {userData.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            {editingId === userData.id ? (
                                                <div className="flex items-center justify-end gap-2">
                                                    <button
                                                        onClick={() => handleSave(userData.id)}
                                                        disabled={saving}
                                                        className="p-2 text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors disabled:opacity-50"
                                                    >
                                                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                                                    </button>
                                                    <button
                                                        onClick={handleCancelEdit}
                                                        className="p-2 text-zinc-500 hover:bg-zinc-100 rounded-lg transition-colors"
                                                    >
                                                        <X className="h-4 w-4" />
                                                    </button>
                                                </div>
                                            ) : (
                                                <div className="flex items-center justify-end gap-2">
                                                    <button
                                                        onClick={() => handleEdit(userData)}
                                                        className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                                                        title="수정"
                                                    >
                                                        <Edit2 className="h-4 w-4" />
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(userData.id, userData.username)}
                                                        className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                                        title="삭제"
                                                        disabled={userData.username === user?.username}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
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
            </div>
        </div>
    );
};
