import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import './PortfolioManagementPage.css';

const PortfolioManagementPage = () => {
  const [activeTab, setActiveTab] = useState('mp'); // 'mp' or 'sub-mp'
  const [modelPortfolios, setModelPortfolios] = useState([]);
  const [subModelPortfolios, setSubModelPortfolios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editingMp, setEditingMp] = useState(null);
  const [editingSubMp, setEditingSubMp] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const { getAuthHeaders } = useAuth();

  const fetchModelPortfolios = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/admin/portfolios/model-portfolios', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setModelPortfolios(data.portfolios);
      } else {
        setError('모델 포트폴리오 목록을 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  const fetchSubModelPortfolios = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/admin/portfolios/sub-model-portfolios', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setSubModelPortfolios(data.portfolios);
      } else {
        setError('Sub-MP 포트폴리오 목록을 불러오는데 실패했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    if (activeTab === 'mp') {
      fetchModelPortfolios();
    } else {
      fetchSubModelPortfolios();
    }
  }, [activeTab, fetchModelPortfolios, fetchSubModelPortfolios]);

  const handleEditMp = (mp) => {
    setEditingMp(mp.id);
    setEditForm({
      name: mp.name,
      description: mp.description,
      strategy: mp.strategy,
      allocation: { ...mp.allocation },
      display_order: mp.display_order,
      is_active: mp.is_active
    });
  };

  const handleEditSubMp = (subMp) => {
    const baseForm = {
      name: subMp.name,
      description: subMp.description,
      asset_class: subMp.asset_class,
      etf_details: (subMp.etf_details || []).map(etf => ({ ...etf })),
      display_order: subMp.display_order,
      is_active: subMp.is_active
    };

    // Cash 자산군 편집 시 기본 KRW 현금 100%로 강제
    const nextForm = subMp.asset_class === 'Cash'
      ? {
          ...baseForm,
          etf_details: [{ category: 'KRW', ticker: 'CASH', name: '현금', weight: 1 }]
        }
      : baseForm;

    setEditingSubMp(subMp.id);
    setEditForm(nextForm);
  };

  const handleCancelEdit = () => {
    setEditingMp(null);
    setEditingSubMp(null);
    setEditForm(null);
  };

  const handleSaveMp = async (mpId) => {
    try {
      const response = await fetch(`/api/admin/portfolios/model-portfolios/${mpId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify(editForm)
      });

      if (response.ok) {
        await fetchModelPortfolios();
        setEditingMp(null);
        setEditForm(null);
        alert('모델 포트폴리오가 업데이트되었습니다.');
      } else {
        const data = await response.json();
        alert(data.detail || '모델 포트폴리오 업데이트에 실패했습니다.');
      }
    } catch (err) {
      alert('서버 연결에 실패했습니다.');
    }
  };

  const handleSaveSubMp = async (subMpId) => {
    // Cash 자산군 저장 시 기본 현금 100%를 강제 설정
    let payload = { ...editForm };
    if (editForm.asset_class === 'Cash') {
      payload = {
        ...payload,
        etf_details: [{ category: 'KRW', ticker: 'CASH', name: '현금', weight: 1 }]
      };
    }

    try {
      const response = await fetch(`/api/admin/portfolios/sub-model-portfolios/${subMpId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        await fetchSubModelPortfolios();
        setEditingSubMp(null);
        setEditForm(null);
        alert('Sub-MP 포트폴리오가 업데이트되었습니다.');
      } else {
        const data = await response.json();
        alert(data.detail || 'Sub-MP 포트폴리오 업데이트에 실패했습니다.');
      }
    } catch (err) {
      alert('서버 연결에 실패했습니다.');
    }
  };

  const handleAddEtf = () => {
    // Cash 자산군은 수동 추가 불가
    if (editForm.asset_class === 'Cash') return;
    if (!editForm.etf_details) {
      setEditForm({ ...editForm, etf_details: [] });
      return;
    }
    setEditForm({
      ...editForm,
      etf_details: [
        ...(editForm.etf_details || []),
        { category: '', ticker: '', name: '', weight: 0 }
      ]
    });
  };

  const handleRemoveEtf = (index) => {
    if (editForm.asset_class === 'Cash') return; // Cash는 삭제 불가
    const newEtfDetails = editForm.etf_details.filter((_, i) => i !== index);
    setEditForm({ ...editForm, etf_details: newEtfDetails });
  };

  const handleEtfChange = (index, field, value) => {
    const newEtfDetails = editForm.etf_details.map((etf, i) => {
      if (i === index) {
        if (field === 'weight') {
          const asNumber = parseFloat(value);
          return { ...etf, weight: Number.isFinite(asNumber) ? asNumber / 100 : 0 };
        }
        return { ...etf, [field]: value };
      }
      return etf;
    });
    setEditForm({ ...editForm, etf_details: newEtfDetails });
  };

  if (loading) {
    return (
      <div className="portfolio-management-page">
        <div className="portfolio-header">
          <h1>포트폴리오 관리</h1>
        </div>
        <div style={{ textAlign: 'center', padding: '40px' }}>로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="portfolio-management-page">
      <div className="portfolio-header">
        <h1>포트폴리오 관리</h1>
        <p>모델 포트폴리오(MP)와 Sub-MP 포트폴리오를 관리할 수 있습니다.</p>
      </div>

      {error && (
        <div className="error-message" style={{ color: 'red', marginBottom: '20px' }}>
          {error}
        </div>
      )}

      <div className="portfolio-tabs">
        <button
          className={`tab-button ${activeTab === 'mp' ? 'active' : ''}`}
          onClick={() => setActiveTab('mp')}
        >
          모델 포트폴리오 (MP)
        </button>
        <button
          className={`tab-button ${activeTab === 'sub-mp' ? 'active' : ''}`}
          onClick={() => setActiveTab('sub-mp')}
        >
          Sub-MP 포트폴리오
        </button>
      </div>

      {activeTab === 'mp' && (
        <div className="portfolios-table-container">
          <table className="portfolios-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>이름</th>
                <th>설명</th>
                <th>전략</th>
                <th>자산 배분</th>
                <th>표시 순서</th>
                <th>활성화</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {modelPortfolios.map((mp) => (
                <tr key={mp.id}>
                  <td>{mp.id}</td>
                  <td>
                    {editingMp === mp.id ? (
                      <input
                        type="text"
                        value={editForm.name}
                        onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                        className="edit-input"
                      />
                    ) : (
                      mp.name
                    )}
                  </td>
                  <td>
                    {editingMp === mp.id ? (
                      <textarea
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        className="edit-textarea"
                        rows="3"
                      />
                    ) : (
                      <div className="description-cell">{mp.description}</div>
                    )}
                  </td>
                  <td>
                    {editingMp === mp.id ? (
                      <input
                        type="text"
                        value={editForm.strategy}
                        onChange={(e) => setEditForm({ ...editForm, strategy: e.target.value })}
                        className="edit-input"
                      />
                    ) : (
                      mp.strategy
                    )}
                  </td>
                  <td>
                    {editingMp === mp.id ? (
                      <div className="allocation-editor">
                        <label>
                          주식: <input
                            type="number"
                            step="0.1"
                            value={editForm.allocation.Stocks}
                            onChange={(e) => setEditForm({
                              ...editForm,
                              allocation: { ...editForm.allocation, Stocks: parseFloat(e.target.value) || 0 }
                            })}
                            className="allocation-input"
                          />%
                        </label>
                        <label>
                          채권: <input
                            type="number"
                            step="0.1"
                            value={editForm.allocation.Bonds}
                            onChange={(e) => setEditForm({
                              ...editForm,
                              allocation: { ...editForm.allocation, Bonds: parseFloat(e.target.value) || 0 }
                            })}
                            className="allocation-input"
                          />%
                        </label>
                        <label>
                          대체투자: <input
                            type="number"
                            step="0.1"
                            value={editForm.allocation.Alternatives}
                            onChange={(e) => setEditForm({
                              ...editForm,
                              allocation: { ...editForm.allocation, Alternatives: parseFloat(e.target.value) || 0 }
                            })}
                            className="allocation-input"
                          />%
                        </label>
                        <label>
                          현금: <input
                            type="number"
                            step="0.1"
                            value={editForm.allocation.Cash}
                            onChange={(e) => setEditForm({
                              ...editForm,
                              allocation: { ...editForm.allocation, Cash: parseFloat(e.target.value) || 0 }
                            })}
                            className="allocation-input"
                          />%
                        </label>
                      </div>
                    ) : (
                      <div className="allocation-display">
                        주식: {mp.allocation?.Stocks || 0}% / 채권: {mp.allocation?.Bonds || 0}% / 
                        대체투자: {mp.allocation?.Alternatives || 0}% / 현금: {mp.allocation?.Cash || 0}%
                      </div>
                    )}
                  </td>
                  <td>
                    {editingMp === mp.id ? (
                      <input
                        type="number"
                        value={editForm.display_order}
                        onChange={(e) => setEditForm({ ...editForm, display_order: parseInt(e.target.value) || 0 })}
                        className="edit-input"
                        style={{ width: '60px' }}
                      />
                    ) : (
                      mp.display_order
                    )}
                  </td>
                  <td>
                    {editingMp === mp.id ? (
                      <input
                        type="checkbox"
                        checked={editForm.is_active}
                        onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                      />
                    ) : (
                      <span className={`status-badge ${mp.is_active ? 'active' : 'inactive'}`}>
                        {mp.is_active ? '활성' : '비활성'}
                      </span>
                    )}
                  </td>
                  <td>
                    {editingMp === mp.id ? (
                      <div className="action-buttons">
                        <button
                          className="btn-save"
                          onClick={() => handleSaveMp(mp.id)}
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
                      <button
                        className="btn-edit"
                        onClick={() => handleEditMp(mp)}
                      >
                        수정
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'sub-mp' && (
        <div className="portfolios-table-container">
          <table className="portfolios-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>이름</th>
                <th>설명</th>
                <th>자산군</th>
                <th>ETF 상세</th>
                <th>표시 순서</th>
                <th>활성화</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {subModelPortfolios.map((subMp) => (
                <tr key={subMp.id}>
                  <td>{subMp.id}</td>
                  <td>
                    {editingSubMp === subMp.id ? (
                      <input
                        type="text"
                        value={editForm.name}
                        onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                        className="edit-input"
                      />
                    ) : (
                      subMp.name
                    )}
                  </td>
                  <td>
                    {editingSubMp === subMp.id ? (
                      <textarea
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        className="edit-textarea"
                        rows="3"
                      />
                    ) : (
                      <div className="description-cell">{subMp.description}</div>
                    )}
                  </td>
                  <td>
                  {editingSubMp === subMp.id ? (
                    <select
                      value={editForm.asset_class}
                      onChange={(e) => {
                        const nextClass = e.target.value;
                        if (nextClass === 'Cash') {
                          setEditForm({
                            ...editForm,
                            asset_class: nextClass,
                            etf_details: [{ category: 'KRW', ticker: 'CASH', name: '현금', weight: 1 }]
                          });
                        } else {
                          setEditForm({ ...editForm, asset_class: nextClass });
                        }
                      }}
                      className="edit-input"
                    >
                      <option value="Stocks">Stocks</option>
                      <option value="Bonds">Bonds</option>
                      <option value="Alternatives">Alternatives</option>
                      <option value="Cash">Cash</option>
                    </select>
                  ) : (
                    subMp.asset_class
                  )}
                  </td>
                  <td>
                  {editingSubMp === subMp.id ? (
                    <div className="etf-editor">
                      {editForm.asset_class === 'Cash' ? (
                        <div className="cash-editor">
                          <div className="etf-item-display" style={{ fontWeight: 600 }}>
                            KRW 현금 (CASH) - 100%
                          </div>
                        </div>
                      ) : (
                        <>
                          {editForm.etf_details.map((etf, index) => (
                            <div key={index} className="etf-item">
                              <input
                                type="text"
                                placeholder="카테고리"
                                value={etf.category}
                                onChange={(e) => handleEtfChange(index, 'category', e.target.value)}
                                className="etf-input"
                              />
                              <input
                                type="text"
                                placeholder="티커"
                                value={etf.ticker}
                                onChange={(e) => handleEtfChange(index, 'ticker', e.target.value)}
                                className="etf-input"
                              />
                              <input
                                type="text"
                                placeholder="이름"
                                value={etf.name}
                                onChange={(e) => handleEtfChange(index, 'name', e.target.value)}
                                className="etf-input"
                              />
                              <input
                                type="number"
                                step="0.1"
                                placeholder="비중(0-100)"
                                value={(etf.weight || 0) * 100}
                                onChange={(e) => handleEtfChange(index, 'weight', e.target.value)}
                                className="etf-input"
                                style={{ width: '80px' }}
                              />
                              <button
                                className="btn-remove"
                                onClick={() => handleRemoveEtf(index)}
                              >
                                삭제
                              </button>
                            </div>
                          ))}
                          <button
                            className="btn-add"
                            onClick={handleAddEtf}
                          >
                            ETF 추가
                          </button>
                        </>
                      )}
                    </div>
                  ) : (
                    <div className="etf-display">
                      {subMp.etf_details && subMp.etf_details.length > 0 ? (
                        subMp.etf_details.map((etf, idx) => (
                          <div key={idx} className="etf-item-display">
                            {etf.category}: {etf.ticker} ({etf.name}) - {(etf.weight || 0) * 100}%
                          </div>
                        ))
                      ) : (
                        <div className="etf-item-display" style={{ color: '#999' }}>ETF 정보 없음</div>
                      )}
                    </div>
                  )}
                  </td>
                  <td>
                    {editingSubMp === subMp.id ? (
                      <input
                        type="number"
                        value={editForm.display_order}
                        onChange={(e) => setEditForm({ ...editForm, display_order: parseInt(e.target.value) || 0 })}
                        className="edit-input"
                        style={{ width: '60px' }}
                      />
                    ) : (
                      subMp.display_order
                    )}
                  </td>
                  <td>
                    {editingSubMp === subMp.id ? (
                      <input
                        type="checkbox"
                        checked={editForm.is_active}
                        onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                      />
                    ) : (
                      <span className={`status-badge ${subMp.is_active ? 'active' : 'inactive'}`}>
                        {subMp.is_active ? '활성' : '비활성'}
                      </span>
                    )}
                  </td>
                  <td>
                    {editingSubMp === subMp.id ? (
                      <div className="action-buttons">
                        <button
                          className="btn-save"
                          onClick={() => handleSaveSubMp(subMp.id)}
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
                      <button
                        className="btn-edit"
                        onClick={() => handleEditSubMp(subMp)}
                      >
                        수정
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default PortfolioManagementPage;

