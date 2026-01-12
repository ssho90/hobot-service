import React, { useState, useEffect, useCallback } from 'react';
import './UpbitAccountSummary.css';

const UpbitAccountSummary = ({ platform = 'upbit' }) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        try {
            const response = await fetch('/api/upbit/account-summary');
            if (response.ok) {
                const result = await response.json();
                if (result.status === 'success') {
                    setData(result);
                    setError(null);
                } else {
                    setError(result.message || 'Failed to fetch data');
                }
            } else {
                setError('API Error');
            }
        } catch (err) {
            console.error('Error fetching account summary:', err);
            setError('Network Error');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 60000); // 1분마다 갱신
        return () => clearInterval(interval);
    }, [fetchData]);

    if (loading && !data) return <div className="card"><p>Loading Account Summary...</p></div>;
    if (error && !data) return <div className="card"><p className="status-error">Error: {error}</p></div>;
    if (!data) return null;

    const { account_info, assets } = data;

    // Format numbers
    const formatKrw = (val) => new Intl.NumberFormat('ko-KR').format(Math.round(val));
    const formatRate = (val) => {
        const rate = val > 0 ? `+${val.toFixed(2)}` : val.toFixed(2);
        return rate + '%';
    };
    const formatPnl = (val) => {
        const sign = val > 0 ? '+' : '';
        return `${sign}${formatKrw(val)}원`;
    };

    const pnlColorClass = (val) => {
        if (val > 0) return 'positive';
        if (val < 0) return 'negative';
        return 'neutral';
    };

    return (
        <div className="upbit-summary-container">
            {/* 계좌 정보 카드 */}
            <div className="summary-card">
                <h3 className="card-title">계좌 정보</h3>

                <div className="info-row">
                    <span className="info-label">Current Strategy</span>
                    <span className="info-value">{account_info.strategy || "N/A"}</span>
                </div>

                <div className="info-row">
                    <span className="info-label">총 평가금액</span>
                    <span className="info-value value-highlight">
                        {formatKrw(account_info.total_asset_amount)} 원
                    </span>
                </div>

                <div className="info-row">
                    <span className="info-label">총 손익</span>
                    <span className={`info-value value-highlight ${pnlColorClass(account_info.total_pnl)}`}>
                        {formatPnl(account_info.total_pnl)} ({formatRate(account_info.total_pnl_rate)})
                    </span>
                </div>

                <div className="info-row">
                    <span className="info-label">예수금</span>
                    <span className="info-value">
                        {formatKrw(account_info.total_krw)} 원
                    </span>
                </div>

                <div className="info-row">
                    <span className="info-label">총 매수금액</span>
                    <span className="info-value">
                        {formatKrw(account_info.total_invest_amount)} 원
                    </span>
                </div>
            </div>

            {/* 보유 자산 카드 */}
            <div className="assets-card">
                <h3 className="card-title">보유 자산</h3>

                <table className="assets-table">
                    <thead>
                        <tr>
                            <th>종목명</th>
                            <th>보유수량</th>
                            <th>평가금액</th>
                            <th>손익률</th>
                        </tr>
                    </thead>
                    <tbody>
                        {assets.map((asset) => (
                            <tr key={asset.currency}>
                                <td>
                                    <div className="asset-name-cell">
                                        <span className="asset-name">{asset.currency}</span>
                                        <span className="asset-ticker">{asset.ticker}</span>
                                    </div>
                                </td>
                                <td className="text-right cell-value">
                                    {asset.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })}
                                </td>
                                <td className="text-right cell-value">
                                    {formatKrw(asset.valuation)}
                                </td>
                                <td className={`text-right pnl-rate ${pnlColorClass(asset.pnl_rate)}`}>
                                    {formatRate(asset.pnl_rate)}
                                </td>
                            </tr>
                        ))}
                        {assets.length === 0 && (
                            <tr>
                                <td colSpan="4" style={{ textAlign: 'center', padding: '20px' }}>
                                    보유 자산이 없습니다.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default UpbitAccountSummary;
