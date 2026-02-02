import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { X } from 'lucide-react';

interface BriefingSummaryModalProps {
    isOpen: boolean;
    onClose: () => void;
    summary: string;
    createdAt: string;
}

export const BriefingSummaryModal: React.FC<BriefingSummaryModalProps> = ({ isOpen, onClose, summary, createdAt }) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
                <div className="flex items-center justify-between p-6 border-b border-stone-200 bg-stone-50">
                    <div>
                        <h2 className="text-xl font-bold text-stone-900 font-serif">Detailed Market Analysis</h2>
                        <p className="text-sm text-stone-500 mt-1">{createdAt}</p>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-stone-200 rounded-full transition-colors text-stone-500 hover:text-stone-700">
                        <X className="w-6 h-6" />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-8 bg-[#fcfbf9]">
                    <article className="prose prose-stone max-w-none prose-headings:font-serif prose-headings:font-bold prose-p:text-stone-700 prose-li:text-stone-700">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown>
                    </article>
                </div>
            </div>
        </div>
    );
};
