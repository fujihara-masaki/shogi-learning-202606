// 将棋盤 + 駒台コンポーネント。
// 駒は文字表示(後から画像に差し替える場合は PieceFace を変更する)。
import { useMemo, useState } from "react";
import type { ImmutablePosition, Move } from "tsshogi";
import { Color, Piece, PieceType, Square, handPieceTypes } from "tsshogi";

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

const RANK_KANJI = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];

interface PieceFaceProps {
  piece: Piece;
  flipped: boolean;
}

/** 駒1枚の見た目。画像駒に差し替える場合はここを変更する。 */
function PieceFace({ piece, flipped }: PieceFaceProps) {
  const text =
    piece.type === PieceType.KING && piece.color === Color.BLACK ? "王" : PIECE_KANJI[piece.type];
  const upsideDown = (piece.color === Color.WHITE) !== flipped;
  const cls = [
    "piece-face",
    upsideDown ? "piece-white" : "piece-black",
    text.length > 1 ? "piece-narrow" : "",
  ].join(" ");
  return <span className={cls}>{text}</span>;
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
  onUserMove: (move: Move) => void;
}

export default function ShogiBoard({
  position,
  flipped,
  interactive,
  lastMoveTo,
  onUserMove,
}: ShogiBoardProps) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<PendingPromotion | null>(null);

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
      setPendingPromotion({ base, promoted });
    } else if (canPromote) {
      onUserMove(promoted);
    } else if (canPlain) {
      onUserMove(base);
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

  function renderHand(color: Color, label: string) {
    const hand = position.hand(color);
    return (
      <div className={`hand-area ${color === Color.WHITE ? "hand-white" : "hand-black"}`}>
        <span className="hand-label">{label}</span>
        <div className="hand-pieces">
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
                draggable={interactive && color === position.color}
                onDragStart={() => handleHandActivate(color, pt)}
                onClick={() => handleHandActivate(color, pt)}
              >
                <PieceFace piece={new Piece(color, pt)} flipped={flipped} />
                {count > 1 && <span className="hand-count">{count}</span>}
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
    <div className="board-wrapper">
      {renderHand(topColor, topColor === Color.WHITE ? "☖後手" : "☗先手")}
      <div className="board-with-coords">
        <div className="file-coords">
          {files.map((f) => (
            <span key={f}>{f}</span>
          ))}
        </div>
        <div className="board-row-container">
          <div className="board-grid">
            {ranks.map((rank) =>
              files.map((file) => {
                const sq = new Square(file, rank);
                const piece = position.board.at(sq);
                const isSelected =
                  selection?.kind === "square" && selection.square.equals(sq);
                const isTarget = legalTargets.has(sq.index);
                const isLast = lastMoveTo?.equals(sq) ?? false;
                const cls = [
                  "board-cell",
                  isSelected ? "selected" : "",
                  isTarget ? "target" : "",
                  isLast ? "last-move" : "",
                ].join(" ");
                return (
                  <div
                    key={`${file}${rank}`}
                    className={cls}
                    data-square={`${file}${rank}`}
                    onClick={() => handleSquareActivate(sq)}
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
                        <PieceFace piece={piece} flipped={flipped} />
                      </span>
                    )}
                    {isTarget && !piece && <span className="target-dot" />}
                  </div>
                );
              }),
            )}
          </div>
          <div className="rank-coords">
            {ranks.map((r) => (
              <span key={r}>{RANK_KANJI[r - 1]}</span>
            ))}
          </div>
        </div>
      </div>
      {renderHand(bottomColor, bottomColor === Color.BLACK ? "☗先手" : "☖後手")}
      {pendingPromotion && (
        <div className="promotion-overlay">
          <div className="promotion-dialog">
            <p>成りますか?</p>
            <div className="promotion-buttons">
              <button
                type="button"
                onClick={() => {
                  onUserMove(pendingPromotion.promoted);
                  setPendingPromotion(null);
                }}
              >
                成る
              </button>
              <button
                type="button"
                onClick={() => {
                  onUserMove(pendingPromotion.base);
                  setPendingPromotion(null);
                }}
              >
                成らず
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
