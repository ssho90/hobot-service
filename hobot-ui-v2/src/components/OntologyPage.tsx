import React, { useState, useEffect, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { runCypherQuery } from '../services/neo4jService';
import { generateCypherFromNaturalLanguage, explainQueryResults, getOntologyQueryLimit, type QueryLimitInfo } from '../services/geminiService';
import { Loader2, Database, X, MessageSquare, Send, Code, ChevronDown, ChevronUp, Sparkles, Lock, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface ChatMessage {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    cypher?: string;
    timestamp: Date;
}

const OntologyPage: React.FC<{ mode?: 'architecture' | 'news' }> = ({ mode = 'architecture' }) => {
    const { isAuthenticated } = useAuth();

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
    const [graphDimensions, setGraphDimensions] = useState({ width: 800, height: 400 });

    // Graph panel collapse state
    const [graphCollapsed, setGraphCollapsed] = useState(false);

    // Reset state when mode changes
    useEffect(() => {
        setChatMessages([]);
        setGraphData({ nodes: [], links: [] });
        setSelectedNode(null);
        setGraphError(null);
        loadDefaultGraph();
    }, [mode]);

    // Load initial graph data
    useEffect(() => {
        // Initial load is handled by the mode change effect above to prevent double loading
        // loadDefaultGraph(); 
    }, []);

    // Fetch query limit when authenticated
    useEffect(() => {
        if (isAuthenticated) {
            fetchQueryLimit();
        } else {
            setQueryLimit(null);
        }
    }, [isAuthenticated]);

    const fetchQueryLimit = async () => {
        const limit = await getOntologyQueryLimit();
        setQueryLimit(limit);
    };

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
    }, [graphCollapsed]);

    // Auto-scroll chat to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages]);

    const loadDefaultGraph = async () => {
        setGraphLoading(true);
        setGraphError(null);
        try {
            // For News graph, we might want a different default query or Limit
            const query = mode === 'architecture'
                ? 'MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 100'
                : 'MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 100'; // Adjust for news if needed

            const result = await runCypherQuery(query, {}, mode);
            setGraphData({ nodes: result.nodes, links: result.links });
        } catch (err: any) {
            setGraphError(err.message || 'Failed to load graph data.');
        } finally {
            setGraphLoading(false);
        }
    };

    const handleSendMessage = async () => {
        if (!isAuthenticated) return;
        if (!userInput.trim() || chatLoading) return;

        // Check if user has remaining queries (non-admin)
        if (queryLimit && !queryLimit.is_unlimited && queryLimit.remaining <= 0) {
            const errorMessage: ChatMessage = {
                id: Date.now().toString(),
                type: 'assistant',
                content: `일일 질의 한도(${queryLimit.daily_limit}회)를 초과했습니다. 내일 다시 시도해주세요.`,
                timestamp: new Date(),
            };
            setChatMessages(prev => [...prev, errorMessage]);
            return;
        }

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            type: 'user',
            content: userInput.trim(),
            timestamp: new Date(),
        };

        setChatMessages(prev => [...prev, userMessage]);
        setUserInput('');
        setChatLoading(true);

        try {
            // Step 1: Convert natural language to Cypher
            // Note: We need to pass 'mode' to backend to use correct schema. 
            const { cypher, error: cypherError, remaining_queries } = await generateCypherFromNaturalLanguage(userMessage.content, mode);

            // Update remaining queries
            if (remaining_queries !== undefined && queryLimit) {
                setQueryLimit({
                    ...queryLimit,
                    remaining: remaining_queries
                });
            }

            if (cypherError || !cypher) {
                throw new Error(cypherError || 'Failed to generate Cypher query');
            }

            // Step 2: Execute Cypher query
            const result = await runCypherQuery(cypher, {}, mode);

            // Step 3: Explain results in natural language
            const explanation = await explainQueryResults(
                userMessage.content,
                cypher,
                result.raw || []
            );

            const assistantMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                type: 'assistant',
                content: explanation,
                cypher: cypher,
                timestamp: new Date(),
            };

            setChatMessages(prev => [...prev, assistantMessage]);
        } catch (err: any) {
            const errorMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                type: 'assistant',
                content: `죄송합니다. 질문을 처리하는 중 오류가 발생했습니다: ${err.message}`,
                timestamp: new Date(),
            };
            setChatMessages(prev => [...prev, errorMessage]);
        } finally {
            setChatLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    };

    const canQuery = isAuthenticated && (queryLimit?.is_unlimited || (queryLimit?.remaining ?? 0) > 0);

    const examples = mode === 'architecture' ? [
        '전체 리소스 개수는?',
        'VNet과 연결된 Subnet 목록을 보여줘',
        '어떤 환경(Environment)들이 있어?',
    ] : [
        '최근 1주일간 가장 많이 언급된 기업은?',
        '특정 키워드와 연관된 뉴스를 찾아줘',
        '뉴스 기사 간의 연결 관계를 보여줘',
    ];

    return (
        <div className="flex flex-col h-[calc(100vh-64px)] bg-gray-50 text-gray-900 font-sans">
            {/* Top Section: Natural Language Query Interface */}
            <div className={`flex flex-col bg-white border-b border-gray-200 shadow-sm transition-all duration-300 ${graphCollapsed ? 'flex-1' : 'h-1/2'}`}>
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100 bg-gradient-to-r from-indigo-50 to-white">
                    <div className="flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-indigo-600" />
                        <h2 className="font-semibold text-gray-800">
                            {mode === 'architecture' ? 'Architecture Graph' : 'News Graph'} 자연어 질의
                        </h2>
                    </div>
                    <div className="flex items-center gap-3">
                        {isAuthenticated && queryLimit && !queryLimit.is_unlimited && (
                            <span className={`text-xs px-2 py-1 rounded-full ${queryLimit.remaining > 5
                                ? 'bg-green-100 text-green-700'
                                : queryLimit.remaining > 0
                                    ? 'bg-yellow-100 text-yellow-700'
                                    : 'bg-red-100 text-red-700'
                                }`}>
                                남은 질의: {queryLimit.remaining}/{queryLimit.daily_limit}
                            </span>
                        )}
                        {isAuthenticated && queryLimit?.is_unlimited && (
                            <span className="text-xs px-2 py-1 rounded-full bg-indigo-100 text-indigo-700">
                                무제한
                            </span>
                        )}
                        <span className="text-xs text-gray-500">자연어로 질문하면 Cypher 쿼리로 변환하여 답변합니다</span>
                    </div>
                </div>

                {/* Chat Messages */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {chatMessages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
                            <MessageSquare className="w-12 h-12 opacity-30" />
                            <p className="text-sm">그래프 데이터베이스에 대해 자연어로 질문해보세요</p>
                            {isAuthenticated && canQuery && (
                                <div className="flex flex-wrap gap-2 mt-2 justify-center">
                                    {examples.map((example) => (
                                        <button
                                            key={example}
                                            onClick={() => setUserInput(example)}
                                            className="px-3 py-1.5 text-xs bg-gray-100 hover:bg-indigo-100 text-gray-600 hover:text-indigo-700 rounded-full transition-colors"
                                        >
                                            {example}
                                        </button>
                                    ))}
                                </div>
                            )}
                            {!isAuthenticated && (
                                <div className="flex items-center gap-2 mt-4 text-amber-600 bg-amber-50 px-4 py-2 rounded-lg">
                                    <Lock className="w-4 h-4" />
                                    <span className="text-sm">로그인 후 이용 가능합니다</span>
                                </div>
                            )}
                        </div>
                    ) : (
                        chatMessages.map((msg) => (
                            <div
                                key={msg.id}
                                className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div
                                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${msg.type === 'user'
                                        ? 'bg-indigo-600 text-white rounded-br-md'
                                        : 'bg-gray-100 text-gray-800 rounded-bl-md'
                                        }`}
                                >
                                    <p className="whitespace-pre-wrap text-sm">{msg.content}</p>

                                    {/* Show Cypher Query Toggle */}
                                    {msg.cypher && (
                                        <div className="mt-2 pt-2 border-t border-gray-200/30">
                                            <button
                                                onClick={() => setShowCypher(showCypher === msg.id ? null : msg.id)}
                                                className="flex items-center gap-1 text-xs opacity-70 hover:opacity-100 transition-opacity"
                                            >
                                                <Code className="w-3 h-3" />
                                                {showCypher === msg.id ? 'Cypher 쿼리 숨기기' : 'Cypher 쿼리 보기'}
                                            </button>
                                            {showCypher === msg.id && (
                                                <pre className="mt-2 p-2 bg-gray-800 text-green-400 rounded text-xs overflow-x-auto font-mono">
                                                    {msg.cypher}
                                                </pre>
                                            )}
                                        </div>
                                    )}

                                    <span className="text-[10px] opacity-50 mt-1 block">
                                        {msg.timestamp.toLocaleTimeString()}
                                    </span>
                                </div>
                            </div>
                        ))
                    )}
                    {chatLoading && (
                        <div className="flex justify-start">
                            <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-2">
                                <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                                <span className="text-sm text-gray-500">분석 중...</span>
                            </div>
                        </div>
                    )}
                    <div ref={chatEndRef} />
                </div>

                {/* Input Area */}
                <div className="p-4 border-t border-gray-100 bg-gray-50/50">
                    <div className="flex gap-2 max-w-4xl mx-auto">
                        {!isAuthenticated ? (
                            <div className="flex-1 flex items-center justify-center px-4 py-3 border border-amber-200 bg-amber-50 rounded-xl text-amber-700 text-sm">
                                <Lock className="w-4 h-4 mr-2" />
                                회원가입해야 사용 가능합니다.
                            </div>
                        ) : !canQuery ? (
                            <div className="flex-1 flex items-center justify-center px-4 py-3 border border-red-200 bg-red-50 rounded-xl text-red-700 text-sm">
                                <AlertCircle className="w-4 h-4 mr-2" />
                                일일 질의 한도를 초과했습니다. 내일 다시 시도해주세요.
                            </div>
                        ) : (
                            <input
                                type="text"
                                value={userInput}
                                onChange={(e) => setUserInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="그래프 DB에 대해 질문하세요... (예: 어떤 리소스들이 있어?)"
                                className="flex-1 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all text-sm"
                                disabled={chatLoading}
                            />
                        )}
                        <button
                            onClick={handleSendMessage}
                            disabled={!canQuery || !userInput.trim() || chatLoading}
                            className={`px-4 py-3 rounded-xl font-medium flex items-center gap-2 transition-all ${!canQuery || !userInput.trim() || chatLoading
                                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                : 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-md hover:shadow-lg'
                                }`}
                        >
                            {chatLoading ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : (
                                <Send className="w-5 h-5" />
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {/* Divider with collapse toggle */}
            <button
                onClick={() => setGraphCollapsed(!graphCollapsed)}
                className="flex items-center justify-center gap-2 py-1.5 bg-gray-100 hover:bg-gray-200 border-y border-gray-200 transition-colors text-gray-600 text-sm"
            >
                {graphCollapsed ? (
                    <>
                        <ChevronUp className="w-4 h-4" />
                        그래프 보기
                    </>
                ) : (
                    <>
                        <ChevronDown className="w-4 h-4" />
                        그래프 숨기기
                    </>
                )}
            </button>

            {/* Bottom Section: Graph Visualization */}
            {!graphCollapsed && (
                <div className="flex-1 flex overflow-hidden">
                    {/* Graph Area */}
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
                                width={graphDimensions.width - (selectedNode ? 320 : 0)}
                                height={graphDimensions.height}
                                graphData={graphData}
                                nodeLabel={(node: any) => {
                                    const props = node.properties || {};
                                    return `${node.labels?.join(', ') || 'Node'}\n${props.name || props.title || ''}`;
                                }}
                                nodeAutoColorBy="labels"
                                linkDirectionalArrowLength={3.5}
                                linkDirectionalArrowRelPos={1}
                                linkLabel="type"
                                linkColor={() => '#999'}
                                linkWidth={1.5}
                                onNodeClick={(node) => setSelectedNode(node)}
                                nodeCanvasObjectMode={() => 'after'}
                                nodeCanvasObject={(node: any, ctx, globalScale) => {
                                    const props = node.properties || {};
                                    const label = props.name || props.title || (node.labels && node.labels[0]) || node.id;
                                    const fontSize = 12 / globalScale;
                                    ctx.font = `${fontSize}px Sans-Serif`;
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'top';
                                    ctx.fillStyle = '#000';
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
                                    ctx.fillStyle = '#666';
                                    ctx.fillText(label, textPos.x, textPos.y);
                                }}
                            />
                        )}
                    </div>

                    {/* Right Properties Panel */}
                    {selectedNode && (
                        <div className="w-80 bg-white border-l border-gray-200 overflow-y-auto shadow-xl flex flex-col">
                            <div className="p-3 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                                <h2 className="font-bold text-sm text-gray-800">Node Properties</h2>
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
            )}
        </div>
    );
};

export default OntologyPage;
