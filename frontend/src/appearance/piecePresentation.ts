import type { PieceVisual } from "./types";

export type KingGlyphPolicy = "black-ou-white-gyoku" | "all-gyoku";

const BASE_TEXT = {
  pawn: "歩",
  lance: "香",
  knight: "桂",
  silver: "銀",
  gold: "金",
  bishop: "角",
  rook: "飛",
} as const;

const PROMOTED_TEXT = {
  pawn: "と",
  lance: "成香",
  knight: "成桂",
  silver: "成銀",
  bishop: "馬",
  rook: "龍",
} as const;

export function pieceVisualText(piece: PieceVisual, kingGlyph: KingGlyphPolicy): string {
  if (piece.kind === "king") {
    return kingGlyph === "black-ou-white-gyoku" && piece.side === "black" ? "王" : "玉";
  }
  if (piece.promoted && piece.kind !== "gold") {
    return PROMOTED_TEXT[piece.kind];
  }
  return BASE_TEXT[piece.kind];
}

export function isPieceUpsideDown(piece: PieceVisual, flipped: boolean): boolean {
  return (piece.side === "white") !== flipped;
}
