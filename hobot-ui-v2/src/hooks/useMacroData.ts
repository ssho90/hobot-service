import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';

export interface HoldingItem {
  stock_code: string;
  stock_name: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  profit_loss: number;
  profit_loss_rate: number;
  eval_amount: number;
}

export interface BalanceData {
  total_eval_amount: number;
  total_purchase_amount: number;
  net_invested_amount?: number;
  total_profit_loss: number;
  total_profit_loss_rate: number;
  total_return_rate?: number;
  holdings: HoldingItem[];
  status?: string;
}

export interface AllocationItem {
  name: string;
  ticker: string;
  weight_percent: number;
}

export interface AssetClassAllocation {
  asset_class: string;
  sub_mp_name?: string;
  sub_mp_description?: string;
  updated_at?: string;
  target: AllocationItem[];
  actual: AllocationItem[];
}

export interface MPData {
  name?: string;
  description?: string;
  updated_at?: string;
  started_at?: string;
  decision_date?: string;
  target_allocation: Record<string, number>;
  actual_allocation: Record<string, number>;
}

export interface RebalancingData {
  mp: MPData;
  sub_mp: AssetClassAllocation[];
  rebalancing_status: {
    needed: boolean;
    reasons: string[];
    thresholds: { mp: number; sub_mp: number };
  };
}

export interface ETFDetail {
  category: string;
  ticker: string;
  name: string;
  weight: number;
}

export interface SubMPCategory {
  sub_mp_id: string;
  sub_mp_name: string;
  sub_mp_description?: string;
  updated_at?: string;
  started_at?: string;
  etf_details: ETFDetail[];
}

export interface SubMP {
  stocks?: SubMPCategory;
  bonds?: SubMPCategory;
  alternatives?: SubMPCategory;
  cash?: SubMPCategory;
}

export interface OverviewData {
  mp_id: string;
  mp_info?: {
    name: string;
    description: string;
    updated_at: string;
    started_at?: string;
  };
  analysis_summary: string;
  reasoning: string;
  sub_mp_reasoning: string;
  target_allocation: {
    Stocks: number;
    Bonds: number;
    Alternatives: number;
    Cash: number;
  };
  sub_mp: SubMP;
  decision_date: string;
}

interface HookOptions {
  enabled?: boolean;
}

interface HookState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refreshing: boolean;
  refresh: () => void;
}

const isAbortError = (error: unknown): boolean => {
  return (error as Error)?.name === 'AbortError';
};

export const useOverview = ({ enabled = true }: HookOptions = {}): HookState<OverviewData> => {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const hasFetched = useRef(false);

  const fetchOverview = useCallback(async (signal?: AbortSignal, isRefresh = false) => {
    if (!enabled) {
      setRefreshing(false);
      return;
    }

    if (!isRefresh && hasFetched.current) {
      setLoading(false);
      return;
    }

    setError(null);
    if (!isRefresh) setLoading(true);

    try {
      const response = await fetch('/api/macro-trading/overview', { signal });
      if (response.ok) {
        const result = await response.json();
        if (result.status === 'success' && result.data) {
          setData(result.data);
        } else {
          setError('API 응답 형식 오류');
        }
      } else {
        setError(`API 오류: ${response.status}`);
      }
    } catch (err) {
      if (isAbortError(err)) return;
      console.error('Error fetching overview:', err);
      setError('API 연결 실패');
    } finally {
      if (signal?.aborted) return;
      if (!isRefresh) {
        setLoading(false);
        hasFetched.current = true;
      }
      setRefreshing(false);
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    fetchOverview(controller.signal);
    return () => controller.abort();
  }, [enabled, fetchOverview]);

  const refresh = useCallback(() => {
    if (!enabled) return;
    setRefreshing(true);
    fetchOverview(undefined, true);
  }, [enabled, fetchOverview]);

  return { data, loading, error, refreshing, refresh };
};

export const useBalance = ({ enabled = true }: HookOptions = {}): HookState<BalanceData> => {
  const { getAuthHeaders, isAuthenticated, loading: authLoading } = useAuth();
  const [data, setData] = useState<BalanceData | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const hasFetched = useRef(false);

  const fetchBalance = useCallback(async (signal?: AbortSignal, isRefresh = false) => {
    if (!isAuthenticated) {
      setRefreshing(false);
      return;
    }

    if (!isRefresh && hasFetched.current) {
      setLoading(false);
      return;
    }

    setError(null);
    if (!isRefresh) setLoading(true);

    try {
      const response = await fetch('/api/kis/balance', {
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        signal
      });

      if (response.ok) {
        const balanceData = await response.json();
        if (balanceData.status === 'error') {
          console.warn('KIS Balance returned error:', balanceData);
        } else {
          setData(balanceData);
        }
      } else if (response.status === 401) {
        setError('KIS API 인증정보가 없습니다.');
      } else {
        setError(`API 오류: ${response.status}`);
      }
    } catch (err) {
      if (isAbortError(err)) return;
      console.error('Balance fetch error:', err);
      setError('데이터를 불러오는데 실패했습니다.');
    } finally {
      if (signal?.aborted) return;
      if (!isRefresh) {
        setLoading(false);
        hasFetched.current = true;
      }
      setRefreshing(false);
    }
  }, [getAuthHeaders, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setData(null);
      setError(null);
      setLoading(false);
      setRefreshing(false);
      hasFetched.current = false;
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!enabled || authLoading || !isAuthenticated) {
      if (!enabled || !isAuthenticated) setLoading(false);
      return;
    }

    const controller = new AbortController();
    fetchBalance(controller.signal);
    return () => controller.abort();
  }, [enabled, authLoading, isAuthenticated, fetchBalance]);

  const refresh = useCallback(() => {
    if (!enabled || !isAuthenticated) return;
    setRefreshing(true);
    fetchBalance(undefined, true);
  }, [enabled, isAuthenticated, fetchBalance]);

  return { data, loading, error, refreshing, refresh };
};

export const useRebalancing = ({ enabled = true }: HookOptions = {}): HookState<RebalancingData> => {
  const { getAuthHeaders, isAuthenticated, loading: authLoading } = useAuth();
  const [data, setData] = useState<RebalancingData | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const hasFetched = useRef(false);

  const fetchRebalancing = useCallback(async (signal?: AbortSignal, isRefresh = false) => {
    if (!isAuthenticated) {
      setRefreshing(false);
      return;
    }

    if (!isRefresh && hasFetched.current) {
      setLoading(false);
      return;
    }

    setError(null);
    if (!isRefresh) setLoading(true);

    try {
      const response = await fetch('/api/macro-trading/rebalancing-status', {
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        signal
      });

      if (response.ok) {
        const resJson = await response.json();
        if (resJson.data) {
          setData(resJson.data);
        } else {
          setData(resJson);
        }
      } else if (response.status === 401) {
        setError('인증이 필요합니다.');
      } else {
        setError(`API 오류: ${response.status}`);
      }
    } catch (err) {
      if (isAbortError(err)) return;
      console.error('Rebalancing fetch error:', err);
      setError('리밸런싱 데이터를 불러오는데 실패했습니다.');
    } finally {
      if (signal?.aborted) return;
      if (!isRefresh) {
        setLoading(false);
        hasFetched.current = true;
      }
      setRefreshing(false);
    }
  }, [getAuthHeaders, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setData(null);
      setError(null);
      setLoading(false);
      setRefreshing(false);
      hasFetched.current = false;
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!enabled || authLoading || !isAuthenticated) {
      if (!enabled || !isAuthenticated) setLoading(false);
      return;
    }

    const controller = new AbortController();
    fetchRebalancing(controller.signal);
    return () => controller.abort();
  }, [enabled, authLoading, isAuthenticated, fetchRebalancing]);

  const refresh = useCallback(() => {
    if (!enabled || !isAuthenticated) return;
    setRefreshing(true);
    fetchRebalancing(undefined, true);
  }, [enabled, isAuthenticated, fetchRebalancing]);

  return { data, loading, error, refreshing, refresh };
};
