import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import './SectorManagementPage.css';

const SectorManagementPage = () => {
  const { getAuthHeaders } = useAuth();
  const [sectors, setSectors] = useState({
    stocks: {},
    bonds: {},
    alternatives: {},
    cash: {}
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingAssetClass, setEditingAssetClass] = useState(null);
  const [editingSectorGroup, setEditingSectorGroup] = useState(null);
  const [editingItems, setEditingItems] = useState([]);

  const assetClassLabels = {
    stocks: '주식',
    bonds: '채권',
    alternatives: '대체투자',
    cash: '현금'
  };

  useEffect(() => {
    fetchSectors();
  }, []);

  const fetchSectors = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/admin/overview-recommended-sectors', {
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        throw new Error('섹터 리스트를 불러오는데 실패했습니다.');
      }

      const result = await response.json();
      if (result.status === 'success') {
        setSectors(result.data);
      }
    } catch (err) {
      setError(err.message);
      console.error('Error fetching sectors:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (assetClass, sectorGroup) => {
    setEditingAssetClass(assetClass);
    setEditingSectorGroup(sectorGroup);
    
    // 해당 섹터 그룹의 항목들을 편집 가능한 형태로 변환
    const items = sectors[assetClass][sectorGroup] || [];
    setEditingItems(items.map(item => ({
      id: item.id,
      ticker: item.ticker,
      name: item.name,
      display_order: item.display_order,
      is_active: item.is_active
    })));
  };

  const handleAddItem = () => {
    setEditingItems([...editingItems, {
      id: null,
      ticker: '',
      name: '',
      display_order: editingItems.length + 1,
      is_active: true
    }]);
  };

  const handleRemoveItem = (index) => {
    const newItems = editingItems.filter((_, i) => i !== index);
    // display_order 재정렬
    newItems.forEach((item, i) => {
      item.display_order = i + 1;
    });
    setEditingItems(newItems);
  };

  const handleItemChange = (index, field, value) => {
    const newItems = [...editingItems];
    newItems[index][field] = value;
    setEditingItems(newItems);
  };

  const handleSave = async () => {
    try {
      setError(null);
      
      // 유효성 검사
      for (const item of editingItems) {
        if (!item.ticker && !item.name) {
          throw new Error('티커 또는 이름을 입력해주세요.');
        }
      }

      const response = await fetch('/api/admin/overview-recommended-sectors', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify({
          asset_class: editingAssetClass,
          items: editingItems.map(item => ({
            sector_group: editingSectorGroup,
            ticker: item.ticker,
            name: item.name,
            display_order: item.display_order,
            is_active: item.is_active
          }))
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || '저장에 실패했습니다.');
      }

      // 저장 성공 후 목록 새로고침
      await fetchSectors();
      setEditingAssetClass(null);
      setEditingSectorGroup(null);
      setEditingItems([]);
      alert('저장되었습니다.');
    } catch (err) {
      setError(err.message);
      console.error('Error saving sectors:', err);
    }
  };

  const handleCancel = () => {
    setEditingAssetClass(null);
    setEditingSectorGroup(null);
    setEditingItems([]);
  };

  const handleDeleteSector = async (sectorId) => {
    if (!window.confirm('이 항목을 삭제하시겠습니까?')) {
      return;
    }

    try {
      const response = await fetch(`/api/admin/overview-recommended-sectors/${sectorId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        throw new Error('삭제에 실패했습니다.');
      }

      await fetchSectors();
      alert('삭제되었습니다.');
    } catch (err) {
      setError(err.message);
      console.error('Error deleting sector:', err);
    }
  };

  const handleAddSectorGroup = (assetClass) => {
    const sectorGroupName = prompt('새 섹터/그룹 이름을 입력하세요:');
    if (!sectorGroupName) return;

    setEditingAssetClass(assetClass);
    setEditingSectorGroup(sectorGroupName);
    setEditingItems([{
      id: null,
      ticker: '',
      name: '',
      display_order: 1,
      is_active: true
    }]);
  };

  if (loading) {
    return <div className="sector-management-loading">로딩 중...</div>;
  }

  return (
    <div className="sector-management-page">
      <div className="page-header">
        <h1>종목 관리</h1>
        <p>Overview AI 추천 섹터/그룹 리스트를 관리합니다.</p>
      </div>

      {error && (
        <div className="error-banner">
          <strong>⚠️ 오류:</strong> {error}
        </div>
      )}

      {editingAssetClass && editingSectorGroup ? (
        <div className="sector-edit-panel">
          <div className="edit-header">
            <h2>
              {assetClassLabels[editingAssetClass]} - {editingSectorGroup}
            </h2>
            <div className="edit-actions">
              <button className="btn-save" onClick={handleSave}>저장</button>
              <button className="btn-cancel" onClick={handleCancel}>취소</button>
            </div>
          </div>

          <div className="edit-items">
            {editingItems.map((item, index) => (
              <div key={index} className="edit-item">
                <div className="item-row">
                  <div className="item-field">
                    <label>티커</label>
                    <input
                      type="text"
                      value={item.ticker}
                      onChange={(e) => handleItemChange(index, 'ticker', e.target.value)}
                      placeholder="예: 360750"
                    />
                  </div>
                  <div className="item-field">
                    <label>이름</label>
                    <input
                      type="text"
                      value={item.name}
                      onChange={(e) => handleItemChange(index, 'name', e.target.value)}
                      placeholder="예: TIGER 미국S&P500"
                    />
                  </div>
                  <div className="item-field">
                    <label>순서</label>
                    <input
                      type="number"
                      value={item.display_order}
                      onChange={(e) => handleItemChange(index, 'display_order', parseInt(e.target.value) || 0)}
                      min="1"
                    />
                  </div>
                  <div className="item-field">
                    <label>
                      <input
                        type="checkbox"
                        checked={item.is_active}
                        onChange={(e) => handleItemChange(index, 'is_active', e.target.checked)}
                      />
                      활성화
                    </label>
                  </div>
                  <button
                    className="btn-remove"
                    onClick={() => handleRemoveItem(index)}
                  >
                    삭제
                  </button>
                </div>
              </div>
            ))}
            <button className="btn-add-item" onClick={handleAddItem}>
              + 항목 추가
            </button>
          </div>
        </div>
      ) : (
        <div className="sector-list">
          {Object.entries(sectors).map(([assetClass, sectorGroups]) => (
            <div key={assetClass} className="asset-class-section">
              <div className="section-header">
                <h2>{assetClassLabels[assetClass]}</h2>
                <button
                  className="btn-add-sector"
                  onClick={() => handleAddSectorGroup(assetClass)}
                >
                  + 섹터 그룹 추가
                </button>
              </div>

              {Object.keys(sectorGroups).length === 0 ? (
                <div className="empty-section">섹터 그룹이 없습니다.</div>
              ) : (
                Object.entries(sectorGroups).map(([sectorGroup, items]) => (
                  <div key={sectorGroup} className="sector-group">
                    <div className="group-header">
                      <h3>{sectorGroup}</h3>
                      <button
                        className="btn-edit"
                        onClick={() => handleEdit(assetClass, sectorGroup)}
                      >
                        편집
                      </button>
                    </div>
                    <div className="group-items">
                      {items
                        .filter(item => item.is_active)
                        .sort((a, b) => a.display_order - b.display_order)
                        .map((item) => (
                          <div key={item.id} className="group-item">
                            <span className="item-ticker">{item.ticker || '-'}</span>
                            <span className="item-name">{item.name}</span>
                            <span className="item-order">순서: {item.display_order}</span>
                            <button
                              className="btn-delete"
                              onClick={() => handleDeleteSector(item.id)}
                            >
                              삭제
                            </button>
                          </div>
                        ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SectorManagementPage;

