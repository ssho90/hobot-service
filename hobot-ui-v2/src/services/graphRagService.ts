export type TimeRange = '7d' | '30d' | '90d';

export interface GraphRagRequestBase {
  question: string;
  time_range: TimeRange;
  country?: string;
  as_of_date?: string;
  top_k_events?: number;
  top_k_documents?: number;
  top_k_stories?: number;
  top_k_evidences?: number;
}

export interface GraphRagNode {
  id: string;
  type: string;
  label: string;
  properties: Record<string, any>;
}

export interface GraphRagLink {
  source: string;
  target: string;
  type: string;
  properties: Record<string, any>;
}

export interface GraphRagEvidence {
  evidence_id?: string;
  text: string;
  doc_id?: string;
  doc_url?: string;
  doc_title?: string;
  doc_category?: string;
  published_at?: string;
  support_labels: string[];
  event_id?: string;
  claim_id?: string;
}

export interface GraphRagContextResponse {
  nodes: GraphRagNode[];
  links: GraphRagLink[];
  evidences: GraphRagEvidence[];
  suggested_queries: string[];
  meta: Record<string, any>;
}

export interface GraphRagPathway {
  event_id?: string;
  theme_id?: string;
  indicator_code?: string;
  explanation: string;
}

export interface GraphRagCitation {
  evidence_id?: string;
  doc_id?: string;
  doc_url?: string;
  doc_title?: string;
  published_at?: string;
  text: string;
  support_labels: string[];
  node_ids: string[];
}

export interface GraphRagAnswerPayload {
  conclusion: string;
  uncertainty: string;
  key_points: string[];
  impact_pathways: GraphRagPathway[];
  evidence_policy: string;
}

export interface GraphRagAnswerRequest extends GraphRagRequestBase {
  model?: 'gemini-3-flash-preview' | 'gemini-3-pro-preview';
  timeout_sec?: number;
  max_prompt_evidences?: number;
  include_context?: boolean;
}

export interface GraphRagAnswerResponse {
  question: string;
  model: string;
  as_of_date: string;
  answer: GraphRagAnswerPayload;
  citations: GraphRagCitation[];
  suggested_queries: string[];
  context_meta: Record<string, any>;
  raw_model_output?: Record<string, any>;
  context?: GraphRagContextResponse | null;
}

const getHeaders = (): Record<string, string> => {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
};

export const fetchGraphRagContext = async (
  payload: GraphRagRequestBase
): Promise<GraphRagContextResponse> => {
  const response = await fetch('/api/graph/rag/context', {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }

  return await response.json();
};

export const fetchGraphRagAnswer = async (
  payload: GraphRagAnswerRequest
): Promise<GraphRagAnswerResponse> => {
  const response = await fetch('/api/graph/rag/answer', {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }

  return await response.json();
};

