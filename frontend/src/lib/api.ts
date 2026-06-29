const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export type PipelineRun = {
  run_id: string;
  custom_topic: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  completed_at?: string;
};

export type VerifiedSource = {
  claim_text: string;
  source_url: string;
  source_title: string;
  claim_type: string;
};

export type QualityHistoryEntry = {
  cycle: number;
  score: number;
  read_ratio: number;
  boost_eligible: boolean;
  issue_count: number;
  passed: boolean;
  gate_failures: string[];
  issue_categories: string[];
};

export type Post = {
  run_id: string;
  title: string;
  subtitle?: string;
  content: string;
  tags: string[];
  status: string;
  revision_count: number;
  pull_quote?: string;
  series_id?: string;
  series_position?: number;
  medium_url?: string;
  quality_score?: number;
  read_ratio_prediction?: number;
  medium_boost_eligible?: boolean;
  word_count?: number;
  verified_sources?: VerifiedSource[];
  quality_history?: QualityHistoryEntry[];
  quality_report?: {
    score: number;
    read_ratio_prediction: number;
    medium_boost_eligible: boolean;
    issues: { category: string; severity: string; suggestion: string }[];
    strengths: string[];
  };
  created_at: string;
};

export type SeriesPost = {
  run_id: string;
  title: string;
  series_position: number;
  status: string;
  quality_score?: number;
  word_count?: number;
};

export type SeriesDetail = {
  series_id: string;
  theme: string;
  status: string;
  created_at: string;
  posts: SeriesPost[];
};

export type Exemplar = {
  run_id: string;
  title: string;
  tags: string[];
  score: number;
  read_ratio: number;
  hook_score: number;
  hook: string;
  intro_word_count: number;
  word_count: number;
  created_at: string;
};

export type AgentUsage = {
  agent_name: string;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  avg_duration_ms: number;
  call_count: number;
};

export type RunUsage = {
  run_id: string;
  total_cost_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_duration_ms: number;
  agent_calls: number;
  first_call?: string;
};

export type AgentLog = {
  run_id: string;
  step: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
};

export type Summary = {
  pipeline_runs: number;
  completed_runs: number;
  total_posts: number;
  published_posts: number;
  total_cost_usd: number;
  total_tokens: number;
  claude_cost_usd: number;
  deepseek_cost_usd: number;
};

export type RevisionSnapshot = {
  run_id: string;
  iteration: number;
  score: number;
  read_ratio: number;
  word_count: number;
  medium_boost_eligible: boolean;
  passed: boolean;
  gate_failures: string[];
  issue_summary: { high: number; medium: number; low: number; total: number };
  strengths: string[];
  topic?: string;
};

export type CostComparison = {
  claude_cost_usd: number;
  claude_tokens_in: number;
  claude_tokens_out: number;
  claude_runs: number;
  deepseek_cost_usd: number;
  deepseek_tokens_in: number;
  deepseek_tokens_out: number;
  deepseek_runs: number;
  equivalent_claude_cost_usd: number;
  savings_usd: number;
  savings_pct: number;
  has_claude_data: boolean;
  has_deepseek_data: boolean;
};

export const api = {
  triggerPipeline: (topic: string) =>
    request<{ run_id: string; message: string }>("/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ custom_topic: topic }),
    }),

  listRuns: () => request<PipelineRun[]>("/pipeline/runs"),
  getRun: (id: string) => request<PipelineRun>(`/pipeline/runs/${id}`),

  listPosts: (status?: string, offset = 0) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (offset > 0) params.set("offset", String(offset));
    const qs = params.toString();
    return request<Post[]>(`/posts${qs ? `?${qs}` : ""}`);
  },
  getPost: (runId: string) => request<Post>(`/posts/${runId}`),
  deletePost: async (runId: string): Promise<void> => {
    const res = await fetch(`${BASE}/posts/${runId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  },
  updateStatus: (runId: string, status: string) =>
    request<Post>(`/posts/${runId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  setMediumUrl: (runId: string, medium_url: string | null) =>
    request<Post>(`/posts/${runId}/medium_url`, {
      method: "PATCH",
      body: JSON.stringify({ medium_url }),
    }),
  updateTags: (runId: string, tags: string[]) =>
    request<Post>(`/posts/${runId}/tags`, {
      method: "PATCH",
      body: JSON.stringify({ tags }),
    }),

  tokenUsage: (runId?: string) =>
    request<AgentUsage[]>(`/analytics/token-usage${runId ? `?run_id=${runId}` : ""}`),
  tokenUsageByRun: () => request<RunUsage[]>("/analytics/token-usage/by-run"),
  summary: () => request<Summary>("/analytics/summary"),
  costComparison: () => request<CostComparison>("/analytics/cost-comparison"),

  getLogs: (runId: string) => request<AgentLog[]>(`/pipeline/runs/${runId}/logs`),

  listExemplars: () => request<Exemplar[]>("/posts/exemplars/list"),
  promoteExemplar: (runId: string) =>
    request<{ run_id: string; status: string }>(`/posts/${runId}/exemplar`, { method: "POST" }),
  deleteExemplar: async (runId: string): Promise<void> => {
    const res = await fetch(`${BASE}/posts/exemplars/${runId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  },

  listSeries: () => request<SeriesDetail[]>("/series"),
  deleteSeries: async (seriesId: string): Promise<void> => {
    const res = await fetch(`${BASE}/series/${seriesId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  },
  getSeries: (id: string) => request<SeriesDetail>(`/series/${id}`),
  triggerSeries: (theme: string, context?: string) =>
    request<{ series_id: string; message: string }>("/series/run", {
      method: "POST",
      body: JSON.stringify({ theme, context: context ?? "" }),
    }),

  revisionCycles: (limit = 100) =>
    request<RevisionSnapshot[]>(`/analytics/revision-cycles?limit=${limit}`),

  /** Open an SSE connection to the live log stream for a run. */
  streamLogs: (runId: string): EventSource =>
    new EventSource(`${BASE}/pipeline/runs/${runId}/stream`),
};
