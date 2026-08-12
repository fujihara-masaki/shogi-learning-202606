import { createContext, useContext } from "react";
import type { BoardThemeId, PieceThemeId } from "./types";
import { DEFAULT_APPEARANCE_SETTINGS, type AppearanceSettings } from "./storage";

export interface AppearanceContextValue {
  pieceTheme: PieceThemeId;
  boardTheme: BoardThemeId;
  setPieceTheme: (theme: PieceThemeId) => void;
  setBoardTheme: (theme: BoardThemeId) => void;
  setAppearance: (settings: AppearanceSettings) => void;
  resetToDefaults: () => void;
  storageWarning: boolean;
}

export const AppearanceContext = createContext<AppearanceContextValue | undefined>(undefined);

export function useAppearance(): AppearanceContextValue {
  return useContext(AppearanceContext) ?? {
    ...DEFAULT_APPEARANCE_SETTINGS,
    setPieceTheme: () => undefined,
    setBoardTheme: () => undefined,
    setAppearance: () => undefined,
    resetToDefaults: () => undefined,
    storageWarning: false,
  };
}
