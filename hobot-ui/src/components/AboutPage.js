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
                                    <i className="bi bi-translate"></i> {currentLang === 'KR' ? 'English' : '한국어'}
                                </button>
                            </div>
                            <span className="hero-badge">AI-Powered Trading</span>
                            <h1 className="hero-title display-4">AI 기반 거시경제 자동매매</h1>
                            <p className="hero-subtitle">
                                데이터와 AI가 만나는 곳에서 시작되는<br />
                                가장 스마트한 자산 관리 솔루션 Hobot
                            </p>
                        </div>
                    </section>

                    <section className="container mb-5 feature-section">
                        <div className="row g-4">
                            <div className="col-md-4">
                                <div className="modern-card">
                                    <div className="icon-wrapper">
                                        <i className="bi bi-cpu feature-icon"></i>
                                    </div>
                                    <h5>AI 전략가</h5>
                                    <p>Gemini Pro가 복잡한 거시경제 지표와 뉴스를 분석하여 최적의 전략을 도출합니다.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="modern-card">
                                    <div className="icon-wrapper">
                                        <i className="bi bi-globe-americas feature-icon"></i>
                                    </div>
                                    <h5>글로벌 커버리지</h5>
                                    <p>미국, 중국, 유로존의 경제 데이터와 원자재, 크립토 시장까지 실시간 모니터링합니다.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="modern-card">
                                    <div className="icon-wrapper">
                                        <i className="bi bi-shield-lock feature-icon"></i>
                                    </div>
                                    <h5>리스크 관리</h5>
                                    <p>Drift 감지 및 자동 방어 로직으로 변동성 높은 시장에서도 자산을 안전하게 보호합니다.</p>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="container mb-5">
                        <div className="row">
                            <div className="col-lg-10 offset-lg-1">
                                <div className="workflow-container">
                                    <h2 className="text-center mb-5 section-title">Daily Workflow</h2>
                                    <div className="workflow-timeline modern-timeline">
                                        <div className="workflow-item">
                                            <div className="time-badge">08:30</div>
                                            <div className="workflow-content">
                                                <h4>시장 정밀 분석</h4>
                                                <p>장 시작 전, AI가 주요 경제 지표(FRED)와 글로벌 뉴스를 분석하여 시장 국면을 진단합니다.</p>
                                            </div>
                                        </div>
                                        <div className="workflow-item">
                                            <div className="time-badge warning">Verify</div>
                                            <div className="workflow-content">
                                                <h4>3일 신호 검증</h4>
                                                <p>일시적 노이즈를 배제하기 위해 신호가 3일 이상 지속될 때만 포트폴리오 변경을 승인합니다.</p>
                                                <span className="safety-tag"><i className="bi bi-shield-check"></i> 노이즈 필터링</span>
                                            </div>
                                        </div>
                                        <div className="workflow-item">
                                            <div className="time-badge success">09:40</div>
                                            <div className="workflow-content">
                                                <h4>안전한 분할 실행</h4>
                                                <p>시장 충격 최소화를 위해 5일간 분할 매매를 수행하며, 돌발 변수에 실시간 대응합니다.</p>
                                                <span className="safety-tag"><i className="bi bi-graph-up-arrow"></i> 5일 분할 진입</span>
                                            </div>
                                        </div>
                                    </div>
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
                                    <i className="bi bi-translate"></i> {currentLang === 'KR' ? 'English' : '한국어'}
                                </button>
                            </div>
                            <span className="hero-badge">AI-Powered Trading</span>
                            <h1 className="hero-title display-4">Intelligent Macro Trading</h1>
                            <p className="hero-subtitle">
                                Where Data Meets AI.<br />
                                The smartest way to manage your assets with Hobot.
                            </p>
                        </div>
                    </section>

                    <section className="container mb-5 feature-section">
                        <div className="row g-4">
                            <div className="col-md-4">
                                <div className="modern-card">
                                    <div className="icon-wrapper">
                                        <i className="bi bi-cpu feature-icon"></i>
                                    </div>
                                    <h5>AI Strategist</h5>
                                    <p>Gemini Pro analyzes complex macro indicators and news to derive optimal strategies.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="modern-card">
                                    <div className="icon-wrapper">
                                        <i className="bi bi-globe-americas feature-icon"></i>
                                    </div>
                                    <h5>Global Coverage</h5>
                                    <p>Real-time monitoring of US, China, Eurozone data, plus commodities and crypto markets.</p>
                                </div>
                            </div>
                            <div className="col-md-4">
                                <div className="modern-card">
                                    <div className="icon-wrapper">
                                        <i className="bi bi-shield-lock feature-icon"></i>
                                    </div>
                                    <h5>Risk Management</h5>
                                    <p>Drift detection and auto-defense logic keep your assets safe in volatile markets.</p>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="container mb-5">
                        <div className="row">
                            <div className="col-lg-10 offset-lg-1">
                                <div className="workflow-container">
                                    <h2 className="text-center mb-5 section-title">Daily Workflow</h2>
                                    <div className="workflow-timeline modern-timeline">
                                        <div className="workflow-item">
                                            <div className="time-badge">08:30</div>
                                            <div className="workflow-content">
                                                <h4>Market Analysis</h4>
                                                <p>AI scans global indicators (FRED) and news to diagnose the market regime before opening.</p>
                                            </div>
                                        </div>
                                        <div className="workflow-item">
                                            <div className="time-badge warning">Verify</div>
                                            <div className="workflow-content">
                                                <h4>3-Day Verification</h4>
                                                <p>Signals must persist for 3+ days to filter out temporary market noise.</p>
                                                <span className="safety-tag"><i className="bi bi-shield-check"></i> Noise Filtering</span>
                                            </div>
                                        </div>
                                        <div className="workflow-item">
                                            <div className="time-badge success">09:40</div>
                                            <div className="workflow-content">
                                                <h4>Safe Execution</h4>
                                                <p>Trades are split over 5 days to minimize impact, with real-time adaptation.</p>
                                                <span className="safety-tag"><i className="bi bi-graph-up-arrow"></i> 5-Day Split Entry</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section>
                </div>
            </div>

            <footer className="modern-footer">
                <div className="container text-center">
                    <div className="footer-content">
                        <p className="copyright">&copy; {new Date().getFullYear()} Hobot Macro Service. All rights reserved.</p>
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
