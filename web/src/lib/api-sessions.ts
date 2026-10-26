// Session API shapes (GET /api/sessions*, clawk_cli/web_routers/sessions.py). Split out of
// api.ts so that facade stays under its code-health line cap.

export interface SessionInfo {
  id: string;
  source: string | null;
  model: string | null;
  title: string | null;
  started_at: number;
  ended_at: number | null;
  last_active: number;
  is_active: boolean;
  message_count: number;
  tool_call_count: number;
  input_tokens: number;
  output_tokens: number;
  preview: string | null;
  parent_session_id?: string | null;
  /** Owning profile stamped by the list/detail endpoints (the store the row
   * was read from). Absent on search-endpoint rows, which carry no stamp. */
  profile?: string;
  /** Sidebar flags (real booleans on list rows); archived rows are hidden by default. */
  archived?: boolean;
  pinned?: boolean;
  end_reason?: string | null;
  cwd?: string | null;
}

export interface SessionLatestDescendantResponse {
  requested_session_id: string;
  session_id: string;
  path: string[];
  changed: boolean;
}

export interface PaginatedSessions {
  sessions: SessionInfo[];
  total: number;
  limit: number;
  offset: number;
  /** ``{profile: "corrupt"}`` when the store is unreadable — an empty page is then NOT "no sessions". */
  storage?: Record<string, string>;
}

export interface SessionMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string | null;
  tool_calls?: Array<{
    id: string;
    function: { name: string; arguments: string };
  }>;
  tool_name?: string;
  tool_call_id?: string;
  timestamp?: number;
}

export interface SessionMessagesResponse {
  session_id: string;
  messages: SessionMessage[];
  pagination?: {
    limit: number;
    offset: number;
    order: "latest" | "oldest";
    returned: number;
  };
}

export interface SessionSearchResult extends SessionInfo {
  session_id: string;
  snippet: string;
  role: string | null;
  session_started: number | null;
  lineage_root?: string;
}

export interface SessionSearchResponse {
  results: SessionSearchResult[];
}

export interface SessionStoreStats {
  total: number;
  active_store: number;
  archived: number;
  messages: number;
  by_source: Record<string, number>;
}

export interface SessionImportResponse {
  ok: boolean;
  imported: number;
  skipped: number;
  detached: number;
  imported_ids: string[];
  skipped_ids: string[];
  errors: Array<Record<string, unknown>>;
}
