import React, { useState } from 'react';
import { Globe, Database, Cpu, Shield, ChartLine, Lock, ShieldCheck, Key, Mail, ArrowRight, Network, ScanSearch, GitBranch, Sparkles, Waypoints } from 'lucide-react';

export const AboutPage: React.FC = () => {
    const [currentLang, setCurrentLang] = useState<'KR' | 'EN'>('KR');

    const toggleLanguage = () => {
        setCurrentLang(prev => prev === 'KR' ? 'EN' : 'KR');
    };

    const processSteps = [
        { num: '01', icon: Database, title: currentLang === 'KR' ? '데이터 수집' : 'Data Collection', desc: currentLang === 'KR' ? '거시경제 지표 (FRED, 뉴스) 수집' : 'Macro Indicators (FRED, News)' },
        { num: '02', icon: Cpu, title: currentLang === 'KR' ? 'AI 분석' : 'AI Analysis', desc: currentLang === 'KR' ? 'AI가 목표 MP, Sub-MP 분석' : 'AI determines Target MP & Sub-MP' },
        { num: '03', icon: Shield, title: currentLang === 'KR' ? '검증 및 안전장치' : 'Verification', desc: currentLang === 'KR' ? '3일 연속 신호 검증' : '3-Day Signal Verification' },
        { num: '04', icon: ChartLine, title: currentLang === 'KR' ? '운용 및 실행' : 'Execution', desc: currentLang === 'KR' ? '5일 분할 리밸런싱' : '5-Day Split Rebalancing' },
    ];

    const securityFeatures = [
        { icon: Lock, title: currentLang === 'KR' ? '데이터 암호화' : 'Data Encryption', desc: currentLang === 'KR' ? 'AES-256 알고리즘으로 암호화' : 'AES-256 encryption' },
        { icon: ShieldCheck, title: currentLang === 'KR' ? 'SSL 보안 통신' : 'SSL Secure Channel', desc: currentLang === 'KR' ? 'HTTPS(SSL/TLS) 보호' : 'HTTPS (SSL/TLS) protection' },
        { icon: Key, title: currentLang === 'KR' ? '접근 제어 (MFA)' : 'Access Control (MFA)', desc: currentLang === 'KR' ? '다단계 인증 및 IP 제어' : 'Multi-Factor Authentication' },
    ];

    const ontologyPipeline = [
        {
            step: '01',
            icon: Network,
            title: currentLang === 'KR' ? '온톨로지 그래프 구성' : 'Ontology Graph Construction',
            desc: currentLang === 'KR'
                ? '뉴스, 거시지표, 자산 데이터를 엔티티-관계 그래프로 정규화합니다.'
                : 'Normalizes news, macro indicators, and assets into a unified entity-relation graph.',
        },
        {
            step: '02',
            icon: ScanSearch,
            title: currentLang === 'KR' ? '시그널 패턴 탐색' : 'Signal Pattern Discovery',
            desc: currentLang === 'KR'
                ? '상승/하락/변동성 신호를 연결 구조에서 탐색해 핵심 원인을 추출합니다.'
                : 'Discovers up/down/volatility patterns from graph connectivity and extracts key drivers.',
        },
        {
            step: '03',
            icon: GitBranch,
            title: currentLang === 'KR' ? '인과 경로 추론' : 'Causal Path Reasoning',
            desc: currentLang === 'KR'
                ? '금리, 고용, 물가, 유동성이 포트폴리오에 미치는 파급 경로를 추론합니다.'
                : 'Infers how rates, labor, inflation, and liquidity propagate into portfolio decisions.',
        },
        {
            step: '04',
            icon: Waypoints,
            title: currentLang === 'KR' ? '전략 액션 연결' : 'Strategy Action Mapping',
            desc: currentLang === 'KR'
                ? '추론 결과를 MP/Sub-MP 판단 근거와 리밸런싱 액션으로 연결합니다.'
                : 'Maps reasoning outputs to MP/Sub-MP rationale and actionable rebalancing signals.',
        },
    ];

    const ontologyOutputs = [
        {
            tag: currentLang === 'KR' ? '핵심 연결' : 'Core Link',
            title: currentLang === 'KR' ? '리스크 전이 경로' : 'Risk Transmission Path',
            desc: currentLang === 'KR'
                ? '어떤 거시 이벤트가 어떤 자산군을 통해 포트폴리오에 영향을 주는지 시각화'
                : 'Visual path from macro events to portfolio impact through each asset class',
        },
        {
            tag: currentLang === 'KR' ? '설명 가능성' : 'Explainability',
            title: currentLang === 'KR' ? '근거 기반 요약' : 'Evidence-Based Summary',
            desc: currentLang === 'KR'
                ? '분석 결과를 일반 투자자도 이해 가능한 문장으로 구조화'
                : 'Transforms model outputs into investor-friendly natural language explanations',
        },
        {
            tag: currentLang === 'KR' ? '실행 연결' : 'Execution',
            title: currentLang === 'KR' ? '전략 반영 우선순위' : 'Strategy Priority Queue',
            desc: currentLang === 'KR'
                ? '즉시 반영, 관찰 유지, 리스크 헤지 등 액션 우선순위를 제공'
                : 'Provides priority actions such as immediate rebalance, monitor, and hedge',
        },
    ];

    return (
        <div className="min-h-screen bg-slate-50">
            {/* Hero Section */}
            <section className="relative py-24 overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-b from-blue-50 to-white" />
                <div className="max-w-5xl mx-auto px-6 text-center relative z-10">
                    <button
                        onClick={toggleLanguage}
                        className="mb-6 px-4 py-2 bg-white border border-zinc-200 rounded-full text-sm text-zinc-600 hover:bg-slate-50 transition-all flex items-center gap-2 mx-auto shadow-sm"
                    >
                        <Globe className="h-4 w-4" />
                        {currentLang === 'KR' ? 'English' : '한국어'}
                    </button>

                    <span className="inline-block px-4 py-1.5 bg-blue-100 text-blue-600 text-sm font-semibold rounded-full mb-6 border border-blue-200">
                        AI-Powered Asset Management
                    </span>

                    <h1 className="text-4xl md:text-5xl font-bold text-zinc-900 mb-6 leading-tight">
                        {currentLang === 'KR' ? '데이터 기반의 똑똑한 투자' : 'Intelligent Data-Driven Investing'}
                    </h1>

                    <p className="text-lg text-zinc-600 max-w-2xl mx-auto leading-relaxed">
                        {currentLang === 'KR'
                            ? 'Stockoverflow는 글로벌 경제 지표와 뉴스를 실시간으로 분석하여 가장 안전하고 확실한 리밸런싱 전략을 제안합니다.'
                            : 'Stockoverflow analyzes global economic indicators and news in real-time to execute the safest and most strategic asset rebalancing.'}
                    </p>
                </div>
            </section>

            {/* Why Stockoverflow */}
            <section className="py-20 px-6 bg-white">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-2xl md:text-3xl font-bold text-zinc-900 mb-6">
                        {currentLang === 'KR' ? '왜 Stockoverflow인가요?' : 'Why Stockoverflow?'}
                    </h2>
                    <p className="text-lg text-blue-600 font-semibold mb-6">
                        {currentLang === 'KR'
                            ? '"수익률 극대화와 안정적 수익, 두 마리 토끼를 모두 잡습니다."'
                            : '"Maximizing Returns & Ensuring Stability. You can have both."'}
                    </p>
                    <p className="text-zinc-600 leading-relaxed">
                        {currentLang === 'KR'
                            ? '단순한 분산 투자가 아닙니다. Stockoverflow는 거시경제(Macro) 데이터를 기반으로 목표 비중을 정하므로, 시장의 상황에 맞게 능동적으로 포트폴리오를 재구성합니다.'
                            : 'It goes beyond simple diversification. By determining target weights based on Macroeconomic Data, Stockoverflow actively reconfigures your portfolio to suit market conditions.'}
                    </p>
                </div>
            </section>

            {/* Core Engine & Logic */}
            <section className="py-20 px-6 bg-slate-50">
                <div className="max-w-6xl mx-auto">
                    <h2 className="text-2xl md:text-3xl font-bold text-zinc-900 mb-12 text-center">
                        {currentLang === 'KR' ? '핵심 엔진 & 로직' : 'Core Engine & Logic'}
                    </h2>

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                        {processSteps.map((step, idx) => (
                            <div key={step.num} className="relative">
                                <div className="bg-white border border-zinc-200 rounded-2xl p-6 text-center hover:border-blue-400 transition-all shadow-sm">
                                    <div className="text-blue-600 text-xs font-bold mb-3">{step.num}</div>
                                    <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mx-auto mb-4">
                                        <step.icon className="h-6 w-6 text-blue-600" />
                                    </div>
                                    <h4 className="text-zinc-900 font-semibold mb-2">{step.title}</h4>
                                    <p className="text-sm text-zinc-500">{step.desc}</p>
                                </div>
                                {idx < processSteps.length - 1 && (
                                    <div className="hidden md:flex absolute top-1/2 -right-3 transform -translate-y-1/2 z-10">
                                        <ArrowRight className="h-5 w-5 text-zinc-300" />
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Ontology Intelligence */}
            <section className="relative py-20 px-6 overflow-hidden bg-slate-950">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.22),transparent_40%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.2),transparent_45%)]" />
                <div className="max-w-6xl mx-auto relative z-10">
                    <div className="text-center mb-12">
                        <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-cyan-500/10 border border-cyan-300/20 text-cyan-200 text-sm font-semibold">
                            <Sparkles className="h-4 w-4" />
                            {currentLang === 'KR' ? 'Ontology Intelligence Layer' : 'Ontology Intelligence Layer'}
                        </span>
                        <h2 className="mt-5 text-2xl md:text-3xl font-bold text-white">
                            {currentLang === 'KR' ? '온톨로지 분석 엔진' : 'Ontology Analysis Engine'}
                        </h2>
                        <p className="mt-4 text-slate-300 max-w-3xl mx-auto leading-relaxed">
                            {currentLang === 'KR'
                                ? 'Stockoverflow는 단순 지표 해석을 넘어, 이벤트-지표-자산 간 연결 관계를 온톨로지 그래프로 분석해 왜 이런 전략이 나왔는지까지 설명합니다.'
                                : 'Stockoverflow goes beyond indicator interpretation by modeling event-indicator-asset relationships as an ontology graph and explaining why each strategy is selected.'}
                        </p>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                        <div className="lg:col-span-3 rounded-2xl border border-white/15 bg-white/5 backdrop-blur-sm p-6">
                            <h3 className="text-lg font-semibold text-white mb-5">
                                {currentLang === 'KR' ? '분석 파이프라인' : 'Analysis Pipeline'}
                            </h3>
                            <div className="space-y-4">
                                {ontologyPipeline.map((item) => (
                                    <div
                                        key={item.step}
                                        className="rounded-xl border border-white/10 bg-slate-900/70 px-4 py-4 flex items-start gap-4"
                                    >
                                        <div className="w-9 h-9 rounded-lg bg-cyan-400/15 border border-cyan-300/30 flex items-center justify-center flex-shrink-0">
                                            <item.icon className="h-4 w-4 text-cyan-200" />
                                        </div>
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-xs font-bold text-cyan-200/90 tracking-wide">{item.step}</span>
                                                <h4 className="text-sm md:text-base font-semibold text-white">{item.title}</h4>
                                            </div>
                                            <p className="text-sm text-slate-300 leading-relaxed">{item.desc}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="lg:col-span-2 space-y-6">
                            <div className="rounded-2xl border border-white/15 bg-white/5 backdrop-blur-sm p-6">
                                <h3 className="text-lg font-semibold text-white mb-4">
                                    {currentLang === 'KR' ? '사용자에게 제공되는 분석 결과' : 'What Users Receive'}
                                </h3>
                                <div className="space-y-3">
                                    {ontologyOutputs.map((item) => (
                                        <div key={item.title} className="rounded-lg border border-white/10 bg-slate-900/60 p-3">
                                            <span className="inline-block text-[11px] px-2 py-1 rounded-md bg-blue-500/20 text-blue-100 border border-blue-300/20 mb-2">
                                                {item.tag}
                                            </span>
                                            <h4 className="text-sm font-semibold text-white mb-1">{item.title}</h4>
                                            <p className="text-xs text-slate-300 leading-relaxed">{item.desc}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="rounded-2xl border border-cyan-300/20 bg-gradient-to-br from-cyan-500/10 via-blue-500/10 to-slate-900 p-5">
                                <p className="text-[11px] tracking-[0.2em] text-cyan-200 uppercase font-bold mb-2">
                                    {currentLang === 'KR' ? 'AI Narrative' : 'AI Narrative'}
                                </p>
                                <p className="text-sm text-slate-100 leading-relaxed">
                                    {currentLang === 'KR'
                                        ? '“지표가 어떻게 연결되어 현재 전략으로 이어졌는지”를 한 눈에 이해할 수 있도록, 복잡한 그래프 추론 결과를 자연어 설명과 실행 우선순위로 변환합니다.'
                                        : '"How indicators connect to today’s strategy" is translated into natural language explanations and prioritized actions from complex graph reasoning.'}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Security */}
            <section className="py-20 px-6 bg-white">
                <div className="max-w-5xl mx-auto">
                    <h2 className="text-2xl md:text-3xl font-bold text-zinc-900 mb-12 text-center">
                        {currentLang === 'KR' ? '엔터프라이즈급 보안' : 'Enterprise-Grade Security'}
                    </h2>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {securityFeatures.map((feature) => (
                            <div
                                key={feature.title}
                                className="bg-slate-50 border border-zinc-200 rounded-2xl p-6 text-center hover:border-emerald-400 transition-all shadow-sm"
                            >
                                <div className="w-14 h-14 bg-emerald-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                                    <feature.icon className="h-7 w-7 text-emerald-600" />
                                </div>
                                <h5 className="text-zinc-900 font-semibold mb-2">{feature.title}</h5>
                                <p className="text-sm text-zinc-500">{feature.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Live Screenshots */}
            <section className="py-20 px-6 bg-slate-50">
                <div className="max-w-6xl mx-auto">
                    <h2 className="text-2xl md:text-3xl font-bold text-zinc-900 mb-4 text-center">
                        {currentLang === 'KR' ? '실제 운영 화면' : 'Live Screenshots'}
                    </h2>
                    <p className="text-zinc-500 text-center mb-12">
                        {currentLang === 'KR'
                            ? '현재 실제로 운영 중인 Trading Dashboard의 화면입니다.'
                            : 'Screenshots from our live Trading Dashboard in production.'}
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Dashboard Overview */}
                        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden hover:shadow-lg transition-all">
                            <img
                                src="/screenshots/dashboard_overview.png"
                                alt="Dashboard Overview"
                                className="w-full h-auto"
                            />
                            <div className="p-4 border-t border-zinc-100">
                                <h4 className="font-semibold text-zinc-900">
                                    {currentLang === 'KR' ? '대시보드 개요' : 'Dashboard Overview'}
                                </h4>
                                <p className="text-sm text-zinc-500 mt-1">
                                    {currentLang === 'KR'
                                        ? '총 평가금액, 수익률, 자산 추이를 한눈에 확인'
                                        : 'Total valuation, returns, and asset trends at a glance'}
                                </p>
                            </div>
                        </div>

                        {/* Portfolio Holdings */}
                        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden hover:shadow-lg transition-all">
                            <img
                                src="/screenshots/portfolio_holdings.png"
                                alt="Portfolio Holdings"
                                className="w-full h-auto"
                            />
                            <div className="p-4 border-t border-zinc-100">
                                <h4 className="font-semibold text-zinc-900">
                                    {currentLang === 'KR' ? '보유 종목' : 'Portfolio Holdings'}
                                </h4>
                                <p className="text-sm text-zinc-500 mt-1">
                                    {currentLang === 'KR'
                                        ? '개별 종목별 수량, 현재가, 평가금액, 수익률 현황'
                                        : 'Individual holdings with quantity, price, valuation, and returns'}
                                </p>
                            </div>
                        </div>

                        {/* Rebalancing Status */}
                        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden hover:shadow-lg transition-all">
                            <img
                                src="/screenshots/rebalancing_status.png"
                                alt="Rebalancing Status"
                                className="w-full h-auto"
                            />
                            <div className="p-4 border-t border-zinc-100">
                                <h4 className="font-semibold text-zinc-900">
                                    {currentLang === 'KR' ? '리밸런싱 현황' : 'Rebalancing Status'}
                                </h4>
                                <p className="text-sm text-zinc-500 mt-1">
                                    {currentLang === 'KR'
                                        ? 'AI 분석 기반 목표(Target) vs 실제(Actual) 비중 비교'
                                        : 'AI-driven Target vs Actual allocation comparison'}
                                </p>
                            </div>
                        </div>

                        {/* Sub-MP Details */}
                        <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden hover:shadow-lg transition-all">
                            <img
                                src="/screenshots/sub_mp_details.png"
                                alt="Sub-MP Details"
                                className="w-full h-auto"
                            />
                            <div className="p-4 border-t border-zinc-100">
                                <h4 className="font-semibold text-zinc-900">
                                    {currentLang === 'KR' ? 'Sub-MP 상세' : 'Sub-MP Details'}
                                </h4>
                                <p className="text-sm text-zinc-500 mt-1">
                                    {currentLang === 'KR'
                                        ? '주식, 채권, 대체, 현금 각 자산군별 세부 비중'
                                        : 'Detailed breakdown by Stocks, Bonds, Alternatives, and Cash'}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="py-12 border-t border-zinc-200 bg-white">
                <div className="max-w-5xl mx-auto px-6 text-center">
                    <p className="text-zinc-500 text-sm mb-2">
                        © {new Date().getFullYear()} Stockoverflow Macro Service. All rights reserved.
                    </p>
                    <div className="flex items-center justify-center gap-2 text-zinc-400 text-sm">
                        <span>Created by <strong className="text-zinc-600">Seungho Shin</strong></span>
                        <span>•</span>
                        <a href="mailto:90shins@gmail.com" className="text-blue-600 hover:underline flex items-center gap-1">
                            <Mail className="h-3 w-3" /> 90shins@gmail.com
                        </a>
                    </div>
                </div>
            </footer>
        </div>
    );
};

export default AboutPage;
