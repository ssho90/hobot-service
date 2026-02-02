import React, { useState, useRef, useEffect } from 'react';
import { generateMarketAnalysis } from '../services/geminiService';
import type { ChatMessage } from '../types';
import { Sparkles, Send, Bot, User, ExternalLink, Loader2 } from 'lucide-react';

export const GeminiAnalyst: React.FC = () => {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    { 
      id: 'welcome', 
      role: 'model', 
      text: "Hello! I'm your AI Market Analyst. Ask me about real-time trends, stock explanations, or market news. Try 'Why is Tech dropping today?' or 'Analyze NVDA'." 
    }
  ]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!query.trim() || loading) return;

    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', text: query };
    setMessages(prev => [...prev, userMsg]);
    setQuery('');
    setLoading(true);

    const result = await generateMarketAnalysis(query);
    
    const botMsg: ChatMessage = { 
      id: (Date.now() + 1).toString(), 
      role: 'model', 
      text: result.text,
      sources: result.sources
    };

    setMessages(prev => [...prev, botMsg]);
    setLoading(false);
  };

  return (
    <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 shadow-lg flex flex-col h-[600px] lg:h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-zinc-800 bg-gradient-to-r from-blue-900/30 to-black rounded-t-xl flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="bg-gradient-to-br from-blue-500 to-purple-600 p-1.5 rounded-lg shadow-lg shadow-blue-500/20">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h3 className="font-bold text-zinc-100">Market Intelligence</h3>
            <p className="text-xs text-blue-400 font-medium">Powered by Gemini AI</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-black/40">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'model' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center border border-zinc-700">
                <Bot className="h-5 w-5 text-blue-400" />
              </div>
            )}
            
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${
              msg.role === 'user' 
                ? 'bg-blue-600 text-white rounded-br-none' 
                : 'bg-zinc-950 text-zinc-200 border border-zinc-800 rounded-bl-none shadow-sm'
            }`}>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.text}</p>
              
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-3 pt-3 border-t border-zinc-800">
                  <p className="text-xs text-zinc-500 mb-2 font-medium uppercase tracking-tight">Sources:</p>
                  <div className="flex flex-wrap gap-2">
                    {msg.sources.map((src, idx) => (
                      <a 
                        key={idx} 
                        href={src.uri} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-[10px] bg-zinc-900 hover:bg-zinc-800 text-blue-400 px-2 py-1 rounded transition-colors border border-zinc-800"
                      >
                        <span className="truncate max-w-[100px]">{src.title}</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {msg.role === 'user' && (
               <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
                 <User className="h-5 w-5 text-white" />
               </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-3 justify-start">
             <div className="flex-shrink-0 w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center border border-zinc-700">
                <Bot className="h-5 w-5 text-blue-400" />
              </div>
              <div className="bg-zinc-950 px-4 py-3 rounded-2xl rounded-bl-none border border-zinc-800 flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
                <span className="text-sm text-zinc-500 font-medium">Analyzing market data...</span>
              </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-zinc-800 bg-zinc-900/20">
        <div className="relative flex items-center gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask about a stock or trend..."
            className="flex-1 bg-black border border-zinc-800 text-zinc-200 text-sm rounded-xl pl-4 pr-12 py-3 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 transition-all placeholder:text-zinc-600"
          />
          <button 
            onClick={handleSend}
            disabled={!query.trim() || loading}
            className="absolute right-2 p-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white rounded-lg transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="text-[10px] text-center text-zinc-600 mt-2 font-medium">
          Gemini may display inaccurate info. Always verify financial data.
        </p>
      </div>
    </div>
  );
};