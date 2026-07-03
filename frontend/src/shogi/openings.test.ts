import { describe, expect, it } from "vitest";
import { Color } from "tsshogi";
import {
  OPENING_LINES,
  applyOpeningPath,
  countMainLineMoves,
  expectedOpeningMove,
  flattenMainLine,
  isExpectedOpeningMove,
  openingFromImportedLine,
  positionFromOpening,
} from "./openings";

describe("opening sample data", () => {
  it("contains fixed sample openings with tree-shaped moves", () => {
    expect(OPENING_LINES.length).toBeGreaterThanOrEqual(3);
    for (const opening of OPENING_LINES) {
      expect(opening.moves.length).toBeGreaterThan(0);
      expect(countMainLineMoves(opening)).toBe(flattenMainLine(opening).length);
    }
  });

  it("can create and advance positions with legal main-line moves", () => {
    for (const opening of OPENING_LINES) {
      const result = applyOpeningPath(opening, flattenMainLine(opening).map(() => 0));
      expect(result.moves).toHaveLength(countMainLineMoves(opening));
    }
  });
});

describe("opening learning helpers", () => {
  const opening = OPENING_LINES[0];

  it("returns the expected next move for the current path", () => {
    expect(expectedOpeningMove(opening, [])?.usi).toBe("7g7f");
    expect(expectedOpeningMove(opening, [0])?.usi).toBe("3c3d");
  });

  it("checks whether a user move matches the expected move", () => {
    const position = positionFromOpening(opening);
    const correct = position.createMoveByUSI("7g7f")!;
    const wrong = position.createMoveByUSI("2g2f")!;
    expect(isExpectedOpeningMove(correct, expectedOpeningMove(opening, []))).toBe(true);
    expect(isExpectedOpeningMove(wrong, expectedOpeningMove(opening, []))).toBe(false);
  });

  it("undo path restores the previous side to move", () => {
    const advanced = applyOpeningPath(opening, [0, 0]);
    expect(advanced.position.color).toBe(Color.BLACK);
    const undone = applyOpeningPath(opening, [0]);
    expect(undone.position.color).toBe(Color.WHITE);
  });
});

describe("openingFromImportedLine", () => {
  it("converts imported linear moves into the existing opening tree shape", () => {
    const opening = openingFromImportedLine({
      id: 12,
      name: "imported nakabisha",
      opening_type: "中飛車",
      initial_sfen: "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1",
      moves: [{ usi: "7g7f" }, { usi: "3c3d" }, { usi: "2h5h", comment: "中飛車へ" }],
      tags: [{ tag: "nakabisha", label: "中飛車" }],
      source: { name: "sample", license_name: "CC0", license_url: "" },
    });
    expect(opening.id).toBe("12");
    expect(opening.category).toBe("中飛車");
    expect(flattenMainLine(opening).map((move) => move.usi)).toEqual(["7g7f", "3c3d", "2h5h"]);
  });
});

it("builds branch choices from imported moves and can switch back to the branch point", () => {
  const start = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";
  const after76 = "lnsgkgsnl/1r5b1/ppppppppp/9/9/2P6/PP1PPPPPP/1B5R1/LNSGKGSNL w - 2";
  const opening = openingFromImportedLine({
    id: 99,
    name: "branch sample",
    opening_type: "角換わり",
    initial_sfen: start,
    moves: [
      { usi: "7g7f", from_sfen: start, to_sfen: after76, variation_group: "main", sort_order: 0 },
      { usi: "3c3d", from_sfen: after76, to_sfen: "lnsgkgsnl/1r5b1/pppppp1pp/6p2/9/2P6/PP1PPPPPP/1B5R1/LNSGKGSNL b - 3", variation_group: "main", sort_order: 0 },
      { usi: "8c8d", from_sfen: after76, to_sfen: "lnsgkgsnl/1r5b1/ppppppppp/9/1p7/2P6/PP1PPPPPP/1B5R1/LNSGKGSNL b - 3", variation_group: "△8四歩型", sort_order: 1 },
    ],
    source: { name: "Wikipedia", license_name: "CC BY-SA", license_url: "", source_url: "https://ja.wikipedia.org/wiki/角換わり" },
  });

  const branchPoint = applyOpeningPath(opening, [0]);
  expect(branchPoint.steps.at(-1)?.node.next).toHaveLength(2);
  expect(branchPoint.steps.at(-1)?.node.next?.map((node) => node.branchLabel)).toEqual(["本線", "△8四歩型"]);
  expect(applyOpeningPath(opening, [0, 0]).moves.map((move) => move.usi)).toEqual(["7g7f", "3c3d"]);
  expect(applyOpeningPath(opening, [0, 1]).moves.map((move) => move.usi)).toEqual(["7g7f", "8c8d"]);
  expect(applyOpeningPath(opening, [0]).position.sfen).toBe(branchPoint.position.sfen);
});
