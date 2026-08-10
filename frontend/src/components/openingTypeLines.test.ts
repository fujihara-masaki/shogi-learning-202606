import { describe, expect, it } from "vitest";
import type { OpeningSummary, OpeningType } from "../api/client";
import { availableOpeningLineCount, importedLinesForType } from "./openingTypeLines";

function openingType(overrides: Partial<OpeningType> = {}): OpeningType {
  return {
    id: 10, category_id: 1, category_name_ja: "相居飛車", parent_id: null,
    name_ja: "棒銀", name_kana: "ぼうぎん", name_en: "Climbing Silver", aliases: [],
    description_short: "説明", source_name: "test", source_url: "", license: "", sort_order: 1,
    is_active: true, opening_line_count: 3, ...overrides,
  };
}

function line(id: number, openingTypeId: number | null, tags: string[]): OpeningSummary {
  return {
    id, name: `line-${id}`, opening_type: "test", opening_type_id: openingTypeId,
    initial_sfen: "startpos", move_count: 1, tags,
    source: { id: null, name: "test", license_name: "", license_url: "" },
  };
}

describe("opening type line grouping", () => {
  it("groups legacy null lines under the unclassified opening type", () => {
    const unclassified = openingType({ id: 99, category_name_ja: "未分類", name_ja: "未分類", opening_line_count: 1 });
    const lines = [line(1, null, ["legacy"]), line(2, 99, []), line(3, 10, ["legacy"])];

    expect(importedLinesForType(unclassified, lines).map((item) => item.id)).toEqual([1, 2]);
    expect(availableOpeningLineCount(unclassified, lines, false, 0)).toBe(2);
    expect(availableOpeningLineCount(unclassified, [lines[0]], true, 0)).toBe(1);
  });

  it("uses matching imported lines for the count while a tag is selected", () => {
    const type = openingType();
    const taggedLines = [line(1, 10, ["attack"]), line(2, 10, ["attack"]), line(3, null, ["attack"])];

    expect(availableOpeningLineCount(type, taggedLines, true, 0)).toBe(2);
    expect(importedLinesForType(type, taggedLines)).toHaveLength(2);
  });
});
