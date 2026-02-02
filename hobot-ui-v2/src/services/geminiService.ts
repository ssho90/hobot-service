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
