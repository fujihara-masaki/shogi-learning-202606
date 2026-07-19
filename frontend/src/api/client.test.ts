import { afterEach, describe, expect, test, vi } from "vitest";
import { fetchAllLearningSamples, fetchLearningSamples, fetchProblems, fetchTsumeTags } from "./client";

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
  test("loads all pages and rejects a changed dataset", async () => {
    const responses = [
      { items: Array(100).fill({}), offset: 0, limit: 100, total: 101, dataset_version: "v1:a" },
      { items: [{}], offset: 100, limit: 100, total: 101, dataset_version: "v1:b" },
    ];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => ({ ok: true, status: 200, json: async () => responses.shift() })));
    await expect(fetchAllLearningSamples("bogin")).rejects.toMatchObject({ code: "NEXT_MOVE_PAGE_INCONSISTENT" });
  });
});
