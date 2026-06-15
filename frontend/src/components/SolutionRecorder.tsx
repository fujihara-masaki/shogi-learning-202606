import { useMemo, useState } from "react";
import {
  HAND_PIECES,
  PIECE_LABEL,
  applyRecordedMove,
  clonePosition,
  isPromotableMove,
  squareToUsi,
  type Color,
  type EditorPosition,
  type PieceCode,
} from "../shogi/editor";

interface Props {
  initialPosition: EditorPosition;
  onMovesChange: (solutionMoves: string[], opponentMoves: string[]) => void;
}

type Selection = { kind: "square"; row: number; col: number } | { kind: "hand"; color: Color; code: PieceCode };
const RANKS = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];

export default function SolutionRecorder({ initialPosition, onMovesChange }: Props) {
  const [position, setPosition] = useState(() => clonePosition(initialPosition));
  const [selection, setSelection] = useState<Selection | null>(null);
  const [promoteNext, setPromoteNext] = useState(false);
  const [history, setHistory] = useState<EditorPosition[]>([]);
  const [recorded, setRecorded] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const files = useMemo(() => [9, 8, 7, 6, 5, 4, 3, 2, 1], []);

  function emit(nextMoves: string[]) {
    const solution = nextMoves.filter((_, i) => i % 2 === 0);
    const opponent = nextMoves.filter((_, i) => i % 2 === 1);
    onMovesChange(solution, opponent);
  }

  function reset() {
    setPosition(clonePosition(initialPosition));
    setSelection(null);
    setPromoteNext(false);
    setHistory([]);
    setRecorded([]);
    setError(null);
    emit([]);
  }

  function undo() {
    const prev = history.at(-1);
    if (!prev) return;
    const nextMoves = recorded.slice(0, -1);
    setPosition(prev);
    setHistory((h) => h.slice(0, -1));
    setRecorded(nextMoves);
    setSelection(null);
    setError(null);
    emit(nextMoves);
  }

  function pushMove(usi: string) {
    try {
      const before = clonePosition(position);
      const next = applyRecordedMove(position, usi);
      const nextMoves = [...recorded, usi];
      setHistory((h) => [...h, before]);
      setPosition(next);
      setRecorded(nextMoves);
      setSelection(null);
      setPromoteNext(false);
      setError(null);
      emit(nextMoves);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function clickSquare(row: number, col: number) {
    const piece = position.board[row][col];
    if (!selection) {
      if (piece && piece.color === position.turn) setSelection({ kind: "square", row, col });
      return;
    }
    if (selection.kind === "square") {
      if (selection.row === row && selection.col === col) {
        setSelection(null);
        return;
      }
      const moving = position.board[selection.row][selection.col];
      if (!moving) return;
      const promote = promoteNext && isPromotableMove(moving, selection.row, row);
      pushMove(`${squareToUsi(selection.row, selection.col)}${squareToUsi(row, col)}${promote ? "+" : ""}`);
      return;
    }
    pushMove(`${selection.code.replace("+", "")}*${squareToUsi(row, col)}`);
  }

  function clickHand(color: Color, code: PieceCode) {
    if (color !== position.turn || (position.hands[color][code] ?? 0) <= 0) return;
    setSelection({ kind: "hand", color, code });
  }

  return (
    <section className="solution-recorder">
      <h2>盤面で解法手順を記録</h2>
      <p className="muted">攻め方の手は solution_moves、玉方の応手は opponent_moves に交互に自動振り分けします。</p>
      {error && <div className="banner banner-error">{error}</div>}
      <div className="board-controls">
        <span className="banner banner-info">次: {recorded.length % 2 === 0 ? "攻め方(solution)" : "玉方(opponent)"} / 手番 {position.turn === "b" ? "先手" : "後手"}</span>
        <label className="inline-check"><input type="checkbox" checked={promoteNext} onChange={(e) => setPromoteNext(e.target.checked)} /> 次の盤上移動を成る</label>
        <button type="button" onClick={undo} disabled={history.length === 0}>1手戻す</button>
        <button type="button" onClick={reset}>記録リセット</button>
      </div>
      <div className="recorder-layout">
        <div className="recorder-hands">
          {(["w", "b"] as Color[]).map((color) => (
            <div key={color} className="hand-area">
              <span className="hand-label">{color === "b" ? "☗先手" : "☖後手"}</span>
              {HAND_PIECES.map((code) => {
                const count = position.hands[color][code] ?? 0;
                if (count <= 0) return null;
                return <button type="button" key={`${color}-${code}`} className="hand-piece" onClick={() => clickHand(color, code)}>{PIECE_LABEL[code]}{count > 1 ? count : ""}</button>;
              })}
            </div>
          ))}
        </div>
        <div>
          <div className="file-coords">{files.map((f) => <span key={f}>{f}</span>)}</div>
          <div className="board-row-container">
            <div className="board-grid editor-grid">
              {position.board.map((row, r) => row.map((piece, c) => (
                <button type="button" key={`${r}-${c}`} className={`board-cell ${selection?.kind === "square" && selection.row === r && selection.col === c ? "selected" : ""}`} onClick={() => clickSquare(r, c)}>
                  {piece && <span className={`piece-face ${piece.color === "w" ? "piece-white" : ""} ${PIECE_LABEL[piece.code].length > 1 ? "piece-narrow" : ""}`}>{PIECE_LABEL[piece.code]}</span>}
                </button>
              )))}
            </div>
            <div className="rank-coords">{RANKS.map((r) => <span key={r}>{r}</span>)}</div>
          </div>
        </div>
        <ol className="recorded-moves">{recorded.map((m, i) => <li key={`${i}-${m}`}>{i % 2 === 0 ? "攻" : "玉"}: {m}</li>)}</ol>
      </div>
    </section>
  );
}
