/// <reference types="node" />

import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { BOARD_THEMES, PIECE_ASSET_KEYS, PIECE_THEMES } from "./catalog";
import type { BoardThemeDefinition, PieceThemeDefinition, ThemeAttribution } from "./types";

function expectCompleteAttribution(attribution: ThemeAttribution | undefined) {
  expect(attribution).toBeDefined();
  expect(attribution?.sourceName).toBeTruthy();
  expect(attribution?.sourceUrl).toMatch(/^https:\/\//);
  expect(attribution?.licenseName).toBeTruthy();
  expect(attribution?.licenseUrl).toMatch(/^https:\/\//);
  expect(attribution?.noticeAnchor).toBeTruthy();
}

async function readPngSize(assetUrl: string) {
  const assetPath = assetUrl.slice(assetUrl.indexOf("assets/shogi/"));
  const png = await readFile(resolve("public", assetPath));
  expect(png.subarray(1, 4).toString("ascii")).toBe("PNG");
  return { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
}

describe("appearance catalog", () => {
  const pieceThemes = Object.values(PIECE_THEMES) as PieceThemeDefinition[];
  const boardThemes = Object.values(BOARD_THEMES) as BoardThemeDefinition[];

  it("has unique IDs whose keys match the definitions", () => {
    const entries = [...Object.entries(PIECE_THEMES), ...Object.entries(BOARD_THEMES)];
    expect(new Set(entries.map(([, theme]) => theme.id)).size).toBe(entries.length);
    for (const [key, theme] of entries) expect(theme.id).toBe(key);
  });

  it("maps every semantic asset for every image piece theme", () => {
    for (const theme of pieceThemes.filter((candidate) => candidate.mode === "image")) {
      expect(Object.keys(theme.assets ?? {}).sort()).toEqual([...PIECE_ASSET_KEYS].sort());
      for (const [key, url] of Object.entries(theme.assets ?? {})) {
        const [side, kind] = key.split(":");
        expect(url).toContain(`assets/shogi/pieces/${theme.id}/${side}/${kind}.png`);
      }
      expectCompleteAttribution(theme.attribution);
    }
  });

  it("requires complete attribution for every image-backed board", () => {
    for (const theme of boardThemes.filter((candidate) => candidate.backgroundImage)) {
      expect(theme.backgroundImage).toContain(`assets/shogi/boards/${theme.id}/board.png`);
      expect(theme.fallbackColor).toMatch(/^#[0-9a-f]{6}$/i);
      expect(theme.lineColor).toMatch(/^#[0-9a-f]{6}$/i);
      expectCompleteAttribution(theme.attribution);
    }
  });

  it("ships every mapped PNG at its expected intrinsic dimensions", async () => {
    for (const theme of pieceThemes.filter((candidate) => candidate.mode === "image")) {
      for (const assetUrl of Object.values(theme.assets ?? {})) {
        await expect(readPngSize(assetUrl)).resolves.toEqual({ width: 140, height: 148 });
      }
    }
    for (const theme of boardThemes.filter((candidate) => candidate.backgroundImage)) {
      await expect(readPngSize(theme.backgroundImage!)).resolves.toEqual({ width: 458, height: 500 });
    }
  });
});
