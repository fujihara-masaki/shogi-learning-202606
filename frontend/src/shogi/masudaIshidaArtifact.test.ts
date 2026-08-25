import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Position } from "tsshogi";

type Node = { from_sfen: string; to_sfen: string; usi: string };
type Artifact = { records: Array<{ initial_sfen: string; nodes: Node[] }> };

const artifactPath = fileURLToPath(
  new URL("../../../backend/app/wikipedia_opening_artifacts/masuda-ishida.json", import.meta.url),
);

describe("Masuda Ishida canonical artifact", () => {
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
      const expectedMoveNumber = node.to_sfen.split(" ").at(-1)!;
      expect(position!.sfen.replace(/\d+$/, expectedMoveNumber)).toBe(node.to_sfen);
    }
    expect(record.nodes).toHaveLength(7);
    expect(record.nodes.at(-1)?.usi).toBe("5i4h");
    expect(record.nodes.map((node) => node.usi)).not.toContain("7h7f");
  });
});
