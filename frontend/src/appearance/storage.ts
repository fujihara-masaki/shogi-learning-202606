import { getBoardTheme, getPieceTheme } from "./catalog";
import type { BoardThemeId, PieceThemeId } from "./types";

export const APPEARANCE_STORAGE_KEY = "shogi.appearance.v1";
export const DEFAULT_APPEARANCE_SETTINGS: AppearanceSettings = {
  pieceTheme: "text-standard",
  boardTheme: "board-standard",
};

export interface AppearanceSettings {
  pieceTheme: PieceThemeId;
  boardTheme: BoardThemeId;
}

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function browserStorage(): StorageLike | undefined {
  if (typeof window === "undefined") return undefined;
  return window.localStorage;
}

export function loadAppearanceSettings(storage?: StorageLike): AppearanceSettings {
  try {
    const value = (storage ?? browserStorage())?.getItem(APPEARANCE_STORAGE_KEY);
    if (!value) return { ...DEFAULT_APPEARANCE_SETTINGS };
    const parsed: unknown = JSON.parse(value);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return { ...DEFAULT_APPEARANCE_SETTINGS };
    const record = parsed as Record<string, unknown>;
    if (record.version !== 1) return { ...DEFAULT_APPEARANCE_SETTINGS };
    const pieceTheme = getPieceTheme(record.pieceTheme);
    const boardTheme = getBoardTheme(record.boardTheme);
    return {
      pieceTheme: pieceTheme?.id ?? DEFAULT_APPEARANCE_SETTINGS.pieceTheme,
      boardTheme: boardTheme?.id ?? DEFAULT_APPEARANCE_SETTINGS.boardTheme,
    };
  } catch {
    return { ...DEFAULT_APPEARANCE_SETTINGS };
  }
}

export function saveAppearanceSettings(settings: AppearanceSettings, storage?: StorageLike): boolean {
  try {
    const target = storage ?? browserStorage();
    if (!target) return false;
    target.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify({ version: 1, ...settings }));
    return true;
  } catch {
    return false;
  }
}

export function resetAppearanceSettings(storage?: StorageLike): boolean {
  try {
    const target = storage ?? browserStorage();
    if (!target) return false;
    target.removeItem(APPEARANCE_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}
