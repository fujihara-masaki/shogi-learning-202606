import { useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { type Move, type Square } from "tsshogi";
import MoveHistory from "../components/MoveHistory";
import ShogiBoard from "../components/ShogiBoard";
import {
  applyOpeningPath,
  expectedOpeningMove,
  findOpening,
  isExpectedOpeningMove,
} from "../shogi/openings";

export default function OpeningStudyPage() {
  const { id } = useParams();
  const opening = id ? findOpening(id) : undefined;
  const [path, setPath] = useState<number[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [hintVisible, setHintVisible] = useState(false);
  const [lastMoveTo, setLastMoveTo] = useState<Square | null>(null);

  const state = useMemo(() => (opening ? applyOpeningPath(opening, path) : null), [opening, path]);
  const expected = useMemo(() => (opening ? expectedOpeningMove(opening, path) : null), [opening, path]);

  if (!opening || !state) {
    return <Navigate to="/openings" replace />;
  }

  const completed = expected === null;

  function handleUserMove(move: Move) {
    if (!expected) return;
    if (!isExpectedOpeningMove(move, expected)) {
      setFeedback(`不正解です。ヒント: ${expected.hint}`);
      setHintVisible(true);
      return;
    }
    setPath((prev) => [...prev, 0]);
    setFeedback(`正解: ${expected.notation}`);
    setHintVisible(false);
    setLastMoveTo(move.to);
  }

  function undo() {
    setPath((prev) => prev.slice(0, -1));
    setFeedback(null);
    setHintVisible(false);
    setLastMoveTo(null);
  }

  function reset() {
    setPath([]);
    setFeedback(null);
    setHintVisible(false);
    setLastMoveTo(null);
  }

  return (
    <div className="opening-study-page" data-testid="opening-study-page">
      <Link to="/openings">← 定跡一覧へ</Link>
      <h1>{opening.name}</h1>
      <p className="muted">{opening.category} / {opening.description}</p>
      <div className="player-layout">
        <div className="player-board">
          <div
            className={`banner ${feedback?.startsWith("不正解") ? "banner-error" : completed ? "banner-success" : "banner-info"}`}
            data-testid="opening-feedback"
          >
            {completed ? "この定跡手順を完了しました" : feedback ?? "盤面上で推奨手を指してください"}
          </div>
          <ShogiBoard
            position={state.position}
            flipped={false}
            interactive={!completed}
            lastMoveTo={lastMoveTo}
            onUserMove={handleUserMove}
          />
          <div className="board-controls">
            <button type="button" onClick={() => setHintVisible((v) => !v)} disabled={completed}>
              ヒント
            </button>
            <button type="button" onClick={undo} disabled={path.length === 0}>
              1手戻る
            </button>
            <button type="button" onClick={reset}>
              最初から
            </button>
          </div>
          {hintVisible && expected && <div className="hint-box">ヒント: {expected.hint}</div>}
        </div>
        <div className="player-side">
          <section className="opening-current" data-testid="opening-current-move">
            <h2>現在の推奨手</h2>
            {expected ? (
              <>
                <p><strong>{expected.notation}</strong> <span className="move-usi">({expected.usi})</span></p>
                <h3>解説</h3>
                <p>{expected.explanation}</p>
                <h3>狙い</h3>
                <p>{expected.aim}</p>
              </>
            ) : (
              <p>すべての手順を学習しました。</p>
            )}
          </section>
          <MoveHistory moves={state.moves} />
        </div>
      </div>
    </div>
  );
}
