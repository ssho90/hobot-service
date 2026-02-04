import neo4j, { Driver, Session } from 'neo4j-driver';

const NEO4J_URI = import.meta.env.VITE_NEO4J_URI || 'bolt://52.78.104.1:7687';
const NEO4J_USER = import.meta.env.VITE_NEO4J_USER || 'neo4j';
const NEO4J_PASSWORD = import.meta.env.VITE_NEO4J_PASSWORD || 'ssh8991!';

let driver: Driver | null = null;

export const getDriver = (): Driver => {
    if (!driver) {
        driver = neo4j.driver(NEO4J_URI, neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD));
    }
    return driver;
};

export const runCypherQuery = async (query: string, params: Record<string, any> = {}) => {
    const driver = getDriver();
    const session: Session = driver.session();

    try {
        const result = await session.run(query, params);

        // Process results for graph visualization (ForceGraph2D format: { nodes, links })
        const nodes: any[] = [];
        const links: any[] = [];
        const nodeIds = new Set();
        const linkIds = new Set();

        result.records.forEach((record) => {
            record.keys.forEach((key) => {
                const value = record.get(key);

                if (value && typeof value === 'object') {
                    if (value.labels) {
                        // It's a Node
                        const id = value.elementId || value.identity.toString();
                        if (!nodeIds.has(id)) {
                            nodes.push({
                                id,
                                labels: value.labels,
                                properties: value.properties || {},
                                val: 1 // Default size
                            });
                            nodeIds.add(id);
                        }
                    } else if (value.type && value.startNodeElementId && value.endNodeElementId) {
                        // It's a Relationship (neo4j v5)
                        const id = value.elementId || value.identity.toString();
                        if (!linkIds.has(id)) {
                            links.push({
                                source: value.startNodeElementId,
                                target: value.endNodeElementId,
                                type: value.type,
                                ...value.properties
                            });
                            linkIds.add(id);
                        }
                    } else if (value.type && value.start && value.end) {
                        // It's a Relationship (neo4j v4)
                        const id = value.identity.toString();
                        if (!linkIds.has(id)) {
                            links.push({
                                source: value.start.toString(),
                                target: value.end.toString(),
                                type: value.type,
                                ...value.properties
                            });
                            linkIds.add(id);
                        }
                    }
                }
            });
        });

        return { nodes, links, raw: result.records };
    } catch (error) {
        console.error('Neo4j Query Error:', error);
        throw error;
    } finally {
        await session.close();
    }
};

export const closeDriver = async () => {
    if (driver) {
        await driver.close();
        driver = null;
    }
};
