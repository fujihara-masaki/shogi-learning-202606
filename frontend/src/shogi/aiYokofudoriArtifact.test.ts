import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Position } from "tsshogi";
import { applyOpeningPath, continueOpeningMainLine, expectedOpeningMove, flattenMainLine, openingFromImportedLine } from "./openings";

type Node = { key: string; parent_key: string | null; usi: string; from_sfen: string; to_sfen: string; sort_order: number; is_main: boolean; variation_group: string };
type Record = { line_name: string; initial_sfen: string; nodes: Node[] };
const path = fileURLToPath(new URL("../../../backend/app/wikipedia_opening_artifacts/ai-yokofudori.json", import.meta.url));
const record = (JSON.parse(readFileSync(path, "utf8")) as { records: Record[] }).records[0];

function fixture() {
  const ids = new Map(record.nodes.map((node, index) => [node.key, index + 1]));
  return openingFromImportedLine({ id: 202, name: record.line_name, opening_type: "相居飛車", initial_sfen: record.initial_sfen,
    moves: record.nodes.map((node) => ({ id: ids.get(node.key), parent_move_id: node.parent_key ? ids.get(node.parent_key)! : null,
      usi: node.usi, from_sfen: node.from_sfen, to_sfen: node.to_sfen, sort_order: node.sort_order,
      is_main: node.is_main, move_key: node.key, variation_group: node.variation_group })),
    source: { name: "Wikipedia 相横歩取り", license_name: "CC BY-SA 4.0", license_url: "" },
  });
}

describe("Ai Yokofudori production canonical tree", () => {
  it("validates every edge and canonical SFEN with tsshogi", () => {
    expect(record.nodes).toHaveLength(24);
    for (const node of record.nodes) {
      const position = Position.newBySFEN(node.from_sfen)!; const move = position.createMoveByUSI(node.usi);
      expect(move).not.toBeNull(); expect(position.isValidMove(move!)).toBe(true); position.doMove(move!);
      expect(position.sfen.replace(/\d+$/, node.to_sfen.split(" ").at(-1)!)).toBe(node.to_sfen);
    }
  });

  it("keeps both branch signatures, labels, leaves, and explicit semantic mains", () => {
    const opening = fixture(); expect(flattenMainLine(opening)).toHaveLength(21);
    let node = opening.moves[0]; for (let i = 1; i < 18; i += 1) node = node.next![0];
    const choices = node.next!;
    expect(choices.map((x) => [x.usi, x.branchLabel, x.isMain])).toEqual([
      ["P*7g", "▲7七歩の受け", false], ["8i7g", "▲7七桂の受け", false], ["8h7g", "▲7七銀の主流形", true],
    ]);
    const prefix = Array(18).fill(0);
    expect(expectedOpeningMove(opening, prefix)?.usi).toBe("8h7g");
    expect(continueOpeningMainLine(opening, []).slice(18)).toEqual([2, 0, 0]);
    expect(choices[0].next).toHaveLength(0); expect(choices[1].next).toHaveLength(0);
    const afterRookRetreat = choices[2].next![0];
    expect(afterRookRetreat.usi).toBe("7f7d");
    expect(afterRookRetreat.next!.map((x) => [x.usi, x.branchLabel, x.isMain])).toEqual([
      ["3d7d", "飛車交換型（超急戦）", true], ["3d3f", "飛車交換拒否型（持久戦）", false],
    ]);
    const paths = [[...prefix, 0], [...prefix, 1], [...prefix, 2, 0, 0], [...prefix, 2, 0, 1]];
    expect(paths.map((p) => applyOpeningPath(opening, p).moves.at(-1)!.usi)).toEqual(["P*7g", "8i7g", "3d7d", "3d3f"]);
  });
});
