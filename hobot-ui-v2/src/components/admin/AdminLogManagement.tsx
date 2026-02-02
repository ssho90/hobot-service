import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { FileText, RefreshCw, Clock, AlertCircle } from 'lucide-react';

export const AdminLogManagement: React.FC = () => {
    const [selectedLogType, setSelectedLogType] = useState('backend');
    const [selectedBackendLogFile, setSelectedBackendLogFile] = useState('log.txt');
    const [logContent, setLogContent] = useState('');
    const [logFile, setLogFile] = useState('');
    const [lines, setLines] = useState(100);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [autoRefresh, setAutoRefresh] = useState(false);
    const [useTimeFilter, setUseTimeFilter] = useState(false);
    const [startTime, setStartTime] = useState('');
    const [endTime, setEndTime] = useState('');
    const { getAuthHeaders } = useAuth();

    const fetchLogs = useCallback(async () => {
        try {
            setLoading(true);
            setError('');

            let url = `/api/admin/logs?log_type=${selectedLogType}&lines=${lines}`;

            if (selectedLogType === 'backend') {
                url += `&log_file=${encodeURIComponent(selectedBackendLogFile)}`;
            }

            if (useTimeFilter && startTime && endTime) {
                url += `&start_time=${encodeURIComponent(startTime)}&end_time=${encodeURIComponent(endTime)}`;
            }

            const response = await fetch(url, {
                headers: getAuthHeaders()
            });

            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success') {
                    setLogContent(data.content || 'No log content available');
                    setLogFile(data.file || '');
                } else {
                    setError(data.message || 'Failed to fetch logs');
                }
            } else {
                const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch logs' }));
                setError(errorData.detail || 'Failed to fetch logs');
            }
        } catch {
            setError('서버 연결에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    }, [selectedLogType, selectedBackendLogFile, lines, useTimeFilter, startTime, endTime, getAuthHeaders]);

    useEffect(() => {
        fetchLogs();
    }, [fetchLogs]);

    useEffect(() => {
        let interval: NodeJS.Timeout | null = null;
        if (autoRefresh) {
            interval = setInterval(() => {
                fetchLogs();
            }, 5000);
        }
        return () => {
            if (interval) clearInterval(interval);
        };
    }, [autoRefresh, fetchLogs]);

    const setTimeRange = (minutesAgo: number) => {
        const now = new Date();
        const kstTime = new Date(now.getTime() + (9 * 60 * 60 * 1000));
        const pastTime = new Date(kstTime.getTime() - minutesAgo * 60 * 1000);

        const formatV1 = (date: Date) => {
            const year = date.getUTCFullYear();
            const month = String(date.getUTCMonth() + 1).padStart(2, '0');
            const day = String(date.getUTCDate()).padStart(2, '0');
            const hours = String(date.getUTCHours()).padStart(2, '0');
            const minutes = String(date.getUTCMinutes()).padStart(2, '0');
            const seconds = String(date.getUTCSeconds()).padStart(2, '0');
            return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
        };

        setEndTime(formatV1(kstTime));
        setStartTime(formatV1(pastTime));
    };

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-zinc-900">
            <div className="flex flex-col md:flex-row md:items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight mb-2">로그 관리</h1>
                    <p className="text-zinc-500">시스템 로그를 실시간으로 확인하고 분석합니다.</p>
                </div>
            </div>

            {/* Controls */}
            <div className="bg-white rounded-xl border border-zinc-200 p-6 mb-8 shadow-sm">
                <div className="flex flex-wrap gap-4 items-end">
                    <div>
                        <label className="block text-sm font-medium text-zinc-600 mb-2">로그 타입</label>
                        <select
                            value={selectedLogType}
                            onChange={(e) => setSelectedLogType(e.target.value)}
                            className="bg-white border border-zinc-200 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none min-w-[160px] text-zinc-900"
                        >
                            <option value="backend">🔧 백엔드 로그</option>
                            <option value="frontend">⚛️ 프론트엔드 로그</option>
                            <option value="nginx">🌐 Nginx 로그</option>
                        </select>
                    </div>

                    {selectedLogType === 'backend' && (
                        <div>
                            <label className="block text-sm font-medium text-zinc-600 mb-2">로그 파일</label>
                            <select
                                value={selectedBackendLogFile}
                                onChange={(e) => setSelectedBackendLogFile(e.target.value)}
                                className="bg-white border border-zinc-200 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none min-w-[200px] text-zinc-900"
                            >
                                <option value="log.txt">📝 Application (log.txt)</option>
                                <option value="error.log">❌ Error (error.log)</option>
                                <option value="access.log">📊 Access (access.log)</option>
                            </select>
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-medium text-zinc-600 mb-2">줄 수</label>
                        <input
                            type="number"
                            value={lines}
                            onChange={(e) => setLines(parseInt(e.target.value) || 100)}
                            min="10"
                            max="5000"
                            className="bg-white border border-zinc-200 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none w-24 text-zinc-900"
                        />
                    </div>

                    <div className="flex items-center pb-3 px-2">
                        <label className="flex items-center gap-2 cursor-pointer text-sm text-zinc-600 hover:text-zinc-900 transition-colors">
                            <input
                                type="checkbox"
                                checked={autoRefresh}
                                onChange={(e) => setAutoRefresh(e.target.checked)}
                                className="w-4 h-4 rounded bg-white border-zinc-300 text-blue-600 focus:ring-blue-500"
                            />
                            <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
                            자동 새로고침 (5초)
                        </label>
                    </div>

                    <button
                        onClick={fetchLogs}
                        disabled={loading}
                        className="ml-auto px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-all disabled:opacity-50 flex items-center gap-2"
                    >
                        {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                        새로고침
                    </button>
                </div>

                {/* Time Filter Toggle */}
                <div className="mt-6 pt-6 border-t border-zinc-200">
                    <label className="flex items-center gap-2 cursor-pointer text-sm text-zinc-600 hover:text-zinc-900 transition-colors w-fit mb-4">
                        <input
                            type="checkbox"
                            checked={useTimeFilter}
                            onChange={(e) => {
                                setUseTimeFilter(e.target.checked);
                                if (!e.target.checked) {
                                    setStartTime('');
                                    setEndTime('');
                                }
                            }}
                            className="w-4 h-4 rounded bg-white border-zinc-300 text-blue-600 focus:ring-blue-500"
                        />
                        <Clock className="w-4 h-4" />
                        시간대 필터 사용
                    </label>

                    {useTimeFilter && (
                        <div className="flex flex-wrap gap-4 items-center animate-in fade-in slide-in-from-top-2">
                            <div>
                                <input
                                    type="datetime-local"
                                    value={startTime}
                                    onChange={(e) => setStartTime(e.target.value)}
                                    step="1"
                                    className="bg-white border border-zinc-200 rounded-lg px-3 py-2 text-sm text-zinc-900 focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            </div>
                            <span className="text-zinc-400">~</span>
                            <div>
                                <input
                                    type="datetime-local"
                                    value={endTime}
                                    onChange={(e) => setEndTime(e.target.value)}
                                    step="1"
                                    className="bg-white border border-zinc-200 rounded-lg px-3 py-2 text-sm text-zinc-900 focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            </div>
                            <div className="flex gap-2 ml-2">
                                {[5, 15, 30, 60, 1440].map((min) => (
                                    <button
                                        key={min}
                                        onClick={() => setTimeRange(min)}
                                        className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-xs text-zinc-600 rounded-md transition-colors"
                                    >
                                        {min >= 60 ? `${min / 60}시간` : `${min}분`}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {error && (
                <div className="mb-6 p-4 bg-red-900/20 border border-red-800/50 rounded-xl flex items-center gap-3 text-red-200">
                    <AlertCircle className="w-5 h-5 flex-shrink-0" />
                    {error}
                </div>
            )}

            {logFile && (
                <div className="mb-4 flex items-center gap-2 text-sm text-zinc-500">
                    <FileText className="w-4 h-4" />
                    현재 파일: <span className="font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-100">{logFile}</span>
                </div>
            )}

            {/* Log Viewer */}
            <div className="bg-[#1e1e1e] rounded-xl border border-zinc-300 shadow-lg overflow-hidden">
                <div className="max-h-[700px] overflow-auto p-4 font-mono text-sm leading-relaxed text-zinc-300 whitespace-pre-wrap break-all custom-scrollbar">
                    {loading && !logContent ? (
                        <div className="text-center py-20 text-zinc-500">로그를 불러오는 중입니다...</div>
                    ) : logContent ? (
                        logContent
                    ) : (
                        <div className="text-center py-20 text-zinc-600">표시할 로그가 없습니다.</div>
                    )}
                </div>
            </div>
        </div>
    );
};
