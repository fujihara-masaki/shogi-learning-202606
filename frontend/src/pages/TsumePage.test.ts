import { describe, expect, test } from "vitest";
import source from "./TsumePage.tsx?raw";

const compactSource = source.replace(/\s+/g, " ");

describe("TsumePage tag fetching dependencies", () => {
  test("keeps problem list query dependent on both mate length and tag filter", () => {
    expect(source).toContain("...(tagFilter ? { tag: tagFilter } : {}),");
    expect(compactSource).toContain("[mateLength, tagFilter]");
  });

  test("fetches tag summaries only when mate length changes", () => {
    const start = compactSource.indexOf("useEffect(() => { let ignore = false; fetchTsumeTags(");
    const end = compactSource.indexOf("}, [mateLength]);", start);
    const tagFetchEffect = compactSource.slice(start, end);

    expect(start).toBeGreaterThanOrEqual(0);
    expect(end).toBeGreaterThan(start);
    expect(tagFetchEffect).toContain("fetchTsumeTags(mateLength > 0 ? { mate_length: mateLength } : {})");
    expect(tagFetchEffect).not.toContain("tagFilter");
  });

  test("validates the selected tag without depending on the outer tag filter state", () => {
    expect(compactSource).toContain(
      'setTagFilter((current) => (current && !tags.some((t) => t.tag === current) ? "" : current));',
    );
  });
});
