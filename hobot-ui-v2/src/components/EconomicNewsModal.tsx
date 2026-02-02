import React, { useEffect, useState } from 'react';
import { X, ExternalLink, Clock, Newspaper } from 'lucide-react';
import { getTimeAgo } from '../utils/formatters';

interface NewsItem {
    id: number;
    title: string;
    link: string;
    description: string;
    published_at: string;
    source: string;
}

interface EconomicNewsModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const EconomicNewsModal: React.FC<EconomicNewsModalProps> = ({ isOpen, onClose }) => {
    const [news, setNews] = useState<NewsItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    const fetchNews = async (pageNum: number) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/macro-trading/economic-news?page=${pageNum}&limit=10`);
            const data = await response.json();
            if (data.status === 'success' && data.data && data.pagination) {
                setNews(data.data);
                setTotalPages(data.pagination.total_pages);
            }
        } catch (error) {
            console.error("Failed to fetch news", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchNews(page);
        }
    }, [isOpen, page]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
                <div className="flex items-center justify-between p-6 border-b border-stone-200 bg-stone-50">
                    <div className="flex items-center gap-3">
                        <div className="bg-stone-100 p-2 rounded-lg">
                            <Newspaper className="w-5 h-5 text-stone-600" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-stone-900 font-serif">Economic Headlines</h2>
                            <p className="text-sm text-stone-500 mt-1">Real-time global economic news feed</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-stone-200 rounded-full transition-colors text-stone-500 hover:text-stone-700">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto bg-[#f9f7f2]">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-20 gap-3">
                            <div className="w-8 h-8 border-4 border-stone-200 border-t-stone-800 rounded-full animate-spin"></div>
                        </div>
                    ) : (
                        <div className="divide-y divide-stone-200">
                            {news.map((item) => (
                                <a
                                    key={item.id}
                                    href={item.link}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="block p-6 hover:bg-white transition-colors group"
                                >
                                    <div className="flex justify-between items-start gap-4">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-1.5">
                                                <span className="text-[10px] font-bold text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-100 uppercase tracking-wide">
                                                    {item.source}
                                                </span>
                                                <span className="text-[10px] text-stone-400 font-medium flex items-center gap-1">
                                                    <Clock className="w-3 h-3" />
                                                    {getTimeAgo(item.published_at)}
                                                </span>
                                            </div>
                                            <h3 className="text-lg font-bold text-stone-900 mb-2 font-serif leading-snug group-hover:text-blue-700 transition-colors">
                                                {item.title}
                                            </h3>
                                            <p className="text-sm text-stone-600 line-clamp-2 leading-relaxed">
                                                {item.description}
                                            </p>
                                        </div>
                                        <ExternalLink className="w-4 h-4 text-stone-300 group-hover:text-blue-400 transition-colors flex-shrink-0" />
                                    </div>
                                </a>
                            ))}
                        </div>
                    )}
                </div>

                <div className="p-4 border-t border-stone-200 flex justify-between items-center bg-white">
                    <span className="text-sm text-stone-500 font-medium">Page {page} of {totalPages}</span>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            disabled={page === 1}
                            className="px-4 py-2 border border-stone-200 rounded-lg text-sm font-medium text-stone-600 bg-white hover:bg-stone-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                        >
                            Previous
                        </button>
                        <button
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            disabled={page === totalPages}
                            className="px-4 py-2 border border-stone-200 rounded-lg text-sm font-medium text-stone-600 bg-white hover:bg-stone-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                        >
                            Next
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
