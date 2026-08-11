import { describe, expect, it } from "vitest";
import { getBoardTheme, getPieceTheme } from "./catalog";
import { resolvePieceAsset } from "./pieceResolver";
import type { PieceKind, PieceThemeDefinition } from "./types";

describe("resolvePieceAsset", () => {
  const image = getPieceTheme("shogi-images-hitomoji")!;
  it.each(["pawn", "lance", "knight", "silver", "gold", "bishop", "rook"] as PieceKind[])("resolves both sides of %s", (kind) => {
    for (const side of ["black", "white"] as const) {
      expect(resolvePieceAsset(image, { side, kind, promoted: false }, "black-ou-white-gyoku", "board", false)?.key).toBe(`${side}:${kind}`);
    }
  });

  it.each([["pawn", "promoted-pawn"], ["lance", "promoted-lance"], ["knight", "promoted-knight"], ["silver", "promoted-silver"], ["bishop", "horse"], ["rook", "dragon"]] as const)("maps promoted %s", (kind, assetKind) => {
    expect(resolvePieceAsset(image, { side: "black", kind, promoted: true }, "all-gyoku", "board", false)?.key).toBe(`black:${assetKind}`);
  });

  it("preserves both king glyph policies when not flipped", () => {
    expect(resolvePieceAsset(image, { side: "black", kind: "king", promoted: false }, "black-ou-white-gyoku", "board", false)?.key).toBe("black:ou");
    expect(resolvePieceAsset(image, { side: "white", kind: "king", promoted: false }, "black-ou-white-gyoku", "board", false)?.key).toBe("white:gyoku");
    expect(resolvePieceAsset(image, { side: "black", kind: "king", promoted: false }, "all-gyoku", "board", false)?.key).toBe("black:gyoku");
  });

  it.each([
    ["black", false, "black:pawn"],
    ["white", false, "white:pawn"],
    ["black", true, "white:pawn"],
    ["white", true, "black:pawn"],
  ] as const)("uses explicit-side orientation for %s with flipped=%s", (side, flipped, key) => {
    expect(resolvePieceAsset(image, { side, kind: "pawn", promoted: false }, "all-gyoku", "board", flipped)).toMatchObject({ key, rotate: false });
  });

  it.each([
    ["black-ou-white-gyoku", "black", false, "black:ou"],
    ["black-ou-white-gyoku", "black", true, "white:ou"],
    ["black-ou-white-gyoku", "white", false, "white:gyoku"],
    ["black-ou-white-gyoku", "white", true, "black:gyoku"],
    ["all-gyoku", "black", false, "black:gyoku"],
    ["all-gyoku", "black", true, "white:gyoku"],
    ["all-gyoku", "white", false, "white:gyoku"],
    ["all-gyoku", "white", true, "black:gyoku"],
  ] as const)("keeps %s glyph semantics for %s with flipped=%s", (policy, side, flipped, key) => {
    expect(resolvePieceAsset(image, { side, kind: "king", promoted: false }, policy, "board", flipped)?.key).toBe(key);
  });

  it("normalizes promoted hand pieces before selecting flipped explicit-side assets", () => {
    expect(resolvePieceAsset(image, { side: "white", kind: "pawn", promoted: true }, "all-gyoku", "hand", true)).toMatchObject({ key: "black:pawn", rotate: false });
  });

  it("rotates an opponent only for rotate-opponent", () => {
    const theme: PieceThemeDefinition = { id: "shogi-images-hitomoji", label: "test", mode: "image", orientation: "rotate-opponent", assets: { "black:pawn": "pawn.png" } };
    for (const [side, flipped, rotate] of [["black", false, false], ["white", false, true], ["black", true, true], ["white", true, false]] as const) {
      expect(resolvePieceAsset(theme, { side, kind: "pawn", promoted: false }, "all-gyoku", "board", flipped)?.rotate).toBe(rotate);
    }
  });

  it("returns null for text, unknown, and missing mappings", () => {
    const piece = { side: "black", kind: "pawn", promoted: false } as const;
    expect(resolvePieceAsset(getPieceTheme("text-standard"), piece, "all-gyoku", "board", false)).toBeNull();
    expect(resolvePieceAsset(getPieceTheme("unknown"), piece, "all-gyoku", "board", false)).toBeNull();
    expect(resolvePieceAsset({ ...image, assets: {} }, piece, "all-gyoku", "board", false)).toBeNull();
  });
});

describe("board catalog", () => {
  it("preserves the pre-theme standard board colors", () => {
    expect(getBoardTheme("board-standard")).toMatchObject({
      fallbackColor: "#f3c970",
      lineColor: "#8a6a33",
    });
  });
});
