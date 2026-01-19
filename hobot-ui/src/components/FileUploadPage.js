import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import './AdminPage.css';

const FileUploadPage = () => {
    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [isDragging, setIsDragging] = useState(false);
    const [error, setError] = useState('');
    const [uploadMessage, setUploadMessage] = useState('');
    const fileInputRef = useRef(null);
    const { getAuthHeaders } = useAuth();

    const formatFileSize = (bytes) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const fetchFiles = useCallback(async () => {
        try {
            setLoading(true);
            const response = await fetch('/api/admin/files', {
                headers: getAuthHeaders()
            });

            if (response.ok) {
                const data = await response.json();
                setFiles(data.files);
            } else {
                setError('파일 목록을 불러오는데 실패했습니다.');
            }
        } catch (err) {
            setError('서버 연결에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    }, [getAuthHeaders]);

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const handleDragEnter = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(true);
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
    };

    const handleDragOver = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);

        const droppedFiles = e.dataTransfer.files;
        if (droppedFiles.length > 0) {
            handleUpload(droppedFiles[0]);
        }
    };

    const handleFileInputChange = (e) => {
        if (e.target.files.length > 0) {
            handleUpload(e.target.files[0]);
        }
    };

    const handleUpload = useCallback(async (file) => {
        const formData = new FormData();
        formData.append('file', file);

        try {
            setUploadMessage('업로드 중...');
            const response = await fetch('/api/admin/files/upload', {
                method: 'POST',
                headers: {
                    ...getAuthHeaders(false)
                },
                body: formData
            });

            if (response.ok) {
                setUploadMessage('업로드가 완료되었습니다.');
                fetchFiles();
                setTimeout(() => setUploadMessage(''), 3000);
            } else {
                const data = await response.json();
                setUploadMessage(`업로드 실패: ${data.detail || '알 수 없는 오류'}`);
            }
        } catch (err) {
            setUploadMessage('업로드 중 오류가 발생했습니다.');
        }
    }, [getAuthHeaders, fetchFiles]);

    useEffect(() => {
        const handlePaste = (e) => {
            const items = e.clipboardData.items;
            for (let i = 0; i < items.length; i++) {
                if (items[i].type.indexOf('image') !== -1) {
                    const file = items[i].getAsFile();
                    const now = new Date();
                    const timestamp = now.toISOString().replace(/[:.]/g, '-');
                    const newFile = new File([file], `clipboard_image_${timestamp}.png`, { type: file.type });
                    handleUpload(newFile);
                } else if (items[i].type === 'text/plain') {
                    items[i].getAsString((text) => {
                        if (!text.trim()) return;
                        const now = new Date();
                        const timestamp = now.toISOString().replace(/[:.]/g, '-');
                        const blob = new Blob([text], { type: 'text/plain' });
                        const file = new File([blob], `clipboard_text_${timestamp}.txt`, { type: 'text/plain' });
                        handleUpload(file);
                    });
                }
            }
        };

        window.addEventListener('paste', handlePaste);
        return () => {
            window.removeEventListener('paste', handlePaste);
        };
    }, [handleUpload]);

    // getAuthHeaders가 Content-Type: application/json을 포함하는지 확인이 어려우므로 
    // formData 전송을 위한 래퍼 함수 (필요시 수정)
    // const uploadHeaders = getAuthHeaders();
    // delete uploadHeaders['Content-Type']; 
    // -> 위 코드에서 getAuthHeaders(false) 같은 옵션이 없다면 직접 헤더 조작 필요. 
    //   UserManagementPage.js 에서는 headers: getAuthHeaders() 만 썼음 (GET).
    //   handleSaveEdit 에서는 ...getAuthHeaders() 하고 Content-Type 덮어씀.
    //   FormData는 Content-Type 헤더를 브라우저가 설정해야 함.

    const handleDownload = async (filename) => {
        try {
            const response = await fetch(`/api/admin/files/${encodeURIComponent(filename)}`, {
                method: 'GET',
                headers: getAuthHeaders()
            });

            if (!response.ok) {
                throw new Error('파일 다운로드 실패');
            }

            // Blob으로 변환하여 다운로드 처리
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        } catch (err) {
            alert('파일 다운로드 중 오류가 발생했습니다.');
        }
    };

    const handleDelete = async (filename) => {
        if (!window.confirm(`정말 ${filename} 파일을 삭제하시겠습니까?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/files/${encodeURIComponent(filename)}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });

            if (response.ok) {
                fetchFiles();
            } else {
                alert('파일 삭제에 실패했습니다.');
            }
        } catch (err) {
            alert('서버 연결에 실패했습니다.');
        }
    };

    return (
        <div className="admin-page">
            <div className="admin-header">
                <h1>파일 업로드</h1>
                <p>서버에 파일을 업로드하고 관리할 수 있습니다.</p>
            </div>

            <div
                className={`upload-drop-zone ${isDragging ? 'active' : ''}`}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current.click()}
            >
                <div className="upload-icon">📁</div>
                <p>클릭하여 파일을 선택하거나, 이곳으로 파일을 드래그하세요.</p>
                <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    onChange={handleFileInputChange}
                />
            </div>

            {uploadMessage && (
                <div className="message" style={{ marginBottom: '20px', color: uploadMessage.includes('실패') ? 'red' : 'green' }}>
                    {uploadMessage}
                </div>
            )}

            {error && (
                <div className="error-message">
                    {error}
                </div>
            )}

            <div className="card">
                <h3>업로드된 파일 목록</h3>
                <div className="table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>파일명</th>
                                <th>크기</th>
                                <th>업로드 일시</th>
                                <th>작업</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan="4" style={{ textAlign: 'center', padding: '20px' }}>로딩 중...</td>
                                </tr>
                            ) : files.length === 0 ? (
                                <tr>
                                    <td colSpan="4" style={{ textAlign: 'center', padding: '20px' }}>파일이 없습니다.</td>
                                </tr>
                            ) : (
                                files.map((file) => (
                                    <tr key={file.name}>
                                        <td>{file.name}</td>
                                        <td>{formatFileSize(file.size)}</td>
                                        <td>{file.last_modified}</td>
                                        <td>
                                            <button
                                                className="btn-sm"
                                                style={{ marginRight: '8px', backgroundColor: '#3b82f6', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                                                onClick={() => handleDownload(file.name)}
                                            >
                                                다운로드
                                            </button>
                                            <button
                                                className="btn-delete btn-sm"
                                                onClick={() => handleDelete(file.name)}
                                            >
                                                삭제
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default FileUploadPage;
