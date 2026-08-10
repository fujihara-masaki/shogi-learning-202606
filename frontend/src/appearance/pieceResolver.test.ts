import { describe, expect, it } from "vitest";
import { getPieceTheme } from "./catalog";
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

  it("preserves both king glyph policies", () => {
    expect(resolvePieceAsset(image, { side: "black", kind: "king", promoted: false }, "black-ou-white-gyoku", "board", false)?.key).toBe("black:ou");
    expect(resolvePieceAsset(image, { side: "white", kind: "king", promoted: false }, "black-ou-white-gyoku", "board", false)?.key).toBe("white:gyoku");
    expect(resolvePieceAsset(image, { side: "black", kind: "king", promoted: false }, "all-gyoku", "board", false)?.key).toBe("black:gyoku");
  });

  it("keeps explicit-side assets independent from flip and handles hand promotion", () => {
    expect(resolvePieceAsset(image, { side: "white", kind: "pawn", promoted: true }, "all-gyoku", "hand", true)).toMatchObject({ key: "white:pawn", rotate: false });
  });

  it("rotates an opponent only for rotate-opponent", () => {
    const theme: PieceThemeDefinition = { id: "shogi-images-hitomoji", label: "test", mode: "image", orientation: "rotate-opponent", assets: { "black:pawn": "pawn.png" } };
    expect(resolvePieceAsset(theme, { side: "white", kind: "pawn", promoted: false }, "all-gyoku", "board", false)?.rotate).toBe(true);
    expect(resolvePieceAsset(theme, { side: "white", kind: "pawn", promoted: false }, "all-gyoku", "board", true)?.rotate).toBe(false);
  });

  it("returns null for text, unknown, and missing mappings", () => {
    const piece = { side: "black", kind: "pawn", promoted: false } as const;
    expect(resolvePieceAsset(getPieceTheme("text-standard"), piece, "all-gyoku", "board", false)).toBeNull();
    expect(resolvePieceAsset(getPieceTheme("unknown"), piece, "all-gyoku", "board", false)).toBeNull();
    expect(resolvePieceAsset({ ...image, assets: {} }, piece, "all-gyoku", "board", false)).toBeNull();
  });
});
