import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Upload, File as FileIcon, Download, Trash2, Image as ImageIcon, X, Loader2, AlertCircle } from 'lucide-react';

interface UploadedFile {
    id: number;
    name: string;
    size: number;
    last_modified: string;
}

export const AdminFileUpload: React.FC = () => {
    const [files, setFiles] = useState<UploadedFile[]>([]);
    const [loading, setLoading] = useState(true);
    const [isDragging, setIsDragging] = useState(false);
    const [error, setError] = useState('');
    const [uploadMessage, setUploadMessage] = useState('');
    const [contentInput, setContentInput] = useState('');
    const [pastedFile, setPastedFile] = useState<File | null>(null);
    const [displayedContent, setDisplayedContent] = useState<{ type: 'text' | 'image', content: string | null } | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const { getAuthHeaders } = useAuth();

    // v1 handles text/image paste separately
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);

    const formatFileSize = (bytes: number) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const fetchFiles = useCallback(async () => {
        try {
            setLoading(true);
            const response = await fetch('/api/admin/files', { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                setFiles(data.files || []);
            } else {
                setError('파일 목록을 불러오는데 실패했습니다.');
            }
        } catch {
            setError('서버 연결에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    }, [getAuthHeaders]);

    const fetchSharedView = useCallback(async () => {
        try {
            const response = await fetch('/api/admin/shared-view', { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                if (data.type && data.content) {
                    setDisplayedContent({ type: data.type, content: data.content });
                }
            }
        } catch (err) {
            console.error('Failed to fetch shared view:', err);
        }
    }, [getAuthHeaders]);

    useEffect(() => {
        const interval = setInterval(fetchSharedView, 2000);
        return () => clearInterval(interval);
    }, [fetchSharedView]);

    useEffect(() => {
        fetchFiles();
        return () => {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
        };
    }, [fetchFiles, previewUrl]);

    const handleUpload = useCallback(async (file: File) => {
        const formData = new FormData();
        formData.append('file', file);

        try {
            setUploadMessage(`'${file.name}' 업로드 중...`);
            // Note: fetch automatically sets Content-Type to multipart/form-data with boundary when body is FormData
            // We need to NOT set Content-Type in headers
            const headers = getAuthHeaders() as Record<string, string>;
            const uploadHeaders = { ...headers };
            delete uploadHeaders['Content-Type'];

            const response = await fetch('/api/admin/files/upload', {
                method: 'POST',
                headers: uploadHeaders,
                body: formData
            });

            if (response.ok) {
                setUploadMessage(`'${file.name}' 업로드가 완료되었습니다.`);
                fetchFiles();
                setTimeout(() => setUploadMessage(''), 3000);
                const data = await response.json();
                return data;
            } else {
                const data = await response.json();
                setUploadMessage(`업로드 실패: ${data.detail || '알 수 없는 오류'}`);
                return null;
            }
        } catch {
            setUploadMessage('업로드 중 오류가 발생했습니다.');
            return null;
        }
    }, [getAuthHeaders, fetchFiles]);

    const updateSharedView = async (type: 'text' | 'image', content: string) => {
        try {
            await fetch('/api/admin/shared-view', {
                method: 'POST',
                headers: {
                    ...getAuthHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ type, content })
            });
            fetchSharedView(); // 즉시 업데이트
        } catch (err) {
            console.error('Failed to update shared view:', err);
            alert('공유 화면 업데이트 실패');
        }
    };

    const handleDragEnter = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
        if (e.dataTransfer.files.length > 0) {
            Array.from(e.dataTransfer.files).forEach(file => {
                handleUpload(file);
            });
        }
    };

    const handleContentPaste = (e: React.ClipboardEvent) => {
        const items = e.clipboardData.items;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                e.preventDefault();
                const file = items[i].getAsFile();
                if (file) {
                    const now = new Date();
                    const timestamp = now.toISOString().replace(/[:.]/g, '-');
                    const newFile = new File([file], `clipboard_image_${timestamp}.png`, { type: file.type });
                    setPastedFile(newFile);
                    setPreviewUrl(URL.createObjectURL(newFile));
                    setContentInput('');
                }
                break;
            }
        }
    };

    useEffect(() => {
        return () => {
            if (displayedContent?.type === 'image' && displayedContent.content) {
                URL.revokeObjectURL(displayedContent.content);
            }
        };
    }, [displayedContent]);

    const handleDisplayContent = async () => {
        if (pastedFile) {
            // 이미지 업로드 후 공유
            const uploadedData = await handleUpload(pastedFile);
            if (uploadedData && uploadedData.id) {
                const imageUrl = `/api/admin/files/${uploadedData.id}`;
                await updateSharedView('image', imageUrl);
                setPastedFile(null);
                setPreviewUrl(null);
            }
        } else if (contentInput.trim()) {
            // 텍스트 공유
            await updateSharedView('text', contentInput);
            setContentInput('');
        } else {
            alert('표시할 텍스트나 이미지가 없습니다.');
        }
    };

    const handleDownload = async (file: UploadedFile) => {
        try {
            const response = await fetch(`/api/admin/files/${file.id}`, {
                method: 'GET',
                headers: getAuthHeaders()
            });
            if (!response.ok) throw new Error();
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = file.name;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        } catch {
            alert('다운로드 실패');
        }
    };

    const handleDelete = async (file: UploadedFile) => {
        if (!confirm(`정말 ${file.name} 파일을 삭제하시겠습니까?`)) return;
        try {
            const response = await fetch(`/api/admin/files/${file.id}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });
            if (response.ok) fetchFiles();
            else alert('삭제 실패');
        } catch {
            alert('오류 발생');
        }
    };

    const triggerFileInput = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            Array.from(e.target.files).forEach(file => {
                handleUpload(file);
            });
        }
    };

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-zinc-900">
            <h1 className="text-3xl font-bold tracking-tight mb-2">파일 업로드 & 관리</h1>
            <p className="text-zinc-500 mb-8">서버에 파일을 업로드하거나 관리합니다.</p>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Left: Upload Area */}
                <div className="space-y-6">
                    {/* Drag & Drop Zone */}
                    <div
                        onDragEnter={handleDragEnter}
                        onDragOver={handleDragEnter}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={triggerFileInput}
                        className={`
                            border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all h-64
                            ${isDragging
                                ? 'border-blue-500 bg-blue-50 scale-[1.02]'
                                : 'border-zinc-300 bg-slate-50 hover:border-zinc-400 hover:bg-slate-100'
                            }
                        `}
                    >
                        <input type="file" className="hidden" ref={fileInputRef} onChange={handleFileChange} multiple />
                        <Upload className={`w-12 h-12 mb-4 ${isDragging ? 'text-blue-600' : 'text-zinc-400'}`} />
                        <h3 className="text-lg font-medium text-zinc-700">파일을 드래그하여 업로드</h3>
                        <p className="text-sm text-zinc-500 mt-2">여러 파일을 드래그하거나 클릭하여 선택</p>
                    </div>

                    {/* Paste Area */}
                    <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
                        <h3 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
                            <ImageIcon className="w-4 h-4" /> 텍스트/이미지 붙여넣기
                        </h3>

                        <div className="relative">
                            <textarea
                                value={contentInput}
                                onChange={(e) => setContentInput(e.target.value)}
                                onPaste={handleContentPaste}
                                placeholder="텍스트를 입력하거나 이미지를 붙여넣으세요 (Ctrl+V)"
                                className="w-full bg-white border border-zinc-200 rounded-lg p-4 h-32 text-sm text-zinc-900 placeholder-zinc-400 focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                            />
                            {previewUrl && (
                                <div className="absolute inset-0 bg-white/90 rounded-lg flex items-center justify-center p-4 border border-zinc-200">
                                    <div className="relative max-h-full">
                                        <img src={previewUrl} alt="Pasted" className="max-h-24 rounded border border-zinc-200 shadow-sm" />
                                        <button
                                            onClick={() => { setPastedFile(null); setPreviewUrl(null); }}
                                            className="absolute -top-2 -right-2 bg-red-500 text-white p-1 rounded-full shadow-lg hover:bg-red-600"
                                        >
                                            <X className="w-3 h-3" />
                                        </button>
                                    </div>
                                    <span className="absolute bottom-2 left-1/2 transform -translate-x-1/2 text-xs text-zinc-500">이미지가 준비되었습니다</span>
                                </div>
                            )}
                        </div>

                        <div className="flex justify-end mt-4">
                            <button
                                onClick={handleDisplayContent}
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm transition-colors shadow-sm font-medium"
                            >
                                화면에 출력
                            </button>
                        </div>
                    </div>

                    {/* Displayed Content Area */}
                    {displayedContent && (
                        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm animate-in fade-in slide-in-from-top-4 duration-300">
                            <h3 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-green-500"></span>
                                최신 출력 내용
                            </h3>
                            <div className="bg-slate-50 rounded-lg p-4 border border-zinc-100 min-h-[100px] flex items-center justify-center">
                                {displayedContent.type === 'image' ? (
                                    <img src={displayedContent.content!} alt="Displayed Content" className="max-w-full h-auto rounded shadow-sm border border-zinc-200" />
                                ) : (
                                    <pre className="whitespace-pre-wrap font-mono text-sm text-zinc-700 w-full break-all">
                                        {displayedContent.content}
                                    </pre>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Messages */}
                    {uploadMessage && (
                        <div className="p-4 bg-blue-900/30 text-blue-400 rounded-lg border border-blue-800 flex items-center justify-center">
                            {uploadMessage}
                        </div>
                    )}
                </div>

                {/* Right: File List */}
                <div className="bg-white rounded-xl border border-zinc-200 p-6 flex flex-col h-[calc(100vh-12rem)] min-h-[500px] shadow-sm">
                    <h3 className="text-lg font-bold mb-4 flex items-center justify-between">
                        <span className="flex items-center gap-2 text-zinc-900"><FileIcon className="w-5 h-5 text-emerald-600" /> 파일 목록</span>
                        <span className="text-xs font-normal text-zinc-500">Total: {files.length}</span>
                    </h3>

                    {error && (
                        <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-lg text-sm flex items-center gap-2 border border-red-100">
                            <AlertCircle className="w-4 h-4" /> {error}
                        </div>
                    )}

                    {loading && files.length === 0 ? (
                        <div className="flex-1 flex items-center justify-center text-zinc-500">
                            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                        </div>
                    ) : (
                        <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
                            {files.length > 0 ? files.map(file => (
                                <div key={file.id} className="flex items-center justify-between p-3 bg-slate-50 border border-zinc-200 rounded-lg hover:bg-white hover:shadow-sm transition-all group">
                                    <div className="flex-1 min-w-0 pr-4">
                                        <div className="font-medium text-zinc-900 truncate">{file.name}</div>
                                        <div className="text-xs text-zinc-500 flex gap-2 mt-0.5">
                                            <span>{formatFileSize(file.size)}</span>
                                            <span>•</span>
                                            <span>{file.last_modified}</span>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 opacity-60 group-hover:opacity-100 transition-opacity">
                                        <button
                                            onClick={() => handleDownload(file)}
                                            className="p-1.5 text-blue-600 hover:bg-blue-50 rounded"
                                            title="다운로드"
                                        >
                                            <Download className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(file)}
                                            className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                                            title="삭제"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            )) : (
                                <div className="text-center py-12 text-zinc-500">
                                    업로드된 파일이 없습니다.
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
