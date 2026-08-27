import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Position } from "tsshogi";
import { applyOpeningPath, continueOpeningMainLine, expectedOpeningMove, flattenMainLine, openingFromImportedLine } from "./openings";

type Node = { key: string; parent_key: string | null; usi: string; from_sfen: string; to_sfen: string; sort_order: number; is_main: boolean; variation_group: string };
type Record = { line_name: string; initial_sfen: string; nodes: Node[] };
const path = fileURLToPath(new URL("../../../backend/app/wikipedia_opening_artifacts/haya-ishida.json", import.meta.url));
const record = (JSON.parse(readFileSync(path, "utf8")) as { records: Record[] }).records[0];

function fixture() {
  const ids = new Map(record.nodes.map((node, index) => [node.key, index + 1]));
  return openingFromImportedLine({
    id: 201, name: record.line_name, opening_type: "振り飛車", initial_sfen: record.initial_sfen,
    moves: record.nodes.map((node) => ({ id: ids.get(node.key), parent_move_id: node.parent_key ? ids.get(node.parent_key)! : null,
      usi: node.usi, from_sfen: node.from_sfen, to_sfen: node.to_sfen, sort_order: node.sort_order,
      is_main: node.is_main, move_key: node.key, variation_group: node.variation_group })),
    source: { name: "Wikipedia 石田流", license_name: "CC BY-SA 4.0", license_url: "" },
  });
}

describe("Haya Ishida production canonical tree", () => {
  it("validates every independent edge with tsshogi", () => {
    for (const node of record.nodes) {
      const position = Position.newBySFEN(node.from_sfen)!;
      const move = position.createMoveByUSI(node.usi);
      expect(move).not.toBeNull(); expect(position.isValidMove(move!)).toBe(true);
      position.doMove(move!);
      expect(position.sfen.replace(/\d+$/, node.to_sfen.split(" ").at(-1)!)).toBe(node.to_sfen);
    }
  });

  it("branches after move five and keeps labels, leaves, and non-leading explicit main", () => {
    const opening = fixture();
    expect(flattenMainLine(opening).map((node) => node.usi)).toEqual(["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e"]);
    const moveFive = opening.moves[0].next![0].next![0].next![0].next![0];
    const choices = moveFive.next!;
    expect(choices.map((node) => [node.usi, node.branchLabel, node.isMain])).toEqual([
      ["7a6b", "△6二銀の変化", false], ["5a4b", "△4二玉の変化", false],
      ["8d8e", "図2-Dへの△8五歩", true], ["2b8h+", "図2-Cの角交換変化", false],
    ]);
    expect(expectedOpeningMove(opening, [0, 0, 0, 0, 0])?.usi).toBe("8d8e");
    expect(continueOpeningMainLine(opening, [])).toEqual([0, 0, 0, 0, 0, 2]);
    expect(continueOpeningMainLine(opening, [0, 0, 0, 0, 0, 0])).toEqual([0, 0, 0, 0, 0, 0, 0]);
    expect(choices[0].next?.[0].usi).toBe("6g6f");
    expect(choices[1].next?.[0].usi).toBe("6g6f");
    expect(choices[0].next?.[0]).not.toBe(choices[1].next?.[0]);
    expect(applyOpeningPath(opening, [0, 0, 0, 0, 0, 3, 0, 0, 0]).moves.map((move) => move.usi)).toEqual(
      ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "2b8h+", "7i8h", "B*4e", "B*7f"],
    );
    expect(choices[0].next?.[0].usi).toBe("6g6f");
    expect(choices[1].next?.[0].usi).toBe("6g6f");
    expect(choices[2].usi).toBe("8d8e");
    expect(choices[3].next?.[0].next?.[0].next?.[0].usi).toBe("B*7f");
  });
});
