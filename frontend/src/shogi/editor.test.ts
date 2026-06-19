import { describe, expect, it } from "vitest";
import { applyRecordedMove, emptyPosition, parseMoveList, parseSfen, toSfen, validateUsiMoves } from "./editor";

describe("editor SFEN utilities", () => {
  it("generates and restores an empty board SFEN", () => {
    const pos = emptyPosition();
    pos.board[0][0] = { color: "w", code: "K" };
    pos.board[8][8] = { color: "b", code: "+R" };
    pos.hands.b.P = 2;
    pos.turn = "w";
    const sfen = toSfen(pos);
    expect(sfen).toBe("k8/9/9/9/9/9/9/9/8+R w 2P 1");
    expect(toSfen(parseSfen(sfen))).toBe(sfen);
  });

  it("rejects malformed SFEN", () => {
    expect(() => parseSfen("9/9 b - 1")).toThrow();
  });
});

describe("USI input parser", () => {
  it("accepts comma and newline separated moves", () => {
    expect(parseMoveList("5e5d+, P*5e\n3a3b")).toEqual(["5e5d+", "P*5e", "3a3b"]);
  });
  it("finds invalid USI moves", () => {
    expect(validateUsiMoves(["5e5d", "P*5e", "bad"])).toEqual(["bad"]);
  });
});

describe("recorded move application", () => {
  it("applies board moves, drops, captures, and alternates turns", () => {
    const pos = parseSfen("4k4/9/9/9/9/9/9/4P4/4K4 b R 1");
    const afterMove = applyRecordedMove(pos, "5h5g");
    expect(toSfen(afterMove)).toBe("4k4/9/9/9/9/9/4P4/9/4K4 w R 2");
    afterMove.hands.w.P = 1;
    const afterDrop = applyRecordedMove(afterMove, "P*5h");
    expect(toSfen(afterDrop)).toBe("4k4/9/9/9/9/9/4P4/4p4/4K4 b R 3");
  });

  it("adds captured pieces to the mover hand as demoted pieces", () => {
    const pos = parseSfen("4k4/9/9/9/9/9/9/4p4/4K4 b - 1");
    pos.board[7][4] = { color: "w", code: "+P" };
    pos.board[8][4] = { color: "b", code: "K" };
    const next = applyRecordedMove(pos, "5i5h");
    expect(next.hands.b.P).toBe(1);
  });
});
