import { Color as TsshogiColor, PieceType, type Piece } from "tsshogi";
import type { EditorPiece, PieceCode } from "../shogi/editor";
import type { PieceKind, PieceVisual } from "./types";

const TSSHOGI_PIECES: Record<PieceType, Pick<PieceVisual, "kind" | "promoted">> = {
  [PieceType.PAWN]: { kind: "pawn", promoted: false },
  [PieceType.LANCE]: { kind: "lance", promoted: false },
  [PieceType.KNIGHT]: { kind: "knight", promoted: false },
  [PieceType.SILVER]: { kind: "silver", promoted: false },
  [PieceType.GOLD]: { kind: "gold", promoted: false },
  [PieceType.BISHOP]: { kind: "bishop", promoted: false },
  [PieceType.ROOK]: { kind: "rook", promoted: false },
  [PieceType.KING]: { kind: "king", promoted: false },
  [PieceType.PROM_PAWN]: { kind: "pawn", promoted: true },
  [PieceType.PROM_LANCE]: { kind: "lance", promoted: true },
  [PieceType.PROM_KNIGHT]: { kind: "knight", promoted: true },
  [PieceType.PROM_SILVER]: { kind: "silver", promoted: true },
  [PieceType.HORSE]: { kind: "bishop", promoted: true },
  [PieceType.DRAGON]: { kind: "rook", promoted: true },
};

const EDITOR_KINDS: Record<PieceCode, PieceKind> = {
  P: "pawn",
  L: "lance",
  N: "knight",
  S: "silver",
  G: "gold",
  B: "bishop",
  R: "rook",
  K: "king",
  "+P": "pawn",
  "+L": "lance",
  "+N": "knight",
  "+S": "silver",
  "+B": "bishop",
  "+R": "rook",
};

export function tsshogiPieceToVisual(piece: Piece): PieceVisual {
  return {
    side: piece.color === TsshogiColor.BLACK ? "black" : "white",
    ...TSSHOGI_PIECES[piece.type],
  };
}

export function editorPieceToVisual(piece: EditorPiece): PieceVisual {
  return {
    side: piece.color === "b" ? "black" : "white",
    kind: EDITOR_KINDS[piece.code],
    promoted: piece.code.startsWith("+"),
  };
}
