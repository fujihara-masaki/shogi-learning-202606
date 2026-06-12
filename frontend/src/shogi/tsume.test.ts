import { describe, expect, it } from "vitest";
import { Color } from "tsshogi";
import {
  applyUsiMoves,
  interleaveLine,
  isCorrectMove,
  positionFromSfen,
} from "./tsume";

// サンプル問題「一間龍から頭金」(3手詰)
const SFEN_3TE = "8k/9/5+R3/9/9/9/9/9/9 b G 1";

describe("positionFromSfen", () => {
  it("SFEN から局面を生成できる", () => {
    const pos = positionFromSfen(SFEN_3TE);
    expect(pos).not.toBeNull();
    expect(pos!.color).toBe(Color.BLACK);
    expect(pos!.sfen).toBe(SFEN_3TE);
  });

  it("不正な SFEN は null を返す", () => {
    expect(positionFromSfen("not-a-sfen")).toBeNull();
  });
});

describe("interleaveLine", () => {
  it("攻め方と玉方の手順を交互に並べる", () => {
    expect(interleaveLine(["a", "b"], ["x"])).toEqual(["a", "x", "b"]);
    expect(interleaveLine(["a", "b", "c"], ["x", "y"])).toEqual([
      "a",
      "x",
      "b",
      "y",
      "c",
    ]);
    expect(interleaveLine(["a"], [])).toEqual(["a"]);
  });
});

describe("applyUsiMoves", () => {
  it("正解手順をすべて適用でき、玉方は手詰まりになる", () => {
    const pos = positionFromSfen(SFEN_3TE)!;
    const result = applyUsiMoves(pos, ["4c1c", "1a2a", "G*2b"]);
    expect(result).not.toBeNull();
    expect(result!.applied).toHaveLength(3);
    expect(result!.applied[0].text).toContain("龍");
    expect(result!.position.color).toBe(Color.WHITE);
    expect(result!.position.checked).toBe(true);
  });

  it("持ち駒を打つ手も適用できる", () => {
    const pos = positionFromSfen("4k4/9/5+B3/9/9/9/9/9/9 b G 1")!;
    const result = applyUsiMoves(pos, ["G*5b"]);
    expect(result).not.toBeNull();
    expect(result!.applied[0].text).toContain("金");
  });

  it("不正な手は null を返す", () => {
    const pos = positionFromSfen(SFEN_3TE)!;
    expect(applyUsiMoves(pos, ["1a1b"])).toBeNull(); // 後手の手は指せない
    expect(applyUsiMoves(pos, ["P*5e"])).toBeNull(); // 持っていない駒は打てない
  });

  it("元の局面は変更しない(イミュータブル)", () => {
    const pos = positionFromSfen(SFEN_3TE)!;
    const before = pos.sfen;
    applyUsiMoves(pos, ["4c1c"]);
    expect(pos.sfen).toBe(before);
  });
});

describe("isCorrectMove", () => {
  it("USI 表記が一致する手を正解と判定する", () => {
    const pos = positionFromSfen(SFEN_3TE)!;
    const move = pos.createMoveByUSI("4c1c")!;
    expect(isCorrectMove(move, "4c1c")).toBe(true);
    expect(isCorrectMove(move, "G*2b")).toBe(false);
  });
});
