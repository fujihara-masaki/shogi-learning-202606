export type PieceSide = "black" | "white";

export type PieceKind =
  | "pawn"
  | "lance"
  | "knight"
  | "silver"
  | "gold"
  | "bishop"
  | "rook"
  | "king";

/** A normalized, display-only representation of a shogi piece. */
export interface PieceVisual {
  side: PieceSide;
  kind: PieceKind;
  promoted: boolean;
}
