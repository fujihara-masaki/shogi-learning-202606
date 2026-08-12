import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

const backendPort = process.env.E2E_BACKEND_PORT ?? "8000";
const API_BASE = `http://127.0.0.1:${backendPort}`;
const E2E_PREFIX = "[e2e]";
const ONE_MOVE_SFEN = "4k4/9/5+B3/9/9/9/9/9/9 b G 1";
const ONE_MOVE_SOLUTION = "G*5b";

type Problem = { id: number; title: string; solution_moves: string[] };

const majorPlayableOpenings = [
  "棒銀",
  "中飛車",
  "向かい飛車",
  "四間飛車",
  "矢倉",
  "角換わり",
  "相掛かり",
  "横歩取り",
  "石田流",
  "ゴキゲン中飛車",
  "角交換四間飛車",
  "右四間飛車",
  "居飛車穴熊",
  "対振り飛車急戦",
];

const additionalPlayableOpenings = [
  "三間飛車",
  "角交換振り飛車",
  "相振り飛車",
  "嬉野流",
  "鬼殺し",
  "早石田",
  "筋違い角",
  "雁木",
  "矢倉棒銀",
  "角換わり棒銀",
  "角換わり早繰り銀",
  "角換わり腰掛け銀",
  "原始棒銀",
  "美濃囲い",
  "穴熊",
  "舟囲い",
  "左美濃",
];

const allPlayableOpenings = [...majorPlayableOpenings, ...additionalPlayableOpenings];

function openingLineByExactTitle(page: Page, title: string) {
  return page.getByTestId("opening-type-line-card").filter({
    has: page.getByTestId("opening-card-title").getByText(title, { exact: true }),
  });
}

function openingTypeCardByExactTitle(page: Page, title: string) {
  return page.getByTestId("opening-type-card").filter({
    has: page.getByTestId("opening-type-card-title").getByText(title, { exact: true }),
  });
}

async function showOpeningTypeLines(page: Page, typeName: string) {
  const card = openingTypeCardByExactTitle(page, typeName);
  await card.getByRole("button", { name: "手順を見る" }).click();
  await expect(card.getByTestId("opening-type-line-list")).toBeVisible();
  return card;
}

async function cleanupE2eProblems(request: APIRequestContext) {
  const res = await request.get(`${API_BASE}/api/tsume-problems`);
  expect(res.ok()).toBeTruthy();
  const problems = (await res.json()) as Problem[];
  await Promise.all(
    problems
      .filter((p) => p.title.startsWith(E2E_PREFIX))
      .map((p) => request.delete(`${API_BASE}/api/tsume-problems/${p.id}`)),
  );
}

async function createE2eProblem(
  request: APIRequestContext,
  title: string,
  overrides: Record<string, unknown> = {},
) {
  const res = await request.post(`${API_BASE}/api/tsume-problems`, {
    data: {
      title,
      initial_sfen: ONE_MOVE_SFEN,
      mate_length: 1,
      solution_moves: [ONE_MOVE_SOLUTION],
      opponent_moves: [],
      difficulty: 1,
      tags: ["e2e"],
      explanation: "E2E test problem",
      is_favorite: false,
      ...overrides,
    },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as Problem;
}


async function showE2eOneMoveProblems(page: Page) {
  await page.goto("/tsume");
  await page.getByTestId("difficulty-filter").getByRole("button", { name: "1手詰", exact: true }).click();
  await page.getByRole("combobox").selectOption("e2e");
}

async function useShogiImagesTheme(page: Page) {
  await page.addInitScript(() => localStorage.setItem("shogi.appearance.v1", JSON.stringify({ version: 1, pieceTheme: "shogi-images-hitomoji", boardTheme: "shogi-images-light" })));
}

async function playGoldDrop(page: Page, square: string) {
  const board = page.getByTestId("shogi-board");
  await board.getByRole("button", { name: "金" }).click();
  await board.locator(`[data-square="${square}"]`).click();
}

async function dragGoldDrop(page: Page, square: string) {
  const board = page.getByTestId("shogi-board");
  const source = board.getByRole("button", { name: "金" });
  const target = board.locator(`[data-square="${square}"]`);

  await expect(source).toHaveAttribute("draggable", "true");
  const dataTransfer = await page.evaluateHandle(() => new DataTransfer());
  await source.dispatchEvent("dragstart", { dataTransfer });
  await expect(target).toHaveClass(/target/);
  await target.dispatchEvent("dragover", { dataTransfer });
  await target.dispatchEvent("drop", { dataTransfer });
}

async function expectImageConstrainedToContainer(image: Locator, container: Locator, cell: Locator) {
  const [imageBox, containerBox, cellBox] = await Promise.all([
    image.boundingBox(),
    container.boundingBox(),
    cell.boundingBox(),
  ]);
  if (!imageBox || !containerBox || !cellBox) throw new Error("Expected visible piece image, container, and board cell");
  const roundingTolerance = 1;
  expect(imageBox.width).toBeLessThanOrEqual(containerBox.width + roundingTolerance);
  expect(imageBox.height).toBeLessThanOrEqual(containerBox.height + roundingTolerance);
  expect(imageBox.width).toBeLessThanOrEqual(cellBox.width * 0.88 + roundingTolerance);
  expect(imageBox.height).toBeLessThanOrEqual(cellBox.height * 0.88 + roundingTolerance);
}

test.beforeEach(async ({ request }) => {
  await cleanupE2eProblems(request);
});

test.afterEach(async ({ request }) => {
  await cleanupE2eProblems(request);
});

test("home presents learning subjects separately from cross-cutting tools", async ({ page }) => {
  await page.goto("/");
  const learning = page.getByRole("region", { name: "学習対象" });
  const tools = page.getByRole("region", { name: "学習を支える機能" });
  for (const name of ["詰め将棋", "定跡学習", "次の一手"])
    await expect(learning.getByRole("link", { name })).toBeVisible();
  for (const name of ["復習", "学習記録", "問題作成"])
    await expect(tools.getByRole("link", { name })).toBeVisible();
  await expect(learning.getByRole("link", { name: "復習" })).toHaveCount(0);
  await expect(learning.getByRole("link", { name: "タイムアタック", exact: true })).toHaveCount(0);
});

test("tsume modes contain only tsume-specific navigation", async ({ page }) => {
  for (const [path, current] of [["/tsume", "問題を解く"], ["/time-attack", "タイムアタック"]]) {
    await page.goto(path);
    const modes = page.getByRole("navigation", { name: "詰め将棋の学習モード" });
    for (const name of ["問題を解く", "タイムアタック"])
      await expect(modes.getByRole("link", { name, exact: true })).toBeVisible();
    await expect(modes.getByRole("link", { name: "復習", exact: true })).toHaveCount(0);
    await expect(modes.getByRole("link", { name: current, exact: true })).toHaveAttribute("aria-current", "page");
  }
  await page.goto("/review");
  await expect(page.getByRole("navigation", { name: "詰め将棋の学習モード" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /間違えた問題/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /お気に入り/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /次の一手/ })).toBeVisible();
});

test("desktop navigation exposes cross-cutting tools without duplicating them in その他", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "メインナビゲーション" });
  await expect(nav.getByRole("link", { name: "学習記録" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "問題作成", exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "作成", exact: true })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "復習", exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "タイムアタック", exact: true })).toHaveCount(0);
  await nav.getByRole("link", { name: "問題作成", exact: true }).click();
  await expect(page).toHaveURL(/\/problem-editor$/);
  await expect(page.getByRole("heading", { name: "詰め将棋問題作成" })).toBeVisible();
  await page.goto("/more");
  for (const name of ["復習", "学習記録", "問題作成"])
    await expect(page.getByTestId("more-page").getByRole("heading", { name, exact: true, includeHidden: true })).toBeHidden();
  for (const name of ["設定", "データ出典"])
    await expect(page.getByTestId("more-page").getByRole("link", { name })).toBeVisible();
  await expect(page.getByTestId("more-page").getByRole("link", { name: "タイムアタック", exact: true })).toHaveCount(0);
});

test("appearance settings are reachable, independent, persistent, resettable, and responsive", async ({ page }) => {
  await page.goto("/more");
  await page.getByRole("link", { name: /設定/ }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { name: "表示設定" })).toBeVisible();
  const attributions = page.getByRole("region", { name: "テーマの出典・ライセンス" });
  await expect(attributions.getByRole("link", { name: "Shogi Images" })).toBeVisible();
  await expect(attributions.getByRole("link", { name: "CC0 1.0" })).toBeVisible();
  await expect(attributions.getByRole("link", { name: "データ出典・ライセンス" })).toHaveAttribute("href", "/licenses");

  await page.getByRole("radio", { name: "Shogi Images 一文字駒", exact: true }).check();
  await expect(page.locator(".appearance-preview .preview-board").locator('img[src*="pieces/shogi-images-hitomoji"]')).toHaveCount(5);
  await expect(page.locator(".appearance-preview .preview-hand").locator('img[src*="pieces/shogi-images-hitomoji"]')).toHaveCount(2);
  await expect(page.locator(".appearance-preview [data-board-theme='board-standard']")).toBeVisible();
  await page.getByRole("radio", { name: /Shogi Images 盤 - 木材（明）/ }).check();
  await expect(page.locator(".appearance-preview [data-board-theme='shogi-images-light']")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("radio", { name: /^Shogi Images 一文字駒(?:\s+選択中)?$/ })).toBeChecked();
  await expect(page.getByRole("radio", { name: /Shogi Images 盤 - 木材（明）/ })).toBeChecked();

  await page.getByRole("button", { name: "標準設定に戻す" }).click();
  await expect(page.getByRole("radio", { name: /標準（文字）/ })).toBeChecked();
  await expect(page.getByRole("radio", { name: /標準盤/ })).toBeChecked();
  await expect(page.getByText("標準設定に戻しました")).toHaveCount(1);

  await page.setViewportSize({ width: 360, height: 740 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("appearance storage corruption and write failures remain non-fatal", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("shogi.appearance.v1", "{broken"));
  await page.goto("/settings");
  await expect(page.getByRole("radio", { name: /標準（文字）/ })).toBeChecked();
  await expect(page.getByRole("radio", { name: /標準盤/ })).toBeChecked();

  await page.evaluate(() => {
    Object.defineProperty(Storage.prototype, "setItem", { configurable: true, value: () => { throw new DOMException("disabled", "QuotaExceededError"); } });
  });
  await page.getByRole("radio", { name: "Shogi Images 一文字駒", exact: true }).check();
  await expect(page.getByRole("radio", { name: /^Shogi Images 一文字駒(?:\s+選択中)?$/ })).toBeChecked();
  await expect(page.getByRole("alert")).toContainText("保存できませんでした");
});

test("desktop nav separates 定跡学習 and 次の一手 with current-page state", async ({ page }) => {
  await page.goto("/openings");
  const nav = page.getByRole("navigation", { name: "メインナビゲーション" });
  const openingsLink = nav.getByRole("link", { name: "定跡学習" });
  const nextMoveLink = nav.getByRole("link", { name: "次の一手" });
  await expect(openingsLink).toBeVisible();
  await expect(nextMoveLink).toBeVisible();
  await expect(openingsLink).toHaveAttribute("aria-current", "page");
  await expect(nextMoveLink).not.toHaveAttribute("aria-current", "page");
  // ページ内モード切替UIは廃止され、定跡手順の内容が直接表示される
  await expect(page.getByTestId("opening-mode-switch")).toHaveCount(0);
  await expect(page.getByTestId("opening-line-study-section")).toBeVisible();

  // 個別の定跡学習画面(/openings/:id)でも「定跡学習」が現在位置になる
  await showOpeningTypeLines(page, "棒銀");
  await openingLineByExactTitle(page, "棒銀").getByRole("link", { name: "学習する" }).click();
  await expect(page.getByTestId("opening-study-page")).toBeVisible();
  await expect(openingsLink).toHaveAttribute("aria-current", "page");
  await expect(nextMoveLink).not.toHaveAttribute("aria-current", "page");
});

test("tsume page plays an existing one-move problem and shows wrong/correct feedback", async ({ page, request }) => {
  const title = `${E2E_PREFIX} tsume feedback ${Date.now()}`;
  const problem = await createE2eProblem(request, title);

  await showE2eOneMoveProblems(page);
  await page.getByTestId(`problem-select-${problem.id}`).click();
  await expect(page.getByTestId("shogi-board")).toBeVisible();

  await playGoldDrop(page, "42");
  await expect(page.getByTestId("tsume-feedback")).toContainText("不正解");
  await page.getByRole("button", { name: "もう一度" }).click();
  await dragGoldDrop(page, "52");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");
});

test("Shogi Images theme renders assets, highlights, flip, and interactions", async ({ page, request }, testInfo) => {
  const title = `${E2E_PREFIX} image theme ${Date.now()}`;
  const problem = await createE2eProblem(request, title, {
    initial_sfen: "4k4/9/5+B3/9/9/9/9/9/4K4 b G 1",
  });
  await useShogiImagesTheme(page);
  await page.goto("/tsume");
  await page.getByTestId("difficulty-filter").getByRole("button", { name: "1手詰", exact: true }).click();
  await page.getByRole("combobox").selectOption("e2e");
  await page.getByTestId(`problem-select-${problem.id}`).click();

  const board = page.getByTestId("shogi-board");
  const surface = board.locator('[data-board-theme="shogi-images-light"]');
  await expect(surface.getByRole("gridcell")).toHaveCount(81);
  await expect(surface).toHaveCSS("background-image", /boards\/shogi-images-light\/board\.png/);
  await expect(surface).toHaveCSS("background-repeat", "no-repeat");
  await expect(surface.locator('img[src*="black/horse.png"]')).toHaveCount(1);
  await expect(surface.locator('img[src*="black/ou.png"]')).toHaveCount(1);
  await expect(surface.locator('img[src*="white/gyoku.png"]')).toHaveCount(1);
  const gold = board.getByRole("button", { name: /持ち駒 金/ });
  const goldImage = gold.locator('img[src*="black/gold.png"]');
  await expect(goldImage).toHaveCount(1);
  await expect(goldImage).toHaveClass(/piece-image-hand/);
  await expectImageConstrainedToContainer(goldImage, gold, surface.getByRole("gridcell").first());

  await gold.click();
  const target = surface.locator('[data-square="52"]');
  await expect(target).toHaveClass(/target/);
  await expect(target).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await gold.press("Escape");
  await expect(target).not.toHaveClass(/target/);
  await gold.focus();
  await gold.press("Enter");
  await target.click();
  await expect(target).toHaveClass(/last-move/);
  await expect(target).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");
  await page.getByRole("button", { name: "もう一度" }).click();
  await dragGoldDrop(page, "52");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");

  await page.getByRole("button", { name: "盤面反転" }).click();
  await expect(surface.locator('img[src*="white/ou.png"]')).toHaveCount(1);
  await expect(surface.locator('img[src*="black/gyoku.png"]')).toHaveCount(1);
  const cells = await surface.getByRole("gridcell").evaluateAll((items) => items.map((item) => {
    const rect = item.getBoundingClientRect();
    return [rect.width, rect.height];
  }));
  expect(new Set(cells.map(([width, height]) => `${width}:${height}`)).size).toBe(1);
  await testInfo.attach("shogi-images-board.png", { body: await board.screenshot(), contentType: "image/png" });
});

test("Shogi Images board retains selected and both last-move highlights", async ({ page }) => {
  await useShogiImagesTheme(page);
  await page.goto("/openings/static-rook-rapid-attack");
  const surface = page.getByTestId("shogi-board").locator('[data-board-theme="shogi-images-light"]');
  const from = surface.locator('[data-square="77"]');
  const to = surface.locator('[data-square="76"]');
  await from.click();
  await expect(from).toHaveClass(/selected/);
  await expect(from).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await to.click();
  await expect(from).toHaveClass(/last-move-from/);
  await expect(to).toHaveClass(/last-move/);
  await expect(from).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(to).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
});

test("Shogi Images 404 falls back to text and keeps the board operable", async ({ page, request }) => {
  const problem = await createE2eProblem(request, `${E2E_PREFIX} image fallback ${Date.now()}`);
  await page.route("**/assets/shogi/**", (route) => route.fulfill({ status: 404 }));
  await useShogiImagesTheme(page);
  await page.goto("/tsume");
  await page.getByTestId("difficulty-filter").getByRole("button", { name: "1手詰", exact: true }).click();
  await page.getByRole("combobox").selectOption("e2e");
  await page.getByTestId(`problem-select-${problem.id}`).click();

  const board = page.getByTestId("shogi-board");
  const surface = board.locator('[data-board-theme="shogi-images-light"]');
  await expect(board.getByRole("button", { name: /持ち駒 金/ })).toContainText("金");
  await expect(surface).toHaveCSS("background-color", "rgb(220, 179, 92)");
  await expect(surface.locator('[data-square="52"]')).toHaveCSS("border-style", "solid");
  await dragGoldDrop(page, "52");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");
});

test("problem editor renders the board editor and required fields", async ({ page }) => {
  await page.goto("/problem-editor");
  await expect(page.getByRole("heading", { name: "詰め将棋問題作成" })).toBeVisible();
  await expect(page.getByTestId("editor-board")).toBeVisible();
  await expect(page.getByRole("link", { name: "＋ 新規作成" })).toBeVisible();
  for (const label of ["title", "mate_length", "difficulty", "tags", "solution_moves", "opponent_moves", "explanation"]) {
    await expect(page.getByLabel(label)).toBeVisible();
  }
  await expect(page.getByRole("button", { name: "現在の局面からSFEN生成" })).toBeVisible();
  await expect(page.getByRole("button", { name: "SFENを盤面へ反映" })).toBeVisible();
  await expect(page.getByRole("button", { name: "この局面から手順記録を開始" })).toBeVisible();
});

test("Shogi Images theme renders EditorBoard and SolutionRecorder with all-gyoku policy", async ({ page }) => {
  await useShogiImagesTheme(page);
  await page.goto("/problem-editor");
  const editor = page.getByTestId("editor-board");
  await expect(editor.locator('[data-board-theme="shogi-images-light"]')).toHaveCount(1);
  const paletteButton = editor.getByRole("button", { name: "先手の玉を配置" });
  const paletteImage = paletteButton.locator('img[src*="black/gyoku.png"]');
  await expect(paletteImage).toHaveCount(1);
  await expect(paletteImage).toHaveClass(/piece-image-plain/);
  await expectImageConstrainedToContainer(
    paletteImage,
    paletteButton,
    editor.locator(".editor-grid .board-cell").first(),
  );
  await expect(editor.getByRole("button", { name: "後手の玉を配置" }).locator('img[src*="white/gyoku.png"]')).toHaveCount(1);

  await page.getByLabel("SFEN").fill(ONE_MOVE_SFEN);
  await page.getByRole("button", { name: "SFENを盤面へ反映" }).click();
  await page.getByRole("button", { name: "この局面から手順記録を開始" }).click();
  const recorder = page.getByTestId("solution-recorder");
  await expect(recorder.locator('[data-board-theme="shogi-images-light"]')).toHaveCount(1);
  await expect(recorder.locator('img[src*="white/gyoku.png"]')).toHaveCount(1);
});

test("board editor can generate and restore SFEN", async ({ page }) => {
  await page.goto("/problem-editor");
  const editor = page.getByTestId("editor-board");
  await editor.getByRole("button", { name: "玉" }).first().click();
  await page.getByTestId("editor-square-5-1").click();
  await expect(page.getByTestId("editor-square-5-1")).toHaveText("玉");
  await editor.getByRole("button", { name: "角" }).first().click();
  await page.getByTestId("editor-square-4-3").click();
  await editor.getByRole("button", { name: "移動" }).click();
  await page.getByTestId("editor-square-4-3").click();
  await page.getByTestId("editor-square-4-4").click();
  await expect(page.getByTestId("editor-square-4-3")).toHaveText("");
  await expect(page.getByTestId("editor-square-4-4")).toHaveText("角");
  await page.getByRole("button", { name: "現在の局面からSFEN生成" }).click();
  const sfen = page.getByLabel("SFEN");
  await expect(sfen).toHaveValue(/k|K|B/);
  const generated = await sfen.inputValue();
  await sfen.fill("9/9/9/9/9/9/9/9/9 b - 1");
  await page.getByRole("button", { name: "SFENを盤面へ反映" }).click();
  await sfen.fill(generated);
  await page.getByRole("button", { name: "SFENを盤面へ反映" }).click();
  await expect(page.getByTestId("editor-square-5-1")).toContainText(/玉|王/);
});

test("solution recorder writes, undoes, and resets USI moves", async ({ page }) => {
  await page.goto("/problem-editor");
  await page.getByLabel("SFEN").fill(ONE_MOVE_SFEN);
  await page.getByRole("button", { name: "SFENを盤面へ反映" }).click();
  await page.getByRole("button", { name: "この局面から手順記録を開始" }).click();

  const recorder = page.getByTestId("solution-recorder");
  await expect(page.getByTestId("recorder-square-5-1")).toHaveText("玉");
  await recorder.getByRole("button", { name: "金" }).click();
  await page.getByTestId("recorder-square-5-2").click();
  await expect(page.getByLabel("solution_moves")).toHaveValue(ONE_MOVE_SOLUTION);
  await expect(page.getByLabel("opponent_moves")).toHaveValue("");

  await page.getByRole("button", { name: "1手戻す" }).click();
  await expect(page.getByLabel("solution_moves")).toHaveValue("");

  await recorder.getByRole("button", { name: "金" }).click();
  await page.getByTestId("recorder-square-5-2").click();
  await page.getByRole("button", { name: "記録リセット" }).click();
  await expect(page.getByLabel("solution_moves")).toHaveValue("");

  await page.getByTestId("recorder-square-4-3").click();
  await page.getByTestId("recorder-square-4-2").click();
  await expect(page.getByLabel("solution_moves")).toHaveValue("4c4b");
});

test("creates a new problem, plays it, edits it, and deletes it", async ({ page }) => {
  const title = `${E2E_PREFIX} one move mate ${Date.now()}`;
  await page.goto("/problem-editor");
  await page.getByLabel("title").fill(title);
  await page.getByLabel("SFEN").fill(ONE_MOVE_SFEN);
  await page.getByRole("button", { name: "SFENを盤面へ反映" }).click();
  await page.getByLabel("mate_length").fill("1");
  await page.getByLabel("difficulty").fill("1");
  await page.getByLabel("tags").fill("e2e");
  await page.getByLabel("solution_moves").fill(ONE_MOVE_SOLUTION);
  await page.getByLabel("explanation").fill("created from E2E");
  await page.getByRole("button", { name: "検証して保存" }).click();
  await expect(page.getByText("保存しました")).toBeVisible();

  await showE2eOneMoveProblems(page);
  const createdProblemItem = page.getByTestId("problem-item").filter({ hasText: title });
  await expect(createdProblemItem).toBeVisible();
  await createdProblemItem.getByRole("button").first().click();
  await playGoldDrop(page, "52");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");

  await page.getByTestId("problem-item").filter({ hasText: title }).getByRole("link", { name: "編集" }).click();
  const editedTitle = `${title} edited`;
  await page.getByLabel("title").fill(editedTitle);
  await page.getByLabel("explanation").fill("edited by E2E");
  await page.getByRole("button", { name: "検証して保存" }).click();
  await expect(page.getByText("保存しました")).toBeVisible();
  await expect(page.getByLabel("title")).toHaveValue(editedTitle);

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator(".problem-item.active").getByRole("button", { name: "削除" }).click();
  await page.getByRole("link", { name: "詰め将棋" }).click();
  await expect(page.getByText(editedTitle)).toHaveCount(0);
  await page.getByRole("link", { name: "学習記録" }).click();
  await expect(page.getByRole("heading", { name: "学習記録", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "復習" }).click();
  await expect(page.getByTestId("review-page")).toContainText("復習");
});



test("opening page uses filters to find opening types and distinguishes availability", async ({ page }) => {
  await page.goto("/openings");
  await expect(page.getByTestId("opening-category-list")).toContainText("相居飛車");
  await expect(page.getByTestId("opening-category-list")).toContainText("対抗型");
  await expect(page.getByTestId("opening-type-list")).toContainText("矢倉");
  await expect(page.getByTestId("opening-type-list")).toContainText("四間飛車");
  await expect(page.getByLabel("データ出典")).toContainText("CC BY-SA");

  await page.getByTestId("opening-category-card").filter({ hasText: "奇襲・B級戦法" }).click();
  await expect(page.getByTestId("opening-type-list")).toContainText("嬉野流");
  await expect(openingTypeCardByExactTitle(page, "嬉野流")).toContainText(/つの手順を学べます|定跡手順は準備中/);
  await expect(page.getByRole("heading", { name: "学習できる定跡ライン" })).toHaveCount(0);
});


test("major opening types show related playable lines", async ({ page }) => {
  await page.goto("/openings");

  for (const openingName of allPlayableOpenings) {
    const card = openingTypeCardByExactTitle(page, openingName);
    await expect(card).toHaveCount(1);
    await expect(card.getByRole("button", { name: "手順を見る" })).toBeVisible();
    await expect(card).toContainText("つの手順を学べます");
  }
});

test("opening type cards expose imported and static lines while keeping empty types visible", async ({ page }) => {
  await page.goto("/openings");
  await expect(openingTypeCardByExactTitle(page, "未分類")).toContainText("定跡手順は準備中");

  await showOpeningTypeLines(page, "矢倉");
  const staticLine = openingLineByExactTitle(page, "矢倉の出だし");
  await expect(staticLine).toBeVisible();
  await staticLine.getByRole("link", { name: "学習する" }).click();
  await expect(page).toHaveURL(/\/openings\/yagura-foundation$/);
  await expect(page.getByTestId("opening-study-page")).toBeVisible();
});

test("opening tag is an auxiliary filter for opening types", async ({ page }) => {
  await page.goto("/openings");
  await page.getByLabel("タグでさらに絞り込む").selectOption("bougin");
  await expect(openingTypeCardByExactTitle(page, "棒銀")).toBeVisible();
  await expect(openingTypeCardByExactTitle(page, "四間飛車")).toHaveCount(0);
});

test("opening catalog failure keeps static study lines reachable", async ({ page }) => {
  await page.route("**/api/opening-types", (route) => route.fulfill({ status: 503, json: { detail: "catalog unavailable" } }));
  await page.goto("/openings");

  await expect(page.getByRole("alert")).toContainText("戦型一覧の取得に失敗しました");
  const fallback = page.getByTestId("opening-static-fallback");
  await expect(fallback.getByTestId("opening-static-fallback-card")).toHaveCount(3);
  await expect(page.getByTestId("opening-type-list")).toHaveCount(0);
  await fallback.getByTestId("opening-static-fallback-card").filter({ hasText: "矢倉の出だし" }).getByRole("link", { name: "学習する" }).click();
  await expect(page).toHaveURL(/\/openings\/yagura-foundation$/);
  await expect(page.getByTestId("opening-study-page")).toBeVisible();
});

test("tag catalog failure does not hide opening types or duplicate static fallback", async ({ page }) => {
  await page.route("**/api/openings/tags", (route) => route.fulfill({ status: 503, json: { detail: "tags unavailable" } }));
  await page.goto("/openings");

  await expect(page.getByRole("alert")).toContainText("タグの取得に失敗しました");
  await expect(page.getByTestId("opening-type-list")).toContainText("矢倉");
  await expect(page.getByTestId("opening-static-fallback")).toHaveCount(0);
  await showOpeningTypeLines(page, "矢倉");
  await expect(openingLineByExactTitle(page, "矢倉の出だし")).toHaveCount(1);
});

test("opening type catalog clears only its error after a successful retry", async ({ page }) => {
  await page.route("**/api/opening-types**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.has("category_id")) {
      await route.fulfill({ status: 503, json: { detail: "temporary catalog error" } });
    } else {
      await route.fallback();
    }
  });
  await page.goto("/openings");
  await expect(page.getByTestId("opening-type-list")).toContainText("矢倉");

  await page.getByTestId("opening-category-card").filter({ hasText: "相居飛車" }).click();
  await expect(page.getByRole("alert")).toContainText("戦型一覧の取得に失敗しました");
  await expect(page.getByTestId("opening-static-fallback")).toBeVisible();

  await page.getByRole("group", { name: "カテゴリで絞り込む" }).getByRole("button", { name: "すべて" }).click();
  await expect(page.getByTestId("opening-type-list")).toContainText("矢倉");
  await expect(page.getByTestId("opening-static-fallback")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("closing type lines clears only the stale type-line error", async ({ page }) => {
  await page.route("**/api/openings/tags", (route) => route.fulfill({ status: 503, json: { detail: "tags unavailable" } }));
  await page.route("**/api/opening-types/*/lines", (route) => route.fulfill({ status: 503, json: { detail: "lines unavailable" } }));
  await page.goto("/openings");

  await showOpeningTypeLines(page, "矢倉");
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("タグの取得に失敗しました");
  await expect(alert).toContainText("学習手順の取得に失敗しました");

  await openingTypeCardByExactTitle(page, "矢倉").getByRole("button", { name: "手順を閉じる" }).click();
  await expect(alert).toContainText("タグの取得に失敗しました");
  await expect(alert).not.toContainText("学習手順の取得に失敗しました");
});

test("same-tag refetch failure does not revive an earlier successful result", async ({ page }) => {
  let failBougin = false;
  let failUntagged = false;
  await page.route("**/api/openings**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname !== "/api/openings") return route.fallback();
    const tag = url.searchParams.get("tag");
    if (tag === "bougin" && failBougin) return route.fulfill({ status: 503, json: { detail: "tagged lines unavailable" } });
    if (!tag && failUntagged) return route.fulfill({ status: 503, json: { detail: "untagged lines unavailable" } });
    return route.fallback();
  });
  await page.goto("/openings");
  await expect(page.getByTestId("opening-type-card")).not.toHaveCount(0);

  const tagFilter = page.getByLabel("タグでさらに絞り込む");
  await tagFilter.selectOption("bougin");
  await expect(openingTypeCardByExactTitle(page, "棒銀")).toBeVisible();

  failUntagged = true;
  await tagFilter.selectOption("");
  await expect(page.getByRole("alert")).toContainText("学習手順の取得に失敗しました");
  failUntagged = false;
  failBougin = true;
  await tagFilter.selectOption("bougin");
  await expect(page.getByRole("alert")).toContainText("学習手順の取得に失敗しました");
  await expect(page.getByTestId("opening-type-card")).toHaveCount(0);
  await expect(page.getByTestId("opening-types-empty")).toHaveCount(0);

  failBougin = false;
  await tagFilter.selectOption("");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await tagFilter.selectOption("bougin");
  await expect(openingTypeCardByExactTitle(page, "棒銀")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});


test("opening list navigates to a seeded opening study page", async ({ page }) => {
  await page.goto("/openings");
  await expect(page.getByRole("heading", { name: "定跡学習" })).toBeVisible();
  await showOpeningTypeLines(page, "棒銀");
  const bouginLine = openingLineByExactTitle(page, "棒銀");
  await expect(bouginLine).toHaveCount(1);
  await bouginLine.getByRole("link", { name: "学習する" }).click();
  await expect(page.getByTestId("opening-study-page")).toBeVisible();
  await expect(page.getByTestId("opening-current-move")).toContainText("7g7f");
});

test("opening study shows book candidates for the current SFEN", async ({ page }) => {
  const requestedSfens: string[] = [];
  await page.route("**/api/book/candidates**", async (route) => {
    const url = new URL(route.request().url());
    const sfen = url.searchParams.get("sfen") ?? "";
    requestedSfens.push(sfen);
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        sfen,
        found: true,
        candidates: [{
          move_usi: sfen.includes("2P6") ? "3c3d" : "7g7f",
          rank: 1,
          score: 30,
          depth: 1,
          pv: "7g7f 3c3d",
          raw: "sample candidate",
          source_id: 1,
          source_name: "Sample YaneuraOu Book",
          source_version: "fixture",
          license: "MIT License",
          license_name: "MIT License",
          source_url: "https://example.test/book",
          copyright_notice: "Copyright sample",
        }],
      }),
    });
  });

  await page.goto("/openings/static-rook-rapid-attack");
  await expect(page.getByTestId("book-candidates")).toContainText("7g7f");
  await expect(page.getByTestId("book-candidates")).toContainText("Sample YaneuraOu Book");
  await expect(page.getByTestId("book-candidates")).toContainText("MIT License");

  const board = page.getByTestId("shogi-board");
  await board.locator('[data-square="77"]').click();
  await board.locator('[data-square="76"]').click();
  await expect(page.getByTestId("book-candidates")).toContainText("3c3d");
  expect(requestedSfens.length).toBeGreaterThanOrEqual(2);
});

test("opening study accepts correct moves and supports wrong feedback, undo, and reset", async ({ page }) => {
  await page.goto("/openings/static-rook-rapid-attack");
  const board = page.getByTestId("shogi-board");

  await board.locator('[data-square="27"]').click();
  await board.locator('[data-square="26"]').click();
  await expect(page.getByTestId("opening-feedback")).toContainText("不正解");
  await expect(page.getByTestId("opening-current-move")).toContainText("▲7六歩");

  await board.locator('[data-square="77"]').click();
  await board.locator('[data-square="76"]').click();
  await expect(page.getByTestId("opening-feedback")).toContainText("正解");
  await expect(page.getByTestId("opening-current-move")).toContainText("△3四歩");
  await expect(page.getByText("7g7f")).toBeVisible();

  await page.getByRole("button", { name: "一手戻る" }).click();
  await expect(page.getByTestId("opening-current-move")).toContainText("▲7六歩");
  await expect(page.getByText("まだ指し手はありません")).toBeVisible();

  await board.locator('[data-square="77"]').click();
  await board.locator('[data-square="76"]').click();
  await page.getByRole("button", { name: "最初に戻る" }).click();
  await expect(page.getByTestId("opening-current-move")).toContainText("▲7六歩");
  await expect(page.getByText("まだ指し手はありません")).toBeVisible();
});

test("time attack setup starts and displays a problem", async ({ page }) => {
  await page.goto("/time-attack");
  await expect(page.getByText("難易度:")).toBeVisible();
  await expect(page.getByText("問題数:")).toBeVisible();
  await page.getByRole("button", { name: "5問" }).click();
  await page.getByRole("button", { name: "スタート" }).click();
  await expect(page.getByText(/第 1 \/ 5 問/)).toBeVisible();
  await expect(page.getByTestId("shogi-board")).toBeVisible();
});

test("time attack applies image appearance without changing its session", async ({ page }) => {
  await useShogiImagesTheme(page);
  await page.goto("/time-attack");
  await page.getByRole("button", { name: "5問" }).click();
  await page.getByRole("button", { name: "スタート" }).click();
  const board = page.getByTestId("shogi-board");
  await expect(board.getByRole("grid")).toHaveAttribute("data-board-theme", "shogi-images-light");
  await expect(board.getByRole("gridcell")).toHaveCount(81);
  await expect(board.locator('img[src*="pieces/shogi-images-hitomoji"]')).not.toHaveCount(0);
  await expect(page.getByText(/第 1 \/ 5 問/)).toBeVisible();
});

test("seeded opening replay controls move forward, backward, reset, and finish", async ({ page }) => {
  await page.goto("/openings");
  await showOpeningTypeLines(page, "中飛車");
  await openingLineByExactTitle(page, "中飛車").getByRole("link", { name: "学習する" }).click();
  await expect(page.getByTestId("opening-current-move")).toContainText("7g7f");

  const replayButtons = page.locator(".opening-replay-controls button");
  await expect(replayButtons).toHaveText(["最初に戻る", "一手戻る", "一手進む", "最後まで進む", "ヒント"]);
  await expect(page.getByRole("button", { name: "最初に戻る" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "一手戻る" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "一手進む" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "最後まで進む" })).toBeEnabled();

  await page.getByRole("button", { name: "一手進む" }).click();
  await expect(page.getByTestId("opening-current-move")).toContainText("3c3d");
  await page.getByRole("button", { name: "一手戻る" }).click();
  await expect(page.getByTestId("opening-current-move")).toContainText("7g7f");
  await page.getByRole("button", { name: "一手進む" }).click();
  await page.getByRole("button", { name: "最初に戻る" }).click();
  await expect(page.getByText("まだ指し手はありません")).toBeVisible();
  await page.getByRole("button", { name: "最後まで進む" }).click();
  await expect(page.getByTestId("opening-feedback")).toContainText("この定跡手順を完了しました。Wikipediaで確認できる手順はここまでです。");
  await expect(page.getByRole("button", { name: "一手進む" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "最後まで進む" })).toBeDisabled();
});


test("licenses page renders data source and MIT License from API", async ({ page }) => {
  await page.route("**/api/licenses", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        tsume_sources: [],
        book_sources: [{
          id: 1,
          name: "Sample YaneuraOu Book",
          version: "fixture",
          source_url: "https://example.test/book",
          license_name: "MIT License",
          license_text: "MIT License\n\nPermission is hereby granted",
          copyright_notice: "Copyright sample",
          file_name: "yaneuraou_book_sample.db",
          file_sha256: "abc123",
          imported_at: "2026-01-01T00:00:00",
          position_count: 1,
          move_count: 2,
          note: "sample",
        }],
      }),
    });
  });
  await page.goto("/licenses");
  await expect(page.getByTestId("licenses-page")).toContainText("Sample YaneuraOu Book");
  await expect(page.getByTestId("licenses-page")).toContainText("MIT License");
});

test("tsume list stays usable with more than one thousand problems", async ({ page }) => {
  const makeProblem = (id: number) => ({
    id,
    title: id <= 8 ? `sample ${id}` : `[tanuki] 1手詰 #${id - 8}`,
    initial_sfen: ONE_MOVE_SFEN,
    mate_length: 1,
    solution_moves: [ONE_MOVE_SOLUTION],
    opponent_moves: [],
    difficulty: 1,
    tags: id > 1000 ? ["1手詰", "unloaded-only"] : ["1手詰", "tanuki-tsume-shogi"],
    explanation: "E2E large list problem",
    is_favorite: false,
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    source_name: id <= 8 ? "" : "tokuhirom/tanuki-tsume-shogi",
    source_url: "",
    source_license: "",
    source_copyright: "",
    external_id: String(id),
    source_hash: `hash-${id}`,
    source_metadata: {},
    stats: { correct_count: id % 3, wrong_count: id % 2, last_answered_at: null, avg_elapsed_ms: null },
  });
  const problems = Array.from({ length: 1075 }, (_, index) => makeProblem(index + 1));
  const requestedUrls: string[] = [];

  await page.route("**/api/tsume-problems**", async (route) => {
    const url = new URL(route.request().url());
    requestedUrls.push(url.toString());
    if (url.pathname === "/api/tsume-problems/tags") {
      const mateLength = url.searchParams.get("mate_length");
      const scopedProblems = mateLength ? problems.filter((p) => p.mate_length === Number(mateLength)) : problems;
      const counts = new Map<string, number>();
      for (const problem of scopedProblems) {
        for (const tag of problem.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
      }
      await route.fulfill({
        json: Array.from(counts, ([tag, count]) => ({ tag, count })).sort((a, b) => a.tag.localeCompare(b.tag)),
      });
      return;
    }
    const idMatch = url.pathname.match(/\/api\/tsume-problems\/(\d+)$/);
    if (idMatch) {
      const problem = problems.find((p) => p.id === Number(idMatch[1]));
      await route.fulfill({ status: problem ? 200 : 404, json: problem ?? { detail: "not found" } });
      return;
    }
    const mateLength = url.searchParams.get("mate_length");
    const tag = url.searchParams.get("tag");
    const limit = Number(url.searchParams.get("limit") ?? problems.length);
    const offset = Number(url.searchParams.get("offset") ?? 0);
    let list = problems;
    if (mateLength) list = list.filter((p) => p.mate_length === Number(mateLength));
    if (tag) list = list.filter((p) => p.tags.includes(tag));
    await route.fulfill({ json: list.slice(offset, offset + limit) });
  });

  await page.goto("/tsume?problem=9");
  await expect(page.getByTestId("problem-item")).toHaveCount(50);
  await expect(page.getByTestId("problem-list")).toContainText("[tanuki] 1手詰 #1");
  await expect(page.getByTestId("problem-list")).toContainText("1手詰 / 正解");
  await expect(page.getByTestId("problem-list")).toContainText("編集");
  await expect(page.getByTestId("problem-list")).toContainText("出典: tokuhirom/tanuki-tsume-shogi");
  await expect(page.getByRole("combobox")).toContainText("tanuki-tsume-shogi（1000）");
  await expect(page.getByRole("combobox")).toContainText("unloaded-only（75）");
  await expect(page.getByTestId("shogi-board")).toBeVisible();
  await expect(page.locator(".problem-item.active")).toContainText("[tanuki] 1手詰 #1");

  await page.getByTestId("problem-select-10").click();
  await expect(page).toHaveURL(/problem=10/);
  await expect(page.locator(".problem-item.active")).toContainText("[tanuki] 1手詰 #2");
  await expect(page.getByTestId("tsume-feedback")).toContainText("1手詰");

  await page.getByRole("button", { name: "もっと読み込む" }).click();
  await expect(page.getByTestId("problem-item")).toHaveCount(100);

  await page.getByRole("combobox").selectOption("unloaded-only");
  await expect(page.getByRole("combobox")).toHaveValue("unloaded-only");
  await expect(page.getByTestId("problem-item")).toHaveCount(50);
  expect(requestedUrls.some((url) => url.includes("tag=unloaded-only") && url.includes("offset=0"))).toBeTruthy();
  expect(requestedUrls.some((url) => url.includes("tag=unloaded-only%EF%BC%8875%EF%BC%89"))).toBeFalsy();
  await page.getByRole("button", { name: "もっと読み込む" }).click();
  await expect(page.getByTestId("problem-item")).toHaveCount(75);
  expect(requestedUrls.some((url) => url.includes("tag=unloaded-only") && url.includes("offset=50"))).toBeTruthy();
  await page.getByTestId("difficulty-filter").getByRole("button", { name: "1手詰", exact: true }).click();
  await expect(page.getByRole("combobox")).toContainText("1手詰（1075）");
  expect(requestedUrls.some((url) => url.includes("/api/tsume-problems/tags?mate_length=1"))).toBeTruthy();
  expect(requestedUrls.some((url) => url.includes("mate_length=1") && url.includes("tag=unloaded-only") && url.includes("offset=0"))).toBeTruthy();
  expect(requestedUrls.some((url) => url.includes("limit=50"))).toBeTruthy();
  expect(requestedUrls.some((url) => url.includes("offset=50"))).toBeTruthy();
});

// ---- UX/UI 改修分の追加テスト ----

// 成りが任意になる1手詰(飛車が 1b→5b で成り/不成どちらでも詰み)
const PROMOTION_SFEN = "3lkl3/8R/5S3/9/9/9/9/9/9 b - 1";
const PROMOTION_SOLUTION = "1b5b+";

test("board shows turn indicator and supports keyboard play with Escape cancel", async ({ page, request }) => {
  const problem = await createE2eProblem(request, `${E2E_PREFIX} keyboard ${Date.now()}`);
  await showE2eOneMoveProblems(page);
  await page.getByTestId(`problem-select-${problem.id}`).click();
  const board = page.getByTestId("shogi-board");
  await expect(board).toBeVisible();
  await expect(page.getByTestId("turn-indicator")).toContainText("▲先手");
  await expect(board.getByRole("grid", { name: "将棋盤" })).toHaveCount(1);
  await expect(board.getByRole("row")).toHaveCount(9);
  const cells = board.getByRole("gridcell");
  await expect(cells).toHaveCount(81);
  await expect(board.locator('[role="gridcell"][data-square]')).toHaveCount(81);
  expect(new Set(await cells.evaluateAll((items) => items.map((item) => item.getAttribute("data-square")))).size).toBe(81);
  await expect(board.locator('[role="gridcell"][tabindex="0"]')).toHaveCount(1);
  await expect(board.locator('[role="gridcell"][tabindex="-1"]')).toHaveCount(80);

  // Enter キーで持ち駒の金を選択できる
  const gold = board.getByRole("button", { name: "金" });
  await gold.press("Enter");
  await expect(gold).toHaveAttribute("aria-pressed", "true");
  await expect(board.locator(".hand-piece.selected")).toHaveCount(1);
  await expect(board.locator(".board-cell.target")).not.toHaveCount(0);

  // 持ち駒ボタンにフォーカスが残ったままでも Escape で選択解除できる
  await gold.press("Escape");
  await expect(gold).toHaveAttribute("aria-pressed", "false");
  await expect(board.locator(".board-cell.target")).toHaveCount(0);

  // Space で再選択し、矢印キーで 5五 → 5二 へ移動してSpaceで着手する
  await gold.press("Space");
  await board.locator('[data-square="55"]').focus();
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Space");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");
});

test("promotion dialog is accessible and Escape cancels without playing a move", async ({ page, request }) => {
  const problem = await createE2eProblem(request, `${E2E_PREFIX} promotion ${Date.now()}`, {
    initial_sfen: PROMOTION_SFEN,
    solution_moves: [PROMOTION_SOLUTION],
  });
  await showE2eOneMoveProblems(page);
  await page.getByTestId(`problem-select-${problem.id}`).click();
  const board = page.getByTestId("shogi-board");
  await board.locator('[data-square="12"]').click();
  await board.locator('[data-square="52"]').click();

  const dialog = page.getByRole("dialog", { name: "成り選択" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "キャンセル" })).toBeVisible();

  // Escape はキャンセル扱いで手は指されない
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("まだ指し手はありません")).toBeVisible();

  await board.locator('[data-square="12"]').click();
  await board.locator('[data-square="52"]').click();
  await dialog.getByRole("button", { name: "成る", exact: true }).click();
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");
});

test("post-clear actions offer retry and next problem", async ({ page, request }) => {
  const stamp = Date.now();
  const first = await createE2eProblem(request, `${E2E_PREFIX} next A ${stamp}`);
  await createE2eProblem(request, `${E2E_PREFIX} next B ${stamp}`);
  await showE2eOneMoveProblems(page);
  await page.getByTestId(`problem-select-${first.id}`).click();
  await playGoldDrop(page, "52");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");

  const actions = page.getByTestId("post-clear-actions");
  await expect(actions).toBeVisible();
  await expect(actions.getByRole("button", { name: "もう一度" })).toBeVisible();
  await actions.getByRole("button", { name: "次の問題" }).click();
  await expect
    .poll(async () => new URL(page.url()).searchParams.get("problem"))
    .not.toBe(String(first.id));
  await expect(page.getByTestId("tsume-feedback")).toContainText("1手詰");
});

test.describe("mobile layout (360px)", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  test("bottom navigation shows primary items and その他 leads to secondary pages", async ({ page }) => {
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "メインナビゲーション" });
    for (const name of ["ホーム", "詰め将棋", "定跡", "次の一手", "その他"]) {
      await expect(nav.getByRole("link", { name, exact: true })).toBeVisible();
    }
    // 「復習」は下部ナビから「その他」へ移動し、副次項目は表示しない
    await expect(nav.getByRole("link", { name: "復習" })).toBeHidden();
    await expect(nav.getByRole("link", { name: "タイムアタック" })).toBeHidden();
    // 5項目でも横スクロールが発生しない
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await nav.getByRole("link", { name: "その他" }).click();
    await expect(page.getByTestId("more-page")).toBeVisible();
    for (const name of ["復習", "学習記録", "問題作成", "設定", "データ出典"]) {
      await expect(
        page.getByTestId("more-page").getByRole("heading", { name, exact: true }),
      ).toBeVisible();
    }
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.getByTestId("more-page").getByRole("link", { name: "問題作成" }).click();
    await expect(page).toHaveURL(/\/problem-editor$/);
    await expect(page.getByRole("heading", { name: "詰め将棋問題作成" })).toBeVisible();
  });

  test("tsume board and problem editor fit within the viewport width", async ({ page, request }) => {
    const problem = await createE2eProblem(request, `${E2E_PREFIX} mobile ${Date.now()}`);
    await showE2eOneMoveProblems(page);
    await page.getByTestId(`problem-select-${problem.id}`).click();
    await expect(page.getByTestId("shogi-board")).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);

    await page.goto("/problem-editor");
    await expect(page.getByTestId("editor-board")).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });

  test("image boards on next learning routes stay inside the viewport", async ({ page }) => {
    await useShogiImagesTheme(page);
    for (const path of ["/openings/static-rook-rapid-attack", "/time-attack"]) {
      await page.goto(path);
      if (path === "/time-attack") {
        await page.getByRole("button", { name: "5問" }).click();
        await page.getByRole("button", { name: "スタート" }).click();
      }
      const board = page.getByTestId("shogi-board");
      await expect(board.getByRole("grid")).toHaveAttribute("data-board-theme", "shogi-images-light");
      const box = await board.boundingBox();
      expect(box).not.toBeNull();
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(360);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  });
});
