// 将棋盤 + 駒台コンポーネント。
// 駒は文字表示(後から画像に差し替える場合は PieceFace を変更する)。
// 盤面は WAI-ARIA APG の Grid パターンに沿い、キーボード(矢印キー + Enter/Space + Esc)でも操作できる。
import { useEffect, useMemo, useRef, useState } from "react";
import type { ImmutablePosition, Move } from "tsshogi";
import { Color, Piece, PieceType, Square, handPieceTypes } from "tsshogi";
import { tsshogiPieceToVisual } from "../appearance/adapters";
import { useAppearance } from "../appearance/useAppearance";
import type { BoardThemeId, PieceThemeId } from "../appearance/types";
import BoardSurface from "./shogi/BoardSurface";
import PieceFace from "./shogi/PieceFace";

const PIECE_KANJI: Record<string, string> = {
  pawn: "歩",
  lance: "香",
  knight: "桂",
  silver: "銀",
  gold: "金",
  bishop: "角",
  rook: "飛",
  king: "玉",
  promPawn: "と",
  promLance: "成香",
  promKnight: "成桂",
  promSilver: "成銀",
  horse: "馬",
  dragon: "龍",
};

// 読み上げ用の駒名(1文字表示だと分かりにくい駒のみ上書き)。
const PIECE_ARIA_NAME: Record<string, string> = {
  ...PIECE_KANJI,
  promPawn: "と金",
};

const RANK_KANJI = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];

function squareKey(sq: Square): string {
  return `${sq.file}${sq.rank}`;
}

function squareLabel(sq: Square): string {
  return `${sq.file}${RANK_KANJI[sq.rank - 1]}`;
}

function colorLabel(color: Color): string {
  return color === Color.BLACK ? "先手" : "後手";
}

type Selection =
  | { kind: "square"; square: Square }
  | { kind: "hand"; pieceType: PieceType; color: Color };

interface PendingPromotion {
  base: Move;
  promoted: Move;
}

export interface ShogiBoardProps {
  position: ImmutablePosition;
  flipped: boolean;
  /** 操作可能か(手番側の駒のみ動かせる) */
  interactive: boolean;
  /** 直前の指し手の移動先(ハイライト用、USI の to 座標) */
  lastMoveTo: Square | null;
  /** 直前の指し手の移動元(打ち駒の場合は null) */
  lastMoveFrom?: Square | null;
  onUserMove: (move: Move) => void;
  pieceTheme?: PieceThemeId;
  boardTheme?: BoardThemeId;
}

export default function ShogiBoard({
  position,
  flipped,
  interactive,
  lastMoveTo,
  lastMoveFrom = null,
  onUserMove,
  pieceTheme,
  boardTheme,
}: ShogiBoardProps) {
  const appearance = useAppearance();
  pieceTheme ??= appearance.pieceTheme;
  boardTheme ??= appearance.boardTheme;
  const [selection, setSelection] = useState<Selection | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<PendingPromotion | null>(null);
  // roving tabindex: 盤面全体で 1 つの Tab ストップを持ち、矢印キーでフォーカスセルを移す。
  const [focusedSq, setFocusedSq] = useState<Square>(() => new Square(5, 5));
  const gridRef = useRef<HTMLDivElement | null>(null);
  const cellRefs = useRef(new Map<string, HTMLDivElement | null>());
  const promoteButtonRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const returnFocusKeyRef = useRef<string | null>(null);

  // 表示順: 通常は筋 9→1・段 1→9。反転時は逆。
  const files = useMemo(() => {
    const f = [9, 8, 7, 6, 5, 4, 3, 2, 1];
    return flipped ? [...f].reverse() : f;
  }, [flipped]);
  const ranks = useMemo(() => {
    const r = [1, 2, 3, 4, 5, 6, 7, 8, 9];
    return flipped ? [...r].reverse() : r;
  }, [flipped]);

  const legalTargets = useMemo(() => {
    if (!selection || !interactive) {
      return new Set<number>();
    }
    const targets = new Set<number>();
    for (const to of Square.all) {
      const from = selection.kind === "square" ? selection.square : selection.pieceType;
      const move = position.createMove(from, to);
      if (!move) continue;
      if (position.isValidMove(move) || position.isValidMove(move.withPromote())) {
        targets.add(to.index);
      }
    }
    return targets;
  }, [selection, position, interactive]);

  // フォーカスセルの移動に追従する。盤面外にフォーカスがあるときは奪わない。
  useEffect(() => {
    const grid = gridRef.current;
    if (!grid || !grid.contains(document.activeElement)) return;
    cellRefs.current.get(squareKey(focusedSq))?.focus();
  }, [focusedSq]);

  // 成り選択ダイアログを開いたら最初のボタンへフォーカスを移す。
  useEffect(() => {
    if (pendingPromotion) {
      promoteButtonRef.current?.focus();
    }
  }, [pendingPromotion]);

  function clearSelection() {
    setSelection(null);
  }

  function emitMove(to: Square) {
    if (!selection) return;
    const from = selection.kind === "square" ? selection.square : selection.pieceType;
    const base = position.createMove(from, to);
    if (!base) return;
    const canPlain = position.isValidMove(base);
    const promoted = base.withPromote();
    const canPromote = selection.kind === "square" && position.isValidMove(promoted);
    clearSelection();
    if (canPlain && canPromote) {
      returnFocusKeyRef.current = squareKey(to);
      setFocusedSq(to);
      setPendingPromotion({ base, promoted });
    } else if (canPromote) {
      onUserMove(promoted);
    } else if (canPlain) {
      onUserMove(base);
    }
  }

  function closePromotion(move: Move | null) {
    setPendingPromotion(null);
    if (move) onUserMove(move);
    const key = returnFocusKeyRef.current;
    returnFocusKeyRef.current = null;
    if (key) {
      // ダイアログ消滅後に移動先セルへフォーカスを戻す。
      requestAnimationFrame(() => cellRefs.current.get(key)?.focus());
    }
  }

  function handleSquareActivate(sq: Square) {
    if (!interactive || pendingPromotion) return;
    const piece = position.board.at(sq);
    if (selection && legalTargets.has(sq.index)) {
      emitMove(sq);
      return;
    }
    if (piece && piece.color === position.color) {
      setSelection({ kind: "square", square: sq });
    } else {
      clearSelection();
    }
  }

  function handleHandActivate(color: Color, pieceType: PieceType) {
    if (!interactive || pendingPromotion) return;
    if (color !== position.color) return;
    if (position.hand(color).count(pieceType) <= 0) return;
    setSelection({ kind: "hand", pieceType, color });
  }

  function handleGridKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (pendingPromotion) return;
    let nextFile = focusedSq.file;
    let nextRank = focusedSq.rank;
    switch (e.key) {
      case "ArrowLeft":
        nextFile = flipped ? nextFile - 1 : nextFile + 1;
        break;
      case "ArrowRight":
        nextFile = flipped ? nextFile + 1 : nextFile - 1;
        break;
      case "ArrowUp":
        nextRank = flipped ? nextRank + 1 : nextRank - 1;
        break;
      case "ArrowDown":
        nextRank = flipped ? nextRank - 1 : nextRank + 1;
        break;
      case "Home":
        nextFile = files[0];
        break;
      case "End":
        nextFile = files[files.length - 1];
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        handleSquareActivate(focusedSq);
        return;
      default:
        return;
    }
    e.preventDefault();
    nextFile = Math.min(9, Math.max(1, nextFile));
    nextRank = Math.min(9, Math.max(1, nextRank));
    if (nextFile !== focusedSq.file || nextRank !== focusedSq.rank) {
      setFocusedSq(new Square(nextFile, nextRank));
    }
  }

  // Escape は盤面セル・持ち駒ボタンのどちらにフォーカスがあっても選択解除できるよう、
  // board-wrapper 全体で受ける(成りダイアログの Escape は stopPropagation 済みで届かない)。
  function handleWrapperKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Escape" || pendingPromotion) return;
    clearSelection();
  }

  function handleDialogKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      closePromotion(null);
      return;
    }
    if (e.key === "Tab") {
      const buttons = dialogRef.current?.querySelectorAll("button");
      if (!buttons || buttons.length === 0) return;
      const list = Array.from(buttons);
      const index = list.indexOf(document.activeElement as HTMLButtonElement);
      e.preventDefault();
      const next = e.shiftKey
        ? index <= 0
          ? list.length - 1
          : index - 1
        : index >= list.length - 1
          ? 0
          : index + 1;
      list[next].focus();
    }
  }

  function cellAriaLabel(sq: Square, piece: Piece | null, flags: { selected: boolean; target: boolean; last: boolean }): string {
    const parts = [squareLabel(sq)];
    if (piece) {
      const name =
        piece.type === PieceType.KING && piece.color === Color.BLACK
          ? "王"
          : PIECE_ARIA_NAME[piece.type];
      parts.push(`${colorLabel(piece.color)}の${name}`);
    } else {
      parts.push("空きマス");
    }
    if (flags.selected) parts.push("選択中");
    if (flags.target) parts.push("移動可能");
    if (flags.last) parts.push("直前の移動先");
    return parts.join(" ");
  }

  function renderHand(color: Color, label: string) {
    const hand = position.hand(color);
    return (
      <div className={`hand-area ${color === Color.WHITE ? "hand-white" : "hand-black"}`}>
        <span className="hand-label" aria-hidden="true">{label}</span>
        <div className="hand-pieces" role="group" aria-label={`${colorLabel(color)}の持ち駒`}>
          {handPieceTypes.map((pt) => {
            const count = hand.count(pt);
            if (count === 0) return null;
            const selected =
              selection?.kind === "hand" && selection.color === color && selection.pieceType === pt;
            return (
              <button
                key={pt}
                type="button"
                className={`hand-piece ${selected ? "selected" : ""}`}
                data-hand-piece={`${color}-${pt}`}
                aria-label={`${colorLabel(color)}の持ち駒 ${PIECE_ARIA_NAME[pt]} ${count}枚`}
                aria-pressed={selected}
                draggable={interactive && color === position.color}
                onDragStart={() => handleHandActivate(color, pt)}
                onClick={() => handleHandActivate(color, pt)}
              >
                <PieceFace
                  pieceTheme={pieceTheme}
                  piece={tsshogiPieceToVisual(new Piece(color, pt))}
                  flipped={flipped}
                  kingGlyph="black-ou-white-gyoku"
                  variant="hand"
                />
                {count > 1 && <span className="hand-count" aria-hidden="true">{count}</span>}
              </button>
            );
          })}
          {hand.counts.every((c) => c.count === 0) && <span className="hand-empty">なし</span>}
        </div>
      </div>
    );
  }

  const topColor = flipped ? Color.BLACK : Color.WHITE;
  const bottomColor = flipped ? Color.WHITE : Color.BLACK;

  return (
    <div className="board-wrapper" data-testid="shogi-board" onKeyDown={handleWrapperKeyDown}>
      <div className="board-turn" data-testid="turn-indicator">
        手番: {position.color === Color.BLACK ? "▲先手" : "△後手"}
      </div>
      {renderHand(topColor, topColor === Color.WHITE ? "☖後手" : "☗先手")}
      <div className="board-with-coords">
        <div className="file-coords" aria-hidden="true">
          {files.map((f) => (
            <span key={f}>{f}</span>
          ))}
        </div>
        <div className="board-row-container">
          <BoardSurface
            boardTheme={boardTheme}
            className="board-grid"
            role="grid"
            aria-label="将棋盤"
            ref={gridRef}
            onKeyDown={handleGridKeyDown}
          >
            {ranks.map((rank) => (
              <div key={rank} className="board-row" role="row">
                {files.map((file) => {
                  const sq = new Square(file, rank);
                  const piece = position.board.at(sq);
                  const isSelected =
                    selection?.kind === "square" && selection.square.equals(sq);
                  const isTarget = legalTargets.has(sq.index);
                  const isLast = lastMoveTo?.equals(sq) ?? false;
                  const isLastFrom = lastMoveFrom?.equals(sq) ?? false;
                  const isFocused = focusedSq.equals(sq);
                  const cls = [
                    "board-cell",
                    isSelected ? "selected" : "",
                    isTarget ? "target" : "",
                    isLast ? "last-move" : "",
                    isLastFrom ? "last-move-from" : "",
                  ].join(" ");
                  return (
                    <div
                      key={`${file}${rank}`}
                      ref={(el) => {
                        cellRefs.current.set(`${file}${rank}`, el);
                      }}
                      role="gridcell"
                      tabIndex={isFocused ? 0 : -1}
                      aria-label={cellAriaLabel(sq, piece, {
                        selected: isSelected,
                        target: isTarget,
                        last: isLast,
                      })}
                      aria-selected={isSelected}
                      className={cls}
                      data-square={`${file}${rank}`}
                      onClick={() => {
                        setFocusedSq(sq);
                        handleSquareActivate(sq);
                      }}
                      onDragOver={(e) => {
                        if (isTarget) e.preventDefault();
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (isTarget) emitMove(sq);
                      }}
                    >
                      {piece && (
                        <span
                          draggable={interactive && piece.color === position.color}
                          onDragStart={() => handleSquareActivate(sq)}
                          className="piece-holder"
                        >
                          <PieceFace
                            pieceTheme={pieceTheme}
                            piece={tsshogiPieceToVisual(piece)}
                            flipped={flipped}
                            kingGlyph="black-ou-white-gyoku"
                            variant="board"
                          />
                        </span>
                      )}
                      {isTarget && !piece && <span className="target-dot" />}
                    </div>
                  );
                })}
              </div>
            ))}
          </BoardSurface>
          <div className="rank-coords" aria-hidden="true">
            {ranks.map((r) => (
              <span key={r}>{RANK_KANJI[r - 1]}</span>
            ))}
          </div>
        </div>
      </div>
      {renderHand(bottomColor, bottomColor === Color.BLACK ? "☗先手" : "☖後手")}
      {pendingPromotion && (
        <div className="promotion-overlay">
          <div
            className="promotion-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="成り選択"
            ref={dialogRef}
            onKeyDown={handleDialogKeyDown}
          >
            <p>成りますか?</p>
            <div className="promotion-buttons">
              <button
                type="button"
                ref={promoteButtonRef}
                onClick={() => closePromotion(pendingPromotion.promoted)}
              >
                成る
              </button>
              <button type="button" onClick={() => closePromotion(pendingPromotion.base)}>
                成らず
              </button>
              <button type="button" onClick={() => closePromotion(null)}>
                キャンセル
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
