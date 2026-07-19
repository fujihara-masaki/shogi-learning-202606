import { afterEach, describe, expect, test, vi } from "vitest";
import { fetchAllLearningSamples, fetchAllLearningSamplesCached, fetchLearningSamples, fetchNextMoveProblem, fetchProblems, fetchTsumeTags } from "./client";

describe("tsume API client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("fetchTsumeTags requests only tag metadata with optional mate_length", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ tag: "頭金", count: 2 }],
    });
    vi.stubGlobal("fetch", fetchMock);

    const tags = await fetchTsumeTags({ mate_length: 3 });

    expect(tags).toEqual([{ tag: "頭金", count: 2 }]);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/tsume-problems/tags?mate_length=3",
      expect.objectContaining({ headers: { "Content-Type": "application/json" } }),
    );
  });

  test("fetchProblems keeps tag, mate_length, limit, and offset for paged tag filtering", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchProblems({ mate_length: 1, tag: "端玉", limit: 50, offset: 50 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/tsume-problems?mate_length=1&tag=%E7%AB%AF%E7%8E%89&limit=50&offset=50",
      expect.objectContaining({ headers: { "Content-Type": "application/json" } }),
    );
  });
});

describe("next move paging", () => {
  afterEach(() => vi.restoreAllMocks());
  test("uses a page object and offset query", async () => {
    const page = { items: [], offset: 100, limit: 20, total: 100, dataset_version: "v1:x" };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => page });
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchLearningSamples("bogin", 20, 100)).resolves.toEqual(page);
    expect(fetchMock.mock.calls[0][0]).toContain("limit=20&offset=100&opening_key=bogin");
  });
  function mockPages(pages: unknown[]) {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => ({ ok: true, status: 200, json: async () => pages.shift() })));
  }
  const problems = (count: number, start = 0) => Array.from({ length: count }, (_, index) => ({ id: start + index, problem_key: `v1:${start + index}` }));
  test("loads multiple pages completely", async () => {
    mockPages([
      { items: problems(100), offset: 0, limit: 100, total: 101, dataset_version: "v1:a" },
      { items: problems(1, 100), offset: 100, limit: 100, total: 101, dataset_version: "v1:a" },
    ]);
    await expect(fetchAllLearningSamples("bogin")).resolves.toHaveLength(101);
  });
  test("rejects a changed dataset version", async () => {
    const responses = [
      { items: problems(100), offset: 0, limit: 100, total: 101, dataset_version: "v1:a" },
      { items: problems(1, 100), offset: 100, limit: 100, total: 101, dataset_version: "v1:b" },
    ];
    mockPages(responses);
    await expect(fetchAllLearningSamples("bogin")).rejects.toMatchObject({ code: "NEXT_MOVE_PAGE_INCONSISTENT" });
  });
  test.each([
    ["total increase", { items: problems(1, 100), offset: 100, limit: 100, total: 102, dataset_version: "v1:a" }],
    ["total decrease", { items: problems(1, 100), offset: 100, limit: 100, total: 100, dataset_version: "v1:a" }],
    ["empty incomplete page", { items: [], offset: 100, limit: 100, total: 101, dataset_version: "v1:a" }],
    ["offset mismatch", { items: problems(1, 100), offset: 99, limit: 100, total: 101, dataset_version: "v1:a" }],
    ["no offset progress", { items: problems(1, 100), offset: 0, limit: 100, total: 101, dataset_version: "v1:a" }],
    ["existing keys only", { items: problems(1), offset: 100, limit: 100, total: 101, dataset_version: "v1:a" }],
  ])("rejects %s", async (_name, second) => {
    mockPages([{ items: problems(100), offset: 0, limit: 100, total: 101, dataset_version: "v1:a" }, second]);
    await expect(fetchAllLearningSamples("bogin")).rejects.toMatchObject({ code: "NEXT_MOVE_PAGE_INCONSISTENT" });
  });
  test("forwards AbortSignal", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockImplementation((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    vi.stubGlobal("fetch", fetchMock);
    const pending = fetchAllLearningSamples("bogin", controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });
  test("forced retry starts again at offset zero", async () => {
    const offsets: string[] = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      const offset = new URL(url).searchParams.get("offset") ?? "";
      offsets.push(offset);
      if (offset === "100") throw new Error("page failed");
      return { ok: true, status: 200, json: async () => ({ items: problems(100), offset: 0, limit: 100, total: 101, dataset_version: "v1:retry" }) };
    }));
    await expect(fetchAllLearningSamplesCached("retry-test", true)).rejects.toThrow("page failed");
    await expect(fetchAllLearningSamplesCached("retry-test", true)).rejects.toThrow("page failed");
    expect(offsets).toEqual(["0", "100", "0", "100"]);
  });
});

describe("next move selection API", () => {
  afterEach(() => vi.restoreAllMocks());
  test("builds policy, opening, and exclusion query", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: 7 }) });
    vi.stubGlobal("fetch", fetchMock);
    await fetchNextMoveProblem({ policy: "random", opening_key: "角換わり", exclude_problem_key: "v1:key" });
    expect(fetchMock.mock.calls[0][0]).toContain("policy=random&opening_key=%E8%A7%92%E6%8F%9B%E3%82%8F%E3%82%8A&exclude_problem_key=v1%3Akey");
  });
  test("returns undefined for a normal 204 candidate exhaustion", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 204 }));
    await expect(fetchNextMoveProblem({ policy: "unattempted" })).resolves.toBeUndefined();
  });
});
