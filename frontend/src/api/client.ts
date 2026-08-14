// バックエンド API クライアント。
// 接続先は VITE_API_BASE で上書き可能(デフォルトはローカルの FastAPI)。

const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface ProblemStats {
  correct_count: number;
  wrong_count: number;
  last_answered_at: string | null;
  avg_elapsed_ms: number | null;
}

export interface TsumeTagSummary {
  tag: string;
  count: number;
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
  source_name: string;
  source_url: string;
  source_license: string;
  source_copyright: string;
  external_id: string;
  source_hash: string;
  source_metadata: Record<string, unknown>;
  stats: ProblemStats;
}

export type TsumeProblemInput = Omit<TsumeProblem, "id" | "created_at" | "updated_at" | "stats" | "source_name" | "source_url" | "source_license" | "source_copyright" | "external_id" | "source_hash" | "source_metadata"> & Partial<Pick<TsumeProblem, "source_name" | "source_url" | "source_license" | "source_copyright" | "external_id" | "source_hash" | "source_metadata">>;

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

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly code: string | null;

  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.status = status;
    this.detail = message;
    this.code = code;
    this.name = "ApiError";
  }
}

export function isNextMoveUnavailable(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = `API error ${res.status}: ${text}`;
    let code: string | null = null;
    try {
      const data = JSON.parse(text) as { detail?: string; code?: string };
      if (typeof data.detail === "string") detail = data.detail;
      if (typeof data.code === "string") code = data.code;
    } catch { /* Preserve existing plain-text error behavior. */ }
    throw new ApiError(res.status, detail, code);
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
  offset?: number;
}

function buildProblemParams(query: ProblemQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.mate_length !== undefined) params.set("mate_length", String(query.mate_length));
  if (query.tag) params.set("tag", query.tag);
  if (query.favorite !== undefined) params.set("favorite", String(query.favorite));
  if (query.random_order) params.set("random_order", "true");
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  return params;
}

export function fetchProblems(query: ProblemQuery = {}): Promise<TsumeProblem[]> {
  const qs = buildProblemParams(query).toString();
  return request<TsumeProblem[]>(`/api/tsume-problems${qs ? `?${qs}` : ""}`);
}

export function fetchTsumeTags(query: Pick<ProblemQuery, "mate_length"> = {}): Promise<TsumeTagSummary[]> {
  const params = new URLSearchParams();
  if (query.mate_length !== undefined) params.set("mate_length", String(query.mate_length));
  const qs = params.toString();
  return request<TsumeTagSummary[]>(`/api/tsume-problems/tags${qs ? `?${qs}` : ""}`);
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
  source_url?: string;
  source_title?: string;
  license?: string;
  source_note?: string;
  coverage_status?: string;
  source_type?: string;
  source_section?: string;
  source_license?: string;
  source_retrieved_at?: string;
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
  id: number;
  ply: number;
  usi: string;
  from_sfen: string;
  to_sfen: string;
  comment: string;
  variation_group: string;
  parent_move_id: number | null;
  sort_order: number;
  move_key: string;
  is_main: boolean;
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
  problem_key: string;
  source: LearningSampleSource;
  candidates: BookCandidate[];
}

export function fetchLearningSampleOpenings(): Promise<LearningSampleOpeningSummary[]> {
  return request<LearningSampleOpeningSummary[]>("/api/learning-samples/openings");
}

export interface LearningSamplePage { items: LearningSample[]; offset: number; limit: number; total: number; dataset_version: string }
export type NextMoveVerdict = "top" | "strong" | "listed" | "unlisted";
export interface NextMoveProgressItem { opening_key: string; opening_name: string; total: number; answered: number; verdict_counts: Record<NextMoveVerdict, number>; top_rate: number }
export interface NextMoveStatusItem { problem_key: string; verdict: NextMoveVerdict | null; result_id: number | null }
export type NextMovePolicy = "random" | "unattempted" | "weak";
export interface NextMoveHistoryResult {
  id: number; problem_key: string; move_usi: string; verdict: NextMoveVerdict;
  candidate_rank: number | null; elapsed_ms: number; answered_at: string;
  opening_key: string; opening_name: string; sample_id: number | null;
  available: boolean; unavailable_reason: string | null;
}
export interface NextMoveHistoryResponse { total_answers: number; verdict_counts: Record<NextMoveVerdict, number>; top_rate: number; recent_results: NextMoveHistoryResult[] }
export interface NextMoveReviewItem {
  problem_key: string; sample_id: number | null; opening_key: string; opening_name: string;
  verdict: "listed" | "unlisted"; move_usi: string; answered_at: string;
  result_id: number; available: boolean; unavailable_reason: string | null;
}
export function fetchNextMoveHistory(): Promise<NextMoveHistoryResponse> { return request("/api/next-move/history"); }
export function fetchNextMoveReview(): Promise<{ items: NextMoveReviewItem[] }> { return request("/api/next-move/review"); }
export function nextMoveVerdictLabel(verdict: NextMoveVerdict): string {
  return ({ top: "◎ 最有力", strong: "○ 有力", listed: "△ 登録候補", unlisted: "? 未登録" })[verdict];
}

export function fetchLearningSamples(openingKey?: string, limit = 100, offset = 0, signal?: AbortSignal): Promise<LearningSamplePage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (openingKey) params.set("opening_key", openingKey);
  return request<LearningSamplePage>(`/api/learning-samples?${params.toString()}`, { signal });
}

export function fetchNextMoveProgress(): Promise<{ openings: NextMoveProgressItem[] }> { return request("/api/next-move/progress"); }
export function fetchNextMoveStatus(openingKey: string): Promise<{ opening_key: string; items: NextMoveStatusItem[] }> {
  return request(`/api/next-move/status?${new URLSearchParams({ opening_key: openingKey })}`);
}

export function fetchNextMoveProblem(options: {
  policy: NextMovePolicy;
  opening_key?: string;
  exclude_problem_key?: string;
  signal?: AbortSignal;
}): Promise<LearningSample | undefined> {
  const params = new URLSearchParams({ policy: options.policy });
  if (options.opening_key) params.set("opening_key", options.opening_key);
  if (options.exclude_problem_key) params.set("exclude_problem_key", options.exclude_problem_key);
  return request<LearningSample | undefined>(`/api/next-move/problems/next?${params}`, { signal: options.signal });
}

export async function fetchAllLearningSamples(openingKey?: string, signal?: AbortSignal): Promise<LearningSample[]> {
  const first = await fetchLearningSamples(openingKey, 100, 0, signal);
  const expectedTotal = first.total;
  const version = first.dataset_version;
  if (first.offset !== 0) throw new ApiError(409, "問題一覧のoffsetが一致しません", "NEXT_MOVE_PAGE_INCONSISTENT");
  const keys = new Set(first.items.map((item) => item.problem_key));
  if (keys.size !== first.items.length || keys.size > expectedTotal) throw new ApiError(409, "問題一覧に重複があります", "NEXT_MOVE_PAGE_INCONSISTENT");
  const items = [...first.items];
  let offset = first.offset + first.items.length;
  while (keys.size < expectedTotal) {
    if (first.items.length === 0 || offset <= first.offset) throw new ApiError(409, "問題一覧のページングが進みません", "NEXT_MOVE_PAGE_INCONSISTENT");
    const page = await fetchLearningSamples(openingKey, 100, offset, signal);
    if (page.total !== expectedTotal || page.dataset_version !== version || page.items.length === 0 || page.offset !== offset) {
      throw new ApiError(409, "問題一覧が取得中に更新されました", "NEXT_MOVE_PAGE_INCONSISTENT");
    }
    const before = keys.size;
    for (const item of page.items) {
      if (!keys.has(item.problem_key)) {
        keys.add(item.problem_key);
        items.push(item);
      }
    }
    if (keys.size === before) throw new ApiError(409, "新しい問題を取得できませんでした", "NEXT_MOVE_PAGE_INCONSISTENT");
    const nextOffset = page.offset + page.items.length;
    if (nextOffset <= offset) throw new ApiError(409, "問題一覧のページングが進みません", "NEXT_MOVE_PAGE_INCONSISTENT");
    offset = nextOffset;
  }
  if (keys.size !== expectedTotal) throw new ApiError(409, "問題一覧の件数が一致しません", "NEXT_MOVE_PAGE_INCONSISTENT");
  return items;
}

const allSamplesCache = new Map<string, Promise<LearningSample[]>>();
export function fetchAllLearningSamplesCached(openingKey: string, force = false): Promise<LearningSample[]> {
  if (force) allSamplesCache.delete(openingKey);
  const existing = allSamplesCache.get(openingKey);
  if (existing) return existing;
  const request = fetchAllLearningSamples(openingKey).catch((error) => {
    allSamplesCache.delete(openingKey);
    throw error;
  });
  allSamplesCache.set(openingKey, request);
  return request;
}

export function fetchLearningSample(id: number): Promise<LearningSample> {
  return request<LearningSample>(`/api/learning-samples/${id}`);
}

export interface NextMoveResultInput {
  sample_id: number;
  problem_key: string;
  move_usi: string;
  hint_count: number;
  elapsed_ms: number;
}

export interface NextMoveResultResponse {
  id: number;
  verdict: "top" | "strong" | "listed" | "unlisted";
  candidate_rank: number | null;
  judgment_position: number | null;
}

export function postNextMoveResult(body: NextMoveResultInput): Promise<NextMoveResultResponse> {
  return request<NextMoveResultResponse>("/api/next-move/results", {method: "POST", body: JSON.stringify(body)});
}

export interface TsumeSourceLicense {
  name: string;
  source_url: string;
  license_name: string;
  copyright_notice: string;
  problem_count: number;
}

export interface LicenseResponse {
  book_sources: BookSource[];
  tsume_sources: TsumeSourceLicense[];
}

export function fetchBookSources(): Promise<BookSource[]> {
  return request<BookSource[]>("/api/book/sources");
}

export function fetchLicenses(): Promise<LicenseResponse> {
  return request<LicenseResponse>("/api/licenses");
}
