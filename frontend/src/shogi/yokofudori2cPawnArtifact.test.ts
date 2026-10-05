import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Position } from "tsshogi";
import { applyOpeningPath, continueOpeningMainLine, expectedOpeningMove, flattenMainLine, openingFromImportedLine, enumerateOpeningTree, countOpeningBranchPoints, openingMainPathAt, openingPathState, openingNodeJumpAccessibleName, findOpeningChoiceIndex } from "./openings";

type Node = { key: string; parent_key: string | null; usi: string; from_sfen: string; to_sfen: string; sort_order: number; is_main: boolean; variation_group: string };
type Record = { line_name: string; initial_sfen: string; nodes: Node[]; source: { url: string; title: string; section: string }; source_note: string; retrieved_date: string; license: string };
const path = fileURLToPath(new URL("../../../backend/app/wikipedia_opening_artifacts/yokofudori-2c-pawn.json", import.meta.url));
const record = (JSON.parse(readFileSync(path, "utf8")) as { records: Record[] }).records[0];

const byKey = new Map(record.nodes.map((node) => [node.key, node]));
const main = Array.from({ length: 16 }, (_, index) => byKey.get(`main-${index + 1}`)!);
const tail = "B*4e 3d3e 4e2g+ B*1e 5a5b 3g3f 1c1d 1e4h".split(" ");
const branchPath = (ply: number): number[] => [...Array(15).fill(0), 1, ...Array(ply - 16).fill(0)];

function fixture() {
  const ids = new Map(record.nodes.map((node, index) => [node.key, index + 1]));
  return openingFromImportedLine({ id: 203, name: record.line_name, opening_type: "相居飛車", initial_sfen: record.initial_sfen,
    moves: [...record.nodes].reverse().map((node) => ({ id: ids.get(node.key), parent_move_id: node.parent_key ? ids.get(node.parent_key)! : null,
      usi: node.usi, from_sfen: node.from_sfen, to_sfen: node.to_sfen, sort_order: node.sort_order,
      is_main: node.is_main, move_key: node.key, variation_group: node.variation_group })),
    source: { name: record.source.title, license_name: record.license, license_url: "", source_url: record.source.url, source_section: record.source.section, source_note: record.source_note, source_retrieved_at: record.retrieved_date },
  });
}

describe("Yokofudori 2c pawn production canonical line", () => {
  it("validates all 24 edges and canonical SFENs with tsshogi", () => {
    expect(main.map((node) => node.usi)).toEqual("7g7f 3c3d 2g2f 8c8d 2f2e 8d8e 6i7h 4a3b 2e2d 2c2d 2h2d P*2c 2d3d 2b8h+ 7i8h B*2e".split(" "));
    expect(record.nodes).toHaveLength(24);
    expect(Array.from({ length: 8 }, (_, index) => byKey.get(`bishop-4e-${16 + index}`)!.usi)).toEqual(tail);
    for (const node of record.nodes) {
      const position = Position.newBySFEN(node.from_sfen)!;
      const move = position.createMoveByUSI(node.usi);
      expect(move).not.toBeNull(); expect(position.isValidMove(move!)).toBe(true);
      position.doMove(move!);
      expect(position.sfen.replace(/\d+$/, node.to_sfen.split(" ").at(-1)!)).toBe(node.to_sfen);
    }
  });

  it("builds, replays, jumps, steps back, and stops at the unchanged semantic-main leaf", () => {
    const opening = fixture();
    expect(flattenMainLine(opening)).toHaveLength(16);
    expect(opening.moves).toHaveLength(1);
    expect(continueOpeningMainLine(opening, [])).toEqual(Array(16).fill(0));
    expect(expectedOpeningMove(opening, Array(15).fill(0))?.usi).toBe("B*2e");
    expect(expectedOpeningMove(opening, Array(16).fill(0))).toBeNull();
    const at = (ply: number) => applyOpeningPath(opening, Array(ply).fill(0));
    const expectCanonicalPosition = (ply: 11 | 12 | 15 | 16, hand: string, turn: "b" | "w") => {
      const result = at(ply);
      expect(result.moves).toHaveLength(ply);
      expect(result.moves.at(-1)?.usi).toBe(byKey.get(`main-${ply}`)!.usi);
      expect(result.position.sfen.replace(/\d+$/, String(ply + 1))).toBe(byKey.get(`main-${ply}`)!.to_sfen);
      const [, actualTurn, actualHand] = result.position.sfen.split(" ");
      expect({ turn: actualTurn, hand: actualHand }).toEqual({ turn, hand });
      return result;
    };

    // Applying shorter and longer production paths reconstructs the position;
    // a drop removed by undo returns to hand and redo consumes it again.
    expectCanonicalPosition(12, "P", "b");
    const beforePawnDrop = expectCanonicalPosition(11, "Pp", "w");
    expect(beforePawnDrop.position.sfen.split("/")[2]).toContain("p1pppp2p"); // 2三 is empty.
    expectCanonicalPosition(12, "P", "b");
    expect(expectedOpeningMove(opening, Array(12).fill(0))?.usi).toBe("2d3d");

    expectCanonicalPosition(16, "B2P", "b");
    const beforeBishopDrop = expectCanonicalPosition(15, "B2Pb", "w");
    expect(beforeBishopDrop.position.sfen.split("/")[4]).toBe("1p7"); // 2五 is empty.
    expectCanonicalPosition(16, "B2P", "b");
    expect(expectedOpeningMove(opening, Array(16).fill(0))).toBeNull();
    expect(at(8).moves).toHaveLength(8);
  });
  it("preserves selected branches, jumps, undo/redo, and semantic-main switching", () => {
    const opening = fixture();
    const entries = enumerateOpeningTree(opening);
    const leaves = entries.filter(({ node }) => !node.next?.length);
    expect([entries.length, flattenMainLine(opening).length, Math.max(...entries.map((entry) => entry.path.length)), countOpeningBranchPoints(opening), leaves.length]).toEqual([24, 16, 23, 1, 2]);
    expect(leaves.map(({ node }) => node.usi).sort()).toEqual(["1e4h", "B*2e"]);
    const choices = applyOpeningPath(opening, Array(15).fill(0)).steps.at(-1)!.node.next!;
    expect(choices.map((node) => node.usi)).toEqual(["B*2e", "B*4e"]);
    expect(findOpeningChoiceIndex(choices, { usi: "B*2e" })).toBe(0);
    expect(findOpeningChoiceIndex(choices, { usi: "B*4e" })).toBe(1);
    expect(continueOpeningMainLine(opening, [])).toEqual(Array(16).fill(0));
    const fullBranch = branchPath(23);
    expect(continueOpeningMainLine(opening, branchPath(16))).toEqual(fullBranch);
    expect(expectedOpeningMove(opening, fullBranch)).toBeNull();
    expect(applyOpeningPath(opening, fullBranch).moves.map((move) => move.usi)).toEqual([...main.slice(0, 15).map((node) => node.usi), ...tail]);

    // Jump to every new node, then undo/redo: parent IDs govern the shuffled input.
    for (let ply = 16; ply <= 23; ply += 1) {
      const path = branchPath(ply);
      const canonical = byKey.get(`bishop-4e-${ply}`)!;
      const entry = entries.find(({ node }) => node.id.endsWith(`-bishop-4e-${ply}`))!;
      expect(entry.path).toEqual(path);
      const result = applyOpeningPath(opening, entry.path);
      expect(result.moves).toHaveLength(ply);
      expect(result.position.sfen.replace(/\d+$/, String(ply + 1))).toBe(canonical.to_sfen);
      expect(result.steps.at(-1)!.node.sourceNote).toBe(record.source_note);
      expect(result.steps.at(-1)!.node.sourceUrl).toContain("oldid=92929426");
      expect(result.steps.at(-1)!.node.sourceSection).toBe(record.source.section);
      expect(openingPathState(path, path)).toBe("current");
      expect(openingPathState(path.slice(0, -1), path)).toBe("ancestor");
      expect(openingPathState(Array(16).fill(0), path)).toBe("other");
      const undone = path.slice(0, -1);
      expect(applyOpeningPath(opening, undone).position.sfen.replace(/\d+$/, String(ply))).toBe(canonical.from_sfen);
      expect([...undone, path.at(-1)!]).toEqual(path);
      expect(continueOpeningMainLine(opening, path)).toEqual(fullBranch);
    }
    for (const ply of [21, 23]) {
      expect(applyOpeningPath(opening, branchPath(ply)).position.sfen.split(" ").slice(1, 3)).toEqual(["w", "2P"]);
    }
    expect(applyOpeningPath(opening, branchPath(18)).position.sfen.split(" ").slice(1, 3)).toEqual(["b", "B2P"]);
    expect(applyOpeningPath(opening, branchPath(19)).position.sfen.split(" ").slice(1, 3)).toEqual(["w", "2P"]);
    const mainPath = openingMainPathAt(opening, fullBranch.slice(0, 15));
    expect(mainPath).toEqual(Array(16).fill(0));
    const restored = applyOpeningPath(opening, mainPath);
    expect(restored.moves.map((move) => move.usi)).toEqual(main.map((node) => node.usi));
    expect(restored.position.sfen.replace(/\d+$/, "17")).toBe(byKey.get("main-16")!.to_sfen);
    expect(openingNodeJumpAccessibleName(opening, mainPath)).toContain("△2三歩基本手順、経路");
    expect(openingNodeJumpAccessibleName(opening, fullBranch)).toContain("△4五角の変化、経路");
    expect(applyOpeningPath(opening, []).position.sfen).toBe(record.initial_sfen);
  });
});
