import { describe, expect, it } from "vitest";
import { Color, Piece, PieceType } from "tsshogi";
import type { EditorPiece, PieceCode } from "../shogi/editor";
import { editorPieceToVisual, tsshogiPieceToVisual } from "./adapters";
import type { PieceKind } from "./types";

const tsshogiCases: Array<[PieceType, PieceKind, boolean]> = [
  [PieceType.PAWN, "pawn", false],
  [PieceType.LANCE, "lance", false],
  [PieceType.KNIGHT, "knight", false],
  [PieceType.SILVER, "silver", false],
  [PieceType.GOLD, "gold", false],
  [PieceType.BISHOP, "bishop", false],
  [PieceType.ROOK, "rook", false],
  [PieceType.KING, "king", false],
  [PieceType.PROM_PAWN, "pawn", true],
  [PieceType.PROM_LANCE, "lance", true],
  [PieceType.PROM_KNIGHT, "knight", true],
  [PieceType.PROM_SILVER, "silver", true],
  [PieceType.HORSE, "bishop", true],
  [PieceType.DRAGON, "rook", true],
];

const editorCases: Array<[PieceCode, PieceKind, boolean]> = [
  ["P", "pawn", false],
  ["L", "lance", false],
  ["N", "knight", false],
  ["S", "silver", false],
  ["G", "gold", false],
  ["B", "bishop", false],
  ["R", "rook", false],
  ["K", "king", false],
  ["+P", "pawn", true],
  ["+L", "lance", true],
  ["+N", "knight", true],
  ["+S", "silver", true],
  ["+B", "bishop", true],
  ["+R", "rook", true],
];

describe("tsshogiPieceToVisual", () => {
  for (const [color, side] of [
    [Color.BLACK, "black"],
    [Color.WHITE, "white"],
  ] as const) {
    it.each(tsshogiCases)(`normalizes every ${side} piece: %s`, (type, kind, promoted) => {
      expect(tsshogiPieceToVisual(new Piece(color, type))).toEqual({ side, kind, promoted });
    });
  }
});

describe("editorPieceToVisual", () => {
  for (const [color, side] of [
    ["b", "black"],
    ["w", "white"],
  ] as const) {
    it.each(editorCases)(`normalizes every ${side} editor piece: %s`, (code, kind, promoted) => {
      const piece: EditorPiece = { color, code };
      expect(editorPieceToVisual(piece)).toEqual({ side, kind, promoted });
    });
  }
});
