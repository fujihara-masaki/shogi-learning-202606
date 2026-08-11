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

export type PieceThemeId = "text-standard" | "shogi-images-hitomoji";
export type BoardThemeId = "board-standard" | "shogi-images-light";
export type PieceOrientationPolicy = "explicit-sides" | "rotate-opponent";
export type PieceLocation = "board" | "hand";

export interface ThemeAttribution {
  sourceName: string;
  sourceUrl: string;
  licenseName: string;
  licenseUrl: string;
  noticeAnchor: string;
}

export type PieceAssetKind = PieceKind | "promoted-pawn" | "promoted-lance" |
  "promoted-knight" | "promoted-silver" | "horse" | "dragon" | "ou" | "gyoku";
export type PieceAssetKey = `${PieceSide}:${PieceAssetKind}`;

export interface PieceThemeDefinition {
  id: PieceThemeId;
  label: string;
  mode: "text" | "image";
  orientation: PieceOrientationPolicy;
  assets?: Partial<Record<PieceAssetKey, string>>;
  attribution?: ThemeAttribution;
}

export interface BoardThemeDefinition {
  id: BoardThemeId;
  label: string;
  backgroundImage?: string;
  fallbackColor: string;
  lineColor: string;
  attribution?: ThemeAttribution;
}
