import { afterEach, describe, expect, test, vi } from "vitest";
import { fetchProblems, fetchTsumeTags } from "./client";

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
