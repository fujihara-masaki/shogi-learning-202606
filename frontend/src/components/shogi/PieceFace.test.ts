import { describe, expect, it } from "vitest";
import type { PieceKind, PieceVisual } from "../../appearance/types";
import { isPieceUpsideDown, pieceVisualText } from "../../appearance/piecePresentation";

const textCases: Array<[PieceKind, boolean, string]> = [
  ["pawn", false, "歩"],
  ["lance", false, "香"],
  ["knight", false, "桂"],
  ["silver", false, "銀"],
  ["gold", false, "金"],
  ["bishop", false, "角"],
  ["rook", false, "飛"],
  ["pawn", true, "と"],
  ["lance", true, "成香"],
  ["knight", true, "成桂"],
  ["silver", true, "成銀"],
  ["bishop", true, "馬"],
  ["rook", true, "龍"],
];

describe("pieceVisualText", () => {
  it.each(textCases)("renders %s (promoted: %s)", (kind, promoted, expected) => {
    expect(pieceVisualText({ side: "black", kind, promoted }, "all-gyoku")).toBe(expected);
  });

  it("preserves each board's king glyph convention", () => {
    const blackKing: PieceVisual = { side: "black", kind: "king", promoted: false };
    const whiteKing: PieceVisual = { side: "white", kind: "king", promoted: false };
    expect(pieceVisualText(blackKing, "black-ou-white-gyoku")).toBe("王");
    expect(pieceVisualText(whiteKing, "black-ou-white-gyoku")).toBe("玉");
    expect(pieceVisualText(blackKing, "all-gyoku")).toBe("玉");
    expect(pieceVisualText(whiteKing, "all-gyoku")).toBe("玉");
  });
});

describe("isPieceUpsideDown", () => {
  it.each([
    ["black", false, false],
    ["white", false, true],
    ["black", true, true],
    ["white", true, false],
  ] as const)("orients %s with flipped=%s", (side, flipped, expected) => {
    expect(isPieceUpsideDown({ side, kind: "pawn", promoted: false }, flipped)).toBe(expected);
  });
});
