import { describe, expect, it } from "vitest";
import { Color } from "tsshogi";
import {
  OPENING_LINES,
  applyOpeningPath,
  countMainLineMoves,
  expectedOpeningMove,
  flattenMainLine,
  isExpectedOpeningMove,
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
