import { describe, expect, it } from "vitest";
import { APPEARANCE_PRESETS, BOARD_THEMES, PIECE_THEMES } from "./catalog";
import { APPEARANCE_STORAGE_KEY, saveAppearanceSettings } from "./storage";

describe("appearance presets", () => {
  it("have unique IDs and reference catalog themes", () => {
    const presets = Object.values(APPEARANCE_PRESETS);
    expect(new Set(presets.map((preset) => preset.id)).size).toBe(presets.length);
    for (const preset of presets) {
      expect(PIECE_THEMES[preset.pieceTheme]).toBeDefined();
      expect(BOARD_THEMES[preset.boardTheme]).toBeDefined();
    }
  });

  it("persist only the two appearance axes, never a preset ID", () => {
    for (const preset of Object.values(APPEARANCE_PRESETS)) {
      let saved = "";
      expect(saveAppearanceSettings(
        { pieceTheme: preset.pieceTheme, boardTheme: preset.boardTheme },
        { getItem: () => null, removeItem: () => undefined, setItem: (key, value) => { expect(key).toBe(APPEARANCE_STORAGE_KEY); saved = value; } },
      )).toBe(true);
      expect(JSON.parse(saved)).toEqual({ version: 1, pieceTheme: preset.pieceTheme, boardTheme: preset.boardTheme });
      expect(saved).not.toContain("presetTheme");
    }
  });
});
