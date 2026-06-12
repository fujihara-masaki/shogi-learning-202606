// 詰め将棋 1 問をプレイする盤面 + 操作 UI(詰め将棋画面・復習画面で共用)。
import { useState } from "react";
import { Color } from "tsshogi";
import type { TsumeProblem } from "../api/client";
import { useTsumeSession, type SessionOutcome } from "../hooks/useTsumeSession";
import MoveHistory from "./MoveHistory";
import ShogiBoard from "./ShogiBoard";

interface Props {
  problem: TsumeProblem;
  onTerminal?: (outcome: SessionOutcome) => void;
}

export default function TsumePlayer({ problem, onTerminal }: Props) {
  const [flipped, setFlipped] = useState(false);
  const [hintLevel, setHintLevel] = useState(0);
  const session = useTsumeSession(problem, { onTerminal });

  const interactive =
    session.status === "playing" && session.position?.color === Color.BLACK;

  const nextSolutionUsi =
    problem.solution_moves[Math.ceil(session.moves.length / 2)] ?? null;

  const statusBanner = () => {
    switch (session.status) {
      case "cleared":
        return <div className="banner banner-success">🎉 正解!クリアしました</div>;
      case "wrong":
        return (
          <div className="banner banner-error">
            ✗ 不正解{session.wrongMoveText ? `(${session.wrongMoveText})` : ""}
            <div className="banner-actions">
              <button type="button" onClick={session.retry}>
                もう一度
              </button>
              <button type="button" onClick={session.showAnswer}>
                答えを見る
              </button>
            </div>
          </div>
        );
      case "opponent":
        return <div className="banner banner-info">玉方の応手…</div>;
      case "showing":
        return <div className="banner banner-info">答えを再生中…</div>;
      case "shown":
        return <div className="banner banner-info">答えの表示が終わりました</div>;
      default:
        return <div className="banner banner-info">{problem.mate_length}手詰:先手番です</div>;
    }
  };

  return (
    <div className="player-layout">
      <div className="player-board">
        {statusBanner()}
        {session.position && (
          <ShogiBoard
            position={session.position}
            flipped={flipped}
            interactive={interactive}
            lastMoveTo={session.lastMoveTo}
            onUserMove={session.handleUserMove}
          />
        )}
        <div className="board-controls">
          <button type="button" onClick={() => setFlipped((f) => !f)}>
            盤面反転
          </button>
          <button type="button" onClick={session.undo} disabled={!session.canUndo}>
            1手戻る
          </button>
          <button type="button" onClick={session.reset}>
            最初に戻る
          </button>
          <button
            type="button"
            onClick={() => setHintLevel((h) => Math.min(h + 1, 2))}
            disabled={session.status !== "playing"}
          >
            ヒント
          </button>
          <button
            type="button"
            onClick={session.showAnswer}
            disabled={session.status === "showing" || session.status === "cleared"}
          >
            答えを見る
          </button>
        </div>
        {hintLevel > 0 && session.status === "playing" && nextSolutionUsi && (
          <div className="hint-box">
            {hintLevel === 1
              ? `ヒント: 次の手は${nextSolutionUsi.includes("*") ? "持ち駒を打つ手" : "盤上の駒を動かす手"}です`
              : `ヒント: 次の正解手 (USI) は ${nextSolutionUsi} です`}
          </div>
        )}
        {(session.status === "cleared" || session.status === "shown") &&
          problem.explanation && (
            <div className="explanation-box">
              <h3>解説</h3>
              <p>{problem.explanation}</p>
            </div>
          )}
      </div>
      <div className="player-side">
        <MoveHistory moves={session.moves} />
        <div className="problem-meta">
          <p>
            ミス: {session.mistakeCount} 回 / 難易度: {"★".repeat(problem.difficulty)}
          </p>
          <p className="muted">
            タグ: {problem.tags.length > 0 ? problem.tags.join("、") : "なし"}
          </p>
        </div>
      </div>
    </div>
  );
}
