import { GoogleGenAI, GenerateContentResponse } from "@google/genai";

// Initialize Gemini Client
// In a real app, ensure process.env.API_KEY is defined. 
// For this demo, we assume the environment is set up correctly as per instructions.
const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

export const generateMarketAnalysis = async (query: string): Promise<{ text: string; sources: { uri: string; title: string }[] }> => {
  try {
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
