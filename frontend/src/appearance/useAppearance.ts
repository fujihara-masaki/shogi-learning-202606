import { createContext, useContext } from "react";
import type { BoardThemeId, PieceThemeId } from "./types";
import { DEFAULT_APPEARANCE_SETTINGS } from "./storage";

export interface AppearanceContextValue {
  pieceTheme: PieceThemeId;
  boardTheme: BoardThemeId;
  setPieceTheme: (theme: PieceThemeId) => void;
  setBoardTheme: (theme: BoardThemeId) => void;
  resetToDefaults: () => void;
  storageWarning: boolean;
}

export const AppearanceContext = createContext<AppearanceContextValue | undefined>(undefined);

export function useAppearance(): AppearanceContextValue {
  return useContext(AppearanceContext) ?? {
    ...DEFAULT_APPEARANCE_SETTINGS,
    setPieceTheme: () => undefined,
    setBoardTheme: () => undefined,
    resetToDefaults: () => undefined,
    storageWarning: false,
  };
}
