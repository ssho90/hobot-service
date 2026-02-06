import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { AlertCircle, CheckCircle2, Loader2, X } from 'lucide-react';

interface RebalancingTestModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const RebalancingTestModal: React.FC<RebalancingTestModalProps> = ({ isOpen, onClose }) => {
    const { getAuthHeaders } = useAuth();
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);
    const [selectedPhase, setSelectedPhase] = useState<number | null>(null);

    if (!isOpen) return null;

    const runTest = async () => {
        if (!selectedPhase) return;

        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const response = await fetch('/api/macro-trading/rebalance/test', {
                method: 'POST',
                headers: {
                    ...getAuthHeaders(),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ max_phase: selectedPhase }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Test execution failed');
            }

            setResult(data);
        } catch (err: any) {
            setError(err.message || 'An unexpected error occurred');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col m-4 overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100">
                    <h3 className="text-lg font-bold text-zinc-900">Rebalancing Test</h3>
                    <button
                        onClick={onClose}
                        className="p-2 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 rounded-lg transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 overflow-y-auto min-h-0 flex-1">
                    <div className="grid grid-cols-2 gap-4 mb-6">
                        <button
                            onClick={() => setSelectedPhase(4)}
                            disabled={loading}
                            className={`p-4 rounded-xl border-2 transition-all text-left relative overflow-hidden group
                                ${selectedPhase === 4
                                    ? 'border-blue-500 bg-blue-50'
                                    : 'border-zinc-200 hover:border-blue-300 hover:bg-slate-50'
                                }`}
                        >
                            <div className="z-10 relative">
                                <h4 className="font-bold text-zinc-900 mb-1">Step 3 & 4</h4>
                                <p className="text-sm text-zinc-500">Drift Check & Planning</p>
                                <p className="text-xs text-zinc-400 mt-2">리밸런싱 필요 여부 확인 및 매매 계획 수립</p>
                            </div>
                            {selectedPhase === 4 && loading && (
                                <div className="absolute top-2 right-2">
                                    <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                                </div>
                            )}
                        </button>

                        <button
                            onClick={() => setSelectedPhase(5)}
                            disabled={loading}
                            className={`p-4 rounded-xl border-2 transition-all text-left relative overflow-hidden group
                                ${selectedPhase === 5
                                    ? 'border-red-500 bg-red-50'
                                    : 'border-zinc-200 hover:border-red-300 hover:bg-slate-50'
                                }`}
                        >
                            <div className="z-10 relative">
                                <h4 className="font-bold text-zinc-900 mb-1">Step 5</h4>
                                <p className="text-sm text-zinc-500">Full Execution</p>
                                <p className="text-xs text-zinc-400 mt-2">실제 매매 주문 실행 (주의)</p>
                            </div>
                            {selectedPhase === 5 && loading && (
                                <div className="absolute top-2 right-2">
                                    <Loader2 className="w-5 h-5 text-red-500 animate-spin" />
                                </div>
                            )}
                        </button>
                    </div>

                    {/* Result Area */}
                    {loading && !result && (
                        <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
                            <Loader2 className="w-8 h-8 mb-3 animate-spin text-blue-500" />
                            <p>Running Test Sequence...</p>
                        </div>
                    )}

                    {error && (
                        <div className="p-4 bg-red-50 border border-red-100 rounded-xl flex items-start gap-3">
                            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                            <div>
                                <h4 className="text-sm font-bold text-red-700 mb-1">Execution Failed</h4>
                                <p className="text-sm text-red-600 whitespace-pre-wrap">{error}</p>
                            </div>
                        </div>
                    )}

                    {result && (
                        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                            <div className="flex items-center gap-2 mb-3">
                                <CheckCircle2 className="w-5 h-5 text-green-500" />
                                <h4 className="font-bold text-zinc-900">Execution Result</h4>
                            </div>
                            <div className="bg-slate-900 rounded-xl p-4 overflow-x-auto">
                                <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap">
                                    {JSON.stringify(result, null, 2)}
                                </pre>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="bg-slate-50 px-6 py-4 border-t border-zinc-200 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-white border border-zinc-300 rounded-lg text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
                    >
                        Close
                    </button>
                    <button
                        onClick={runTest}
                        disabled={!selectedPhase || loading}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-300 disabled:cursor-not-allowed text-white rounded-lg text-sm font-bold transition-all shadow-sm flex items-center gap-2"
                    >
                        {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                        진행
                    </button>
                </div>
            </div>
        </div>
    );
};
