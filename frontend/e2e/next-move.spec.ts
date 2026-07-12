import { expect, test, type Page } from "@playwright/test";

// 「次の一手」学習モードのE2E。
// E2E用DBには定跡DB由来の learning_samples が無いため、既存テストと同様に API をモックする。

const INITIAL_SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";

const SOURCE = {
  id: 1,
  name: "Sample YaneuraOu Book",
  version: "fixture",
  license_name: "MIT License",
  source_url: "https://example.test/book",
  copyright_notice: "Copyright sample",
};

function candidate(moveUsi: string, rank: number, score: number | null, pv: string | null) {
  return {
    move_usi: moveUsi,
    rank,
    score,
    depth: 30,
    pv,
    raw: null,
    source_id: SOURCE.id,
    source_name: SOURCE.name,
    source_version: SOURCE.version,
    license: SOURCE.license_name,
    license_name: SOURCE.license_name,
    source_url: SOURCE.source_url,
    copyright_notice: SOURCE.copyright_notice,
  };
}

function sample(
  id: number,
  openingKey: string,
  openingName: string,
  rank: number,
  candidates: ReturnType<typeof candidate>[],
  sfen: string = INITIAL_SFEN,
) {
  return {
    id,
    book_source_id: SOURCE.id,
    book_position_id: id,
    opening_key: openingKey,
    opening_name: openingName,
    sfen,
    sample_rank: rank,
    sample_reason: "test sample",
    created_at: "2026-01-01T00:00:00",
    source: SOURCE,
    candidates,
  };
}

// 後手番で、後手の歩が5七(白視点で成り任意の位置)から5八へ進める局面
const GOTE_PROMOTION_SFEN = "4k4/9/9/9/9/9/4p4/9/4K4 w - 1";

const SAMPLES = [
  sample(101, "bogin", "棒銀", 1, [
    candidate("7g7f", 1, 52, "7g7f 3c3d 2g2f"),
    candidate("2g2f", 2, 40, "2g2f 8c8d"),
    candidate("5g5f", 3, 21, null),
    candidate("9g9f", 4, -8, null),
  ]),
  sample(102, "bogin", "棒銀", 2, [candidate("7g7f", 1, 10, "7g7f")]),
  sample(201, "shikenbisha", "四間飛車", 3, [candidate("2h6h", 1, 15, "2h6h 8c8d")]),
  // 一覧(OPENINGS)には含めず、URL直接アクセスで後手番・成りの判定を確認する
  sample(
    301,
    "gote-sample",
    "後手番サンプル",
    1,
    [candidate("5g5h+", 1, 20, "5g5h+"), candidate("5g5h", 2, 5, null)],
    GOTE_PROMOTION_SFEN,
  ),
];

const OPENINGS = [
  { opening_key: "bogin", opening_name: "棒銀", sample_count: 2, first_rank: 1 },
  { opening_key: "shikenbisha", opening_name: "四間飛車", sample_count: 1, first_rank: 3 },
];

async function mockNextMoveApi(page: Page, requestedUrls?: string[]) {
  await page.route("**/api/learning-samples**", async (route) => {
    const url = new URL(route.request().url());
    requestedUrls?.push(url.pathname + url.search);
    if (url.pathname === "/api/learning-samples/openings") {
      await route.fulfill({ json: OPENINGS });
      return;
    }
    const idMatch = url.pathname.match(/\/api\/learning-samples\/(\d+)$/);
    if (idMatch) {
      const found = SAMPLES.find((s) => s.id === Number(idMatch[1]));
      await route.fulfill({ status: found ? 200 : 404, json: found ?? { detail: "learning sample not found" } });
      return;
    }
    const openingKey = url.searchParams.get("opening_key");
    const list = openingKey ? SAMPLES.filter((s) => s.opening_key === openingKey) : SAMPLES;
    await route.fulfill({ json: list });
  });
}

async function playMove(page: Page, from: string, to: string) {
  const board = page.getByTestId("shogi-board");
  await board.locator(`[data-square="${from}"]`).click();
  await board.locator(`[data-square="${to}"]`).click();
}

test.describe("次の一手学習モード", () => {
  test.beforeEach(async ({ page }) => {
    await mockNextMoveApi(page);
  });

  test("定跡学習トップでモードを切り替えられ、次の一手一覧では答えを表示しない", async ({ page }) => {
    await page.goto("/openings");
    const linesButton = page.getByTestId("opening-mode-lines");
    const nextMoveButton = page.getByTestId("opening-mode-next-move");
    await expect(linesButton).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("opening-line-study-section")).toBeVisible();
    await expect(page.getByTestId("openings-page")).not.toContainText("PR #16");
    await expect(page.getByTestId("openings-page")).not.toContainText("learning_samples");

    await nextMoveButton.click();
    await expect(nextMoveButton).toHaveAttribute("aria-pressed", "true");
    await expect(page).toHaveURL(/mode=next-move/);
    await expect(page.getByTestId("next-move-section")).toBeVisible();
    // 初期状態では先頭の戦型(棒銀)が選択され、その問題のみ表示される
    await expect(page.getByTestId("next-move-opening-filter")).toHaveValue("bogin");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);
    // 一覧では内部ID・SFEN・候補手・評価値を出さない
    await expect(page.getByTestId("next-move-problem-list")).not.toContainText("サンプル局面");
    await expect(page.getByTestId("next-move-problem-list")).not.toContainText("7g7f");
    await expect(page.getByTestId("next-move-problem-list")).not.toContainText("評価値");
    await expect(page.getByTestId("next-move-problem-list")).toContainText("出典: Sample YaneuraOu Book");
  });

  test("戦型フィルターで問題を絞り込める", async ({ page }) => {
    const requestedUrls: string[] = [];
    await mockNextMoveApi(page, requestedUrls);
    await page.goto("/openings?mode=next-move");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);
    expect(requestedUrls.some((url) => url.includes("opening_key=bogin"))).toBeTruthy();
    await page.getByTestId("next-move-opening-filter").selectOption("shikenbisha");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(1);
    await expect(page.getByTestId("next-move-problem-list")).toContainText("四間飛車");
    expect(requestedUrls.some((url) => url.includes("opening_key=shikenbisha"))).toBeTruthy();
    // 戦型を選ばない全件取得は行わない(取得の偏り対策)
    expect(requestedUrls.every((url) => !url.match(/\/api\/learning-samples\?(?!.*opening_key=)/))).toBeTruthy();
  });

  test("着手前は候補手・評価値・PVを表示しない", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    await expect(page.getByTestId("next-move-heading")).toContainText("棒銀");
    await expect(page.getByTestId("next-move-progress")).toContainText("問題 1 / 2");
    await expect(page.getByTestId("shogi-board")).toBeVisible();
    await expect(page.getByTestId("next-move-feedback")).toContainText("次の一手");
    await expect(page.getByTestId("next-move-result")).toHaveCount(0);
    await expect(page.getByTestId("next-move-page")).not.toContainText("7g7f");
    await expect(page.getByTestId("next-move-page")).not.toContainText("評価値");
    await expect(page.getByTestId("next-move-page")).not.toContainText("PV");
  });

  test("段階ヒントは要求したときだけ表示される", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    await expect(page.getByTestId("next-move-hints")).toHaveCount(0);
    await page.getByTestId("next-move-hint-button").click();
    await expect(page.getByTestId("next-move-hints")).toContainText("ヒント1");
    await expect(page.getByTestId("next-move-hints")).not.toContainText("7六");
    await page.getByTestId("next-move-hint-button").click();
    await expect(page.getByTestId("next-move-hints")).toContainText("ヒント2");
    await expect(page.getByTestId("next-move-hints")).toContainText("7六");
    await expect(page.getByTestId("next-move-hint-button")).toBeDisabled();
  });

  test("最上位候補を指すと順位・評価値・候補比較が表示される", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    await playMove(page, "77", "76");
    await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");
    const result = page.getByTestId("next-move-result");
    await expect(result).toContainText("第1候補");
    await expect(result).toContainText("52");
    await expect(result).toContainText("7g7f");
    await expect(result).toContainText("7g7f 3c3d 2g2f");
    await expect(result).toContainText("出典: Sample YaneuraOu Book");
    await expect(result).toContainText("MIT License");

    await page.getByTestId("next-move-compare-button").click();
    await expect(page.getByTestId("next-move-compare-button")).toHaveAttribute("aria-pressed", "true");
    const table = page.getByTestId("next-move-candidate-table");
    await expect(table).toBeVisible();
    await expect(table).toContainText("2g2f");
    await expect(table).toContainText("あなたの手");
  });

  test("第2候補を指しても不正解扱いにならず、最上位候補との差を表示する", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    await playMove(page, "27", "26");
    const feedback = page.getByTestId("next-move-feedback");
    await expect(feedback).toContainText("有力候補");
    await expect(feedback).not.toContainText("不正解");
    const result = page.getByTestId("next-move-result");
    await expect(result).toContainText("第2候補");
    await expect(result).toContainText("最上位候補");
    await expect(result).toContainText("7g7f");
    await expect(result).toContainText("12");
    await expect(page.getByTestId("next-move-page")).not.toContainText("不正解");
  });

  test("候補外の合法手はDB未登録の説明になり、悪手とは断定しない", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    await playMove(page, "17", "16");
    const feedback = page.getByTestId("next-move-feedback");
    await expect(feedback).toContainText("定跡DBには候補手として登録されていません");
    await expect(feedback).toContainText("局面上の評価を完全に否定するものではありません");
    await expect(page.getByTestId("next-move-page")).not.toContainText("不正解");
    await expect(page.getByTestId("next-move-page")).not.toContainText("悪手");
    // 候補比較から最上位候補は確認できる
    await page.getByTestId("next-move-compare-button").click();
    await expect(page.getByTestId("next-move-candidate-table")).toContainText("7g7f");
  });

  test("「もう一度考える」で初期局面に戻る", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    await playMove(page, "77", "76");
    await expect(page.getByTestId("next-move-result")).toBeVisible();
    await page.getByTestId("next-move-retry-button").click();
    await expect(page.getByTestId("next-move-result")).toHaveCount(0);
    await expect(page.getByTestId("next-move-feedback")).toContainText("次の一手");
    // 盤面が初期化され、もう一度同じ手を指せる
    await playMove(page, "77", "76");
    await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");
  });

  test("「次の問題」で同じ戦型の別サンプルへ進み、見出しへフォーカスする", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    await playMove(page, "77", "76");
    await page.getByTestId("next-move-next-button").click();
    await expect(page).toHaveURL(/next-move\/102/);
    await expect(page.getByTestId("next-move-progress")).toContainText("問題 2 / 2");
    await expect(page.getByTestId("next-move-heading")).toBeFocused();
    // 新しい問題は未解答状態から始まる
    await expect(page.getByTestId("next-move-result")).toHaveCount(0);
  });

  test("キーボードだけで着手から結果確認・次の問題まで操作できる", async ({ page }) => {
    await page.goto("/openings/next-move/101");
    const board = page.getByTestId("shogi-board");
    // 7七の歩をキーボードで選択し、7六へ移動して着手
    await board.locator('[data-square="55"]').focus();
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");

    await page.getByTestId("next-move-compare-button").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("next-move-candidate-table")).toBeVisible();

    await page.getByTestId("next-move-next-button").focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/next-move\/102/);
  });

  test("後手番の局面では盤面が反転し、成る手・成らない手が別候補として判定される", async ({ page }) => {
    await page.goto("/openings/next-move/301");
    await expect(page.getByTestId("turn-indicator")).toContainText("△後手");
    // 後手視点に盤面が反転している(筋座標が 1→9 の順)
    await expect(page.locator(".file-coords span").first()).toHaveText("1");
    await expect(page.getByTestId("next-move-feedback")).toContainText("後手番です");

    // 後手の歩 5七→5八 で成り選択ダイアログが開き、「成る」は最上位候補(5g5h+)
    await playMove(page, "57", "58");
    const dialog = page.getByRole("dialog", { name: "成り選択" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "成る", exact: true }).click();
    await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");
    const result = page.getByTestId("next-move-result");
    await expect(result).toContainText("第1候補");
    await expect(result).toContainText("5g5h+");

    // 同じ移動でも「成らず」は第2候補(5g5h)として区別して判定される
    await page.getByTestId("next-move-retry-button").click();
    await playMove(page, "57", "58");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "成らず" }).click();
    await expect(page.getByTestId("next-move-feedback")).toContainText("有力候補");
    await expect(result).toContainText("第2候補");
    await expect(result).toContainText("5g5h");
  });

  test("存在しない問題はエラー表示と一覧への導線を出す", async ({ page }) => {
    await page.goto("/openings/next-move/999");
    await expect(page.getByRole("alert")).toContainText("問題の取得に失敗しました");
    await expect(page.getByRole("link", { name: "← 次の一手一覧へ" })).toBeVisible();
  });
});

test.describe("次の一手 mobile layout (360px)", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  test.beforeEach(async ({ page }) => {
    await mockNextMoveApi(page);
  });

  test("一覧と挑戦画面が360px幅で横スクロールしない", async ({ page }) => {
    await page.goto("/openings?mode=next-move");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await page.goto("/openings/next-move/101");
    await expect(page.getByTestId("shogi-board")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await playMove(page, "77", "76");
    await page.getByTestId("next-move-compare-button").click();
    await expect(page.getByTestId("next-move-candidate-table")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
