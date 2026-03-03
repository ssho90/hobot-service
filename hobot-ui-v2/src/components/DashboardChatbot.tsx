import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, ChevronUp, Loader2, MessageCircle, Send, X } from 'lucide-react';
import {
  fetchGraphRagAnswer,
  streamGraphRagAnswer,
  type GraphRagAnswerResponse,
  type GraphRagAnswerRequest,
} from '../services/graphRagService';
import { useAuth } from '../context/AuthContext';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

const MOBILE_BREAKPOINT = 1024;
const MIN_INPUT_HEIGHT = 56;
const MAX_INPUT_HEIGHT = 220;
const MIN_QUESTION_LENGTH = 3;

const suggestedQuestions = [
  '테슬라 주가 전망 어때?',
  '한국 부동산 지금 매수하기 괜찮아보여?',
  '한국 주식 유망한 섹터 추천해줘',
];

const buildFriendlyAnswer = (response: GraphRagAnswerResponse): string => {
  const summary = response.answer.conclusion?.trim();
  const points = (response.answer.key_points || [])
    .map((point) => String(point || '').trim())
    .filter((point) => point.length > 0)
    .slice(0, 5);
  const uncertainty = response.answer.uncertainty?.trim();

  const lines: string[] = [];
  lines.push(summary || '분석 결과를 정리해드릴게요.');

  if (points.length > 0) {
    lines.push('', '핵심 포인트');
    points.forEach((point) => lines.push(`- ${point}`));
  }

  if (uncertainty) {
    lines.push('', `참고: ${uncertainty}`);
  }

  return lines.join('\n');
};

export const DashboardChatbot: React.FC = () => {
  const { user } = useAuth();
  const isAdminUser = user?.role === 'admin';
  const [isOpen, setIsOpen] = useState(false);
  const [isMobileLayout, setIsMobileLayout] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.innerWidth < MOBILE_BREAKPOINT;
  });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [inputHeight, setInputHeight] = useState(MIN_INPUT_HEIGHT);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const resizeSessionRef = useRef<{ startY: number; startHeight: number } | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const hasAskedFirstQuestion = useMemo(
    () => messages.some((message) => message.role === 'user'),
    [messages]
  );

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, isOpen]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleResize = () => {
      setIsMobileLayout(window.innerWidth < MOBILE_BREAKPOINT);
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    inputRef.current?.focus();
  }, [isOpen, isMobileLayout]);

  useEffect(() => {
    if (!isOpen || !isMobileLayout) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen, isMobileLayout]);

  const clampInputHeight = useCallback((height: number) => {
    return Math.min(MAX_INPUT_HEIGHT, Math.max(MIN_INPUT_HEIGHT, height));
  }, []);

  const handleResizeMove = useCallback(
    (event: PointerEvent) => {
      const session = resizeSessionRef.current;
      if (!session) return;
      const delta = session.startY - event.clientY;
      setInputHeight(clampInputHeight(session.startHeight + delta));
    },
    [clampInputHeight]
  );

  const stopInputResize = useCallback(() => {
    resizeSessionRef.current = null;
    window.removeEventListener('pointermove', handleResizeMove);
    window.removeEventListener('pointerup', stopInputResize);
  }, [handleResizeMove]);

  useEffect(() => {
    return () => {
      window.removeEventListener('pointermove', handleResizeMove);
      window.removeEventListener('pointerup', stopInputResize);
    };
  }, [handleResizeMove, stopInputResize]);

  const startInputResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    resizeSessionRef.current = {
      startY: event.clientY,
      startHeight: inputHeight,
    };
    window.addEventListener('pointermove', handleResizeMove);
    window.addEventListener('pointerup', stopInputResize);
  };

  const sendQuestion = useCallback(
    async (overrideQuestion?: string) => {
      if (!isAdminUser) return;
      const question = (overrideQuestion ?? input).trim();
      if (!question || loading) return;
      if (question.length < MIN_QUESTION_LENGTH) {
        const now = Date.now();
        setMessages((prev) => [
          ...prev,
          {
            id: `u-${now}`,
            role: 'user',
            content: question,
            timestamp: new Date(now),
          },
          {
            id: `a-${now + 1}`,
            role: 'assistant',
            content: `질문은 ${MIN_QUESTION_LENGTH}글자 이상 입력해주세요.`,
            timestamp: new Date(now + 1),
          },
        ]);
        setInput('');
        return;
      }

      const userMessage: ChatMessage = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: question,
        timestamp: new Date(),
      };
      const assistantId = `a-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const assistantPlaceholder: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
      setInput('');
      setLoading(true);

      const payload: GraphRagAnswerRequest = {
        question,
        time_range: '30d',
        model: 'gemini-3-flash-preview',
        include_context: false,
      };

      let finalResponse: GraphRagAnswerResponse | null = null;

      try {
        try {
          await streamGraphRagAnswer(payload, (event) => {
            if (event.type === 'delta') {
              setMessages((prev) =>
                prev.map((message) =>
                  message.id === assistantId
                    ? { ...message, content: `${message.content}${event.text}` }
                    : message
                )
              );
              return;
            }

            if (event.type === 'done') {
              finalResponse = event.response;
              return;
            }

            if (event.type === 'error') {
              throw new Error(event.error || '답변 생성 중 오류가 발생했습니다.');
            }
          });
        } catch {
          finalResponse = await fetchGraphRagAnswer(payload);
          const fallbackText = buildFriendlyAnswer(finalResponse);
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, content: fallbackText }
                : message
            )
          );
        }

        if (!finalResponse) {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, content: '답변 결과를 받지 못했어요. 잠시 후 다시 시도해주세요.' }
                : message
            )
          );
          return;
        }
        const response = finalResponse;

        setMessages((prev) =>
          prev.map((message) => {
            if (message.id !== assistantId) return message;
            if (message.content.trim().length > 0) return message;
            return { ...message, content: buildFriendlyAnswer(response) };
          })
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.';
        setMessages((prev) =>
          prev.map((chatMessage) =>
            chatMessage.id === assistantId
              ? { ...chatMessage, content: `요청 처리 중 오류가 발생했습니다: ${message}` }
              : chatMessage
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [input, loading, isAdminUser]
  );

  const handleSend = async () => {
    await sendQuestion();
  };

  const lockedInputMessage = '관리자(admin)만 사용 가능한 기능입니다.';

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const panel = (
    <div
      className={`flex flex-col bg-white shadow-2xl ${
        isMobileLayout
          ? 'fixed inset-0 z-[60]'
          : 'fixed right-0 top-16 bottom-0 z-40 w-full max-w-[440px] border-l border-zinc-200'
      }`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 bg-gradient-to-r from-blue-50 to-white">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white">
            <Bot className="h-4 w-4" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-zinc-900">StockOverflow Chat</h2>
            <p className="text-[11px] text-zinc-500">주식·부동산·거시경제 질문을 바로 물어보세요</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setIsOpen(false)}
          className="rounded-md border border-zinc-200 bg-white p-1.5 text-zinc-500 hover:text-zinc-900 hover:bg-zinc-50"
          aria-label="챗봇 닫기"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 mb-4">
            <p className="text-sm font-semibold text-zinc-900 mb-1">무엇이든 질문해보세요</p>
            <p className="text-xs text-zinc-500">
              시장 전망, 종목 분석, 부동산 흐름까지 대화형으로 바로 답변해드립니다.
            </p>
          </div>
        )}

        {!hasAskedFirstQuestion && (
          <div className="mb-4">
            <p className="text-xs font-semibold text-zinc-600 mb-2">추천 질문</p>
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => void sendQuestion(question)}
                  disabled={loading || !isAdminUser}
                  className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-700 hover:bg-blue-100 disabled:opacity-60"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-3">
          {messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[88%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white rounded-br-md'
                    : 'bg-zinc-100 text-zinc-900 rounded-bl-md'
                }`}
              >
                {message.content || (message.role === 'assistant' && loading ? '답변 생성 중...' : '')}
                <div className={`mt-1 text-[10px] ${message.role === 'user' ? 'text-blue-100' : 'text-zinc-400'}`}>
                  {message.timestamp.toLocaleTimeString()}
                </div>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-md bg-zinc-100 px-3 py-2 text-xs text-zinc-500 flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
                분석 중...
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
      </div>

      <div className="border-t border-zinc-200 bg-white px-4 py-3">
        <div className="flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={inputRef}
              value={isAdminUser ? input : lockedInputMessage}
              onChange={(event) => {
                if (!isAdminUser) return;
                setInput(event.target.value);
              }}
              onKeyDown={handleKeyDown}
              placeholder="질문을 입력하세요..."
              className="w-full rounded-xl border border-zinc-300 px-3 pt-6 pb-2 pr-10 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 resize-none"
              style={{ height: `${inputHeight}px` }}
              disabled={loading || !isAdminUser}
              readOnly={!isAdminUser}
            />
            <button
              type="button"
              onPointerDown={startInputResize}
              className="absolute right-2 top-2 h-5 w-5 text-zinc-400 hover:text-zinc-700 cursor-ns-resize flex items-center justify-center"
              aria-label="입력창 높이 조절"
              title="드래그해서 입력창 높이 조절"
            >
              <ChevronUp className="h-3 w-3" />
            </button>
          </div>
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={loading || !isAdminUser || input.trim().length < MIN_QUESTION_LENGTH}
            className={`h-11 w-11 rounded-xl flex items-center justify-center ${
              loading || !isAdminUser || input.trim().length < MIN_QUESTION_LENGTH
                ? 'bg-zinc-200 text-zinc-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
            aria-label="질문 전송"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-xl hover:bg-blue-700"
          aria-label="챗봇 열기"
        >
          <MessageCircle className="h-4 w-4" />
          AI 챗봇
        </button>
      )}

      {isOpen && panel}
    </>
  );
};
