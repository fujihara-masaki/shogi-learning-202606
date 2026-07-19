import { expect, test, type Page } from "@playwright/test";

// 「次の一手」機能のE2E。
// 小規模専用DBと実backendを通すケースに加え、詳細なUI操作はAPIモックで検証する。

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
  problemKey: string = `v1:problem-${id}`,
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
    problem_key: problemKey,
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
  // 同じproblem_keyを共有する別sample ID。save noticeのsample境界テスト専用。
  sample(103, "notice-reset", "通知リセット", 1, [candidate("7g7f", 1, 10, "7g7f")], INITIAL_SFEN, "v1:problem-101"),
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

async function mockNextMoveApi(
  page: Page,
  requestedUrls?: string[],
  resultHandler?: (body: Record<string, unknown>, requestCount: number) => {status?: number; json?: unknown} | "abort",
) {
  let resultRequestCount = 0;
  await page.route("**/api/next-move/results", async (route) => {
    resultRequestCount += 1;
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const response = resultHandler?.(body, resultRequestCount) ?? {
      json: {id: resultRequestCount, verdict: "top", candidate_rank: 1, judgment_position: 1},
    };
    if (response === "abort") await route.abort("connectionfailed");
    else await route.fulfill({status: response.status ?? 200, json: response.json ?? {}});
  });
  await page.route("**/api/next-move/progress", (route) => route.fulfill({ json: { openings: OPENINGS.map((o) => ({
    opening_key: o.opening_key, opening_name: o.opening_name, total: o.opening_key === "bogin" ? 250 : o.sample_count, answered: o.opening_key === "bogin" ? 1 : 0,
    verdict_counts: { top: o.opening_key === "bogin" ? 1 : 0, strong: 0, listed: 0, unlisted: 0 }, top_rate: o.opening_key === "bogin" ? 1 : 0,
  })) } }));
  await page.route("**/api/next-move/status**", (route) => {
    const opening = new URL(route.request().url()).searchParams.get("opening_key");
    const items = SAMPLES.filter((s) => s.opening_key === opening).map((s, index) => ({ problem_key: s.problem_key, verdict: index ? null : "top", result_id: index ? null : 1 }));
    return route.fulfill({ json: { opening_key: opening, items } });
  });
  await page.route("**/api/next-move/problems/next**", (route) =>
    route.fulfill({ json: SAMPLES[0] }),
  );
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
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 100);
    const total = limit === 30 && openingKey === "bogin" ? 250 : list.length;
    await route.fulfill({ json: { items: list.slice(offset, offset + limit), offset, limit, total, dataset_version: "v1:e2e" } });
  });
}

async function playMove(page: Page, from: string, to: string) {
  const board = page.getByTestId("shogi-board");
  await board.locator(`[data-square="${from}"]`).click();
  await board.locator(`[data-square="${to}"]`).click();
}

// APIをモックせず、小規模専用DBと実backendを通す。
test("専用DBから次の一手一覧と出典を取得できる", async ({ page }) => {
  await page.goto("/next-move");
  await expect(page.getByTestId("next-move-problem-card").first()).toBeVisible();
  await expect(page.getByTestId("next-move-problem-list")).toContainText("出典: E2E YaneuraOu fixture");
  await expect(page.getByTestId("next-move-section").locator('[role="alert"]')).toHaveCount(0);
});

test("戦型取得が503の場合は原因と復旧手順を表示する", async ({ page }) => {
  const detail = "次の一手専用DBが存在しません: /very/long/path/to/next_move.db";
  await page.route("**/api/learning-samples/openings", (route) =>
    route.fulfill({ status: 503, json: { detail } }),
  );
  await page.goto("/next-move");
  const recovery = page.getByTestId("next-move-db-recovery");
  await expect(recovery).toContainText(detail);
  await expect(recovery).toContainText("通常DBと次の一手専用DB");
  await expect(recovery).toContainText("やねうら王定跡からの学習用サンプル抽出");
  await expect(recovery).toContainText("app.importers.yaneuraou_book");
  await expect(recovery).toContainText("extract_learning_samples");
  await expect(recovery).toContainText("validate_next_move_db.py");
  await expect(page.getByTestId("next-move-opening-filter")).toHaveCount(0);
  await expect(page.getByTestId("next-move-empty-state")).toHaveCount(0);
});

test("問題一覧取得が503の場合も専用DBの利用不可を表示する", async ({ page }) => {
  await page.route("**/api/learning-samples**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/openings")) {
      await route.fulfill({ json: OPENINGS });
    } else {
      await route.fulfill({ status: 503, json: { detail: "learning_samplesが0件です" } });
    }
  });
  await page.goto("/next-move");
  await expect(page.getByTestId("next-move-db-recovery")).toContainText("learning_samplesが0件です");
  await expect(page.getByTestId("next-move-empty-state")).toHaveCount(0);
});

test("問題詳細のスキーマ異常503でも原因と復旧手順を表示する", async ({ page }) => {
  const detail = "次の一手専用DBの必須テーブルまたは必須カラムが不足しています: learning_samples.problem_key";
  await page.route("**/api/learning-samples/101", (route) => route.fulfill({ status: 503, json: { detail } }));
  await page.goto("/next-move/101");
  const recovery = page.getByTestId("next-move-db-recovery");
  await expect(recovery).toContainText(detail);
  await expect(recovery).toContainText("validate_next_move_db.py");
});

test("500では一般エラーだけを表示しDB復旧手順を表示しない", async ({ page }) => {
  await page.route("**/api/learning-samples/openings", (route) =>
    route.fulfill({ status: 500, json: { detail: "internal error" } }),
  );
  await page.goto("/next-move");
  await expect(page.getByRole("alert")).toContainText("戦型一覧の取得に失敗しました: internal error");
  await expect(page.getByTestId("next-move-db-recovery")).toHaveCount(0);
});

test("360px幅でも長いDB異常案内がページ全体を横スクロールさせない", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.route("**/api/learning-samples/openings", (route) => route.fulfill({
    status: 503,
    json: { detail: `DBを開けません: /${"very-long-database-directory/".repeat(12)}next_move.db` },
  }));
  await page.goto("/next-move");
  await expect(page.getByTestId("next-move-db-recovery")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
});

test.describe("次の一手", () => {
  test.beforeEach(async ({ page }) => {
    await mockNextMoveApi(page);
  });

  test("次の一手一覧を独立ページとして表示し、答えを表示しない", async ({ page }) => {
    await page.goto("/next-move");
    await expect(page.getByTestId("next-move-list-page").getByRole("heading", { name: "次の一手", level: 1 })).toBeVisible();
    await expect(page.getByTestId("next-move-section")).toBeVisible();
    // 初期状態では先頭の戦型(棒銀)が選択され、その問題のみ表示される
    await expect(page.getByTestId("next-move-opening-filter")).toHaveValue("bogin");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);
    await expect(page.getByTestId("next-move-summary")).toContainText("挑戦済み 1 / 全250問");
    await expect(page.getByTestId("next-move-summary")).toContainText("最有力率 100%");
    await expect(page.getByText("全250問中2問を表示")).toBeVisible();
    await expect(page.getByLabel("最新状態: 最有力")).toBeVisible();
    await expect(page.getByLabel("最新状態: 未挑戦")).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "問題一覧" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3 })).toHaveCount(2);
    // 一覧では内部ID・SFEN・候補手・評価値を出さない
    await expect(page.getByTestId("next-move-problem-list")).not.toContainText("サンプル局面");
    await expect(page.getByTestId("next-move-problem-list")).not.toContainText("7g7f");
    await expect(page.getByTestId("next-move-problem-list")).not.toContainText("評価値");
    await expect(page.getByTestId("next-move-problem-list")).toContainText("出典: Sample YaneuraOu Book");
  });

  test("status API失敗時も一覧と挑戦導線を表示する", async ({ page }) => {
    await page.route("**/api/next-move/status**", (route) => route.fulfill({ status: 500, json: { detail: "failed" } }));
    await page.goto("/next-move");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);
    await expect(page.getByRole("link", { name: "挑戦する" }).first()).toBeVisible();
  });

  test("30件だけ表示すると全件数の注記を表示する", async ({ page }) => {
    const thirty = Array.from({ length: 30 }, (_, index) => ({ ...SAMPLES[0], id: 1000 + index, problem_key: `problem-${index}` }));
    await page.route("**/api/learning-samples?**", (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("limit") !== "30") return route.fallback();
      return route.fulfill({ json: { items: thirty, offset: 0, limit: 30, total: 250, dataset_version: "v1:thirty" } });
    });
    await page.goto("/next-move");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(30);
    await expect(page.getByText("全250問中30問を表示")).toBeVisible();
  });

  test("後続ページ失敗を説明しoffset 0から再試行できる", async ({ page }) => {
    let firstRequests = 0;
    await page.route("**/api/learning-samples?**", async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("opening_key") !== "bogin") return route.fallback();
      const offset = Number(url.searchParams.get("offset"));
      if (offset === 0) {
        firstRequests += 1;
        const unique = Array.from({ length: 100 }, (_, index) => ({ ...SAMPLES[0], id: 1000 + index, problem_key: `v1:retry-${index}` }));
        await route.fulfill({ json: { items: unique, offset: 0, limit: 100, total: 101, dataset_version: "v1:retry" } });
      } else await route.fulfill({ status: 500, json: { detail: "page failed" } });
    });
    await page.goto("/next-move/101");
    await expect(page.getByTestId("next-move-page-error")).toContainText("最後まで取得できませんでした");
    await page.getByRole("button", { name: "offset 0から再試行" }).click();
    await expect.poll(() => firstRequests).toBeGreaterThan(1);
  });

  test("100件を超える戦型でも正確な問題X/Yを表示する", async ({ page }) => {
    const many = Array.from({ length: 101 }, (_, index) => ({ ...SAMPLES[0], id: 1000 + index, problem_key: `many-${index}` }));
    await page.route("**/api/learning-samples**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/learning-samples/1100") return route.fulfill({ json: many[100] });
      if (url.pathname === "/api/learning-samples") {
        const offset = Number(url.searchParams.get("offset") ?? 0);
        const limit = Number(url.searchParams.get("limit") ?? 100);
        return route.fulfill({ json: { items: many.slice(offset, offset + limit), offset, limit, total: 101, dataset_version: "v1:many" } });
      }
      return route.fallback();
    });
    await page.goto("/next-move/1100");
    await expect(page.getByTestId("next-move-progress")).toContainText("問題 101 / 101");
  });

  test("101問では100問目から101問目へ進み、101問目でだけ完了する", async ({ page }) => {
    const many = Array.from({ length: 101 }, (_, index) => ({ ...SAMPLES[0], id: 2000 + index, problem_key: `v1:sequence-${index}` }));
    await page.route("**/api/learning-samples**", async (route) => {
      const url = new URL(route.request().url());
      const match = url.pathname.match(/\/(\d+)$/);
      if (match) return route.fulfill({ json: many[Number(match[1]) - 2000] });
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return route.fulfill({ json: { items: many.slice(offset, offset + 100), offset, limit: 100, total: 101, dataset_version: "v1:sequence" } });
    });
    await page.goto("/next-move/2099");
    await page.getByTestId("next-move-skip-button").click();
    await expect(page).toHaveURL(/next-move\/2100/);
    await expect(page.getByTestId("next-move-complete")).toHaveCount(0);
    await page.getByTestId("next-move-skip-button").click();
    await expect(page.getByTestId("next-move-complete")).toBeVisible();
  });

  for (const inconsistency of ["empty", "version"] as const) {
    test(`${inconsistency}な途中ページから再試行成功後に101問目まで進める`, async ({ page }) => {
      let offsetZero = 0;
      const first = [
        ...Array.from({ length: 99 }, (_, index) => ({ ...SAMPLES[0], id: 3000 + index, problem_key: `v1:${inconsistency}-${index}` })),
        SAMPLES[0],
      ];
      await page.route("**/api/learning-samples?**", async (route) => {
        const url = new URL(route.request().url());
        const offset = Number(url.searchParams.get("offset") ?? 0);
        if (offset === 0) {
          offsetZero += 1;
          return route.fulfill({ json: { items: first, offset: 0, limit: 100, total: 101, dataset_version: "v1:before" } });
        }
        if (offsetZero > 1) {
          return route.fulfill({ json: { items: [SAMPLES[1]], offset: 100, limit: 100, total: 101, dataset_version: "v1:before" } });
        }
        return route.fulfill({ json: { items: inconsistency === "empty" ? [] : [{ ...SAMPLES[1], problem_key: "v1:last" }],
          offset: 100, limit: 100, total: 101, dataset_version: inconsistency === "version" ? "v1:after" : "v1:before" } });
      });
      await page.goto("/next-move/101");
      await expect(page.getByTestId("next-move-page-error")).toContainText("最後まで取得できませんでした");
      await page.getByRole("button", { name: "offset 0から再試行" }).click();
      await expect.poll(() => offsetZero).toBe(2);
      await expect(page.getByTestId("next-move-page-error")).toHaveCount(0);
      await expect(page.getByTestId("next-move-progress")).toContainText("問題 100 / 101");
      await page.getByTestId("next-move-skip-button").click();
      await expect(page).toHaveURL(/next-move\/102/);
      await expect(page.getByTestId("next-move-complete")).toHaveCount(0);
      await page.getByTestId("next-move-skip-button").click();
      await expect(page.getByTestId("next-move-complete")).toBeVisible();
    });
  }

  test("ナビの「次の一手」が一覧・個別問題で現在位置になる", async ({ page }) => {
    await page.goto("/next-move");
    const nav = page.getByRole("navigation", { name: "メインナビゲーション" });
    const nextMoveLink = nav.getByRole("link", { name: "次の一手" });
    await expect(nextMoveLink).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: "定跡学習" })).not.toHaveAttribute("aria-current", "page");

    await page.goto("/next-move/101");
    await expect(page.getByTestId("next-move-heading")).toContainText("棒銀");
    await expect(nextMoveLink).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: "定跡学習" })).not.toHaveAttribute("aria-current", "page");
  });

  test("旧URLは新URLへリダイレクトされ、戻る操作でループしない", async ({ page }) => {
    await page.goto("/");
    await page.goto("/openings?mode=next-move");
    await expect(page).toHaveURL(/\/next-move$/);
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);

    await page.goto("/openings/next-move/101");
    await expect(page).toHaveURL(/\/next-move\/101$/);
    await expect(page.getByTestId("next-move-heading")).toContainText("棒銀");

    // リダイレクトはreplaceのため、戻る操作で旧URLへ戻ってループしない
    await page.goBack();
    await expect(page).toHaveURL(/\/next-move$/);
    await page.goBack();
    await expect(new URL(page.url()).pathname).toBe("/");
  });

  test("個別問題の戻るリンクは次の一手一覧(/next-move)へ戻る", async ({ page }) => {
    await page.goto("/next-move/101");
    await page.getByRole("link", { name: "← 次の一手一覧へ" }).click();
    await expect(page).toHaveURL(/\/next-move$/);
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);

    // 解答後の「次の一手一覧へ戻る」も同じ一覧へ戻る
    await page.goto("/next-move/101");
    await playMove(page, "77", "76");
    await page.getByRole("link", { name: "次の一手一覧へ戻る" }).click();
    await expect(page).toHaveURL(/\/next-move$/);
  });

  test("戦型フィルターで問題を絞り込める", async ({ page }) => {
    const requestedUrls: string[] = [];
    await mockNextMoveApi(page, requestedUrls);
    await page.goto("/next-move");
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
    await page.goto("/next-move/101");
    await expect(page.getByTestId("next-move-heading")).toContainText("棒銀");
    await expect(page.getByTestId("next-move-progress")).toContainText("問題 1 / 2");
    await expect(page.getByTestId("shogi-board")).toBeVisible();
    await expect(page.getByTestId("next-move-feedback")).toContainText("次の一手");
    await expect(page.getByTestId("next-move-result")).toHaveCount(0);
    await expect(page.getByTestId("next-move-page")).not.toContainText("7g7f");
    await expect(page.getByTestId("next-move-page")).not.toContainText("評価値");
    await expect(page.getByTestId("next-move-page")).not.toContainText("PV");
    await expect(page.getByText("評価値・PV・候補順位とは")).toHaveCount(0);
  });

  test("段階ヒントは要求したときだけ表示される", async ({ page }) => {
    await page.goto("/next-move/101");
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
    await page.goto("/next-move/101");
    await playMove(page, "77", "76");
    await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");
    const result = page.getByTestId("next-move-result");
    await expect(result).toContainText("第1候補");
    await expect(result).toContainText("52");
    await expect(result).toContainText("7g7f");
    await expect(result).toContainText("7g7f 3c3d 2g2f");
    await expect(result).toContainText("出典: Sample YaneuraOu Book");
    await expect(result).toContainText("MIT License");

    const terminology = page.getByTestId("next-move-terminology");
    const summary = terminology.getByText("評価値・PV・候補順位とは");
    await expect(summary).toBeVisible();
    await summary.focus();
    await expect(summary).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(terminology).toHaveAttribute("open", "");
    await expect(terminology.locator("dt")).toHaveText(["評価値", "PV", "候補順位"]);
    await page.keyboard.press("Space");
    await expect(terminology).not.toHaveAttribute("open", "");

    await page.getByTestId("next-move-compare-button").click();
    await expect(page.getByTestId("next-move-compare-button")).toHaveAttribute("aria-pressed", "true");
    const table = page.getByTestId("next-move-candidate-table");
    await expect(table).toBeVisible();
    await expect(table).toContainText("2g2f");
    await expect(table).toContainText("あなたの手");
  });

  test("着手ごとに5項目だけを一度POSTし、ヒント・時間と再挑戦を記録する", async ({ page }) => {
    const posts: Record<string, unknown>[] = [];
    await mockNextMoveApi(page, undefined, (body) => {
      posts.push(body);
      return {json: {id: posts.length, verdict: "top", candidate_rank: 1, judgment_position: 1}};
    });
    await page.goto("/next-move/101");
    await page.getByTestId("next-move-hint-button").click();
    await playMove(page, "77", "76");
    await expect.poll(() => posts.length).toBe(1);
    expect(Object.keys(posts[0]).sort()).toEqual(["elapsed_ms", "hint_count", "move_usi", "problem_key", "sample_id"]);
    expect(posts[0]).toMatchObject({sample_id: 101, problem_key: "v1:problem-101", move_usi: "7g7f", hint_count: 1});
    expect(posts[0].elapsed_ms).toEqual(expect.any(Number));
    expect(posts[0].elapsed_ms as number).toBeGreaterThanOrEqual(0);
    await page.getByTestId("next-move-retry-button").click();
    await playMove(page, "77", "76");
    await expect.poll(() => posts.length).toBe(2);
    expect(posts[1]).toMatchObject({hint_count: 0, move_usi: "7g7f"});
  });

  test("409でも判定を維持して再読み込み案内を表示し、自動再送しない", async ({ page }) => {
    let posts = 0;
    await mockNextMoveApi(page, undefined, () => {
      posts += 1;
      return {status: 409, json: {detail: "changed", code: "NEXT_MOVE_PROBLEM_CHANGED"}};
    });
    await page.goto("/next-move/101");
    await playMove(page, "77", "76");
    await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");
    await expect(page.getByTestId("next-move-save-message")).toContainText("再読み込みしてください");
    await page.waitForTimeout(100);
    expect(posts).toBe(1);
  });

  for (const failure of ["500", "network"] as const) {
    test(`${failure}でも判定を維持し、自動再送しない`, async ({ page }) => {
      let posts = 0;
      await mockNextMoveApi(page, undefined, () => {
        posts += 1;
        return failure === "network" ? "abort" : {status: 500, json: {detail: "failed", code: "SAVE_FAILED"}};
      });
      await page.goto("/next-move/101");
      await playMove(page, "77", "76");
      await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");
      await expect(page.getByTestId("next-move-save-message")).toContainText("確認できませんでした");
      await page.waitForTimeout(100);
      expect(posts).toBe(1);
    });
  }

  test("再挑戦後に返った前attemptの失敗は表示しない", async ({ page }) => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/next-move/results", async (route) => {
      await pending;
      await route.fulfill({status: 500, json: {detail: "late failure", code: "SAVE_FAILED"}});
    });
    await page.goto("/next-move/101");
    await playMove(page, "77", "76");
    await expect(page.getByTestId("next-move-feedback")).toContainText("最有力候補");
    await page.getByTestId("next-move-retry-button").click();
    release();
    await page.waitForTimeout(100);
    await expect(page.getByTestId("next-move-save-message")).toHaveCount(0);
    // The now-released route fails immediately: create a notice on sample 101.
    await playMove(page, "77", "76");
    await expect(page.getByTestId("next-move-save-message")).toContainText("確認できませんでした");
    // sample 103 deliberately shares problem_key with 101; the sample ID boundary must still clear it.
    await page.goto("/next-move/103");
    await expect(page.getByTestId("next-move-heading")).toContainText("通知リセット");
    await expect(page.getByTestId("next-move-save-message")).toHaveCount(0);
  });

  test("第2候補を指しても不正解扱いにならず、最上位候補との差を表示する", async ({ page }) => {
    await page.goto("/next-move/101");
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
    await page.goto("/next-move/101");
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
    await page.goto("/next-move/101");
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
    await page.goto("/next-move/101");
    await playMove(page, "77", "76");
    await page.getByTestId("next-move-next-button").click();
    await expect(page).toHaveURL(/next-move\/102/);
    await expect(page.getByTestId("next-move-progress")).toContainText("問題 2 / 2");
    await expect(page.getByTestId("next-move-heading")).toBeFocused();
    // 新しい問題は未解答状態から始まる
    await expect(page.getByTestId("next-move-result")).toHaveCount(0);
  });

  for (const policy of ["random", "unattempted"] as const) {
    test(`一覧の${policy}出題から開始し解答後もpolicyと除外キーを維持する`, async ({ page }) => {
      const requests: URL[] = [];
      await page.route("**/api/next-move/problems/next**", async (route) => {
        const url = new URL(route.request().url());
        requests.push(url);
        await route.fulfill({ json: requests.length === 1 ? SAMPLES[0] : SAMPLES[1] });
      });
      await page.goto("/next-move");
      await page.getByRole("button", { name: policy === "random" ? "ランダムに1問" : "未挑戦から1問" }).click();
      await expect(page).toHaveURL(new RegExp(`policy=${policy}`));
      await playMove(page, "77", "76");
      await page.getByTestId("next-move-next-button").click();
      await expect(page).toHaveURL(/next-move\/102/);
      expect(requests[1].searchParams.get("policy")).toBe(policy);
      expect(requests[1].searchParams.get("exclude_problem_key")).toBe("v1:problem-101");
    });
  }

  test("着手前スキップは結果をPOSTせず次問題の見出しへフォーカスする", async ({ page }) => {
    let resultPosts = 0;
    await page.route("**/api/next-move/results", async (route) => { resultPosts += 1; await route.fulfill({ json: {} }); });
    await page.goto("/next-move/101?policy=random&opening_key=bogin");
    await page.route("**/api/next-move/problems/next**", (route) => route.fulfill({ json: SAMPLES[1] }));
    await page.getByTestId("next-move-skip-button").click();
    await expect(page).toHaveURL(/next-move\/102/);
    await expect(page.getByTestId("next-move-heading")).toBeFocused();
    expect(resultPosts).toBe(0);
  });

  test("1問戦型の最終問題をスキップすると操作UIを消して完了する", async ({ page }) => {
    await page.goto("/next-move/201");
    await page.getByTestId("next-move-skip-button").click();
    await expect(page.getByTestId("next-move-complete")).toBeVisible();
    await expect(page.getByTestId("shogi-board")).toHaveCount(0);
    await expect(page.getByTestId("next-move-hint-button")).toHaveCount(0);
    await expect(page.getByTestId("next-move-skip-button")).toHaveCount(0);
  });

  test("完了後のランダム継続は除外キーを送り、204と同一問題を処理する", async ({ page }) => {
    let calls = 0;
    const excludes: (string | null)[] = [];
    await page.route("**/api/next-move/problems/next**", async (route) => {
      calls += 1;
      excludes.push(new URL(route.request().url()).searchParams.get("exclude_problem_key"));
      if (calls === 1) await route.fulfill({ status: 204, body: "" });
      else await route.fulfill({ json: SAMPLES[1] });
    });
    await page.goto("/next-move/102");
    await page.getByTestId("next-move-skip-button").click();
    await page.getByRole("button", { name: "ランダムに続ける" }).click();
    await expect(page.getByRole("alert")).toContainText("ほかの問題はありません");
    await page.getByRole("button", { name: "ランダムに続ける" }).click();
    await expect(page.getByTestId("shogi-board")).toBeVisible();
    expect(excludes).toEqual(["v1:problem-102", "v1:problem-102"]);
  });

  test("通常順次移動は1→2→3で進み、APIを使わず3問目だけで完了する", async ({ page }) => {
    const three = [0, 1, 2].map((index) => sample(401 + index, "three", "三問", index + 1,
      [candidate("7g7f", 1, 1, null)], INITIAL_SFEN, `v1:three-${index}`));
    let policyCalls = 0;
    let listCalls = 0;
    await page.route("**/api/next-move/problems/next**", async (route) => { policyCalls += 1; await route.abort(); });
    await page.route("**/api/learning-samples**", async (route) => {
      const url = new URL(route.request().url());
      const match = url.pathname.match(/\/(\d+)$/);
      if (match) return route.fulfill({ json: three.find((item) => item.id === Number(match[1])) });
      if (url.pathname.endsWith("/openings")) return route.fulfill({ json: [{ opening_key: "three", opening_name: "三問", sample_count: 3, first_rank: 1 }] });
      listCalls += 1;
      return route.fulfill({ json: { items: three, offset: 0, limit: 100, total: 3, dataset_version: "v1:three" } });
    });
    await page.goto("/next-move/401");
    for (const nextId of [402, 403]) {
      await page.getByTestId("next-move-skip-button").click();
      await expect(page).toHaveURL(new RegExp(`/next-move/${nextId}`));
      await expect(page.getByTestId("next-move-complete")).toHaveCount(0);
    }
    await page.getByTestId("next-move-skip-button").click();
    await expect(page.getByTestId("next-move-complete")).toBeVisible();
    expect(policyCalls).toBe(0);
    expect(listCalls).toBe(1);
  });

  test("キーボードだけで着手から結果確認・次の問題まで操作できる", async ({ page }) => {
    await page.goto("/next-move/101");
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
    await page.goto("/next-move/301");
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
    await page.goto("/next-move/999");
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
    await page.goto("/next-move");
    await expect(page.getByTestId("next-move-problem-card")).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await page.goto("/next-move/101");
    await expect(page.getByTestId("shogi-board")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await playMove(page, "77", "76");
    await page.getByTestId("next-move-compare-button").click();
    await expect(page.getByTestId("next-move-candidate-table")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
