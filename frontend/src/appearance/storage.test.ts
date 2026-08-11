import { describe, expect, it } from "vitest";
import { APPEARANCE_STORAGE_KEY, DEFAULT_APPEARANCE_SETTINGS, loadAppearanceSettings, resetAppearanceSettings, saveAppearanceSettings } from "./storage";

function storageWith(value: string | null) {
  return { getItem: () => value, setItem: () => undefined, removeItem: () => undefined };
}

describe("appearance storage", () => {
  it("loads valid version 1 settings", () => expect(loadAppearanceSettings(storageWith(JSON.stringify({ version: 1, pieceTheme: "shogi-images-hitomoji", boardTheme: "shogi-images-light" })))).toEqual({ pieceTheme: "shogi-images-hitomoji", boardTheme: "shogi-images-light" }));
  it.each([null, "null", "[]", "{broken", JSON.stringify({ version: 0, pieceTheme: "text-standard", boardTheme: "board-standard" }), JSON.stringify({ version: 2, pieceTheme: "text-standard", boardTheme: "board-standard" }), JSON.stringify({ version: 1, pieceTheme: "unknown", boardTheme: "board-standard" }), JSON.stringify({ version: 1, pieceTheme: "text-standard", boardTheme: "unknown" })])("falls back for invalid value %#", (value) => expect(loadAppearanceSettings(storageWith(value))).toEqual(DEFAULT_APPEARANCE_SETTINGS));
  it("falls back when getItem throws", () => expect(loadAppearanceSettings({ ...storageWith(null), getItem: () => { throw new Error("disabled"); } })).toEqual(DEFAULT_APPEARANCE_SETTINGS));
  it("saves the versioned payload", () => { let saved = ""; const ok = saveAppearanceSettings({ pieceTheme: "text-standard", boardTheme: "shogi-images-light" }, { ...storageWith(null), setItem: (key, value) => { expect(key).toBe(APPEARANCE_STORAGE_KEY); saved = value; } }); expect(ok).toBe(true); expect(JSON.parse(saved)).toEqual({ version: 1, pieceTheme: "text-standard", boardTheme: "shogi-images-light" }); });
  it("reports setItem exceptions", () => expect(saveAppearanceSettings(DEFAULT_APPEARANCE_SETTINGS, { ...storageWith(null), setItem: () => { throw new Error("quota"); } })).toBe(false));
  it("removes the versioned key", () => { let removed = ""; expect(resetAppearanceSettings({ ...storageWith(null), removeItem: (key) => { removed = key; } })).toBe(true); expect(removed).toBe(APPEARANCE_STORAGE_KEY); });
  it("reports removeItem exceptions", () => expect(resetAppearanceSettings({ ...storageWith(null), removeItem: () => { throw new Error("disabled"); } })).toBe(false));
});
