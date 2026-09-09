import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Position } from "tsshogi";
import {
  applyOpeningPath,
  continueOpeningMainLine,
  expectedOpeningMove,
  flattenMainLine,
  openingFromImportedLine,
  openingMainSwitchAccessibleName,
  openingNodeJumpAccessibleName,
} from "./openings";

type Node = { key: string; parent_key: string | null; usi: string; from_sfen: string; to_sfen: string; sort_order: number; is_main: boolean; variation_group: string };
type Record = { line_name: string; initial_sfen: string; nodes: Node[] };
const path = fileURLToPath(new URL("../../../backend/app/wikipedia_opening_artifacts/yokofudori-4e-bishop.json", import.meta.url));
const record = (JSON.parse(readFileSync(path, "utf8")) as { records: Record[] }).records[0];

function fixture() {
  const ids = new Map(record.nodes.map((node, index) => [node.key, index + 1]));
  return openingFromImportedLine({ id: 202, name: record.line_name, opening_type: "相居飛車", initial_sfen: record.initial_sfen,
    moves: record.nodes.map((node) => ({ id: ids.get(node.key), parent_move_id: node.parent_key ? ids.get(node.parent_key)! : null,
      usi: node.usi, from_sfen: node.from_sfen, to_sfen: node.to_sfen, sort_order: node.sort_order,
      is_main: node.is_main, move_key: node.key, variation_group: node.variation_group })),
    source: { name: "Wikipedia 横歩取り4五角", license_name: "CC BY-SA 4.0", license_url: "" },
  });
}

describe("Yokofudori 4e bishop production canonical tree", () => {
  it("validates every edge and canonical SFEN with tsshogi", () => {
    expect(record.nodes).toHaveLength(35);
    for (const node of record.nodes) {
      const position = Position.newBySFEN(node.from_sfen)!; const move = position.createMoveByUSI(node.usi);
      expect(move).not.toBeNull(); expect(position.isValidMove(move!)).toBe(true); position.doMove(move!);
      expect(position.sfen.replace(/\d+$/, node.to_sfen.split(" ").at(-1)!)).toBe(node.to_sfen);
    }
  });

  it("keeps four reviewed branches and the 26-ply semantic main", () => {
    const opening=fixture(); expect(flattenMainLine(opening)).toHaveLength(26); let node=opening.moves[0]; for(let i=1;i<20;i+=1) node=node.next![0];
    expect(node.next!.map(x=>[x.usi,x.branchLabel,x.isMain])).toEqual([["B*7g","▲7七角の主流変化",true],["3d2d","▲2四飛の主流変化",false],["P*8g","▲8七歩の変化",false],["3d3e","▲3五飛の変化",false]]);
    const prefix=Array(20).fill(0);expect(expectedOpeningMove(opening,prefix)?.usi).toBe("B*7g");expect(continueOpeningMainLine(opening,[])).toHaveLength(26);
    const paths=[[...prefix,0,0,0,0,0,0],[...prefix,1,0,0,0,0,0,0],[...prefix,2],[...prefix,3]];expect(paths.map(p=>applyOpeningPath(opening,p).moves.at(-1)!.usi)).toEqual(["S*8g","8h1a+","P*8g","3d3e"]);
  });
  it("supports selected paths, node jumps, and main switching",()=>{
    const opening=fixture();const prefix=Array(20).fill(0);const path=[...prefix,1,0,0,0,0,0,0];expect(applyOpeningPath(opening,path).moves).toHaveLength(27);expect(continueOpeningMainLine(opening,path)).toEqual(path);
    const common=Array(20).fill("1").join("-");expect(openingNodeJumpAccessibleName(opening,[...prefix,2])).toBe(`21手目 P*8g、USI P*8g、▲8七歩の変化、経路 ${common}-3、ここへ移動`);expect(openingMainSwitchAccessibleName(opening,prefix,false)).toBe(`この分岐点の本線へ切り替える、第21手の分岐点 ルート、経路 ${common}`);
  });
});
