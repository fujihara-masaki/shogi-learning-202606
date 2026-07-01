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

export interface OpeningCategory {
  id: number;
  name_ja: string;
  sort_order: number;
  description: string;
  source_url: string;
  license: string;
}

export interface OpeningType {
  id: number;
  category_id: number;
  category_name_ja: string;
  parent_id: number | null;
  name_ja: string;
  name_kana: string;
  name_en: string;
  aliases: string[];
  description_short: string;
  source_name: string;
  source_url: string;
  license: string;
  sort_order: number;
  is_active: boolean;
  opening_line_count: number;
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
  opening_type_id: number | null;
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
  opening_type_id: number | null;
  initial_sfen: string;
  moves: ImportedOpeningMove[];
  positions: ImportedOpeningPosition[];
  tags: ImportedOpeningTag[];
  source: OpeningSourceSummary;
}

export function fetchOpeningCategories(): Promise<OpeningCategory[]> {
  return request<OpeningCategory[]>("/api/opening-categories");
}

export function fetchOpeningTypes(categoryId?: number): Promise<OpeningType[]> {
  const qs = categoryId ? `?category_id=${encodeURIComponent(String(categoryId))}` : "";
  return request<OpeningType[]>(`/api/opening-types${qs}`);
}

export function fetchOpeningTypeLines(id: number): Promise<OpeningSummary[]> {
  return request<OpeningSummary[]>(`/api/opening-types/${id}/lines`);
}

export function fetchOpeningType(id: number): Promise<OpeningType> {
  return request<OpeningType>(`/api/opening-types/${id}`);
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

export interface BookSource {
  id: number;
  name: string;
  version: string;
  source_url: string;
  license_name: string;
  license_text?: string;
  copyright_notice: string;
  file_name: string;
  file_sha256: string;
  imported_at: string;
  position_count: number;
  move_count: number;
  note: string;
}

export interface BookCandidate {
  move_usi: string;
  rank: number | null;
  score: number | null;
  depth: number | null;
  pv: string | null;
  raw: string | null;
  source_id: number;
  source_name: string;
  source_version: string | null;
  license: string | null;
  license_name: string | null;
  source_url: string | null;
  copyright_notice: string | null;
}

export interface BookCandidatesResponse {
  sfen: string;
  found: boolean;
  candidates: BookCandidate[];
}

export function fetchBookCandidates(sfen: string): Promise<BookCandidatesResponse> {
  const params = new URLSearchParams({ sfen });
  return request<BookCandidatesResponse>(`/api/book/candidates?${params.toString()}`);
}


export interface LearningSampleOpeningSummary {
  opening_key: string;
  opening_name: string;
  sample_count: number;
  first_rank: number;
}

export interface LearningSampleSource {
  id: number;
  name: string;
  version: string;
  license_name: string;
  source_url: string;
  copyright_notice: string;
}

export interface LearningSample {
  id: number;
  book_source_id: number;
  book_position_id: number;
  opening_key: string;
  opening_name: string;
  sfen: string;
  sample_rank: number;
  sample_reason: string;
  created_at: string;
  source: LearningSampleSource;
  candidates: BookCandidate[];
}

export function fetchLearningSampleOpenings(): Promise<LearningSampleOpeningSummary[]> {
  return request<LearningSampleOpeningSummary[]>("/api/learning-samples/openings");
}

export function fetchLearningSamples(openingKey?: string, limit = 20): Promise<LearningSample[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (openingKey) params.set("opening_key", openingKey);
  return request<LearningSample[]>(`/api/learning-samples?${params.toString()}`);
}

export function fetchLearningSample(id: number): Promise<LearningSample> {
  return request<LearningSample>(`/api/learning-samples/${id}`);
}

export interface LicenseResponse {
  book_sources: BookSource[];
}

export function fetchBookSources(): Promise<BookSource[]> {
  return request<BookSource[]>("/api/book/sources");
}

export function fetchLicenses(): Promise<LicenseResponse> {
  return request<LicenseResponse>("/api/licenses");
}
