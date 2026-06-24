// バックエンド API クライアント。
// 接続先は VITE_API_BASE で上書き可能(デフォルトはローカルの FastAPI)。

const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface ProblemStats {
  correct_count: number;
  wrong_count: number;
  last_answered_at: string | null;
  avg_elapsed_ms: number | null;
}

export interface TsumeProblem {
  id: number;
  title: string;
  initial_sfen: string;
  mate_length: number;
  solution_moves: string[];
  opponent_moves: string[];
  difficulty: number;
  tags: string[];
  explanation: string;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
  stats: ProblemStats;
}

export type TsumeProblemInput = Omit<TsumeProblem, "id" | "created_at" | "updated_at" | "stats">;

export interface ValidationResponse { valid: boolean; errors: string[] }

export interface ProblemResultInput {
  is_correct: boolean;
  elapsed_ms: number;
  mistake_count: number;
}

export interface TimeAttackResult {
  id: number;
  mode: string;
  mate_length: number;
  total_questions: number;
  correct_count: number;
  mistake_count: number;
  elapsed_ms: number;
  played_at: string;
}

export interface TimeAttackResultInput {
  mode: string;
  mate_length: number;
  total_questions: number;
  correct_count: number;
  mistake_count: number;
  elapsed_ms: number;
}

export interface OverallStats {
  total_answers: number;
  total_correct: number;
  total_wrong: number;
  accuracy: number;
  avg_elapsed_ms: number | null;
}

export interface RecentResult {
  id: number;
  problem_id: number;
  title: string;
  mate_length: number;
  is_correct: boolean;
  elapsed_ms: number;
  mistake_count: number;
  answered_at: string;
}

export interface StatsResponse {
  overall: OverallStats;
  by_mate_length: Record<string, OverallStats>;
  recent_results: RecentResult[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export interface ProblemQuery {
  mate_length?: number;
  tag?: string;
  favorite?: boolean;
  random_order?: boolean;
  limit?: number;
}

export function fetchProblems(query: ProblemQuery = {}): Promise<TsumeProblem[]> {
  const params = new URLSearchParams();
  if (query.mate_length !== undefined) params.set("mate_length", String(query.mate_length));
  if (query.tag) params.set("tag", query.tag);
  if (query.favorite !== undefined) params.set("favorite", String(query.favorite));
  if (query.random_order) params.set("random_order", "true");
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  const qs = params.toString();
  return request<TsumeProblem[]>(`/api/tsume-problems${qs ? `?${qs}` : ""}`);
}

export function fetchProblem(id: number): Promise<TsumeProblem> {
  return request<TsumeProblem>(`/api/tsume-problems/${id}`);
}

export function createProblem(body: TsumeProblemInput): Promise<TsumeProblem> {
  return request<TsumeProblem>(`/api/tsume-problems`, { method: "POST", body: JSON.stringify(body) });
}

export function updateProblem(id: number, body: TsumeProblemInput): Promise<TsumeProblem> {
  return request<TsumeProblem>(`/api/tsume-problems/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteProblem(id: number): Promise<void> {
  return request<void>(`/api/tsume-problems/${id}`, { method: "DELETE" });
}

export function validateProblem(body: TsumeProblemInput): Promise<ValidationResponse> {
  return request<ValidationResponse>(`/api/tsume-problems/validate`, { method: "POST", body: JSON.stringify(body) });
}

export function postProblemResult(id: number, body: ProblemResultInput): Promise<unknown> {
  return request(`/api/tsume-problems/${id}/result`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function setFavorite(id: number, isFavorite: boolean): Promise<TsumeProblem> {
  return request<TsumeProblem>(`/api/tsume-problems/${id}/favorite`, {
    method: "POST",
    body: JSON.stringify({ is_favorite: isFavorite }),
  });
}

export function fetchReviewProblems(): Promise<TsumeProblem[]> {
  return request<TsumeProblem[]>("/api/review-problems");
}

export function postTimeAttackResult(body: TimeAttackResultInput): Promise<TimeAttackResult> {
  return request<TimeAttackResult>("/api/time-attack/result", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchTimeAttackResults(): Promise<TimeAttackResult[]> {
  return request<TimeAttackResult[]>("/api/time-attack/results");
}

export function fetchStats(): Promise<StatsResponse> {
  return request<StatsResponse>("/api/stats");
}

export interface OpeningTagSummary {
  tag: string;
  label: string;
  count: number;
  max_score: number;
}

export interface OpeningSourceSummary {
  id: number | null;
  name: string;
  license_name: string;
  license_url: string;
}

export interface OpeningSummary {
  id: number;
  name: string;
  opening_type: string;
  initial_sfen: string;
  move_count: number;
  tags: string[];
  source: OpeningSourceSummary;
}

export interface ImportedOpeningMove {
  ply: number;
  usi: string;
  from_sfen: string;
  to_sfen: string;
  comment: string;
}

export interface ImportedOpeningPosition {
  ply: number;
  sfen: string;
}

export interface ImportedOpeningTag {
  tag: string;
  label: string;
  score: number;
  reason: string;
}

export interface ImportedOpeningDetail {
  id: number;
  name: string;
  opening_type: string;
  initial_sfen: string;
  moves: ImportedOpeningMove[];
  positions: ImportedOpeningPosition[];
  tags: ImportedOpeningTag[];
  source: OpeningSourceSummary;
}

export function fetchOpeningTags(): Promise<OpeningTagSummary[]> {
  return request<OpeningTagSummary[]>("/api/openings/tags");
}

export function fetchOpenings(tag?: string): Promise<OpeningSummary[]> {
  const qs = tag ? `?tag=${encodeURIComponent(tag)}` : "";
  return request<OpeningSummary[]>(`/api/openings${qs}`);
}

export function fetchOpening(id: number): Promise<ImportedOpeningDetail> {
  return request<ImportedOpeningDetail>(`/api/openings/${id}`);
}
