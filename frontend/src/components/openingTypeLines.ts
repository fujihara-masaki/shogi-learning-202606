import type { OpeningSummary, OpeningType } from "../api/client";

// 現行APIにはfallback戦型を表す機械可読キーがないため、seedで保証される分類名を一箇所で扱う。
export function isUnclassifiedOpeningType(type: OpeningType): boolean {
  return type.name_ja === "未分類" && type.category_name_ja === "未分類";
}

export function importedLinesForType(type: OpeningType, lines: OpeningSummary[]): OpeningSummary[] {
  return lines.filter((line) => (
    line.opening_type_id === type.id
    || (line.opening_type_id === null && isUnclassifiedOpeningType(type))
  ));
}

export function expandedImportedLinesForType(
  type: OpeningType,
  fetchedTypeLines: OpeningSummary[],
  matchingLines: OpeningSummary[],
  tagSelected: boolean,
): OpeningSummary[] {
  const matchedIds = tagSelected ? new Set(matchingLines.map((line) => line.id)) : null;
  const linkedLines = matchedIds
    ? fetchedTypeLines.filter((line) => matchedIds.has(line.id))
    : fetchedTypeLines;
  const unclassifiedLines = importedLinesForType(type, matchingLines)
    .filter((line) => line.opening_type_id === null);
  return [...linkedLines, ...unclassifiedLines];
}

export function availableOpeningLineCount(
  type: OpeningType,
  matchingLines: OpeningSummary[],
  tagSelected: boolean,
  staticCount: number,
): number {
  if (tagSelected) return importedLinesForType(type, matchingLines).length;
  const unclassifiedCount = isUnclassifiedOpeningType(type)
    ? matchingLines.filter((line) => line.opening_type_id === null).length
    : 0;
  return type.opening_line_count + unclassifiedCount + staticCount;
}
