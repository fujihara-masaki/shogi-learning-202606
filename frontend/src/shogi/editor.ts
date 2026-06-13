export type Color = "b" | "w";
export type PieceCode = "P" | "L" | "N" | "S" | "G" | "B" | "R" | "K" | "+P" | "+L" | "+N" | "+S" | "+B" | "+R";
export interface EditorPiece { color: Color; code: PieceCode }
export type BoardState = (EditorPiece | null)[][];
export type Hands = Record<Color, Record<string, number>>;
export interface EditorPosition { board: BoardState; hands: Hands; turn: Color; moveNumber: number }
export const PIECES: PieceCode[] = ["P", "L", "N", "S", "G", "B", "R", "K", "+P", "+L", "+N", "+S", "+B", "+R"];
export const HAND_PIECES = ["R", "B", "G", "S", "N", "L", "P"] as const;
export const PIECE_LABEL: Record<string, string> = { P:"歩", L:"香", N:"桂", S:"銀", G:"金", B:"角", R:"飛", K:"玉", "+P":"と", "+L":"成香", "+N":"成桂", "+S":"成銀", "+B":"馬", "+R":"龍" };
export function emptyPosition(): EditorPosition { return { board: Array.from({length:9},()=>Array<EditorPiece|null>(9).fill(null)), hands: { b:{}, w:{} }, turn:"b", moveNumber:1 }; }
export function initialPosition(): EditorPosition { return parseSfen("lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"); }
function clone(p: EditorPosition): EditorPosition { return { board: p.board.map(r=>r.map(x=>x?{...x}:null)), hands:{ b:{...p.hands.b}, w:{...p.hands.w} }, turn:p.turn, moveNumber:p.moveNumber }; }
export function clonePosition(p: EditorPosition): EditorPosition { return clone(p); }
export function parseSfen(sfen: string): EditorPosition {
  const parts = sfen.trim().split(/\s+/); if (parts.length < 4) throw new Error("SFENは '盤面 手番 持ち駒 手数' の形式で入力してください");
  const rows = parts[0].split("/"); if (rows.length !== 9) throw new Error("盤面は9段である必要があります");
  const pos = emptyPosition();
  rows.forEach((row, r) => { let f=0; for (let i=0;i<row.length;i++){ const ch=row[i]; if (/\d/.test(ch)){ f+=Number(ch); continue; } let promoted=false; let pc=ch; if(ch==="+"){ promoted=true; pc=row[++i]; if(!pc) throw new Error("成駒の表記が不正です"); } const upper=pc.toUpperCase(); const code=(promoted?`+${upper}`:upper) as PieceCode; if(!PIECES.includes(code)) throw new Error(`不明な駒です: ${pc}`); if(f>=9) throw new Error("1段のマス数が多すぎます"); pos.board[r][f++]={ color: pc===upper ? "b":"w", code }; } if(f!==9) throw new Error("1段は9マスである必要があります"); });
  if(parts[1]!=="b" && parts[1]!=="w") throw new Error("手番は b または w で指定してください"); pos.turn=parts[1] as Color;
  if(parts[2]!=="-"){ const re=/(\d*)([RBGSLNPPrbgslnp])/g; let used=""; for(const m of parts[2].matchAll(re)){ const count=m[1]?Number(m[1]):1; const piece=m[2]; const color=piece===piece.toUpperCase()?"b":"w"; const code=piece.toUpperCase(); pos.hands[color][code]=(pos.hands[color][code]??0)+count; used+=m[0]; } if(used!==parts[2]) throw new Error("持ち駒の表記が不正です"); }
  pos.moveNumber=Number(parts[3]); if(!Number.isInteger(pos.moveNumber)||pos.moveNumber<1) throw new Error("手数は1以上の整数にしてください"); return pos;
}
export function toSfen(pos: EditorPosition): string {
  const rows=pos.board.map(row=>{ let out="", empty=0; for(const piece of row){ if(!piece){ empty++; continue; } if(empty){ out+=String(empty); empty=0; } const raw=piece.code.replace("+", ""); out+=(piece.code.startsWith("+")?"+":"")+(piece.color==="b"?raw:raw.toLowerCase()); } return out+(empty?String(empty):""); });
  const hand = (["b","w"] as Color[]).flatMap(c=>HAND_PIECES.map(pc=>({c,pc,n:pos.hands[c][pc]??0})).filter(x=>x.n>0).map(x=>`${x.n>1?x.n:""}${x.c==="b"?x.pc:x.pc.toLowerCase()}`)).join("") || "-";
  return `${rows.join("/")} ${pos.turn} ${hand} ${pos.moveNumber}`;
}
export function setHand(pos: EditorPosition, color: Color, piece: string, count: number): EditorPosition { const next=clone(pos); next.hands[color][piece]=Math.max(0, count); return next; }
export function parseMoveList(text: string): string[] { return text.split(/[\n,]/).map(s=>s.trim()).filter(Boolean); }
export function validateUsiMoves(moves: string[]): string[] { const re=/^(?:[1-9][a-i][1-9][a-i]\+?|[PLNSGBR]\*[1-9][a-i])$/; return moves.filter(m=>!re.test(m)); }
