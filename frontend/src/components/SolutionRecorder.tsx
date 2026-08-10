import { useMemo, useState } from "react";
import { editorPieceToVisual } from "../appearance/adapters";
import { developmentThemeOverrides } from "../appearance/developmentThemes";
import type { BoardThemeId, PieceThemeId } from "../appearance/types";
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
import BoardSurface from "./shogi/BoardSurface";
import PieceFace from "./shogi/PieceFace";

interface Props {
  initialPosition: EditorPosition;
  onMovesChange: (solutionMoves: string[], opponentMoves: string[]) => void;
  pieceTheme?: PieceThemeId;
  boardTheme?: BoardThemeId;
}

type Selection =
  | { kind: "square"; row: number; col: number }
  | { kind: "hand"; color: Color; code: PieceCode };

const FILES = [9, 8, 7, 6, 5, 4, 3, 2, 1];
const RANKS = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];

export default function SolutionRecorder({ initialPosition, onMovesChange, pieceTheme, boardTheme }: Props) {
  const developmentThemes = developmentThemeOverrides();
  pieceTheme ??= developmentThemes.pieceTheme ?? "text-standard";
  boardTheme ??= developmentThemes.boardTheme ?? "board-standard";
  const [position, setPosition] = useState(() => clonePosition(initialPosition));
  const [selection, setSelection] = useState<Selection | null>(null);
  const [promoteNext, setPromoteNext] = useState(false);
  const [history, setHistory] = useState<EditorPosition[]>([]);
  const [recorded, setRecorded] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const files = useMemo(() => FILES, []);

  function emit(nextMoves: string[]) {
    const solution = nextMoves.filter((_, index) => index % 2 === 0);
    const opponent = nextMoves.filter((_, index) => index % 2 === 1);
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
    setHistory((items) => items.slice(0, -1));
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
      setHistory((items) => [...items, before]);
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
      if (piece && piece.color === position.turn) {
        setSelection({ kind: "square", row, col });
      }
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
      pushMove(
        `${squareToUsi(selection.row, selection.col)}${squareToUsi(row, col)}${promote ? "+" : ""}`,
      );
      return;
    }
    pushMove(`${selection.code.replace("+", "")}*${squareToUsi(row, col)}`);
  }

  function clickHand(color: Color, code: PieceCode) {
    if (color !== position.turn || (position.hands[color][code] ?? 0) <= 0) return;
    setSelection({ kind: "hand", color, code });
  }

  return (
    <section className="solution-recorder" data-testid="solution-recorder">
      <h2>盤面で解法手順を記録</h2>
      <p className="muted">
        攻め方の手は solution_moves、玉方の応手は opponent_moves に交互に自動振り分けします。
      </p>
      {error && <div className="banner banner-error" role="alert">{error}</div>}
      <div className="board-controls">
        <span className="banner banner-info">
          次: {recorded.length % 2 === 0 ? "攻め方(solution)" : "玉方(opponent)"} / 手番{" "}
          {position.turn === "b" ? "先手" : "後手"}
        </span>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={promoteNext}
            onChange={(e) => setPromoteNext(e.target.checked)}
          />
          次の盤上移動を成る
        </label>
        <button type="button" onClick={undo} disabled={history.length === 0}>
          1手戻す
        </button>
        <button type="button" onClick={reset}>
          記録リセット
        </button>
      </div>
      <div className="recorder-layout">
        <div className="recorder-hands">
          {(["w", "b"] as Color[]).map((color) => (
            <div key={color} className="hand-area">
              <span className="hand-label">{color === "b" ? "☗先手" : "☖後手"}</span>
              {HAND_PIECES.map((code) => {
                const count = position.hands[color][code] ?? 0;
                if (count <= 0) return null;
                return (
                  <button
                    type="button"
                    key={`${color}-${code}`}
                    className="hand-piece"
                    aria-label={`${color === "b" ? "先手" : "後手"}の持ち駒 ${PIECE_LABEL[code]} ${count}枚`}
                    aria-pressed={
                      selection?.kind === "hand" && selection.color === color && selection.code === code
                    }
                    onClick={() => clickHand(color, code)}
                  >
                    <PieceFace
                      pieceTheme={pieceTheme}
                      piece={editorPieceToVisual({ color, code })}
                      kingGlyph="all-gyoku"
                      variant="plain"
                    />
                    {count > 1 ? count : ""}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div>
          <div className="file-coords">
            {files.map((file) => (
              <span key={file}>{file}</span>
            ))}
          </div>
          <div className="board-row-container">
            <BoardSurface className="board-grid editor-grid" boardTheme={boardTheme}>
              {position.board.map((row, rowIndex) =>
                row.map((piece, colIndex) => (
                  <button
                    type="button"
                    key={`${rowIndex}-${colIndex}`}
                    className={`board-cell ${
                      selection?.kind === "square" &&
                      selection.row === rowIndex &&
                      selection.col === colIndex
                        ? "selected"
                        : ""
                    }`}
                    data-testid={`recorder-square-${9 - colIndex}-${rowIndex + 1}`}
                    aria-label={`${9 - colIndex}${RANKS[rowIndex]} ${
                      piece ? `${piece.color === "b" ? "先手" : "後手"}の${PIECE_LABEL[piece.code]}` : "空きマス"
                    }`}
                    onClick={() => clickSquare(rowIndex, colIndex)}
                  >
                    {piece && (
                      <PieceFace
                        pieceTheme={pieceTheme}
                        piece={editorPieceToVisual(piece)}
                        kingGlyph="all-gyoku"
                        variant="board"
                      />
                    )}
                  </button>
                )),
              )}
            </BoardSurface>
            <div className="rank-coords">
              {RANKS.map((rank) => (
                <span key={rank}>{rank}</span>
              ))}
            </div>
          </div>
        </div>
        <ol className="recorded-moves">
          {recorded.map((move, index) => (
            <li key={`${index}-${move}`}>
              {index % 2 === 0 ? "攻" : "玉"}: {move}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
