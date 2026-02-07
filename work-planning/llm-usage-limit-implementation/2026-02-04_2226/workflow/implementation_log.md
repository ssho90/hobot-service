# Implementation Log - LLM Usage Limit & Tracking

## Task
- Track usage of AI services (Macro Graph, Architecture Graph) per user.
- Restrict usage to 20 questions per day.
- Use existing `llm_usage_logs` table.

## Changes

### Backend (`hobot/main.py`)
1.  **Request Model Update**: 
    - Updated `GeminiCypherRequest` to include `database` field (default: "architecture").
2.  **Schema Definition**: 
    - Added `MACRO_GRAPH_SCHEMA` for Macro Graph Cypher generation. (legacy: `news`)
3.  **Rate Limiting**:
    - Replaced in-memory usage tracking with Database-based tracking.
    - `check_ontology_rate_limit` now queries `llm_usage_logs` counting rows for the current day where `user_id` matches and `service_name` is relevant.
    - Relevant service names: `architecture_graph_cypher`, `macro_graph_cypher`, (and legacy `news_graph_cypher`, `ontology_generate_cypher`).
4.  **Usage Tracking**:
    - Updated `gemini_generate_cypher` to:
        - Select schema based on `request.database`.
        - Log LLM usage with distinct service name: `{database}_graph_cypher`.
        - Verify rate limit before execution.

### Frontend (`hobot-ui-v2`)
1.  **Service Update (`services/geminiService.ts`)**:
    - Updated `generateCypherFromNaturalLanguage` to accept `database` parameter and pass it to the backend API.
2.  **Component Update (`components/OntologyPage.tsx`)**:
    - Updated `handleSendMessage` to pass the current `mode` ('architecture' or 'macro') as the `database` argument.

## Verification
- Usage is tracked in `llm_usage_logs` with `service_name` allowing per-service tracking.
- Rate limit logic sums up usage for graph features and enforces 20 daily limit.
- Frontend correctly propagates the selected mode.
