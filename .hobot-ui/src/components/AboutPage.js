import React, { useState } from 'react';
import './AboutPage.css';
import Header from './Header';

const AboutPage = () => {
    const [currentLang, setCurrentLang] = useState('KR');

    const toggleLanguage = () => {
        setCurrentLang(prev => prev === 'KR' ? 'EN' : 'KR');
    };

    return (
        <div className="about-page-container">
            <Header />
            <div className="about-page-content">
                {/* Korean Content */}
                <div style={{ display: currentLang === 'KR' ? 'block' : 'none' }} className="fade-in">
                    <section className="hero-section text-center">
                        <div className="container">
                            <div className="hero-actions">
                                <button className="hero-lang-btn" onClick={toggleLanguage}>
                                    <i className="bi bi-translate"></i> English
                                </button>
                            </div>
                            <span className="hero-badge">AI-Powered Asset Management</span>
                            <h1 className="hero-title display-4">데이터 기반의 똑똑한 투자</h1>
                            <p className="hero-subtitle">
                                Stockoverflow는 글로벌 경제 지표와 뉴스를 실시간으로 분석하여<br />
                                가장 안전하고 확실한 리밸런싱 전략을 제안합니다.
                            </p>
                        </div>
                    </section>

                    {/* System Overview */}
                    <section className="container mb-5 intro-section">
                        <div className="row justify-content-center">
                            <div className="col-lg-10">
                                <div className="text-center mb-5">
                                    <h2 className="section-header">왜 Stockoverflow인가요?</h2>
                                    <p className="section-desc mb-4">
                                        <strong>"수익률 극대화와 안정적 수익, 두 마리 토끼를 모두 잡습니다."</strong>
                                    </p>
                                    <p className="section-desc">
                                        단순한 분산 투자가 아닙니다. Stockoverflow는 <strong>거시경제(Macro) 데이터</strong>를 기반으로 목표 비중을 정하므로,
                                        시장의 상황에 맞게 <strong>능동적으로 포트폴리오를 재구성</strong>합니다.
                                        상승장에서는 적극적인 투자로 수익을 극대화하고, 하락장에서는 안전자산 비중을 늘려 소중한 자산을 지켜냅니다.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </section>

                    {/* Core Engine: Data & Logic - Flowchart */}
                    <section className="container mb-5 engine-section">
                        <h2 className="text-center mb-5 section-header">핵심 엔진 & 로직</h2>
                        <div className="process-flow-container">
                            {/* Step 1 */}
                            <div className="process-step">
                                <div className="step-number">01</div>
                                <div className="step-icon">
                                    <i className="bi bi-database-fill-gear"></i>
                                </div>
                                <div className="step-content">
                                    <h4>데이터 수집</h4>
                                    <p className="step-desc">거시경제 지표 (FRED, 뉴스) 수집</p>
                                </div>
                            </div>

                            {/* Arrow */}
                            <div className="process-arrow">
                                <i className="bi bi-arrow-right-circle-fill"></i>
                            </div>

                            {/* Step 2 */}
                            <div className="process-step">
                                <div className="step-number">02</div>
                                <div className="step-icon">
                                    <i className="bi bi-cpu-fill"></i>
                                </div>
                                <div className="step-content">
                                    <h4>AI 분석</h4>
                                    <p className="step-desc">AI가 목표 MP, Sub-MP 분석</p>
                                </div>
                            </div>

                            {/* Arrow */}
                            <div className="process-arrow">
                                <i className="bi bi-arrow-right-circle-fill"></i>
                            </div>

                            {/* Step 3 */}
                            <div className="process-step">
                                <div className="step-number">03</div>
                                <div className="step-icon">
                                    <i className="bi bi-shield-check"></i>
                                </div>
                                <div className="step-content">
                                    <h4>검증 및 안전장치</h4>
                                    <ul className="step-list">
                                        <li>3일 연속 신호 검증</li>
                                        <li>매매 충돌 방지 알고리즘</li>
                                        <li>시장 급변 방어로직</li>
                                    </ul>
                                </div>
                            </div>

                            {/* Arrow */}
                            <div className="process-arrow">
                                <i className="bi bi-arrow-right-circle-fill"></i>
                            </div>

                            {/* Step 4 */}
                            <div className="process-step">
                                <div className="step-number">04</div>
                                <div className="step-icon">
                                    <i className="bi bi-graph-up-arrow"></i>
                                </div>
                                <div className="step-content">
                                    <h4>운용 및 실행</h4>
                                    <ul className="step-list">
                                        <li>5일 분할 리밸런싱</li>
                                        <li>슬리피지 최소화 알고리즘</li>
                                        <li>실시간 체결 확인 알람</li>
                                        <li>자동 에러 복구 및 알람</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </section>

                    {/* Live Dashboard Screenshots */}
                    <section className="screenshot-section-wrapper mb-5">
                        <div className="container">
                            <h2 className="text-center mb-5 section-header">투명한 운용 현황</h2>
                            <div className="screenshot-container">
                                <div className="row g-5 align-items-center mb-5">
                                    <div className="col-lg-6">
                                        <div className="screenshot-frame">
                                            <img src="/assets/dashboard-account.jpg" alt="자산 현황 대시보드" className="dashboard-img" />
                                        </div>
                                    </div>
                                    <div className="col-lg-6">
                                        <div className="screenshot-text">
                                            <h3><i className="bi bi-pie-chart-fill me-2"></i> 실시간 자산 모니터링</h3>
                                            <p>
                                                총 자산의 평가 금액과 누적 수익률을 한눈에 확인할 수 있습니다.
                                                보유 중인 모든 종목의 현재가와 수익 현황이 실시간으로 동기화됩니다.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div className="row g-5 align-items-center">
                                    <div className="col-lg-6 order-lg-2">
                                        <div className="screenshot-frame">
                                            <img src="/assets/dashboard-rebalancing.jpg" alt="리밸런싱 현황" className="dashboard-img" />
                                        </div>
                                    </div>
                                    <div className="col-lg-6 order-lg-1">
                                        <div className="screenshot-text">
                                            <h3><i className="bi bi-sliders me-2"></i> 정밀 리밸런싱 관리</h3>
                                            <p>
                                                AI가 산출한 목표 비중(Target)과 현재 비중(Actual)을 비교하여,
                                                오차 범위 내에서 정밀하게 비중을 조절합니다.
                                                주식/채권/대체/현금 등 자산군별 밸런스를 자동으로 유지합니다.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section>

                    {/* Security */}
                    <section className="container mb-5 security-section">
                        <h2 className="text-center mb-5 section-header">엔터프라이즈급 보안</h2>
                        <div className="row g-4 text-center">
                            <div className="col-md-4">
                                <div className="security-item">
                                    <div className="security-icon">
                                        <i className="bi bi-lock-fill"></i>
                                    </div>
                                    <h5>데이터 암호화</h5>
                                    <p>모든 API 키와 중요 정보는 AES-256 알고리즘으로 암호화되어 DB에 저장됩니다.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="security-item">
                                    <div className="security-icon">
                                        <i className="bi bi-shield-lock-fill"></i>
                                    </div>
                                    <h5>SSL 보안 통신</h5>
                                    <p>서버와 클라이언트 간의 모든 통신은 HTTPS(SSL/TLS)을 통해 안전하게 보호됩니다.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="security-item">
                                    <div className="security-icon">
                                        <i className="bi bi-key-fill"></i>
                                    </div>
                                    <h5>접근 제어 (MFA)</h5>
                                    <p>관리자 페이지 접근 시 다단계 인증(MFA) 및 엄격한 IP 접근 제어를 적용합니다.</p>
                                </div>
                            </div>
                        </div>
                    </section>
                </div>

                {/* English Content */}
                <div style={{ display: currentLang === 'EN' ? 'block' : 'none' }} className="fade-in">
                    <section className="hero-section text-center">
                        <div className="container">
                            <div className="hero-actions">
                                <button className="hero-lang-btn" onClick={toggleLanguage}>
                                    <i className="bi bi-translate"></i> 한국어
                                </button>
                            </div>
                            <span className="hero-badge">AI-Powered Asset Management</span>
                            <h1 className="hero-title display-4">Intelligent Data-Driven Investing</h1>
                            <p className="hero-subtitle">
                                Stockoverflow analyzes global economic indicators and news in real-time<br />
                                to execute the safest and most strategic asset rebalancing.
                            </p>
                        </div>
                    </section>

                    <section className="container mb-5 intro-section">
                        <div className="row justify-content-center">
                            <div className="col-lg-10">
                                <div className="text-center mb-5">
                                    <h2 className="section-header">Why Stockoverflow?</h2>
                                    <p className="section-desc mb-4">
                                        <strong>"Maximizing Returns & Ensuring Stability. You can have both."</strong>
                                    </p>
                                    <p className="section-desc">
                                        It goes beyond simple diversification. By determining target weights based on <strong>Macroeconomic Data</strong>,
                                        Stockoverflow <strong>actively reconfigures your portfolio</strong> to suit market conditions.
                                        It aggressively captures growth in bull markets while shifting to safe assets in bear markets to protect your wealth.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </section>

                    {/* Core Engine: Data & Logic - Flowchart */}
                    <section className="container mb-5 engine-section">
                        <h2 className="text-center mb-5 section-header">Core Engine & Logic</h2>
                        <div className="process-flow-container">
                            {/* Step 1 */}
                            <div className="process-step">
                                <div className="step-number">01</div>
                                <div className="step-icon">
                                    <i className="bi bi-database-fill-gear"></i>
                                </div>
                                <div className="step-content">
                                    <h4>Data Collection</h4>
                                    <p className="step-desc">Macro Indicators (FRED, News)</p>
                                </div>
                            </div>

                            {/* Arrow */}
                            <div className="process-arrow">
                                <i className="bi bi-arrow-right-circle-fill"></i>
                            </div>

                            {/* Step 2 */}
                            <div className="process-step">
                                <div className="step-number">02</div>
                                <div className="step-icon">
                                    <i className="bi bi-cpu-fill"></i>
                                </div>
                                <div className="step-content">
                                    <h4>AI Analysis</h4>
                                    <p className="step-desc">AI determines Target MP & Sub-MP</p>
                                </div>
                            </div>

                            {/* Arrow */}
                            <div className="process-arrow">
                                <i className="bi bi-arrow-right-circle-fill"></i>
                            </div>

                            {/* Step 3 */}
                            <div className="process-step">
                                <div className="step-number">03</div>
                                <div className="step-icon">
                                    <i className="bi bi-shield-check"></i>
                                </div>
                                <div className="step-content">
                                    <h4>Verification</h4>
                                    <ul className="step-list">
                                        <li>3-Day Signal Verification</li>
                                        <li>Conflict Prevention Algorithm</li>
                                        <li>Market Defense Logic</li>
                                    </ul>
                                </div>
                            </div>

                            {/* Arrow */}
                            <div className="process-arrow">
                                <i className="bi bi-arrow-right-circle-fill"></i>
                            </div>

                            {/* Step 4 */}
                            <div className="process-step">
                                <div className="step-number">04</div>
                                <div className="step-icon">
                                    <i className="bi bi-graph-up-arrow"></i>
                                </div>
                                <div className="step-content">
                                    <h4>Execution</h4>
                                    <ul className="step-list">
                                        <li>5-Day Split Rebalancing</li>
                                        <li>Slippage Minimization</li>
                                        <li>Real-time Execution Alerts</li>
                                        <li>Auto-Recovery System</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="screenshot-section-wrapper mb-5">
                        <div className="container">
                            <h2 className="text-center mb-5 section-header">Transparent Operations</h2>
                            <div className="screenshot-container">
                                <div className="row g-5 align-items-center mb-5">
                                    <div className="col-lg-6">
                                        <div className="screenshot-frame">
                                            <img src="/assets/dashboard-account.jpg" alt="Account Dashboard" className="dashboard-img" />
                                        </div>
                                    </div>
                                    <div className="col-lg-6">
                                        <div className="screenshot-text">
                                            <h3><i className="bi bi-pie-chart-fill me-2"></i> Real-time Asset Monitoring</h3>
                                            <p>
                                                View total asset valuation and cumulative returns at a glance.
                                                Real-time synchronization keeps track of current prices and profit status for all holdings.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div className="row g-5 align-items-center">
                                    <div className="col-lg-6 order-lg-2">
                                        <div className="screenshot-frame">
                                            <img src="/assets/dashboard-rebalancing.jpg" alt="Rebalancing Status" className="dashboard-img" />
                                        </div>
                                    </div>
                                    <div className="col-lg-6 order-lg-1">
                                        <div className="screenshot-text">
                                            <h3><i className="bi bi-sliders me-2"></i> Precision Rebalancing</h3>
                                            <p>
                                                Dynamically compares AI-derived Target weights with Actual weights,
                                                adjusting positions within a precise tolerance range.
                                                Automatically maintains balance across Equity, Bond, Alternative, and Cash assets.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="container mb-5 security-section">
                        <h2 className="text-center mb-5 section-header">Enterprise-Grade Security</h2>
                        <div className="row g-4 text-center">
                            <div className="col-md-4">
                                <div className="security-item">
                                    <div className="security-icon">
                                        <i className="bi bi-lock-fill"></i>
                                    </div>
                                    <h5>Data Encryption</h5>
                                    <p>All API keys and critical credentials are stored using AES-256 encryption.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="security-item">
                                    <div className="security-icon">
                                        <i className="bi bi-shield-lock-fill"></i>
                                    </div>
                                    <h5>SSL Secure Channel</h5>
                                    <p>All client-server communications are protected via HTTPS (SSL/TLS).</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="security-item">
                                    <div className="security-icon">
                                        <i className="bi bi-key-fill"></i>
                                    </div>
                                    <h5>Access Control (MFA)</h5>
                                    <p>Admin access is protected by Multi-Factor Authentication (MFA) and strict IP whitelisting.</p>
                                </div>
                            </div>
                        </div>
                    </section>
                </div>
            </div>

            <footer className="modern-footer">
                <div className="container text-center">
                    <div className="footer-content">
                        <p className="copyright">&copy; {new Date().getFullYear()} Stockoverflow Macro Service. All rights reserved.</p>
                        <div className="creator-info">
                            <span>Created by <strong>Seungho Shin</strong></span>
                            <span className="separator">•</span>
                            <a href="mailto:90shins@gmail.com" className="email-link">90shins@gmail.com</a>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
};

export default AboutPage;
