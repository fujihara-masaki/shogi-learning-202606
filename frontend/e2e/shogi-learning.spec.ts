import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8000";
const E2E_PREFIX = "[e2e]";
const ONE_MOVE_SFEN = "4k4/9/5+B3/9/9/9/9/9/9 b G 1";
const ONE_MOVE_SOLUTION = "G*5b";

type Problem = { id: number; title: string; solution_moves: string[] };

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

async function createE2eProblem(request: APIRequestContext, title: string) {
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
    },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as Problem;
}

async function playGoldDrop(page: Page, square: string) {
  const board = page.getByTestId("shogi-board");
  await board.getByRole("button", { name: "金" }).click();
  await board.locator(`[data-square="${square}"]`).click();
}

test.beforeEach(async ({ request }) => {
  await cleanupE2eProblems(request);
});

test.afterEach(async ({ request }) => {
  await cleanupE2eProblems(request);
});

test("home shows the main feature links", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "将棋学習アプリ" })).toBeVisible();
  for (const name of ["詰め将棋", "タイムアタック", "復習", "履歴", "問題作成"]) {
    await expect(page.getByRole("link", { name }).first()).toBeVisible();
  }
});

test("tsume page plays an existing one-move problem and shows wrong/correct feedback", async ({ page, request }) => {
  const title = `${E2E_PREFIX} tsume feedback ${Date.now()}`;
  const problem = await createE2eProblem(request, title);

  await page.goto("/tsume");
  await page.getByTestId("difficulty-filter").getByRole("button", { name: "1手詰", exact: true }).click();
  await page.getByTestId(`problem-select-${problem.id}`).click();
  await expect(page.getByTestId("shogi-board")).toBeVisible();

  await playGoldDrop(page, "42");
  await expect(page.getByTestId("tsume-feedback")).toContainText("不正解");
  await page.getByRole("button", { name: "もう一度" }).click();
  await playGoldDrop(page, "52");
  await expect(page.getByTestId("tsume-feedback")).toContainText("正解");
});

test("problem editor renders the board editor and required fields", async ({ page }) => {
  await page.goto("/problem-editor");
  await expect(page.getByRole("heading", { name: "盤面エディタ・問題作成" })).toBeVisible();
  await expect(page.getByTestId("editor-board")).toBeVisible();
  await expect(page.getByRole("link", { name: "＋ 新規作成" })).toBeVisible();
  for (const label of ["title", "mate_length", "difficulty", "tags", "solution_moves", "opponent_moves", "explanation"]) {
    await expect(page.getByLabel(label)).toBeVisible();
  }
  await expect(page.getByRole("button", { name: "現在の局面からSFEN生成" })).toBeVisible();
  await expect(page.getByRole("button", { name: "SFENを盤面へ反映" })).toBeVisible();
  await expect(page.getByRole("button", { name: "この局面から手順記録を開始" })).toBeVisible();
});

test("board editor can generate and restore SFEN", async ({ page }) => {
  await page.goto("/problem-editor");
  const editor = page.getByTestId("editor-board");
  await editor.getByRole("button", { name: "玉" }).first().click();
  await page.getByTestId("editor-square-5-1").click();
  await editor.getByRole("button", { name: "角" }).first().click();
  await page.getByTestId("editor-square-4-3").click();
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

  await page.goto("/tsume");
  await page.getByTestId("difficulty-filter").getByRole("button", { name: "1手詰", exact: true }).click();
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
  await page.getByRole("link", { name: "履歴" }).click();
  await expect(page.getByRole("heading", { name: "学習履歴" })).toBeVisible();
  await page.getByRole("link", { name: "復習" }).click();
  await expect(page.getByRole("heading", { name: "復習" })).toBeVisible();
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
