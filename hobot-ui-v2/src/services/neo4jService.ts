// Neo4j API calls through backend proxy
// All database connections are managed on the backend for security

export interface GraphNode {
    id: string;
    labels: string[];
    properties: Record<string, any>;
    val: number;
}

export interface GraphLink {
    source: string;
    target: string;
    type: string;
    [key: string]: any;
}

export interface GraphData {
    nodes: GraphNode[];
    links: GraphLink[];
    raw: any[];
}

export const runCypherQuery = async (
    query: string,
    params: Record<string, any> = {},
    database: string = 'architecture'
): Promise<GraphData> => {
    try {
        const response = await fetch('/api/neo4j/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ query, params, database }),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `API error: ${response.status}`);
        }

        const result = await response.json();

        if (result.status === 'success' && result.data) {
            return {
                nodes: result.data.nodes || [],
                links: result.data.links || [],
                raw: result.data.raw || []
            };
        }

        throw new Error('API 응답 형식 오류');
    } catch (error) {
        console.error('Neo4j Query Error:', error);
        throw error;
    }
};

export const checkNeo4jHealth = async (database: string = 'architecture'): Promise<{ status: string; message: string }> => {
    try {
        const response = await fetch(`/api/neo4j/health?database=${database}`);

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('Neo4j Health Check Error:', error);
        return { status: 'error', message: error instanceof Error ? error.message : 'Connection failed' };
    }
};

// Legacy exports for compatibility (no-op since backend handles connections)
export const getDriver = () => {
    console.warn('getDriver() is deprecated. Neo4j connections are now managed by the backend.');
    return null;
};

export const closeDriver = async () => {
    console.warn('closeDriver() is deprecated. Neo4j connections are now managed by the backend.');
};
