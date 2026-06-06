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
  custom_topic: string | null;
  publish_live: boolean;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  completed_at?: string;
};

export type Post = {
  run_id: string;
  title: string;
  subtitle?: string;
  content: string;
  tags: string[];
  status: string;
  revision_count: number;
  medium_url?: string;
  quality_report?: {
    score: number;
    read_ratio_prediction: number;
    issues: { category: string; severity: string; suggestion: string }[];
    strengths: string[];
  };
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

export type Summary = {
  pipeline_runs: number;
  completed_runs: number;
  total_posts: number;
  published_posts: number;
  total_cost_usd: number;
  total_tokens: number;
};

export const api = {
  triggerPipeline: (topic: string | null, publishLive: boolean) =>
    request<{ run_id: string; message: string }>("/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ custom_topic: topic, publish_live: publishLive }),
    }),

  listRuns: () => request<PipelineRun[]>("/pipeline/runs"),
  getRun: (id: string) => request<PipelineRun>(`/pipeline/runs/${id}`),

  listPosts: (status?: string) =>
    request<Post[]>(`/posts${status ? `?status=${status}` : ""}`),
  getPost: (runId: string) => request<Post>(`/posts/${runId}`),

  tokenUsage: (runId?: string) =>
    request<AgentUsage[]>(`/analytics/token-usage${runId ? `?run_id=${runId}` : ""}`),
  tokenUsageByRun: () => request<AgentUsage[]>("/analytics/token-usage/by-run"),
  summary: () => request<Summary>("/analytics/summary"),
};
