import React, { useState, useEffect, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { runCypherQuery } from '../services/neo4jService';
import { Play, Loader2, Database, X } from 'lucide-react';

const OntologyPage: React.FC = () => {
    const [query, setQuery] = useState('MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 100');
    const [graphData, setGraphData] = useState<{ nodes: any[]; links: any[] }>({ nodes: [], links: [] });
    const [selectedNode, setSelectedNode] = useState<any | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

    useEffect(() => {
        // Initial load
        handleRunQuery();

        // Resize observer for responsive graph
        const resizeObserver = new ResizeObserver((entries) => {
            if (entries[0]) {
                setDimensions({
                    width: entries[0].contentRect.width,
                    height: entries[0].contentRect.height,
                });
            }
        });

        if (containerRef.current) {
            resizeObserver.observe(containerRef.current);
        }

        return () => resizeObserver.disconnect();
    }, []);

    const handleRunQuery = async () => {
        setLoading(true);
        setError(null);
        setSelectedNode(null); // Clear selection on new query
        try {
            const result = await runCypherQuery(query);
            setGraphData({ nodes: result.nodes, links: result.links });
        } catch (err: any) {
            setError(err.message || 'An error occurred while executing the query.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-64px)] bg-gray-50 text-gray-900 font-sans">
            {/* Toolbar */}
            <div className="bg-white border-b border-gray-200 p-4 shadow-sm z-10">
                <div className="flex flex-col md:flex-row gap-4 max-w-7xl mx-auto">
                    <div className="flex-1 relative">
                        <textarea
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            className="w-full border border-gray-300 rounded-lg p-3 pr-12 font-mono text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all shadow-sm resize-none h-24 md:h-16"
                            placeholder="Enter Cypher Query..."
                        />
                        {/* Optional: Add query templates here if needed */}
                    </div>
                    <button
                        onClick={handleRunQuery}
                        disabled={loading}
                        className={`px-6 py-2 rounded-lg font-medium flex items-center gap-2 transition-colors self-end md:self-auto h-12 md:h-16
              ${loading
                                ? 'bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200'
                                : 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-md hover:shadow-lg'
                            }`}
                    >
                        {loading ? <Loader2 className="animate-spin w-5 h-5" /> : <Play className="w-5 h-5" />}
                        {loading ? 'Running...' : 'Run Query'}
                    </button>
                </div>
                {error && (
                    <div className="mt-2 text-red-600 text-sm bg-red-50 p-2 rounded border border-red-100 animate-in fade-in slide-in-from-top-1">
                        Error: {error}
                    </div>
                )}
            </div>

            {/* Main Content */}
            <div className="flex-1 relative overflow-hidden flex" ref={containerRef}>
                {/* Graph Area */}
                <div className="flex-1 bg-gray-50 relative">
                    {(graphData.nodes.length === 0 && !loading && !error) ? (
                        <div className="absolute inset-0 flex items-center justify-center text-gray-400 flex-col gap-4">
                            <Database className="w-16 h-16 opacity-20" />
                            <p>No data to visualize. Run a query to see the graph.</p>
                        </div>
                    ) : (
                        <ForceGraph2D
                            width={dimensions.width - (selectedNode ? 384 : 0)} // Subtract 96 (tokens) * 4 = 384px when panel is open
                            height={dimensions.height}
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
                                // Draw text below the node (node radius is typically 4-5)
                                ctx.fillText(label, node.x, node.y + 6);
                            }}
                            linkCanvasObjectMode={() => 'after'}
                            linkCanvasObject={(link: any, ctx, globalScale) => {
                                const label = link.type;
                                if (!label) return;

                                // Calculate middle point of the link
                                const start = link.source;
                                const end = link.target;
                                if (typeof start !== 'object' || typeof end !== 'object') return;

                                const textPos = {
                                    x: (start.x + end.x) / 2,
                                    y: (start.y + end.y) / 2,
                                };

                                // Draw background for better readability
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

                                // Draw text
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
                    <div className="w-96 bg-white border-l border-gray-200 overflow-y-auto shadow-xl z-20 flex flex-col">
                        <div className="p-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                            <h2 className="font-bold text-lg text-gray-800">Node Properties</h2>
                            <button
                                onClick={() => setSelectedNode(null)}
                                className="text-gray-400 hover:text-gray-600 p-1 hover:bg-gray-200 rounded"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="p-4 space-y-6">
                            {/* Primary Info */}
                            <div>
                                <div className="inline-block px-2 py-1 rounded text-xs font-semibold bg-blue-100 text-blue-800 mb-2">
                                    {selectedNode.labels ? selectedNode.labels.join(', ') : 'Node'}
                                </div>
                                <div className="text-sm text-gray-500 font-mono break-all">
                                    ID: {selectedNode.id}
                                </div>
                            </div>

                            {/* Properties Table */}
                            <div>
                                <h3 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">Properties</h3>
                                <div className="space-y-3">
                                    {Object.entries(selectedNode.properties || {}).map(([key, value]: [string, any]) => (
                                        <div key={key} className="grid grid-cols-3 gap-2 text-sm border-b border-gray-50 pb-2 last:border-0">
                                            <div className="font-medium text-gray-600 break-words">{key}</div>
                                            <div className="col-span-2 text-gray-900 break-words font-mono text-xs bg-gray-50 p-1.5 rounded">
                                                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default OntologyPage;
