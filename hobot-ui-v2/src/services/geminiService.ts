// Gemini API calls through backend proxy
// All API keys are managed on the backend for security

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
    const response = await fetch('/api/gemini/generate-cypher', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ 
        question, 
        schema_override: schemaOverride 
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `API error: ${response.status}`);
    }

    const result = await response.json();
    
    if (result.status === 'success' && result.data) {
      return { cypher: result.data.cypher || '' };
    }

    return {
      cypher: '',
      error: "API 응답 형식 오류"
    };
  } catch (error) {
    console.error("Cypher Generation Error:", error);
    return {
      cypher: '',
      error: error instanceof Error ? error.message : "Cypher 쿼리 생성에 실패했습니다."
    };
  }
};

export const explainQueryResults = async (
  question: string,
  cypher: string,
  results: any[]
): Promise<string> => {
  try {
    const response = await fetch('/api/gemini/explain-results', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question, cypher, results }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const result = await response.json();
    
    if (result.status === 'success' && result.data) {
      return result.data.explanation || "결과를 설명할 수 없습니다.";
    }

    return "API 응답 형식 오류";
  } catch (error) {
    console.error("Result Explanation Error:", error);
    return "결과 설명을 생성할 수 없습니다.";
  }
};

export const generateMarketAnalysis = async (query: string): Promise<{ text: string; sources: { uri: string; title: string }[] }> => {
  try {
    const response = await fetch('/api/gemini/market-analysis', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const result = await response.json();
    
    if (result.status === 'success' && result.data) {
      return {
        text: result.data.text || "분석을 생성할 수 없습니다.",
        sources: result.data.sources || []
      };
    }

    return {
      text: "API 응답 형식 오류",
      sources: []
    };
  } catch (error) {
    console.error("Market Analysis API Error:", error);
    return {
      text: "실시간 시장 데이터를 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
      sources: []
    };
  }
};
