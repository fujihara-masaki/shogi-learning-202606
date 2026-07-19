import { describe, expect, it } from "vitest";
import {
  UNLISTED_MOVE_DESCRIPTION,
  hintsForTopCandidate,
  judgeNextMove,
  notationForUsi,
  normalizeNextMoveCandidates,
  positionFromSfen,
  type NextMoveCandidateLike,
} from "./nextMove";

const INITIAL_SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";

function candidate(overrides: Partial<NextMoveCandidateLike> & { move_usi: string }): NextMoveCandidateLike {
  return { rank: null, score: null, depth: null, pv: null, ...overrides };
}

const CANDIDATES: NextMoveCandidateLike[] = [
  candidate({ move_usi: "7g7f", rank: 1, score: 52, depth: 32, pv: "7g7f 3c3d 2g2f" }),
  candidate({ move_usi: "2g2f", rank: 2, score: 40, depth: 30, pv: "2g2f 8c8d" }),
  candidate({ move_usi: "5g5f", rank: 3, score: 21, depth: 24, pv: "5g5f" }),
  candidate({ move_usi: "9g9f", rank: 4, score: -8, depth: 20, pv: null }),
];

describe("judgeNextMove", () => {
  it("backend共通fixtureと同じrank/score/depth/move_usi順でtop/strong/listedを判定する", () => {
    const fixture = [
      candidate({move_usi: "7g7f", rank: 1, score: null, depth: 9}),
      candidate({move_usi: "2g2f", rank: 1, score: 20, depth: null}),
      candidate({move_usi: "5g5f", rank: 1, score: 20, depth: 4}),
      candidate({move_usi: "9g9f", rank: 4, score: 99, depth: 99}),
    ];
    expect(normalizeNextMoveCandidates(fixture).map((item) => item.move_usi)).toEqual(["5g5f", "2g2f", "7g7f", "9g9f"]);
    expect(judgeNextMove("5g5f", fixture).kind).toBe("top");
    expect(judgeNextMove("2g2f", fixture).kind).toBe("strong");
    expect(judgeNextMove("9g9f", fixture).kind).toBe("listed");
  });
  it("最上位候補を指した場合は top と判定し評価値差は 0", () => {
    const verdict = judgeNextMove("7g7f", CANDIDATES);
    expect(verdict.kind).toBe("top");
    expect(verdict.label).toBe("最有力候補");
    expect(verdict.candidateRank).toBe(1);
    expect(verdict.candidate?.score).toBe(52);
    expect(verdict.best?.move_usi).toBe("7g7f");
    expect(verdict.scoreDiffFromBest).toBe(0);
  });

  it("第2候補は不正解扱いではなく有力候補と判定する", () => {
    const verdict = judgeNextMove("2g2f", CANDIDATES);
    expect(verdict.kind).toBe("strong");
    expect(verdict.label).toBe("有力候補");
    expect(verdict.candidateRank).toBe(2);
    expect(verdict.scoreDiffFromBest).toBe(12);
    expect(verdict.description).not.toContain("不正解");
  });

  it("評価値差は絶対値で返す(最上位より score が大きい候補でも正の値)", () => {
    const reversed = [
      candidate({ move_usi: "7g7f", rank: 1, score: -10 }),
      candidate({ move_usi: "2g2f", rank: 2, score: 30 }),
    ];
    expect(judgeNextMove("2g2f", reversed).scoreDiffFromBest).toBe(40);
  });

  it("双方が負の score でも評価値差は絶対値になる", () => {
    const negatives = [
      candidate({ move_usi: "7g7f", rank: 1, score: -5 }),
      candidate({ move_usi: "2g2f", rank: 2, score: -45 }),
    ];
    expect(judgeNextMove("2g2f", negatives).scoreDiffFromBest).toBe(40);
  });

  it("rank 4 以降はその他の登録候補として扱う", () => {
    const verdict = judgeNextMove("9g9f", CANDIDATES);
    expect(verdict.kind).toBe("listed");
    expect(verdict.label).toBe("その他の登録候補");
    expect(verdict.candidateRank).toBe(4);
    expect(verdict.scoreDiffFromBest).toBe(60);
  });

  it("候補外の手は DB 未登録の説明を返し、悪手とは断定しない", () => {
    const verdict = judgeNextMove("1g1f", CANDIDATES);
    expect(verdict.kind).toBe("unlisted");
    expect(verdict.candidate).toBeNull();
    expect(verdict.candidateRank).toBeNull();
    expect(verdict.description).toBe(UNLISTED_MOVE_DESCRIPTION);
    expect(verdict.description).not.toContain("悪手");
    expect(verdict.description).not.toContain("不正解");
    expect(verdict.best?.move_usi).toBe("7g7f");
  });

  it("score が欠けている場合は評価値差を計算しない", () => {
    const noScore = [candidate({ move_usi: "7g7f", rank: 1 }), candidate({ move_usi: "2g2f", rank: 2, score: 30 })];
    expect(judgeNextMove("2g2f", noScore).scoreDiffFromBest).toBeNull();
    expect(judgeNextMove("7g7f", noScore).scoreDiffFromBest).toBeNull();
  });

  it("rank が無い候補は並び順から順位を補完する", () => {
    const unranked = [candidate({ move_usi: "7g7f" }), candidate({ move_usi: "2g2f" })];
    expect(judgeNextMove("2g2f", unranked).candidateRank).toBe(2);
    expect(judgeNextMove("2g2f", unranked).kind).toBe("strong");
  });

  it("候補が空でも安全に unlisted を返す", () => {
    const verdict = judgeNextMove("7g7f", []);
    expect(verdict.kind).toBe("unlisted");
    expect(verdict.best).toBeNull();
  });
});

describe("hintsForTopCandidate", () => {
  it("最上位候補から駒種と移動先の2段階ヒントを導出する", () => {
    const position = positionFromSfen(INITIAL_SFEN);
    expect(position).not.toBeNull();
    const hints = hintsForTopCandidate(position!, CANDIDATES);
    expect(hints).toHaveLength(2);
    expect(hints[0].text).toContain("歩");
    expect(hints[1].text).toContain("7六");
  });

  it("候補が無ければヒントも無し", () => {
    const position = positionFromSfen(INITIAL_SFEN);
    expect(hintsForTopCandidate(position!, [])).toEqual([]);
  });
});

describe("notationForUsi", () => {
  it("USI を日本語表記へ変換する", () => {
    const position = positionFromSfen(INITIAL_SFEN);
    expect(notationForUsi(position!, "7g7f")).toBe("☗７六歩");
  });

  it("解釈できない手は USI のまま返す", () => {
    const position = positionFromSfen(INITIAL_SFEN);
    expect(notationForUsi(position!, "5a5b")).toBe("5a5b");
  });
});
