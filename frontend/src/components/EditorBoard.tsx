import { useMemo, useState } from "react";
import { HAND_PIECES, PIECE_LABEL, PIECES, clonePosition, type Color, type EditorPiece, type EditorPosition } from "../shogi/editor";

interface Props { position: EditorPosition; onChange: (next: EditorPosition) => void }
type Tool = { kind: "piece"; piece: EditorPiece } | { kind: "erase" } | { kind: "move" };
const RANKS = ["一","二","三","四","五","六","七","八","九"];
function pieceText(p: EditorPiece) { return PIECE_LABEL[p.code]; }
export default function EditorBoard({ position, onChange }: Props) {
  const [tool, setTool] = useState<Tool>({ kind: "piece", piece: { color: "b", code: "P" } });
  const [selected, setSelected] = useState<[number, number] | null>(null);
  const files = useMemo(() => [9,8,7,6,5,4,3,2,1], []);
  function click(r: number, f: number) {
    const next = clonePosition(position);
    if (tool.kind === "erase") next.board[r][f] = null;
    if (tool.kind === "piece") next.board[r][f] = { ...tool.piece };
    if (tool.kind === "move") {
      if (selected) { next.board[r][f] = next.board[selected[0]][selected[1]]; next.board[selected[0]][selected[1]] = null; setSelected(null); }
      else if (next.board[r][f]) setSelected([r,f]);
    }
    onChange(next);
  }
  function updateHand(color: Color, code: string, value: string) { const next=clonePosition(position); next.hands[color][code]=Math.max(0, Number(value)||0); onChange(next); }
  return <div className="editor-board-layout">
    <div className="editor-tools">
      <strong>配置する駒</strong>
      <div className="tool-row"><button type="button" className={tool.kind==="move"?"active":""} onClick={()=>setTool({kind:"move"})}>移動</button><button type="button" className={tool.kind==="erase"?"active":""} onClick={()=>setTool({kind:"erase"})}>削除</button></div>
      {(["b","w"] as Color[]).map(color => <div key={color}><div className="muted">{color==="b"?"☗先手":"☖後手"}</div><div className="piece-palette">{PIECES.map(code => <button type="button" key={`${color}-${code}`} className={tool.kind==="piece"&&tool.piece.color===color&&tool.piece.code===code?"active":""} onClick={()=>setTool({kind:"piece", piece:{color, code}})}>{PIECE_LABEL[code]}</button>)}</div></div>)}
    </div>
    <div><div className="file-coords">{files.map(f=><span key={f}>{f}</span>)}</div><div className="board-row-container"><div className="board-grid editor-grid">{position.board.map((row,r)=>row.map((piece,f)=><button type="button" key={`${r}-${f}`} className={`board-cell ${selected?.[0]===r&&selected?.[1]===f?"selected":""}`} onClick={()=>click(r,f)}>{piece && <span className={`piece-face ${piece.color==="w"?"piece-white":""} ${PIECE_LABEL[piece.code].length>1?"piece-narrow":""}`}>{pieceText(piece)}</span>}</button>))}</div><div className="rank-coords">{RANKS.map(x=><span key={x}>{x}</span>)}</div></div></div>
    <div className="editor-hands">{(["b","w"] as Color[]).map(color => <fieldset key={color}><legend>{color==="b"?"先手の持ち駒":"後手の持ち駒"}</legend>{HAND_PIECES.map(pc=><label key={pc}>{PIECE_LABEL[pc]}<input type="number" min="0" value={position.hands[color][pc]??0} onChange={e=>updateHand(color, pc, e.target.value)} /></label>)}</fieldset>)}</div>
  </div>;
}
