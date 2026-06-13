import { describe, expect, it } from "vitest";
import { emptyPosition, parseMoveList, parseSfen, toSfen, validateUsiMoves } from "./editor";

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
