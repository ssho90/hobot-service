export const safeNumber = (value: string | number | undefined | null): number => {
  const num = Number(value);
  return Number.isNaN(num) ? 0 : num;
};

export const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(safeNumber(value));
};

export const formatPercent = (value: number): string => {
  const num = safeNumber(value);
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
};

export const getTimeAgo = (dateString?: string): string => {
  if (!dateString) return '';
  const now = new Date();
  const date = new Date(dateString);
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) return `${diffInSeconds}s ago`;
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  return `${Math.floor(diffInSeconds / 86400)}d ago`;
};
