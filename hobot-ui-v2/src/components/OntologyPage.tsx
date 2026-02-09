import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { runCypherQuery } from '../services/neo4jService';
import { generateCypherFromNaturalLanguage, explainQueryResults, getOntologyQueryLimit, type QueryLimitInfo } from '../services/geminiService';
import {
    fetchGraphRagAnswer,
    fetchGraphRagContext,
    type GraphRagAnswerResponse,
    type GraphRagCitation,
    type GraphRagEvidence,
    type GraphRagContextResponse,
    type TimeRange,
} from '../services/graphRagService';
import {
    AlertCircle,
    ChevronDown,
    ChevronUp,
    Code,
    Database,
    ExternalLink,
    FileText,
    Filter,
    Loader2,
    Lock,
    MessageSquare,
    PanelRightClose,
    PanelRightOpen,
    Play,
    Route,
    Send,
    Sparkles,
    Terminal,
    TrendingUp,
    X
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface ChatMessage {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    cypher?: string;
    timestamp: Date;
    rag?: {
        model: string;
        uncertainty: string;
        keyPoints: string[];
        citations: GraphRagCitation[];
    };
}

interface IndicatorPoint {
    obsDate: string;
    value: number;
}

interface MacroPresetQuery {
    id: string;
    name: string;
    description: string;
    query: string;
}

type MacroAnswerModel = 'gemini-3-flash-preview' | 'gemini-3-pro-preview';
const MACRO_ANSWER_MODEL_STORAGE_KEY = 'ontology.macro.answerModel';

const macroPresetQueries: MacroPresetQuery[] = [
    {
        id: 'theme-indicator',
        name: '테마-지표',
        description: 'MacroTheme와 EconomicIndicator 관계',
        query: `MATCH (t:MacroTheme)<-[r:BELONGS_TO]-(i:EconomicIndicator) RETURN t, r, i`
    },
    {
        id: 'news-theme-indicator',
        name: '뉴스-테마-지표',
        description: 'Document가 참조하는 Theme과 Indicator',
        query: `MATCH (d:Document)-[r1:ABOUT_THEME]->(t:MacroTheme)<-[r2:BELONGS_TO]-(i:EconomicIndicator) RETURN d, r1, t, r2, i LIMIT 200`
    },
    {
        id: 'entity-network',
        name: 'Entity 네트워크',
        description: '주요 기관/인물과 Alias, 뉴스 연결',
        query: `MATCH (e:Entity)-[r1:HAS_ALIAS]->(a:EntityAlias) OPTIONAL MATCH (d:Document)-[r2:MENTIONS]->(e) RETURN e, r1, a, d, r2 LIMIT 150`
    },
    {
        id: 'rates-ecosystem',
        name: 'Rates 에코시스템',
        description: '금리 테마의 지표와 최근 Observation',
        query: `MATCH (t:MacroTheme {theme_id: 'rates'})<-[r1:BELONGS_TO]-(i:EconomicIndicator)-[r2:HAS_OBSERVATION]->(o:IndicatorObservation) WHERE o.obs_date >= date() - duration({days: 14}) RETURN t, r1, i, r2, o LIMIT 200`
    },
    {
        id: 'multi-layer',
        name: '다층 관계',
        description: 'Theme + Indicator + Document + Entity 연결',
        query: `MATCH (t:MacroTheme)<-[r1:BELONGS_TO]-(i:EconomicIndicator) OPTIONAL MATCH (d:Document)-[r2:ABOUT_THEME]->(t) OPTIONAL MATCH (d)-[r3:MENTIONS]->(e:Entity) RETURN t, r1, i, d, r2, e, r3 LIMIT 200`
    },
    {
        id: 'derived-features',
        name: '파생 피처',
        description: '지표 + Observation + DerivedFeature 연결',
        query: `MATCH (i:EconomicIndicator)-[r1:HAS_OBSERVATION]->(o:IndicatorObservation)-[r2:HAS_FEATURE]->(f:DerivedFeature) WHERE o.obs_date >= date() - duration({days: 7}) RETURN i, r1, o, r2, f LIMIT 300`
    }
];

const macroQuestionTemplates = [
    '최근 7일간 인플레이션 리스크를 높인 이벤트/뉴스는?',
    '유동성 악화(NETLIQ 하락)와 관련된 상위 원인은?',
    '금리 인상 → 신용 스프레드 확대 경로가 최근 관측되는가?',
    '최근 30일 기준 테마별 핵심 Story를 근거 문서와 함께 요약해줘',
    'Growth 테마와 가장 강하게 연결된 지표 변화는?',
    '최근 이벤트 중 리스크 자산에 부정적인 시그널만 추려줘',
    'Labor 관련 이벤트가 물가 지표에 준 영향 경로를 보여줘',
    '향후 1~2주 리밸런싱에 참고할 Macro Narrative Top 3를 알려줘'
];

const getLinkEndpointId = (value: any): string => {
    if (!value) return '';
    if (typeof value === 'string') return value;
    if (typeof value === 'object' && value.id) return String(value.id);
    return String(value);
};

const toLinkKey = (source: string, relationType: string, target: string): string =>
    `${source}->${relationType}->${target}`;

const normalizeDateInput = (value: Date): string => value.toISOString().slice(0, 10);

const getCitationConfidence = (citation: GraphRagCitation): 'high' | 'medium' | 'low' => {
    const labels = citation.support_labels || [];
    if (labels.includes('Fact')) return 'high';
    if (labels.includes('Claim')) return 'medium';
    return 'low';
};

const contextToGraphData = (context: GraphRagContextResponse): { nodes: any[]; links: any[] } => {
    const nodes = context.nodes.map((node) => ({
        id: node.id,
        labels: [node.type],
        properties: {
            ...node.properties,
            _display_label: node.label,
            _node_type: node.type,
        },
        val: 1,
    }));

    const links = context.links.map((link) => ({
        source: link.source,
        target: link.target,
        type: link.type,
        ...link.properties,
    }));

    return { nodes, links };
};

const renderSparkline = (points: IndicatorPoint[]) => {
    if (points.length < 2) {
        return <p className="text-[11px] text-gray-400">시계열 데이터가 부족합니다.</p>;
    }

    const width = 220;
    const height = 64;
    const minValue = Math.min(...points.map((point) => point.value));
    const maxValue = Math.max(...points.map((point) => point.value));
    const valueRange = maxValue - minValue || 1;

    const coords = points
        .map((point, index) => {
            const x = (index / (points.length - 1)) * (width - 12) + 6;
            const normalized = (point.value - minValue) / valueRange;
            const y = height - (normalized * (height - 12) + 6);
            return `${x},${y}`;
        })
        .join(' ');

    return (
        <svg width={width} height={height} className="rounded border border-gray-100 bg-white">
            <polyline
                points={coords}
                fill="none"
                stroke="#4f46e5"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
};

const OntologyPage: React.FC<{ mode?: 'architecture' | 'macro' }> = ({ mode = 'architecture' }) => {
    const { isAuthenticated, user } = useAuth();
    const isAdmin = user?.role === 'admin';

    // Chat state
    const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
    const [userInput, setUserInput] = useState('');
    const [chatLoading, setChatLoading] = useState(false);
    const [showCypher, setShowCypher] = useState<string | null>(null);
    const chatEndRef = useRef<HTMLDivElement>(null);

    // Query limit state
    const [queryLimit, setQueryLimit] = useState<QueryLimitInfo | null>(null);

    // Graph state
    const [graphData, setGraphData] = useState<{ nodes: any[]; links: any[] }>({ nodes: [], links: [] });
    const [selectedNode, setSelectedNode] = useState<any | null>(null);
    const [graphLoading, setGraphLoading] = useState(false);
    const [graphError, setGraphError] = useState<string | null>(null);
    const graphContainerRef = useRef<HTMLDivElement>(null);
    const [graphDimensions, setGraphDimensions] = useState({ width: 800, height: 600 });

    // Sidebar state
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [activePreset, setActivePreset] = useState<string | null>(null);

    // Cypher Query Input state
    const [cypherQueryOpen, setCypherQueryOpen] = useState(false);
    const [cypherInput, setCypherInput] = useState('');
    const [cypherError, setCypherError] = useState<string | null>(null);
    const [lastExecutedQuery, setLastExecutedQuery] = useState<string | null>(null);

    // Macro GraphRAG state (D-3)
    const [macroTimeRange, setMacroTimeRange] = useState<TimeRange>('30d');
    const [macroCountry, setMacroCountry] = useState<string>('all');
    const [macroCategory, setMacroCategory] = useState<string>('all');
    const [macroTheme, setMacroTheme] = useState<string>('all');
    const [macroConfidence, setMacroConfidence] = useState<'all' | 'high' | 'medium' | 'low'>('all');
    const [macroTopK, setMacroTopK] = useState<number>(50);
    const [macroAsOfDate, setMacroAsOfDate] = useState<string>(normalizeDateInput(new Date()));
    const [macroAnswerModel, setMacroAnswerModel] = useState<MacroAnswerModel>(() => {
        if (typeof window === 'undefined') {
            return 'gemini-3-flash-preview';
        }

        const stored = window.localStorage.getItem(MACRO_ANSWER_MODEL_STORAGE_KEY);
        if (stored === 'gemini-3-flash-preview' || stored === 'gemini-3-pro-preview') {
            return stored;
        }
        return 'gemini-3-flash-preview';
    });
    const [macroAnswer, setMacroAnswer] = useState<GraphRagAnswerResponse | null>(null);
    const [macroEvidences, setMacroEvidences] = useState<GraphRagEvidence[]>([]);
    const [macroSuggestedQueries, setMacroSuggestedQueries] = useState<string[]>([]);
    const [macroPathwayIndex, setMacroPathwayIndex] = useState<number>(-1);
    const [citationPage, setCitationPage] = useState<number>(1);
    const [highlightedNodeIds, setHighlightedNodeIds] = useState<string[]>([]);
    const [highlightedLinkKeys, setHighlightedLinkKeys] = useState<string[]>([]);

    // Indicator side panel state
    const [indicatorSeries, setIndicatorSeries] = useState<IndicatorPoint[]>([]);
    const [indicatorLoading, setIndicatorLoading] = useState(false);
    const [indicatorError, setIndicatorError] = useState<string | null>(null);

    // Reset state when mode changes
    useEffect(() => {
        setChatMessages([]);
        setGraphData({ nodes: [], links: [] });
        setSelectedNode(null);
        setGraphError(null);
        setMacroAnswer(null);
        setMacroEvidences([]);
        setMacroSuggestedQueries([]);
        setMacroPathwayIndex(-1);
        setHighlightedNodeIds([]);
        setHighlightedLinkKeys([]);
        loadDefaultGraph();
    }, [mode]);

    // Fetch query limit when authenticated
    useEffect(() => {
        if (isAuthenticated) {
            fetchQueryLimit();
        } else {
            setQueryLimit(null);
        }
    }, [isAuthenticated]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem(MACRO_ANSWER_MODEL_STORAGE_KEY, macroAnswerModel);
    }, [macroAnswerModel]);

    // Resize observer for graph
    useEffect(() => {
        const resizeObserver = new ResizeObserver((entries) => {
            if (entries[0]) {
                setGraphDimensions({
                    width: entries[0].contentRect.width,
                    height: entries[0].contentRect.height,
                });
            }
        });

        if (graphContainerRef.current) {
            resizeObserver.observe(graphContainerRef.current);
        }

        return () => resizeObserver.disconnect();
    }, [sidebarOpen, selectedNode]);

    // Auto-scroll chat to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages]);

    const highlightedNodeSet = useMemo(() => new Set(highlightedNodeIds), [highlightedNodeIds]);
    const highlightedLinkSet = useMemo(() => new Set(highlightedLinkKeys), [highlightedLinkKeys]);

    const fetchQueryLimit = async () => {
        const limit = await getOntologyQueryLimit();
        setQueryLimit(limit);
    };

    const loadDefaultGraph = async () => {
        setGraphLoading(true);
        setGraphError(null);
        try {
            const query = mode === 'architecture'
                ? 'MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 100'
                : 'MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 120';

            const result = await runCypherQuery(query, {}, mode);
            setGraphData({ nodes: result.nodes, links: result.links });
        } catch (error: any) {
            setGraphError(error.message || 'Failed to load graph data.');
        } finally {
            setGraphLoading(false);
        }
    };

    const executePresetQuery = async (preset: MacroPresetQuery) => {
        setGraphLoading(true);
        setGraphError(null);
        setActivePreset(preset.id);
        setCypherInput(preset.query);
        setLastExecutedQuery(preset.query);
        try {
            const result = await runCypherQuery(preset.query, {}, mode);
            setGraphData({ nodes: result.nodes, links: result.links });
            setMacroAnswer(null);
            setMacroPathwayIndex(-1);
            setHighlightedNodeIds([]);
            setHighlightedLinkKeys([]);
        } catch (error: any) {
            setGraphError(error.message || 'Failed to execute query.');
        } finally {
            setGraphLoading(false);
        }
    };

    const executeCypherQuery = async () => {
        if (!cypherInput.trim()) return;

        setGraphLoading(true);
        setGraphError(null);
        setCypherError(null);
        setActivePreset(null);
        setLastExecutedQuery(cypherInput.trim());

        try {
            const result = await runCypherQuery(cypherInput.trim(), {}, mode);
            setGraphData({ nodes: result.nodes, links: result.links });
            setMacroAnswer(null);
            setMacroPathwayIndex(-1);
            setHighlightedNodeIds([]);
            setHighlightedLinkKeys([]);
        } catch (error: any) {
            setCypherError(error.message || 'Cypher 쿼리 실행 실패');
            setGraphError(error.message || 'Failed to execute query.');
        } finally {
            setGraphLoading(false);
        }
    };

    const handleCypherKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            executeCypherQuery();
        }
    };

    const docMetaByDocId = useMemo(() => {
        const map = new Map<string, { country?: string; category?: string }>();
        graphData.nodes.forEach((node: any) => {
            const labels: string[] = node.labels || [];
            if (!labels.includes('Document')) return;
            const docId = node.properties?.doc_id;
            if (!docId) return;
            map.set(String(docId), {
                country: node.properties?.country ? String(node.properties.country) : undefined,
                category: node.properties?.category ? String(node.properties.category) : undefined,
            });
        });
        return map;
    }, [graphData.nodes]);

    const eventThemesMap = useMemo(() => {
        const map = new Map<string, Set<string>>();
        graphData.links.forEach((link: any) => {
            const sourceId = getLinkEndpointId(link.source);
            const targetId = getLinkEndpointId(link.target);
            if (!sourceId.startsWith('event:') || !targetId.startsWith('theme:') || link.type !== 'ABOUT_THEME') {
                return;
            }
            if (!map.has(sourceId)) {
                map.set(sourceId, new Set<string>());
            }
            map.get(sourceId)?.add(targetId.replace('theme:', ''));
        });
        return map;
    }, [graphData.links]);

    const availableCountries = useMemo(() => {
        const values = new Set<string>();
        graphData.nodes.forEach((node: any) => {
            const country = node.properties?.country;
            if (country) values.add(String(country));
        });
        return Array.from(values).sort();
    }, [graphData.nodes]);

    const availableCategories = useMemo(() => {
        const values = new Set<string>();
        graphData.nodes.forEach((node: any) => {
            const category = node.properties?.category;
            if (category) values.add(String(category));
        });
        macroEvidences.forEach((evidence) => {
            if (evidence.doc_category) values.add(evidence.doc_category);
        });
        return Array.from(values).sort();
    }, [graphData.nodes, macroEvidences]);

    const availableThemes = useMemo(() => {
        const values = new Set<string>();
        graphData.nodes.forEach((node: any) => {
            const labels: string[] = node.labels || [];
            if (!labels.includes('MacroTheme')) return;
            const themeId = node.properties?.theme_id;
            if (themeId) values.add(String(themeId));
        });
        return Array.from(values).sort();
    }, [graphData.nodes]);

    const filteredCitations = useMemo(() => {
        if (!macroAnswer) return [];

        return macroAnswer.citations.filter((citation) => {
            if (macroConfidence !== 'all' && getCitationConfidence(citation) !== macroConfidence) {
                return false;
            }

            if (macroCountry !== 'all' && citation.doc_id) {
                const country = docMetaByDocId.get(citation.doc_id)?.country;
                if (country && country !== macroCountry) {
                    return false;
                }
            }

            if (macroCategory !== 'all' && citation.doc_id) {
                const category = citation.doc_id ? docMetaByDocId.get(citation.doc_id)?.category : undefined;
                const fallbackCategory = macroEvidences.find((evidence) => evidence.doc_id === citation.doc_id)?.doc_category;
                const effectiveCategory = category || fallbackCategory;
                if (effectiveCategory && effectiveCategory !== macroCategory) {
                    return false;
                }
            }

            if (macroTheme !== 'all') {
                const eventNodeId = citation.node_ids.find((nodeId) => nodeId.startsWith('event:'));
                if (eventNodeId) {
                    const themes = eventThemesMap.get(eventNodeId);
                    if (themes && !themes.has(macroTheme)) {
                        return false;
                    }
                }
            }

            return true;
        });
    }, [macroAnswer, macroConfidence, macroCountry, macroCategory, macroTheme, docMetaByDocId, macroEvidences, eventThemesMap]);

    const selectedNodeType = useMemo(() => {
        if (!selectedNode) return '';
        if (selectedNode.labels?.length > 0) return String(selectedNode.labels[0]);
        const fallbackType = selectedNode.properties?._node_type;
        return fallbackType ? String(fallbackType) : '';
    }, [selectedNode]);

    const selectedNodeDocId = useMemo(() => {
        if (!selectedNode || selectedNodeType !== 'Document') return '';
        const docId = selectedNode.properties?.doc_id;
        return docId ? String(docId) : '';
    }, [selectedNode, selectedNodeType]);

    const selectedNodeCitations = useMemo(() => {
        if (!selectedNodeDocId) return [];
        return filteredCitations.filter((citation) => citation.doc_id === selectedNodeDocId);
    }, [filteredCitations, selectedNodeDocId]);

    const citationPageSize = 8;
    const citationTotalPages = Math.max(1, Math.ceil(filteredCitations.length / citationPageSize));
    const paginatedCitations = useMemo(() => {
        const safePage = Math.min(citationPage, citationTotalPages);
        const startIndex = (safePage - 1) * citationPageSize;
        return filteredCitations.slice(startIndex, startIndex + citationPageSize);
    }, [filteredCitations, citationPage, citationTotalPages]);

    useEffect(() => {
        setCitationPage(1);
    }, [macroAnswer, macroConfidence, macroCountry, macroCategory, macroTheme]);

    const selectedIndicatorCode = useMemo(() => {
        if (!selectedNode || selectedNodeType !== 'EconomicIndicator') return '';
        const directCode = selectedNode.properties?.indicator_code;
        if (directCode) return String(directCode);
        const id = String(selectedNode.id || '');
        if (id.startsWith('indicator:')) {
            return id.replace('indicator:', '');
        }
        return '';
    }, [selectedNode, selectedNodeType]);

    const clearPathHighlight = () => {
        setMacroPathwayIndex(-1);
        setHighlightedNodeIds([]);
        setHighlightedLinkKeys([]);
    };

    const applyPathHighlight = (
        index: number,
        response?: GraphRagAnswerResponse | null,
        citationsOverride?: GraphRagCitation[]
    ) => {
        const source = response || macroAnswer;
        if (!source || index < 0 || index >= source.answer.impact_pathways.length) {
            clearPathHighlight();
            return;
        }

        const pathway = source.answer.impact_pathways[index];
        const nodeIdSet = new Set<string>();
        if (pathway.event_id) nodeIdSet.add(`event:${pathway.event_id}`);
        if (pathway.theme_id) nodeIdSet.add(`theme:${pathway.theme_id}`);
        if (pathway.indicator_code) nodeIdSet.add(`indicator:${pathway.indicator_code}`);

        const citationSource = citationsOverride || filteredCitations;
        citationSource.slice(0, 5).forEach((citation) => {
            citation.node_ids.forEach((nodeId) => nodeIdSet.add(nodeId));
        });

        const linkKeyList: string[] = [];
        graphData.links.forEach((link: any) => {
            const sourceId = getLinkEndpointId(link.source);
            const targetId = getLinkEndpointId(link.target);
            const linkKey = toLinkKey(sourceId, String(link.type || ''), targetId);

            const isCorePath =
                (pathway.event_id && pathway.theme_id && sourceId === `event:${pathway.event_id}` && targetId === `theme:${pathway.theme_id}` && link.type === 'ABOUT_THEME') ||
                (pathway.event_id && pathway.indicator_code && sourceId === `event:${pathway.event_id}` && targetId === `indicator:${pathway.indicator_code}` && link.type === 'AFFECTS');

            if (isCorePath || (nodeIdSet.has(sourceId) && nodeIdSet.has(targetId))) {
                linkKeyList.push(linkKey);
            }
        });

        setMacroPathwayIndex(index);
        setHighlightedNodeIds(Array.from(nodeIdSet));
        setHighlightedLinkKeys(linkKeyList);
    };

    const refreshMacroContext = async (questionOverride?: string) => {
        const question = questionOverride || userInput.trim() || macroQuestionTemplates[0];

        setGraphLoading(true);
        setGraphError(null);
        setActivePreset(null);
        try {
            const context = await fetchGraphRagContext({
                question,
                time_range: macroTimeRange,
                country: macroCountry === 'all' ? undefined : macroCountry,
                as_of_date: macroAsOfDate || undefined,
                top_k_events: Math.max(10, Math.floor(macroTopK * 0.7)),
                top_k_documents: macroTopK,
                top_k_stories: Math.max(10, Math.floor(macroTopK * 0.5)),
                top_k_evidences: macroTopK,
            });

            setGraphData(contextToGraphData(context));
            setMacroEvidences(context.evidences);
            setMacroSuggestedQueries(context.suggested_queries);
            setMacroAnswer(null);
            setCitationPage(1);
            clearPathHighlight();
        } catch (error: any) {
            setGraphError(error.message || 'GraphRAG context 로딩 실패');
        } finally {
            setGraphLoading(false);
        }
    };

    const handleMacroQuestion = async (question: string) => {
        const response = await fetchGraphRagAnswer({
            question,
            time_range: macroTimeRange,
            country: macroCountry === 'all' ? undefined : macroCountry,
            as_of_date: macroAsOfDate || undefined,
            model: macroAnswerModel,
            include_context: true,
            top_k_events: Math.max(10, Math.floor(macroTopK * 0.7)),
            top_k_documents: macroTopK,
            top_k_stories: Math.max(10, Math.floor(macroTopK * 0.5)),
            top_k_evidences: macroTopK,
        });

        setMacroAnswer(response);
        setMacroSuggestedQueries(response.suggested_queries);
        setCitationPage(1);

        if (response.context) {
            setGraphData(contextToGraphData(response.context));
            setMacroEvidences(response.context.evidences);
        }

        if (response.answer.impact_pathways.length > 0) {
            applyPathHighlight(0, response, response.citations);
        } else {
            clearPathHighlight();
        }

        const keyPointsText = response.answer.key_points.length > 0
            ? `\n\n핵심 포인트:\n${response.answer.key_points.map((point) => `- ${point}`).join('\n')}`
            : '';
        const uncertaintyText = response.answer.uncertainty
            ? `\n\n불확실성: ${response.answer.uncertainty}`
            : '';

        const assistantMessage: ChatMessage = {
            id: (Date.now() + 1).toString(),
            type: 'assistant',
            content: `${response.answer.conclusion}${keyPointsText}${uncertaintyText}`,
            timestamp: new Date(),
            rag: {
                model: response.model,
                uncertainty: response.answer.uncertainty,
                keyPoints: response.answer.key_points,
                citations: response.citations,
            },
        };

        setChatMessages((prev) => [...prev, assistantMessage]);
    };

    const handleSendMessage = async () => {
        if (!isAuthenticated) return;
        if (!userInput.trim() || chatLoading) return;

        if (mode !== 'macro' && queryLimit && !queryLimit.is_unlimited && queryLimit.remaining <= 0) {
            const errorMessage: ChatMessage = {
                id: Date.now().toString(),
                type: 'assistant',
                content: `일일 질의 한도(${queryLimit.daily_limit}회)를 초과했습니다. 내일 다시 시도해주세요.`,
                timestamp: new Date(),
            };
            setChatMessages((prev) => [...prev, errorMessage]);
            return;
        }

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            type: 'user',
            content: userInput.trim(),
            timestamp: new Date(),
        };

        setChatMessages((prev) => [...prev, userMessage]);
        setUserInput('');
        setChatLoading(true);

        try {
            if (mode === 'macro') {
                await handleMacroQuestion(userMessage.content);
            } else {
                const { cypher, error: cypherError, remaining_queries } = await generateCypherFromNaturalLanguage(userMessage.content, mode);

                if (remaining_queries !== undefined && queryLimit) {
                    setQueryLimit({
                        ...queryLimit,
                        remaining: remaining_queries
                    });
                }

                if (cypherError || !cypher) {
                    throw new Error(cypherError || 'Failed to generate Cypher query');
                }

                const result = await runCypherQuery(cypher, {}, mode);
                const explanation = await explainQueryResults(
                    userMessage.content,
                    cypher,
                    result.raw || []
                );

                const assistantMessage: ChatMessage = {
                    id: (Date.now() + 1).toString(),
                    type: 'assistant',
                    content: explanation,
                    cypher,
                    timestamp: new Date(),
                };

                setChatMessages((prev) => [...prev, assistantMessage]);
            }
        } catch (error: any) {
            const errorMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                type: 'assistant',
                content: `죄송합니다. 질문을 처리하는 중 오류가 발생했습니다: ${error.message}`,
                timestamp: new Date(),
            };
            setChatMessages((prev) => [...prev, errorMessage]);
        } finally {
            setChatLoading(false);
        }
    };

    const handleKeyDown = (event: React.KeyboardEvent) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleSendMessage();
        }
    };

    useEffect(() => {
        if (mode !== 'macro' || !selectedIndicatorCode) {
            setIndicatorSeries([]);
            setIndicatorError(null);
            setIndicatorLoading(false);
            return;
        }

        let mounted = true;

        const fetchIndicatorSeries = async () => {
            setIndicatorLoading(true);
            setIndicatorError(null);
            try {
                const result = await runCypherQuery(
                    `
                    MATCH (i:EconomicIndicator {indicator_code: $indicator_code})-[:HAS_OBSERVATION]->(o:IndicatorObservation)
                    RETURN toString(o.obs_date) AS obs_date, toFloat(o.value) AS value
                    ORDER BY o.obs_date DESC
                    LIMIT 30
                    `,
                    { indicator_code: selectedIndicatorCode },
                    'macro'
                );

                const rows: IndicatorPoint[] = (result.raw || [])
                    .map((row: any) => ({
                        obsDate: String(row.obs_date || ''),
                        value: Number(row.value),
                    }))
                    .filter((row: IndicatorPoint) => row.obsDate && Number.isFinite(row.value))
                    .reverse();

                if (mounted) {
                    setIndicatorSeries(rows);
                }
            } catch (error: any) {
                if (mounted) {
                    setIndicatorError(error.message || '지표 시계열을 불러오지 못했습니다.');
                    setIndicatorSeries([]);
                }
            } finally {
                if (mounted) {
                    setIndicatorLoading(false);
                }
            }
        };

        fetchIndicatorSeries();
        return () => {
            mounted = false;
        };
    }, [mode, selectedIndicatorCode]);

    const indicatorSummary = useMemo(() => {
        if (indicatorSeries.length === 0) {
            return null;
        }
        const latest = indicatorSeries[indicatorSeries.length - 1];
        const previous = indicatorSeries.length > 1 ? indicatorSeries[indicatorSeries.length - 2] : null;
        const delta = previous ? latest.value - previous.value : 0;
        const deltaPct = previous && previous.value !== 0 ? (delta / Math.abs(previous.value)) * 100 : 0;

        return {
            latest,
            previous,
            delta,
            deltaPct,
        };
    }, [indicatorSeries]);

    const canQuery = isAuthenticated && (
        mode === 'macro' ||
        queryLimit?.is_unlimited ||
        (queryLimit?.remaining ?? 0) > 0
    );

    const examples = mode === 'architecture'
        ? [
            '전체 리소스 개수는?',
            'VNet과 연결된 Subnet 목록을 보여줘',
            '어떤 환경(Environment)들이 있어?',
        ]
        : macroQuestionTemplates;

    const suggestedQueries = (macroAnswer?.suggested_queries && macroAnswer.suggested_queries.length > 0)
        ? macroAnswer.suggested_queries
        : macroSuggestedQueries;

    return (
        <div className="flex h-[calc(100vh-64px)] bg-gray-50 text-gray-900 font-sans overflow-hidden">
            <div className="flex-1 flex flex-col overflow-hidden relative">
                <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white shadow-sm z-10">
                    <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-indigo-600" />
                        <h1 className="font-semibold text-gray-800">
                            {mode === 'architecture' ? 'Architecture Graph' : 'Macro Graph'}
                        </h1>
                    </div>
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg transition-colors"
                    >
                        {sidebarOpen ? (
                            <>
                                <PanelRightClose className="w-4 h-4" />
                                질문창 닫기
                            </>
                        ) : (
                            <>
                                <PanelRightOpen className="w-4 h-4" />
                                질문창 열기
                            </>
                        )}
                    </button>
                </div>

                {mode === 'macro' && (
                    <div className="px-4 py-3 bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-700 text-white">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-white/20 rounded-lg backdrop-blur-sm">
                                    <Database className="w-5 h-5" />
                                </div>
                                <div>
                                    <h2 className="text-sm font-bold">Knowledge Graph 기반 거시경제 분석</h2>
                                    <p className="text-xs text-indigo-100">
                                        Event → Theme → Indicator 경로와 Evidence 근거를 함께 확인해 의사결정 품질을 높입니다.
                                    </p>
                                </div>
                            </div>
                            <div className="hidden md:flex items-center gap-2 text-xs text-indigo-200">
                                <span className="px-2 py-1 bg-white/10 rounded">Rates</span>
                                <span className="px-2 py-1 bg-white/10 rounded">Inflation</span>
                                <span className="px-2 py-1 bg-white/10 rounded">Growth</span>
                                <span className="px-2 py-1 bg-white/10 rounded">Labor</span>
                                <span className="px-2 py-1 bg-white/10 rounded">Liquidity</span>
                            </div>
                        </div>
                    </div>
                )}

                {mode === 'macro' && (
                    <div className="px-4 py-3 border-b border-gray-200 bg-white">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="text-xs font-semibold text-gray-700">📊 그래프 탐색</span>
                            <span className="text-[10px] text-gray-400">클릭하여 관계 시각화</span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {macroPresetQueries.map((preset) => (
                                <button
                                    key={preset.id}
                                    onClick={() => executePresetQuery(preset)}
                                    className={`group flex flex-col items-start px-3 py-2 rounded-lg transition-all ${activePreset === preset.id
                                        ? 'bg-indigo-600 text-white shadow-lg'
                                        : 'bg-gray-50 border border-gray-200 text-gray-700 hover:bg-indigo-50 hover:border-indigo-300'
                                        }`}
                                >
                                    <span className="text-xs font-medium">{preset.name}</span>
                                    <span className={`text-[10px] ${activePreset === preset.id ? 'text-indigo-200' : 'text-gray-400'}`}>
                                        {preset.description}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {mode === 'macro' && (
                    <div className="px-4 py-3 border-b border-gray-200 bg-white">
                        <div className="flex items-center gap-2 mb-2">
                            <Filter className="w-4 h-4 text-indigo-600" />
                            <span className="text-xs font-semibold text-gray-700">Evidence/경로 필터</span>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-7 gap-2">
                            <label className="text-[11px] text-gray-600">
                                기간
                                <select
                                    value={macroTimeRange}
                                    onChange={(event) => setMacroTimeRange(event.target.value as TimeRange)}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                >
                                    <option value="7d">7d</option>
                                    <option value="30d">30d</option>
                                    <option value="90d">90d</option>
                                </select>
                            </label>
                            <label className="text-[11px] text-gray-600">
                                국가
                                <select
                                    value={macroCountry}
                                    onChange={(event) => setMacroCountry(event.target.value)}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                >
                                    <option value="all">전체</option>
                                    {availableCountries.map((country) => (
                                        <option key={country} value={country}>{country}</option>
                                    ))}
                                </select>
                            </label>
                            <label className="text-[11px] text-gray-600">
                                카테고리
                                <select
                                    value={macroCategory}
                                    onChange={(event) => setMacroCategory(event.target.value)}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                >
                                    <option value="all">전체</option>
                                    {availableCategories.map((category) => (
                                        <option key={category} value={category}>{category}</option>
                                    ))}
                                </select>
                            </label>
                            <label className="text-[11px] text-gray-600">
                                테마
                                <select
                                    value={macroTheme}
                                    onChange={(event) => setMacroTheme(event.target.value)}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                >
                                    <option value="all">전체</option>
                                    {availableThemes.map((theme) => (
                                        <option key={theme} value={theme}>{theme}</option>
                                    ))}
                                </select>
                            </label>
                            <label className="text-[11px] text-gray-600">
                                근거 신뢰도
                                <select
                                    value={macroConfidence}
                                    onChange={(event) => setMacroConfidence(event.target.value as 'all' | 'high' | 'medium' | 'low')}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                >
                                    <option value="all">전체</option>
                                    <option value="high">높음 (Fact)</option>
                                    <option value="medium">중간 (Claim)</option>
                                    <option value="low">낮음 (기타)</option>
                                </select>
                            </label>
                            <label className="text-[11px] text-gray-600">
                                기준일
                                <input
                                    type="date"
                                    value={macroAsOfDate}
                                    onChange={(event) => setMacroAsOfDate(event.target.value)}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                />
                            </label>
                            <label className="text-[11px] text-gray-600">
                                Top-K
                                <select
                                    value={macroTopK}
                                    onChange={(event) => setMacroTopK(Number(event.target.value))}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                >
                                    <option value={30}>30</option>
                                    <option value={50}>50</option>
                                    <option value={80}>80</option>
                                    <option value={100}>100</option>
                                </select>
                            </label>
                            <label className="text-[11px] text-gray-600">
                                답변 모델
                                <select
                                    value={macroAnswerModel}
                                    onChange={(event) => setMacroAnswerModel(event.target.value as MacroAnswerModel)}
                                    className="mt-1 w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
                                >
                                    <option value="gemini-3-flash-preview">gemini-3-flash-preview (기본)</option>
                                    <option value="gemini-3-pro-preview">gemini-3-pro-preview</option>
                                </select>
                            </label>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                            <button
                                onClick={() => refreshMacroContext()}
                                className="px-3 py-1.5 text-xs font-medium rounded border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                            >
                                컨텍스트 갱신
                            </button>
                            <span className="text-[11px] text-gray-500">
                                근거 {filteredCitations.length}건 · 경로 {macroAnswer?.answer.impact_pathways.length || 0}건
                            </span>
                        </div>
                    </div>
                )}

                {mode === 'macro' && macroAnswer && (
                    <div className="px-4 py-3 border-b border-gray-200 bg-indigo-50/40">
                        <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                                <Route className="w-4 h-4 text-indigo-600" />
                                <span className="text-xs font-semibold text-gray-800">Path Explorer</span>
                            </div>
                            <span className="text-[11px] text-gray-500">
                                모델: {macroAnswer.model}
                            </span>
                        </div>
                        <p className="text-xs text-gray-700 mb-2">{macroAnswer.answer.conclusion}</p>
                        <div className="flex flex-wrap gap-2 mb-2">
                            {macroAnswer.answer.impact_pathways.map((pathway, index) => (
                                <button
                                    key={`${pathway.event_id || 'evt'}-${index}`}
                                    onClick={() => applyPathHighlight(index)}
                                    className={`px-2 py-1 rounded text-[11px] border transition-colors ${macroPathwayIndex === index
                                        ? 'bg-indigo-600 border-indigo-700 text-white'
                                        : 'bg-white border-indigo-200 text-indigo-700 hover:bg-indigo-100'
                                        }`}
                                >
                                    {pathway.event_id || 'event'} → {pathway.theme_id || 'theme'} → {pathway.indicator_code || 'indicator'}
                                </button>
                            ))}
                            {macroAnswer.answer.impact_pathways.length === 0 && (
                                <span className="text-[11px] text-gray-500">표시 가능한 영향 경로가 없습니다.</span>
                            )}
                        </div>
                        {macroPathwayIndex >= 0 && macroAnswer.answer.impact_pathways[macroPathwayIndex] && (
                            <p className="text-[11px] text-gray-600">
                                {macroAnswer.answer.impact_pathways[macroPathwayIndex].explanation}
                            </p>
                        )}
                    </div>
                )}

                {isAdmin && (
                    <div className="border-b border-gray-200 bg-gray-50">
                        <button
                            onClick={() => setCypherQueryOpen(!cypherQueryOpen)}
                            className="w-full px-4 py-2 flex items-center justify-between text-sm font-medium text-gray-700 hover:bg-gray-100 transition-colors"
                        >
                            <div className="flex items-center gap-2">
                                <Terminal className="w-4 h-4 text-indigo-600" />
                                <span>Cypher 쿼리 직접 입력</span>
                                {lastExecutedQuery && (
                                    <span className="px-2 py-0.5 text-[10px] bg-green-100 text-green-700 rounded">최근 쿼리 실행됨</span>
                                )}
                            </div>
                            {cypherQueryOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>

                        {cypherQueryOpen && (
                            <div className="px-4 pb-4">
                                <div className="relative">
                                    <textarea
                                        value={cypherInput}
                                        onChange={(event) => setCypherInput(event.target.value)}
                                        onKeyDown={handleCypherKeyDown}
                                        placeholder="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100"
                                        className="w-full h-24 p-3 pr-24 font-mono text-sm bg-white border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-none"
                                        spellCheck={false}
                                    />
                                    <button
                                        onClick={executeCypherQuery}
                                        disabled={!cypherInput.trim() || graphLoading}
                                        className="absolute right-2 bottom-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
                                    >
                                        {graphLoading ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <Play className="w-4 h-4" />
                                        )}
                                        실행
                                    </button>
                                </div>

                                {cypherError && (
                                    <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-sm text-red-700">
                                        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                                        <span>{cypherError}</span>
                                    </div>
                                )}

                                <div className="mt-2 text-[11px] text-gray-500">
                                    <span className="font-medium">팁:</span> Enter로 실행, Shift+Enter로 줄바꿈.
                                    <span className="ml-2 text-indigo-600">
                                        현재 노드: {graphData.nodes.length}개, 관계: {graphData.links.length}개
                                    </span>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                <div className="flex-1 flex overflow-hidden">
                    <div className="flex-1 relative" ref={graphContainerRef}>
                        {graphLoading ? (
                            <div className="absolute inset-0 flex items-center justify-center bg-gray-50">
                                <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
                            </div>
                        ) : graphError ? (
                            <div className="absolute inset-0 flex items-center justify-center bg-gray-50">
                                <div className="text-center text-red-500">
                                    <p>{graphError}</p>
                                    <button
                                        onClick={loadDefaultGraph}
                                        className="mt-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700"
                                    >
                                        다시 시도
                                    </button>
                                </div>
                            </div>
                        ) : graphData.nodes.length === 0 ? (
                            <div className="absolute inset-0 flex items-center justify-center text-gray-400 flex-col gap-4 bg-gray-50">
                                <Database className="w-16 h-16 opacity-20" />
                                <p>그래프 데이터가 없습니다.</p>
                            </div>
                        ) : (
                            <ForceGraph2D
                                width={graphDimensions.width}
                                height={graphDimensions.height}
                                graphData={graphData}
                                nodeLabel={(node: any) => {
                                    const props = node.properties || {};
                                    const primary = props._display_label || props.name || props.title || props.indicator_code || '';
                                    return `${node.labels?.join(', ') || 'Node'}\n${primary}`;
                                }}
                                nodeAutoColorBy={(node: any) => (node.labels?.[0] || 'Node')}
                                linkDirectionalArrowLength={3.5}
                                linkDirectionalArrowRelPos={1}
                                linkLabel="type"
                                linkColor={(link: any) => {
                                    if (highlightedLinkSet.size === 0) return '#9ca3af';
                                    const sourceId = getLinkEndpointId(link.source);
                                    const targetId = getLinkEndpointId(link.target);
                                    const key = toLinkKey(sourceId, String(link.type || ''), targetId);
                                    return highlightedLinkSet.has(key) ? '#2563eb' : 'rgba(156, 163, 175, 0.2)';
                                }}
                                linkWidth={(link: any) => {
                                    if (highlightedLinkSet.size === 0) return 1.5;
                                    const sourceId = getLinkEndpointId(link.source);
                                    const targetId = getLinkEndpointId(link.target);
                                    const key = toLinkKey(sourceId, String(link.type || ''), targetId);
                                    return highlightedLinkSet.has(key) ? 2.8 : 0.8;
                                }}
                                onNodeClick={(node) => setSelectedNode(node)}
                                nodeCanvasObjectMode={() => 'after'}
                                nodeCanvasObject={(node: any, ctx, globalScale) => {
                                    const props = node.properties || {};
                                    const label = props._display_label || props.name || props.title || props.indicator_code || (node.labels && node.labels[0]) || node.id;
                                    const fontSize = 12 / globalScale;

                                    const hasHighlight = highlightedNodeSet.size > 0;
                                    const nodeIsHighlighted = highlightedNodeSet.has(String(node.id));

                                    if (hasHighlight && nodeIsHighlighted) {
                                        ctx.beginPath();
                                        ctx.arc(node.x, node.y, 8 / globalScale, 0, 2 * Math.PI, false);
                                        ctx.lineWidth = 2 / globalScale;
                                        ctx.strokeStyle = '#2563eb';
                                        ctx.stroke();
                                    }

                                    ctx.font = `${fontSize}px Sans-Serif`;
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'top';
                                    ctx.fillStyle = hasHighlight && !nodeIsHighlighted ? 'rgba(107, 114, 128, 0.55)' : '#111827';
                                    ctx.fillText(label, node.x, node.y + 6);
                                }}
                                linkCanvasObjectMode={() => 'after'}
                                linkCanvasObject={(link: any, ctx, globalScale) => {
                                    const label = link.type;
                                    if (!label) return;

                                    const start = link.source;
                                    const end = link.target;
                                    if (typeof start !== 'object' || typeof end !== 'object') return;

                                    const textPos = {
                                        x: (start.x + end.x) / 2,
                                        y: (start.y + end.y) / 2,
                                    };

                                    const fontSize = 10 / globalScale;
                                    ctx.font = `${fontSize}px Sans-Serif`;
                                    const textWidth = ctx.measureText(label).width;
                                    const bgPadding = 2 / globalScale;

                                    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
                                    ctx.fillRect(
                                        textPos.x - textWidth / 2 - bgPadding,
                                        textPos.y - fontSize / 2 - bgPadding,
                                        textWidth + bgPadding * 2,
                                        fontSize + bgPadding * 2
                                    );

                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'middle';
                                    ctx.fillStyle = '#6b7280';
                                    ctx.fillText(label, textPos.x, textPos.y);
                                }}
                            />
                        )}
                    </div>

                    {selectedNode && (
                        <div className="absolute top-0 right-0 w-96 h-full bg-white border-l border-gray-200 overflow-y-auto shadow-xl flex flex-col z-20">
                            <div className="p-3 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                                <h2 className="font-bold text-sm text-gray-800">Node Detail</h2>
                                <button
                                    onClick={() => setSelectedNode(null)}
                                    className="text-gray-400 hover:text-gray-600 p-1 hover:bg-gray-200 rounded"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            <div className="p-3 space-y-4 text-sm">
                                <div>
                                    <div className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 mb-1">
                                        {selectedNode.labels ? selectedNode.labels.join(', ') : 'Node'}
                                    </div>
                                    <div className="text-xs text-gray-500 font-mono break-all">
                                        ID: {selectedNode.id}
                                    </div>
                                </div>

                                {mode === 'macro' && selectedNodeType === 'Document' && (
                                    <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-3">
                                        <h3 className="text-xs font-semibold text-indigo-800 mb-2 flex items-center gap-1">
                                            <FileText className="w-3 h-3" />
                                            Document Insight
                                        </h3>
                                        <p className="text-xs text-gray-700 leading-relaxed">
                                            {selectedNode.properties?.title || selectedNode.properties?._display_label || '제목 없음'}
                                        </p>
                                        {selectedNode.properties?.url && (
                                            <a
                                                href={String(selectedNode.properties.url)}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="mt-2 inline-flex items-center gap-1 text-[11px] text-indigo-700 hover:text-indigo-900"
                                            >
                                                원문 열기
                                                <ExternalLink className="w-3 h-3" />
                                            </a>
                                        )}
                                        <div className="mt-2 text-[11px] text-gray-500">
                                            {selectedNode.properties?.country && <span className="mr-2">국가: {String(selectedNode.properties.country)}</span>}
                                            {selectedNode.properties?.category && <span className="mr-2">카테고리: {String(selectedNode.properties.category)}</span>}
                                            {selectedNode.properties?.published_at && <span>발행: {String(selectedNode.properties.published_at).slice(0, 10)}</span>}
                                        </div>

                                        <div className="mt-3">
                                            <h4 className="text-[11px] font-semibold text-gray-700 mb-1">Evidence / Claim</h4>
                                            <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                                                {selectedNodeCitations.map((citation, index) => (
                                                    <div key={`${citation.evidence_id || citation.doc_id || 'citation'}-${index}`} className="rounded border border-gray-200 bg-white p-2">
                                                        <p className="text-[11px] text-gray-700">{citation.text}</p>
                                                        <div className="mt-1 flex items-center gap-2 text-[10px] text-gray-500">
                                                            <span className="px-1.5 py-0.5 rounded bg-gray-100">{getCitationConfidence(citation)}</span>
                                                            {citation.support_labels.length > 0 && (
                                                                <span>{citation.support_labels.join(', ')}</span>
                                                            )}
                                                        </div>
                                                    </div>
                                                ))}
                                                {selectedNodeCitations.length === 0 && (
                                                    <p className="text-[11px] text-gray-400">선택된 필터 기준 근거가 없습니다.</p>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {mode === 'macro' && selectedNodeType === 'EconomicIndicator' && (
                                    <div className="rounded-lg border border-emerald-100 bg-emerald-50/50 p-3">
                                        <h3 className="text-xs font-semibold text-emerald-800 mb-2 flex items-center gap-1">
                                            <TrendingUp className="w-3 h-3" />
                                            Indicator Snapshot
                                        </h3>
                                        <p className="text-xs text-gray-700 mb-2">
                                            {selectedNode.properties?.name || selectedNode.properties?._display_label || selectedIndicatorCode}
                                        </p>
                                        {indicatorLoading ? (
                                            <div className="flex items-center gap-2 text-[11px] text-gray-500">
                                                <Loader2 className="w-3 h-3 animate-spin" />
                                                지표 시계열 로딩 중...
                                            </div>
                                        ) : indicatorError ? (
                                            <p className="text-[11px] text-red-600">{indicatorError}</p>
                                        ) : (
                                            <>
                                                {indicatorSummary && (
                                                    <div className="mb-2 text-[11px] text-gray-700">
                                                        <div>최신값: <span className="font-semibold">{indicatorSummary.latest.value.toFixed(4)}</span></div>
                                                        {indicatorSummary.previous && (
                                                            <div>
                                                                변동: <span className={indicatorSummary.delta >= 0 ? 'text-emerald-700' : 'text-red-600'}>
                                                                    {indicatorSummary.delta >= 0 ? '+' : ''}{indicatorSummary.delta.toFixed(4)}
                                                                </span>
                                                                {' '}({indicatorSummary.deltaPct >= 0 ? '+' : ''}{indicatorSummary.deltaPct.toFixed(2)}%)
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                                {renderSparkline(indicatorSeries)}
                                            </>
                                        )}
                                        {selectedIndicatorCode && (
                                            <a
                                                href={`https://fred.stlouisfed.org/series/${selectedIndicatorCode}`}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="mt-2 inline-flex items-center gap-1 text-[11px] text-emerald-700 hover:text-emerald-900"
                                            >
                                                FRED 원시계열 보기
                                                <ExternalLink className="w-3 h-3" />
                                            </a>
                                        )}
                                    </div>
                                )}

                                <div>
                                    <h3 className="text-xs font-semibold text-gray-700 mb-2 border-b pb-1">Properties</h3>
                                    <div className="space-y-2">
                                        {Object.entries(selectedNode.properties || {}).map(([key, value]: [string, any]) => (
                                            <div key={key} className="grid grid-cols-3 gap-1 text-xs border-b border-gray-50 pb-1 last:border-0">
                                                <div className="font-medium text-gray-600 break-words">{key}</div>
                                                <div className="col-span-2 text-gray-900 break-words font-mono bg-gray-50 p-1 rounded">
                                                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                </div>
                                            </div>
                                        ))}
                                        {Object.keys(selectedNode.properties || {}).length === 0 && (
                                            <p className="text-gray-400 text-xs">No properties</p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div
                className={`bg-white border-l border-gray-200 flex flex-col transition-all duration-300 overflow-hidden ${sidebarOpen ? 'w-[420px]' : 'w-0'
                    }`}
            >
                {sidebarOpen && (
                    <>
                        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-indigo-50 to-white">
                            <div className="flex items-center gap-2">
                                <Sparkles className="w-5 h-5 text-indigo-600" />
                                <h2 className="font-semibold text-gray-800 text-sm">자연어 질의</h2>
                            </div>
                            <div className="flex items-center gap-2">
                                {isAuthenticated && queryLimit && !queryLimit.is_unlimited && mode !== 'macro' && (
                                    <span className={`text-xs px-2 py-1 rounded-full ${queryLimit.remaining > 5
                                        ? 'bg-green-100 text-green-700'
                                        : queryLimit.remaining > 0
                                            ? 'bg-yellow-100 text-yellow-700'
                                            : 'bg-red-100 text-red-700'
                                        }`}>
                                        {queryLimit.remaining}/{queryLimit.daily_limit}
                                    </span>
                                )}
                                {isAuthenticated && (queryLimit?.is_unlimited || mode === 'macro') && (
                                    <span className="text-xs px-2 py-1 rounded-full bg-indigo-100 text-indigo-700">
                                        ∞
                                    </span>
                                )}
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-3 space-y-3">
                            {mode === 'macro' && suggestedQueries.length > 0 && (
                                <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-2">
                                    <p className="text-[11px] font-semibold text-indigo-800 mb-1">추천 질의</p>
                                    <div className="flex flex-wrap gap-1.5">
                                        {suggestedQueries.slice(0, 6).map((query) => (
                                            <button
                                                key={query}
                                                onClick={() => setUserInput(query)}
                                                className="text-[11px] px-2 py-1 rounded bg-white border border-indigo-200 text-indigo-700 hover:bg-indigo-100 text-left"
                                            >
                                                {query}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {mode === 'macro' && macroAnswer && (
                                <div className="rounded-lg border border-gray-200 bg-white p-2">
                                    <div className="flex items-center justify-between mb-1">
                                        <p className="text-[11px] font-semibold text-gray-700">Evidence Explorer</p>
                                        <span className="text-[10px] text-gray-500">
                                            {citationPage}/{citationTotalPages}
                                        </span>
                                    </div>
                                    <div className="space-y-1.5">
                                        {paginatedCitations.map((citation, index) => {
                                            const confidence = getCitationConfidence(citation);
                                            return (
                                                <div
                                                    key={`${citation.evidence_id || citation.doc_id || 'citation'}-${index}`}
                                                    className="rounded border border-gray-100 bg-gray-50 p-2"
                                                >
                                                    <p className="text-[11px] text-gray-700 line-clamp-2">
                                                        {citation.text}
                                                    </p>
                                                    <div className="mt-1 flex items-center gap-1.5 text-[10px]">
                                                        <span
                                                            className={`px-1 py-0.5 rounded ${
                                                                confidence === 'high'
                                                                    ? 'bg-emerald-100 text-emerald-700'
                                                                    : confidence === 'medium'
                                                                        ? 'bg-amber-100 text-amber-700'
                                                                        : 'bg-gray-200 text-gray-600'
                                                            }`}
                                                        >
                                                            {confidence}
                                                        </span>
                                                        {citation.doc_id && (
                                                            <span className="text-gray-500">{citation.doc_id}</span>
                                                        )}
                                                        {citation.doc_url && (
                                                            <a
                                                                href={citation.doc_url}
                                                                target="_blank"
                                                                rel="noreferrer"
                                                                className="text-indigo-600 hover:text-indigo-800"
                                                            >
                                                                링크
                                                            </a>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                        {paginatedCitations.length === 0 && (
                                            <p className="text-[11px] text-gray-400">선택한 필터에 해당하는 Evidence가 없습니다.</p>
                                        )}
                                    </div>
                                    <div className="mt-2 flex items-center justify-between">
                                        <button
                                            onClick={() => setCitationPage((page) => Math.max(1, page - 1))}
                                            disabled={citationPage <= 1}
                                            className="px-2 py-1 text-[10px] rounded border border-gray-200 text-gray-600 disabled:opacity-40"
                                        >
                                            이전
                                        </button>
                                        <span className="text-[10px] text-gray-500">
                                            총 {filteredCitations.length}건
                                        </span>
                                        <button
                                            onClick={() => setCitationPage((page) => Math.min(citationTotalPages, page + 1))}
                                            disabled={citationPage >= citationTotalPages}
                                            className="px-2 py-1 text-[10px] rounded border border-gray-200 text-gray-600 disabled:opacity-40"
                                        >
                                            다음
                                        </button>
                                    </div>
                                </div>
                            )}

                            {chatMessages.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
                                    <MessageSquare className="w-10 h-10 opacity-30" />
                                    <p className="text-xs text-center">그래프 DB에 대해<br />자연어로 질문해보세요</p>
                                    {isAuthenticated && canQuery && (
                                        <div className="flex flex-col gap-2 mt-2 w-full px-2">
                                            {examples.map((example) => (
                                                <button
                                                    key={example}
                                                    onClick={() => setUserInput(example)}
                                                    className="px-3 py-2 text-xs bg-gray-100 hover:bg-indigo-100 text-gray-600 hover:text-indigo-700 rounded-lg transition-colors text-left"
                                                >
                                                    {example}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                    {!isAuthenticated && (
                                        <div className="flex items-center gap-2 mt-4 text-amber-600 bg-amber-50 px-3 py-2 rounded-lg">
                                            <Lock className="w-4 h-4" />
                                            <span className="text-xs">로그인 후 이용 가능</span>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                chatMessages.map((message) => (
                                    <div
                                        key={message.id}
                                        className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                                    >
                                        <div
                                            className={`max-w-[95%] rounded-2xl px-3 py-2 ${message.type === 'user'
                                                ? 'bg-indigo-600 text-white rounded-br-md'
                                                : 'bg-gray-100 text-gray-800 rounded-bl-md'
                                                }`}
                                        >
                                            <p className="whitespace-pre-wrap text-xs">{message.content}</p>

                                            {message.rag && (
                                                <div className="mt-2 border-t border-gray-200/50 pt-2">
                                                    <div className="text-[10px] text-gray-600">
                                                        모델: {message.rag.model} · 근거 {message.rag.citations.length}건
                                                    </div>
                                                    <div className="mt-1 flex flex-wrap gap-1">
                                                        {message.rag.citations.slice(0, 3).map((citation, index) => (
                                                            <a
                                                                key={`${citation.evidence_id || citation.doc_id || 'citation'}-${index}`}
                                                                href={citation.doc_url || '#'}
                                                                target="_blank"
                                                                rel="noreferrer"
                                                                className={`text-[10px] px-1.5 py-0.5 rounded ${citation.doc_url
                                                                    ? 'bg-white text-indigo-700 border border-indigo-200 hover:bg-indigo-50'
                                                                    : 'bg-gray-200 text-gray-500'
                                                                    }`}
                                                            >
                                                                {citation.doc_id || citation.evidence_id || `근거 ${index + 1}`}
                                                            </a>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {message.cypher && (
                                                <div className="mt-2 pt-2 border-t border-gray-200/30">
                                                    <button
                                                        onClick={() => setShowCypher(showCypher === message.id ? null : message.id)}
                                                        className="flex items-center gap-1 text-[10px] opacity-70 hover:opacity-100 transition-opacity"
                                                    >
                                                        <Code className="w-3 h-3" />
                                                        {showCypher === message.id ? 'Cypher 숨기기' : 'Cypher 보기'}
                                                    </button>
                                                    {showCypher === message.id && (
                                                        <pre className="mt-2 p-2 bg-gray-800 text-green-400 rounded text-[10px] overflow-x-auto font-mono">
                                                            {message.cypher}
                                                        </pre>
                                                    )}
                                                </div>
                                            )}

                                            <span className="text-[9px] opacity-50 mt-1 block">
                                                {message.timestamp.toLocaleTimeString()}
                                            </span>
                                        </div>
                                    </div>
                                ))
                            )}
                            {chatLoading && (
                                <div className="flex justify-start">
                                    <div className="bg-gray-100 rounded-2xl rounded-bl-md px-3 py-2 flex items-center gap-2">
                                        <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                                        <span className="text-xs text-gray-500">분석 중...</span>
                                    </div>
                                </div>
                            )}
                            <div ref={chatEndRef} />
                        </div>

                        <div className="p-3 border-t border-gray-100 bg-gray-50/50">
                            {mode === 'macro' && (
                                <div className="mb-2">
                                    <p className="text-[11px] text-gray-500 mb-1">질문 템플릿</p>
                                    <div className="flex flex-wrap gap-1">
                                        {macroQuestionTemplates.slice(0, 8).map((template) => (
                                            <button
                                                key={template}
                                                onClick={() => setUserInput(template)}
                                                className="text-[10px] px-2 py-1 rounded bg-white border border-gray-200 text-gray-600 hover:bg-indigo-50 hover:text-indigo-700"
                                            >
                                                {template.length > 28 ? `${template.slice(0, 28)}...` : template}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {!isAuthenticated ? (
                                <div className="flex items-center justify-center px-3 py-2 border border-amber-200 bg-amber-50 rounded-lg text-amber-700 text-xs">
                                    <Lock className="w-3 h-3 mr-2" />
                                    로그인 필요
                                </div>
                            ) : !canQuery ? (
                                <div className="flex items-center justify-center px-3 py-2 border border-red-200 bg-red-50 rounded-lg text-red-700 text-xs">
                                    <AlertCircle className="w-3 h-3 mr-2" />
                                    일일 한도 초과
                                </div>
                            ) : (
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={userInput}
                                        onChange={(event) => setUserInput(event.target.value)}
                                        onKeyDown={handleKeyDown}
                                        placeholder="질문을 입력하세요..."
                                        className="flex-1 px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all text-xs"
                                        disabled={chatLoading}
                                    />
                                    <button
                                        onClick={handleSendMessage}
                                        disabled={!userInput.trim() || chatLoading}
                                        className={`px-3 py-2 rounded-lg font-medium flex items-center transition-all ${!userInput.trim() || chatLoading
                                            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                            : 'bg-indigo-600 text-white hover:bg-indigo-700'
                                            }`}
                                    >
                                        {chatLoading ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <Send className="w-4 h-4" />
                                        )}
                                    </button>
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};

export default OntologyPage;
