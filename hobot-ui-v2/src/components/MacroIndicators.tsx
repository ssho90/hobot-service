import React, { useState, useEffect } from 'react';
import { DollarSign, Users, AlertTriangle, LineChart, List, RefreshCw } from 'lucide-react';
import { FredIndicatorStatusModal } from './FredIndicatorStatusModal';
import { ChartCard } from './ChartCard';
import { ExpandedChartModal } from './ExpandedChartModal';

interface IndicatorStatus {
  code: string;
  name: string;
  frequency: string;
  unit: string;
  last_updated: string | null;
  latest_value: number | null;
  last_collected_at: string | null;
  description: string;
  sparkline?: { date: string; value: number }[];
  error?: string;
}

// Indicator grouping
const INDICATOR_GROUPS = {
  liquidity: {
    title: '유동성',
    icon: <DollarSign className="h-5 w-5 text-blue-400" />,
    codes: ['NETLIQ', 'WALCL', 'RRPONTSYD', 'WTREGEN']
  },
  employment: {
    title: '고용',
    icon: <Users className="h-5 w-5 text-emerald-400" />,
    codes: ['PAYEMS', 'UNRATE']
  },
  prices: {
    title: '물가',
    icon: <AlertTriangle className="h-5 w-5 text-amber-400" />,
    // Codes may vary depending on what FRED collector imports, check fred_collector.py
    codes: ['CPIAUCSL', 'PCEPI', 'FEDFUNDS', 'DFII10', 'T10YIE', 'PCEPILFE']
  },
  growth: {
    title: '경기성장 및 리스크 신호',
    icon: <LineChart className="h-5 w-5 text-rose-400" />,
    codes: ['GDPNOW', 'T10Y2Y', 'DGS10', 'DGS2', 'BAMLH0A0HYM2', 'VIXCLS', 'STLFSI4']
  }
};

export const MacroIndicators: React.FC = () => {
  const [isFredModalOpen, setIsFredModalOpen] = useState(false);
  const [indicators, setIndicators] = useState<IndicatorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndicator, setSelectedIndicator] = useState<IndicatorStatus | null>(null);

  const fetchIndicators = async () => {
    try {
      setLoading(true);
      const apiUrl = (import.meta as any).env.VITE_API_URL || '';
      const response = await fetch(`${apiUrl}/api/macro-trading/fred-indicators`);

      if (!response.ok) {
        throw new Error('Failed to fetch indicators');
      }

      const data = await response.json();
      setIndicators(data.data);
      setError(null);
    } catch (err: any) {
      console.error('Error fetching indicators:', err);
      setError('Failed to load macro data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIndicators();
  }, []);

  const mapSparklineToData = (sparkline?: { date: string; value: number }[]) => {
    if (!sparkline) return [];
    return sparkline.map(point => ({
      date: point.date,
      value: point.value
    }));
  };

  // Helper to check for stale data (Logic copied from FredIndicatorStatusModal)
  const checkIsStale = (ind: IndicatorStatus) => {
    if (!ind.last_collected_at) return true;

    const collectedDate = new Date(ind.last_collected_at);
    const now = new Date();
    const diffDays = (now.getTime() - collectedDate.getTime()) / (1000 * 3600 * 24);

    if (ind.frequency === 'daily' && diffDays > 2) return true;
    if (ind.frequency === 'weekly' && diffDays > 8) return true;
    if (ind.frequency === 'monthly' && diffDays > 32) return true;
    if (ind.frequency === 'quarterly' && diffDays > 95) return true;
    if (diffDays > 365) return true;

    return false;
  };

  // Helper to get indicators for a specific group
  const getGroupIndicators = (groupCodes: string[]) => {
    return groupCodes
      .map(code => indicators.find(i => i.code === code))
      .filter((i): i is IndicatorStatus => !!i);
  };

  const renderChartGrid = (groupKey: keyof typeof INDICATOR_GROUPS) => {
    const group = INDICATOR_GROUPS[groupKey];
    const groupInds = getGroupIndicators(group.codes);

    if (groupInds.length === 0) return null;

    return (
      <div key={groupKey}>
        <h3 className="text-lg font-bold text-zinc-800 mb-5 flex items-center gap-2">
          {group.icon} {group.title}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {groupInds.map(ind => {
            // Determine color
            let color = "#3b82f6";
            if (ind.frequency === 'daily') color = "#10b981";
            if (ind.frequency === 'monthly') color = "#f59e0b";
            if (ind.frequency === 'weekly') color = "#8b5cf6";

            // Determine icon
            return (
              <ChartCard
                key={ind.code}
                title={ind.name}
                subtitle={`${ind.code} • ${ind.frequency}`}
                data={mapSparklineToData(ind.sparkline)}
                color={color}
                frequency={ind.frequency}
                latestValue={ind.latest_value || undefined}
                unit={ind.unit}
                isStale={checkIsStale(ind)}
                lastCollectedAt={ind.last_collected_at}
                onExpand={() => setSelectedIndicator(ind)}
              />
            );
          })}
        </div>
      </div>
    );
  };

  if (loading && indicators.length === 0) {
    return (
      <div className="flex items-center justify-center p-12">
        <RefreshCw className="w-8 h-8 animate-spin text-zinc-300" />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <div className="flex justify-end">
        <button
          onClick={() => setIsFredModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-zinc-200 rounded-lg text-sm font-medium text-zinc-600 hover:bg-zinc-50 hover:text-blue-600 hover:border-blue-200 transition-all shadow-sm"
        >
          <List className="w-4 h-4" />
          FRED 지표 목록 확인
        </button>
      </div>

      <FredIndicatorStatusModal
        isOpen={isFredModalOpen}
        onClose={() => setIsFredModalOpen(false)}
      />

      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-lg flex items-center justify-center">
          <p>{error}</p>
          <button onClick={fetchIndicators} className="ml-4 underline text-sm">Retry</button>
        </div>
      )}

      {/* Render Groups */}
      {(Object.keys(INDICATOR_GROUPS) as Array<keyof typeof INDICATOR_GROUPS>).map(key =>
        renderChartGrid(key)
      )}

      {/* Expanded Chart Modal */}
      <ExpandedChartModal
        isOpen={!!selectedIndicator}
        onClose={() => setSelectedIndicator(null)}
        title={selectedIndicator?.name || ''}
        subtitle={`${selectedIndicator?.code || ''} - ${selectedIndicator?.description || ''}`}
        data={mapSparklineToData(selectedIndicator?.sparkline)}
        color={selectedIndicator?.frequency === 'daily' ? "#10b981" : "#3b82f6"}
        frequency={selectedIndicator?.frequency || ''}
        unit={selectedIndicator?.unit || ''}
      />
    </div>
  );
};