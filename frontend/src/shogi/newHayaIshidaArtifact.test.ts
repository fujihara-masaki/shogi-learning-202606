import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Position } from "tsshogi";

type Node = { from_sfen: string; to_sfen: string; usi: string };
type Artifact = { records: Array<{ initial_sfen: string; nodes: Node[] }> };

const artifactPath = fileURLToPath(
  new URL("../../../backend/app/wikipedia_opening_artifacts/new-haya-ishida.json", import.meta.url),
);

describe("new Haya Ishida canonical artifact", () => {
  it("replays every tracked edge with tsshogi", () => {
    const artifact = JSON.parse(readFileSync(artifactPath, "utf8")) as Artifact;
    const record = artifact.records[0];
    const position = Position.newBySFEN(record.initial_sfen);
    expect(position).not.toBeNull();
    for (const node of record.nodes) {
      expect(position!.sfen.replace(/\d+$/, node.from_sfen.split(" ").at(-1)!)).toBe(node.from_sfen);
      const move = position!.createMoveByUSI(node.usi);
      expect(move).not.toBeNull();
      expect(position!.isValidMove(move!)).toBe(true);
      position!.doMove(move!);
      // tsshogi intentionally preserves the imported SFEN move number; its
      // board/turn/hands projection must otherwise match canonical SFEN.
      const expectedMoveNumber = node.to_sfen.split(" ").at(-1)!;
      const replayed = position!.sfen.replace(/\d+$/, expectedMoveNumber);
      expect(replayed).toBe(node.to_sfen);
    }
    expect(record.nodes).toHaveLength(17);
    expect(record.nodes.at(-1)?.usi).toBe("B*5e");
  });
});
