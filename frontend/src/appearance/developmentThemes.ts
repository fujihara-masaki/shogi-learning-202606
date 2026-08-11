import { getBoardTheme, getPieceTheme } from "./catalog";
import type { BoardThemeId, PieceThemeId } from "./types";

/**
 * Explicit development/E2E selection path for PR-B. This is deliberately not a
 * user setting and is replaced by the persisted appearance model in PR-C.
 */
export function developmentThemeOverrides(): {
  pieceTheme?: PieceThemeId;
  boardTheme?: BoardThemeId;
} {
  if (!import.meta.env.DEV || typeof window === "undefined") return {};
  const query = new URLSearchParams(window.location.search);
  const piece = getPieceTheme(query.get("pieceTheme"));
  const board = getBoardTheme(query.get("boardTheme"));
  return {
    pieceTheme: piece?.id,
    boardTheme: board?.id,
  };
}
