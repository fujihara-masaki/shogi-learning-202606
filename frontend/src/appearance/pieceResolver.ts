import type { KingGlyphPolicy } from "./piecePresentation";
import type { PieceAssetKey, PieceLocation, PieceThemeDefinition, PieceVisual } from "./types";

export interface ResolvedPieceAsset { src: string; rotate: boolean; key: PieceAssetKey }

function kindKey(piece: PieceVisual, kingGlyph: KingGlyphPolicy): PieceAssetKey extends `${string}:${infer K}` ? K : never {
  if (piece.kind === "king") return kingGlyph === "black-ou-white-gyoku" && piece.side === "black" ? "ou" : "gyoku";
  if (!piece.promoted) return piece.kind;
  return ({ pawn: "promoted-pawn", lance: "promoted-lance", knight: "promoted-knight", silver: "promoted-silver", bishop: "horse", rook: "dragon", gold: "gold" } as const)[piece.kind];
}

export function resolvePieceAsset(theme: PieceThemeDefinition | undefined, piece: PieceVisual, kingGlyph: KingGlyphPolicy, location: PieceLocation, flipped: boolean): ResolvedPieceAsset | null {
  if (!theme || theme.mode !== "image" || !theme.assets) return null;
  const normalized = location === "hand" ? { ...piece, promoted: false } : piece;
  // An explicit-side asset's side describes its painted orientation, not ownership.
  // Board flipping changes only that orientation; glyph selection above still uses ownership.
  const assetSide = theme.orientation === "rotate-opponent"
    ? "black"
    : flipped
      ? normalized.side === "black" ? "white" : "black"
      : normalized.side;
  const key = `${assetSide}:${kindKey(normalized, kingGlyph)}` as PieceAssetKey;
  const src = theme.assets[key];
  if (!src) return null;
  const rotate = theme.orientation === "rotate-opponent" && ((normalized.side === "white") !== flipped);
  return { src, rotate, key };
}
