export type RealEstateView = 'detail' | 'monthly' | 'region';

export interface RealEstateQueryParams {
  view: RealEstateView;
  startYm: string;
  endYm: string;
  lawdCodes?: string;
  propertyType?: string;
  transactionType?: string;
  limit?: number;
  offset?: number;
}

export interface RealEstateQueryResponse {
  view: RealEstateView;
  source: string;
  start_ym: string;
  end_ym: string;
  property_type: string;
  transaction_type: string;
  lawd_codes: string[];
  limit: number;
  offset: number;
  total: number;
  rows: Record<string, unknown>[];
  fallback_used: boolean;
  meta: Record<string, unknown>;
}

const toQuery = (params: RealEstateQueryParams): string => {
  const searchParams = new URLSearchParams();
  searchParams.set('view', params.view);
  searchParams.set('start_ym', params.startYm);
  searchParams.set('end_ym', params.endYm);
  searchParams.set('property_type', params.propertyType ?? 'apartment');
  searchParams.set('transaction_type', params.transactionType ?? 'sale');
  searchParams.set('limit', String(params.limit ?? 500));
  searchParams.set('offset', String(params.offset ?? 0));
  if (params.lawdCodes && params.lawdCodes.trim().length > 0) {
    searchParams.set('lawd_codes', params.lawdCodes.trim());
  }
  return searchParams.toString();
};

export const fetchRealEstateQuery = async (
  params: RealEstateQueryParams
): Promise<RealEstateQueryResponse> => {
  const query = toQuery(params);
  const response = await fetch(`/api/macro/real-estate?${query}`);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail =
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Failed to fetch real-estate data (${response.status})`;
    throw new Error(detail);
  }
  return (await response.json()) as RealEstateQueryResponse;
};
