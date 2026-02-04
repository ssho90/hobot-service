import { GoogleGenAI, type GenerateContentResponse } from "@google/genai";

// Initialize Gemini Client lazily
// In Vite, use import.meta.env for environment variables
const getGeminiClient = () => {
  const apiKey = import.meta.env.VITE_GEMINI_API_KEY || '';
  if (!apiKey) {
    return null;
  }
  return new GoogleGenAI({ apiKey });
};

// Graph DB schema description for Cypher generation
const GRAPH_SCHEMA = `
Graph Database Schema:
- Node Labels: Resource, VNet, Subnet, Subscription, Environment
- Relationships: 
  - (Resource)-[:BELONGS_TO]->(Subscription)
  - (VNet)-[:BELONGS_TO]->(Subscription)
  - (Subnet)-[:PART_OF]->(VNet)
  - (Resource)-[:DEPLOYED_IN]->(Subnet)
  - (Resource)-[:IN_ENVIRONMENT]->(Environment)
  - (VNet)-[:IN_ENVIRONMENT]->(Environment)
- Common Node Properties: name, id, type, status, region, createdAt
- Resource types may include: VM, Storage, Database, LoadBalancer, etc.
`;

export interface GraphQueryResult {
  cypher: string;
  answer: string;
  rawData?: any[];
}

export const generateCypherFromNaturalLanguage = async (
  question: string,
  schemaOverride?: string
): Promise<{ cypher: string; error?: string }> => {
  try {
    const ai = getGeminiClient();
    if (!ai) {
      return {
        cypher: '',
        error: "Gemini API is not configured. Please set the VITE_GEMINI_API_KEY environment variable."
      };
    }

    const schema = schemaOverride || GRAPH_SCHEMA;

    const response: GenerateContentResponse = await ai.models.generateContent({
      model: 'gemini-2.0-flash',
      contents: `${schema}

User Question: ${question}

Generate a Cypher query to answer this question. 
IMPORTANT: 
- Return ONLY the Cypher query, no explanation
- Use LIMIT 50 for safety unless specific count is requested
- Match the schema labels and relationships exactly`,
      config: {
        systemInstruction: "You are a Cypher query expert. Generate only valid Neo4j Cypher queries based on the given schema. Return ONLY the query, no markdown formatting, no explanations.",
      },
    });

    const cypher = response.text?.trim().replace(/```cypher\n?/g, '').replace(/```\n?/g, '').trim() || '';
    return { cypher };
  } catch (error) {
    console.error("Cypher Generation Error:", error);
    return {
      cypher: '',
      error: "Failed to generate Cypher query."
    };
  }
};

export const explainQueryResults = async (
  question: string,
  cypher: string,
  results: any[]
): Promise<string> => {
  try {
    const ai = getGeminiClient();
    if (!ai) {
      return "Gemini API is not configured.";
    }

    const resultsStr = JSON.stringify(results.slice(0, 20), null, 2);

    const response: GenerateContentResponse = await ai.models.generateContent({
      model: 'gemini-2.0-flash',
      contents: `User asked: "${question}"

Cypher query used: ${cypher}

Query results (JSON):
${resultsStr}

Please provide a clear, human-readable answer to the user's question based on these results. 
- Be concise but informative
- Highlight key findings
- Use bullet points for multiple items if appropriate
- If no results, say so clearly`,
      config: {
        systemInstruction: "You are a helpful assistant that explains graph database query results in plain language. Be concise and focus on answering the user's original question.",
      },
    });

    return response.text || "Unable to explain results.";
  } catch (error) {
    console.error("Result Explanation Error:", error);
    return "Unable to generate explanation for the results.";
  }
};

export const generateMarketAnalysis = async (query: string): Promise<{ text: string; sources: { uri: string; title: string }[] }> => {
  try {
    const ai = getGeminiClient();
    if (!ai) {
      return {
        text: "Gemini API is not configured. Please set the VITE_GEMINI_API_KEY environment variable.",
        sources: []
      };
    }

    const response: GenerateContentResponse = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: query,
      config: {
        tools: [{ googleSearch: {} }], // Enable Search Grounding for real-time market news
        systemInstruction: "You are a senior financial market analyst for 'StockOverflow'. Provide concise, data-backed insights. When asked about specific stocks or market trends, use Google Search to find the latest information. Summarize key reasons for price movements. Keep the tone professional but accessible.",
      },
    });

    const text = response.text || "I couldn't generate an analysis at this moment.";

    // Extract grounding chunks for sources
    const sources: { uri: string; title: string }[] = [];
    if (response.candidates?.[0]?.groundingMetadata?.groundingChunks) {
      response.candidates[0].groundingMetadata.groundingChunks.forEach((chunk: any) => {
        if (chunk.web?.uri && chunk.web?.title) {
          sources.push({
            uri: chunk.web.uri,
            title: chunk.web.title,
          });
        }
      });
    }

    return { text, sources };
  } catch (error) {
    console.error("Gemini API Error:", error);
    return {
      text: "Unable to retrieve real-time market data at the moment. Please check your API configuration.",
      sources: []
    };
  }
};
