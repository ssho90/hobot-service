import React, { useState } from 'react';
import './AboutPage.css';

const AboutPage = () => {
    const [currentLang, setCurrentLang] = useState('KR');

    const toggleLanguage = () => {
        setCurrentLang(prev => prev === 'KR' ? 'EN' : 'KR');
    };

    return (
        <div className="about-page">
            <div className="about-content">
                {/* Korean Content */}
                <div style={{ display: currentLang === 'KR' ? 'block' : 'none' }}>
                    <div className="hero-section text-center">
                        <div className="container">
                            <h1 className="hero-title display-4">AI 기반 매크로 트레이딩</h1>
                            <p className="lead" style={{ maxWidth: '700px', margin: '0 auto' }}>
                                Hobot은 고도화된 AI를 활용하여 글로벌 경제 지표를 분석하고, 안전하고 전략적인 자산 리밸런싱을 수행합니다.
                            </p>
                        </div>
                    </div>

                    <div className="container mb-5">
                        <div className="row mb-5">
                            <div className="col-lg-8 offset-lg-2">
                                <h2 className="text-center mb-4">일일 워크플로우</h2>
                                <div className="workflow-timeline">
                                    <div className="workflow-item">
                                        <h4><span className="badge bg-primary">08:30</span> 시장 정밀 분석</h4>
                                        <p className="text-muted">
                                            매일 아침 장 시작 전, AI 에이전트가 주요 경제 지표(FRED)와 미국/중국/유로존의 뉴스를 분석합니다. 현재 시장 국면(성장 vs 인플레이션 등)을 판단하여 최적의 모델 포트폴리오(MP)를 선정합니다.
                                        </p>
                                    </div>
                                    <div className="workflow-item">
                                        <h4><span className="badge bg-warning text-dark">검증</span> 3일 신호 검증 (3-Day Rule)</h4>
                                        <p className="text-muted">
                                            일시적인 시장 노이즈에 반응하지 않도록, 새로운 신호가 3일 연속 유지될 때만 포트폴리오 변경을 승인합니다.
                                            <br /><span className="safety-badge mt-2 d-inline-block"><i className="bi bi-shield-check"></i> 노이즈 필터링</span>
                                        </p>
                                    </div>
                                    <div className="workflow-item">
                                        <h4><span className="badge bg-success">09:40</span> 안전한 분할 실행</h4>
                                        <p className="text-muted">
                                            시장 충격을 최소화하기 위해 리밸런싱은 **5일간 분할**하여 진행됩니다. 실행 중 중요 경제 이벤트 발생 시 로직이 자동으로 대응하여 안전하게 자산을 보호합니다.
                                            <br /><span className="safety-badge mt-2 d-inline-block"><i className="bi bi-graph-up-arrow"></i> 5일 분할 진입</span>
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="row g-4">
                            <div className="col-md-4">
                                <div className="card feature-card text-center p-4">
                                    <i className="bi bi-cpu feature-icon"></i>
                                    <h5>AI 전략가</h5>
                                    <p className="small text-muted">Gemini Pro 기반으로 단순 퀀트 모델이 놓칠 수 있는 복합적인 거시경제 흐름을 분석합니다.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="card feature-card text-center p-4">
                                    <i className="bi bi-globe-americas feature-icon"></i>
                                    <h5>글로벌 커버리지</h5>
                                    <p className="small text-muted">미국 연준(Fed), 중국, 유로존의 지표뿐만 아니라 원자재 및 크립토 시장까지 모니터링합니다.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="card feature-card text-center p-4">
                                    <i className="bi bi-shield-lock feature-icon"></i>
                                    <h5>리스크 관리</h5>
                                    <p className="small text-muted">괴리율(Drift) 체크, 충돌 방지 로직, 자동 에러 복구 등 다중 안전 장치를 탑재했습니다.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* English Content */}
                <div style={{ display: currentLang === 'EN' ? 'block' : 'none' }}>
                    <div className="hero-section text-center">
                        <div className="container">
                            <h1 className="hero-title display-4">AI-Driven Macro Trading</h1>
                            <p className="lead" style={{ maxWidth: '700px', margin: '0 auto' }}>
                                Hobot uses advanced AI to analyze global economic data and execute safe, strategic portfolio rebalancing.
                            </p>
                        </div>
                    </div>

                    <div className="container mb-5">
                        <div className="row mb-5">
                            <div className="col-lg-8 offset-lg-2">
                                <h2 className="text-center mb-4">Daily Workflow</h2>
                                <div className="workflow-timeline">
                                    <div className="workflow-item">
                                        <h4><span className="badge bg-primary">08:30</span> Market Analysis</h4>
                                        <p className="text-muted">
                                            Every morning before the market opens, Hobot's AI agents scan global economic indicators (FRED) and news from major economies (US, China, Eurozone). It determines the current market regime (Growth vs Inflation) and selects the optimal Model Portfolio (MP).
                                        </p>
                                    </div>
                                    <div className="workflow-item">
                                        <h4><span className="badge bg-warning text-dark">Verify</span> 3-Day Signal Check</h4>
                                        <p className="text-muted">
                                            To avoid reacting to market noise, Hobot validates signals over a 3-day period. Only when a trend is confirmed stable does it trigger a portfolio change.
                                            <br /><span className="safety-badge mt-2 d-inline-block"><i className="bi bi-shield-check"></i> Noise Filtering</span>
                                        </p>
                                    </div>
                                    <div className="workflow-item">
                                        <h4><span className="badge bg-success">09:40</span> Safe Execution</h4>
                                        <p className="text-muted">
                                            Rebalancing isn't instant. To minimize slippage and impact, trades are split over <b>5 days</b>. If market conditions change mid-execution, the system automatically adapts to protect assets.
                                            <br /><span className="safety-badge mt-2 d-inline-block"><i className="bi bi-graph-up-arrow"></i> 5-Day Split Entry</span>
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="row g-4">
                            <div className="col-md-4">
                                <div className="card feature-card text-center p-4">
                                    <i className="bi bi-cpu feature-icon"></i>
                                    <h5>AI Strategist</h5>
                                    <p className="small text-muted">Powered by Gemini Pro, analyzing complex macro data relationships that traditional quant models might miss.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="card feature-card text-center p-4">
                                    <i className="bi bi-globe-americas feature-icon"></i>
                                    <h5>Global Coverage</h5>
                                    <p className="small text-muted">Monitors indicators from the US (Fed), China, and Eurozone, plus commodities and crypto markets.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="card feature-card text-center p-4">
                                    <i className="bi bi-shield-lock feature-icon"></i>
                                    <h5>Risk Management</h5>
                                    <p className="small text-muted">Built-in safety checks for drift, conflict handling, and automated error recovery.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <footer className="bg-light py-4 mt-5 border-top">
                <div className="container text-center text-muted">
                    <p>&copy; 2026 Hobot Macro Service. All rights reserved.</p>
                    <p className="small">Powered by Ssho's Hobot Engine.</p>
                    <button
                        className="btn btn-sm btn-outline-secondary mt-2"
                        onClick={toggleLanguage}
                    >
                        <i className="bi bi-globe2 me-1"></i> {currentLang === 'KR' ? 'English' : '한국어'}
                    </button>
                </div>
            </footer>
        </div>
    );
};

export default AboutPage;
