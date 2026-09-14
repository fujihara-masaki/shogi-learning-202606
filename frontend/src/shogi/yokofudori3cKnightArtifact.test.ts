import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Position } from "tsshogi";
import { applyOpeningPath, continueOpeningMainLine, expectedOpeningMove, flattenMainLine, openingFromImportedLine } from "./openings";

type Node = { key: string; parent_key: string | null; usi: string; from_sfen: string; to_sfen: string; sort_order: number; is_main: boolean; variation_group: string };
type Record = { line_name: string; initial_sfen: string; nodes: Node[] };
const path = fileURLToPath(new URL("../../../backend/app/wikipedia_opening_artifacts/yokofudori-3c-knight.json", import.meta.url));
const record = (JSON.parse(readFileSync(path, "utf8")) as { records: Record[] }).records[0];

function fixture() {
  const ids = new Map(record.nodes.map((node, index) => [node.key, index + 1]));
  return openingFromImportedLine({ id: 203, name: record.line_name, opening_type: "相居飛車", initial_sfen: record.initial_sfen,
    moves: record.nodes.map((node) => ({ id: ids.get(node.key), parent_move_id: node.parent_key ? ids.get(node.parent_key)! : null,
      usi: node.usi, from_sfen: node.from_sfen, to_sfen: node.to_sfen, sort_order: node.sort_order,
      is_main: node.is_main, move_key: node.key, variation_group: node.variation_group })),
    source: { name: "Wikipedia 横歩取り3三桂", license_name: "CC BY-SA 4.0", license_url: "" },
  });
}

describe("Yokofudori 3c knight production canonical line", () => {
  it("validates all 16 edges and canonical SFENs with tsshogi", () => {
    expect(record.nodes.map((node) => node.usi)).toEqual("7g7f 3c3d 2g2f 8c8d 2f2e 8d8e 6i7h 4a3b 2e2d 2c2d 2h2d 8e8f 8g8f 8b8f 2d3d 2a3c".split(" "));
    for (const node of record.nodes) {
      const position = Position.newBySFEN(node.from_sfen)!;
      const move = position.createMoveByUSI(node.usi);
      expect(move).not.toBeNull(); expect(position.isValidMove(move!)).toBe(true);
      position.doMove(move!);
      expect(position.sfen.replace(/\d+$/, node.to_sfen.split(" ").at(-1)!)).toBe(node.to_sfen);
    }
  });

  it("builds, replays, jumps, steps back, and stops at the linear leaf", () => {
    const opening = fixture();
    expect(flattenMainLine(opening)).toHaveLength(16);
    expect(opening.moves).toHaveLength(1);
    expect(continueOpeningMainLine(opening, [])).toEqual(Array(16).fill(0));
    expect(expectedOpeningMove(opening, Array(15).fill(0))?.usi).toBe("2a3c");
    expect(expectedOpeningMove(opening, Array(16).fill(0))).toBeNull();
    const leaf = applyOpeningPath(opening, Array(16).fill(0));
    expect(leaf.moves).toHaveLength(16); expect(leaf.moves.at(-1)?.usi).toBe("2a3c");
    const back = applyOpeningPath(opening, Array(15).fill(0));
    expect(back.moves.at(-1)?.usi).toBe("2d3d"); expect(expectedOpeningMove(opening, Array(15).fill(0))?.usi).toBe("2a3c");
    expect(applyOpeningPath(opening, Array(8).fill(0)).moves).toHaveLength(8);
  });
});
