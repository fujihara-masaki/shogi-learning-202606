import { useMemo, useState } from "react";
import { editorPieceToVisual } from "../appearance/adapters";
import type { BoardThemeId, PieceThemeId } from "../appearance/types";
import {
  HAND_PIECES,
  PIECE_LABEL,
  PIECES,
  clonePosition,
  type Color,
  type EditorPiece,
  type EditorPosition,
} from "../shogi/editor";
import BoardSurface from "./shogi/BoardSurface";
import PieceFace from "./shogi/PieceFace";

interface Props {
  position: EditorPosition;
  onChange: (next: EditorPosition) => void;
  pieceTheme?: PieceThemeId;
  boardTheme?: BoardThemeId;
}

type Tool = { kind: "piece"; piece: EditorPiece } | { kind: "erase" } | { kind: "move" };

const RANKS = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];
const FILES = [9, 8, 7, 6, 5, 4, 3, 2, 1];

function pieceText(piece: EditorPiece) {
  return PIECE_LABEL[piece.code];
}

export default function EditorBoard({ position, onChange, pieceTheme = "text-standard", boardTheme = "board-standard" }: Props) {
  const [tool, setTool] = useState<Tool>({
    kind: "piece",
    piece: { color: "b", code: "P" },
  });
  const [selected, setSelected] = useState<[number, number] | null>(null);
  const files = useMemo(() => FILES, []);

  function click(row: number, col: number) {
    const next = clonePosition(position);
    if (tool.kind === "erase") {
      next.board[row][col] = null;
    }
    if (tool.kind === "piece") {
      next.board[row][col] = { ...tool.piece };
    }
    if (tool.kind === "move") {
      if (selected) {
        next.board[row][col] = next.board[selected[0]][selected[1]];
        next.board[selected[0]][selected[1]] = null;
        setSelected(null);
      } else if (next.board[row][col]) {
        setSelected([row, col]);
      }
    }
    onChange(next);
  }

  function updateHand(color: Color, code: string, value: string) {
    const next = clonePosition(position);
    next.hands[color][code] = Math.max(0, Number(value) || 0);
    onChange(next);
  }

  return (
    <div className="editor-board-layout" data-testid="editor-board">
      <div className="editor-tools">
        <strong>配置する駒</strong>
        <div className="tool-row">
          <button
            type="button"
            className={tool.kind === "move" ? "active" : ""}
            aria-pressed={tool.kind === "move"}
            onClick={() => setTool({ kind: "move" })}
          >
            移動
          </button>
          <button
            type="button"
            className={tool.kind === "erase" ? "active" : ""}
            aria-pressed={tool.kind === "erase"}
            onClick={() => setTool({ kind: "erase" })}
          >
            削除
          </button>
        </div>
        {(["b", "w"] as Color[]).map((color) => (
          <div key={color}>
            <div className="muted">{color === "b" ? "☗先手" : "☖後手"}</div>
            <div className="piece-palette">
              {PIECES.map((code) => (
                <button
                  type="button"
                  key={`${color}-${code}`}
                  className={
                    tool.kind === "piece" && tool.piece.color === color && tool.piece.code === code
                      ? "active"
                      : ""
                  }
                  aria-pressed={
                    tool.kind === "piece" && tool.piece.color === color && tool.piece.code === code
                  }
                  aria-label={`${color === "b" ? "先手" : "後手"}の${PIECE_LABEL[code]}を配置`}
                  onClick={() => setTool({ kind: "piece", piece: { color, code } })}
                >
                  <PieceFace
                    pieceTheme={pieceTheme}
                    piece={editorPieceToVisual({ color, code })}
                    kingGlyph="all-gyoku"
                    variant="plain"
                  />
                </button>
              ))}
            </div>
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
                    selected?.[0] === rowIndex && selected?.[1] === colIndex ? "selected" : ""
                  }`}
                  data-testid={`editor-square-${9 - colIndex}-${rowIndex + 1}`}
                  aria-label={`${9 - colIndex}${RANKS[rowIndex]} ${
                    piece ? `${piece.color === "b" ? "先手" : "後手"}の${pieceText(piece)}` : "空きマス"
                  }`}
                  onClick={() => click(rowIndex, colIndex)}
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
      <div className="editor-hands">
        {(["b", "w"] as Color[]).map((color) => (
          <fieldset key={color}>
            <legend>{color === "b" ? "先手の持ち駒" : "後手の持ち駒"}</legend>
            {HAND_PIECES.map((code) => (
              <label key={code}>
                {PIECE_LABEL[code]}
                <input
                  type="number"
                  min="0"
                  value={position.hands[color][code] ?? 0}
                  onChange={(e) => updateHand(color, code, e.target.value)}
                />
              </label>
            ))}
          </fieldset>
        ))}
      </div>
    </div>
  );
}
