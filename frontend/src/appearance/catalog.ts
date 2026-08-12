import type {
  AppearancePresetDefinition,
  BoardThemeDefinition,
  BoardThemeId,
  PieceAssetKey,
  PieceThemeDefinition,
  PieceThemeId,
  ThemeAttribution,
} from "./types";

const assetPath = (path: string): string => `${import.meta.env.BASE_URL}assets/shogi/${path}`;
export const SHOGI_IMAGES_ATTRIBUTION = {
  sourceName: "Shogi Images",
  sourceUrl: "https://sunfish-shogi.github.io/shogi-images/",
  licenseName: "CC0 1.0",
  licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/deed.ja",
  noticeAnchor: "shogi-images",
} as const;

const kinds = ["pawn", "lance", "knight", "silver", "gold", "bishop", "rook", "ou", "gyoku", "promoted-pawn", "promoted-lance", "promoted-knight", "promoted-silver", "horse", "dragon"] as const;
export const PIECE_ASSET_KEYS = ["black", "white"].flatMap((side) =>
  kinds.map((kind) => `${side}:${kind}` as PieceAssetKey),
);

const imageAssets = (themeId: string) => Object.fromEntries(
  ["black", "white"].flatMap((side) => kinds.map((kind) => [
    `${side}:${kind}` as PieceAssetKey,
    assetPath(`pieces/${themeId}/${side}/${kind}.png`),
  ])),
) as Record<PieceAssetKey, string>;

export const PIECE_THEMES = {
  "text-standard": { id: "text-standard", label: "標準（文字）", mode: "text", orientation: "rotate-opponent" },
  "shogi-images-hitomoji": { id: "shogi-images-hitomoji", label: "Shogi Images 一文字駒", mode: "image", orientation: "explicit-sides", assets: imageAssets("shogi-images-hitomoji"), attribution: SHOGI_IMAGES_ATTRIBUTION },
  "shogi-images-futamoji": { id: "shogi-images-futamoji", label: "Shogi Images 二文字駒", mode: "image", orientation: "explicit-sides", assets: imageAssets("shogi-images-futamoji"), attribution: SHOGI_IMAGES_ATTRIBUTION },
  "shogi-images-hitomoji-dark": { id: "shogi-images-hitomoji-dark", label: "Shogi Images 一文字駒（ダーク）", mode: "image", orientation: "explicit-sides", assets: imageAssets("shogi-images-hitomoji-dark"), attribution: SHOGI_IMAGES_ATTRIBUTION },
} satisfies Record<PieceThemeId, PieceThemeDefinition>;

export const BOARD_THEMES = {
  "board-standard": { id: "board-standard", label: "標準盤", fallbackColor: "#f3c970", lineColor: "#8a6a33" },
  "shogi-images-light": { id: "shogi-images-light", label: "Shogi Images 盤 - 木材（明）", backgroundImage: assetPath("boards/shogi-images-light/board.png"), fallbackColor: "#dcb35c", lineColor: "#3c2a12", attribution: SHOGI_IMAGES_ATTRIBUTION },
  "shogi-images-warm": { id: "shogi-images-warm", label: "Shogi Images 盤 - 木材（暖）", backgroundImage: assetPath("boards/shogi-images-warm/board.png"), fallbackColor: "#d69a0b", lineColor: "#30220d", attribution: SHOGI_IMAGES_ATTRIBUTION },
  "shogi-images-dark": { id: "shogi-images-dark", label: "Shogi Images 盤 - ダーク", backgroundImage: assetPath("boards/shogi-images-dark/board.png"), fallbackColor: "#333333", lineColor: "#f0f0f0", attribution: SHOGI_IMAGES_ATTRIBUTION },
} satisfies Record<BoardThemeId, BoardThemeDefinition>;

export const APPEARANCE_PRESETS = {
  "image-light": { id: "image-light", label: "画像・明るい", pieceTheme: "shogi-images-hitomoji", boardTheme: "shogi-images-light" },
  traditional: { id: "traditional", label: "伝統", pieceTheme: "shogi-images-futamoji", boardTheme: "shogi-images-warm" },
  dark: { id: "dark", label: "ダーク", pieceTheme: "shogi-images-hitomoji-dark", boardTheme: "shogi-images-dark" },
} satisfies Record<string, AppearancePresetDefinition>;

export interface ThemeAttributionGroup {
  attribution: ThemeAttribution;
  pieceThemes: PieceThemeDefinition[];
  boardThemes: BoardThemeDefinition[];
}

export function getThemeAttributionGroups(): ThemeAttributionGroup[] {
  const groups = new Map<string, ThemeAttributionGroup>();
  const groupFor = (attribution: ThemeAttribution) => {
    const key = `${attribution.sourceUrl}:${attribution.licenseUrl}`;
    const existing = groups.get(key);
    if (existing) return existing;
    const group = { attribution, pieceThemes: [], boardThemes: [] };
    groups.set(key, group);
    return group;
  };
  for (const theme of Object.values(PIECE_THEMES)) {
    if ("attribution" in theme && theme.attribution) groupFor(theme.attribution).pieceThemes.push(theme);
  }
  for (const theme of Object.values(BOARD_THEMES)) {
    if ("attribution" in theme && theme.attribution) groupFor(theme.attribution).boardThemes.push(theme);
  }
  return [...groups.values()];
}

export function getPieceTheme(value: unknown): PieceThemeDefinition | undefined {
  return typeof value === "string" && Object.hasOwn(PIECE_THEMES, value) ? PIECE_THEMES[value as PieceThemeId] : undefined;
}
export function getBoardTheme(value: unknown): BoardThemeDefinition | undefined {
  return typeof value === "string" && Object.hasOwn(BOARD_THEMES, value) ? BOARD_THEMES[value as BoardThemeId] : undefined;
}
