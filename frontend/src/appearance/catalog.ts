import type { BoardThemeDefinition, BoardThemeId, PieceAssetKey, PieceThemeDefinition, PieceThemeId } from "./types";

const assetPath = (path: string): string => `${import.meta.env.BASE_URL}assets/shogi/${path}`;
const attribution = {
  sourceName: "Shogi Images",
  sourceUrl: "https://shogi-extend.com/shogi-images/",
  licenseName: "CC0 1.0",
  licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/deed.ja",
  noticeAnchor: "shogi-images",
} as const;

const kinds = ["pawn", "lance", "knight", "silver", "gold", "bishop", "rook", "ou", "gyoku", "promoted-pawn", "promoted-lance", "promoted-knight", "promoted-silver", "horse", "dragon"] as const;
const imageAssets = Object.fromEntries(
  ["black", "white"].flatMap((side) => kinds.map((kind) => [
    `${side}:${kind}` as PieceAssetKey,
    assetPath(`pieces/shogi-images-hitomoji/${side}/${kind}.png`),
  ])),
) as Partial<Record<PieceAssetKey, string>>;

export const PIECE_THEMES = {
  "text-standard": { id: "text-standard", label: "標準（文字）", mode: "text", orientation: "rotate-opponent" },
  "shogi-images-hitomoji": { id: "shogi-images-hitomoji", label: "Shogi Images 一文字駒", mode: "image", orientation: "explicit-sides", assets: imageAssets, attribution },
} satisfies Record<PieceThemeId, PieceThemeDefinition>;

export const BOARD_THEMES = {
  "board-standard": { id: "board-standard", label: "標準盤", fallbackColor: "#dcb35c", lineColor: "#3c2a12" },
  "shogi-images-light": { id: "shogi-images-light", label: "Shogi Images 盤 - 木材（明）", backgroundImage: assetPath("boards/shogi-images-light/board.png"), fallbackColor: "#dcb35c", lineColor: "#3c2a12", attribution },
} satisfies Record<BoardThemeId, BoardThemeDefinition>;

export function getPieceTheme(value: unknown): PieceThemeDefinition | undefined {
  return typeof value === "string" && Object.hasOwn(PIECE_THEMES, value) ? PIECE_THEMES[value as PieceThemeId] : undefined;
}
export function getBoardTheme(value: unknown): BoardThemeDefinition | undefined {
  return typeof value === "string" && Object.hasOwn(BOARD_THEMES, value) ? BOARD_THEMES[value as BoardThemeId] : undefined;
}
