import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("shogi.appearance.v1"));
});

test("presets are atomic, remain independently editable, and theme changes retain the preview board", async ({ page }) => {
  await page.goto("/settings");

  const mainPreview = page.locator(".appearance-preview");
  const previewBoard = mainPreview.locator(".preview-board");
  await expect(page.locator(".appearance-compact-preview")).toHaveCount(8);
  await previewBoard.evaluate((element) => { element.setAttribute("data-mount-probe", "retained"); });

  await page.getByRole("button", { name: "ダーク", exact: true }).click();
  await expect(page.getByRole("radio", { name: /^Shogi Images 一文字駒（ダーク）/ })).toBeChecked();
  await expect(page.getByRole("radio", { name: /^Shogi Images 盤 - ダーク/ })).toBeChecked();
  await expect(mainPreview.getByText("駒: Shogi Images 一文字駒（ダーク）", { exact: true })).toBeVisible();
  await expect(mainPreview.getByText("盤: Shogi Images 盤 - ダーク", { exact: true })).toBeVisible();
  await expect(previewBoard).toHaveAttribute("data-board-theme", "shogi-images-dark");
  await expect(previewBoard).toHaveAttribute("data-mount-probe", "retained");
  await expect(mainPreview.locator('img[src*="pieces/shogi-images-hitomoji-dark"]')).toHaveCount(7);

  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("shogi.appearance.v1") ?? "null"))).toEqual({
    version: 1,
    pieceTheme: "shogi-images-hitomoji-dark",
    boardTheme: "shogi-images-dark",
  });

  await page.getByRole("radio", { name: "Shogi Images 一文字駒", exact: true }).check();
  await page.getByRole("radio", { name: "Shogi Images 盤 - 木材（暖）", exact: true }).check();
  await expect(previewBoard).toHaveAttribute("data-mount-probe", "retained");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("shogi.appearance.v1") ?? "null"))).toEqual({
    version: 1,
    pieceTheme: "shogi-images-hitomoji",
    boardTheme: "shogi-images-warm",
  });

  await page.getByRole("button", { name: "伝統", exact: true }).click();
  await page.goto("/problem-editor");
  const editor = page.getByTestId("editor-board");
  await expect(editor.locator('[data-board-theme="shogi-images-warm"]')).toHaveCount(1);
  await expect(editor.locator('img[src*="pieces/shogi-images-futamoji"]')).not.toHaveCount(0);
});

test("the licenses page derives all Shogi Images theme names from the catalog", async ({ page }) => {
  await page.goto("/licenses");
  const card = page.locator("#shogi-images");
  await expect(card).toContainText("Shogi Images 一文字駒");
  await expect(card).toContainText("Shogi Images 二文字駒");
  await expect(card).toContainText("Shogi Images 一文字駒（ダーク）");
  await expect(card).toContainText("Shogi Images 盤 - 木材（明）");
  await expect(card).toContainText("Shogi Images 盤 - 木材（暖）");
  await expect(card).toContainText("Shogi Images 盤 - ダーク");
  await expect(card.getByRole("link", { name: "CC0 1.0" })).toHaveAttribute("href", "https://creativecommons.org/publicdomain/zero/1.0/deed.ja");
});

test.describe("360px high-DPR appearance settings", () => {
  test.use({ viewport: { width: 360, height: 740 }, deviceScaleFactor: 2 });

  test("additional assets load at intrinsic size without horizontal scrolling", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("button", { name: "ダーク", exact: true }).click();

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const darkPiece = page.locator('.appearance-preview img[src*="pieces/shogi-images-hitomoji-dark"]').first();
    const darkSize = await darkPiece.evaluate((image: HTMLImageElement) => ({
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
      renderedWidth: image.getBoundingClientRect().width,
      renderedHeight: image.getBoundingClientRect().height,
    }));
    expect(darkSize.naturalWidth).toBeGreaterThan(0);
    expect(darkSize.naturalHeight).toBeGreaterThan(0);
    expect(darkSize.renderedWidth).toBeLessThanOrEqual(52);
    expect(darkSize.renderedHeight).toBeLessThanOrEqual(52);

    await page.getByRole("button", { name: "伝統", exact: true }).click();
    const traditionalPiece = page.locator('.appearance-preview img[src*="pieces/shogi-images-futamoji"]').first();
    await expect(traditionalPiece).toBeVisible();
    expect(await traditionalPiece.evaluate((image: HTMLImageElement) => image.naturalWidth > 0 && image.naturalHeight > 0)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    const compactBounds = await page.locator(".appearance-compact-preview").evaluateAll((elements) => elements.map((element) => {
      const bounds = element.getBoundingClientRect();
      return { left: bounds.left, right: bounds.right };
    }));
    for (const bounds of compactBounds) {
      expect(bounds.left).toBeGreaterThanOrEqual(0);
      expect(bounds.right).toBeLessThanOrEqual(360);
    }
  });
});
