// 「次の一手」挑戦画面。
// 着手前は候補手・評価値・PVを表示せず、盤面で1手指したあとに定跡DBの候補手と比較する。
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Color } from "tsshogi";
import { fetchLearningSample, fetchLearningSamples, type LearningSample } from "../api/client";
import { NextMoveCandidateComparison, NextMoveResultPanel } from "../components/NextMoveResultPanel";
import ShogiBoard from "../components/ShogiBoard";
import { useNextMoveSession } from "../hooks/useNextMoveSession";
import { positionFromSfen } from "../shogi/nextMove";

export default function NextMoveStudyPage() {
  const { id } = useParams();
  return <NextMoveStudyContent key={id ?? "missing"} id={id} />;
}

interface SampleState {
  /** どの問題IDに対する結果か(表示中IDと異なる間は loading 扱い) */
  id: number | null;
  sample: LearningSample | null;
  error: string | null;
}

interface SiblingsState {
  /** どの戦型に対する結果か */
  key: string | null;
  samples: LearningSample[];
}

function NextMoveStudyContent({ id }: { id: string | undefined }) {
  const sampleId = id && /^\d+$/.test(id) ? Number(id) : null;
  const [sampleState, setSampleState] = useState<SampleState>({ id: null, sample: null, error: null });
  // 同じ戦型の問題一覧(進捗表示と「次の問題」用)。取得に失敗しても出題自体は続行できる。
  const [siblings, setSiblings] = useState<SiblingsState>({ key: null, samples: [] });
  const [comparisonVisible, setComparisonVisible] = useState(false);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const sample = sampleState.id === sampleId ? sampleState.sample : null;
  const loadError = sampleState.id === sampleId ? sampleState.error : null;
  const loading = sampleId !== null && sampleState.id !== sampleId;
  const session = useNextMoveSession(sample);

  useEffect(() => {
    if (sampleId === null) return;
    let cancelled = false;
    fetchLearningSample(sampleId)
      .then((data) => {
        if (!cancelled) setSampleState({ id: sampleId, sample: data, error: null });
      })
      .catch((e) => {
        if (!cancelled) setSampleState({ id: sampleId, sample: null, error: `問題の取得に失敗しました: ${e}` });
      });
    return () => {
      cancelled = true;
    };
  }, [sampleId]);

  const openingKey = sample?.opening_key ?? null;
  useEffect(() => {
    if (!openingKey) return;
    let cancelled = false;
    fetchLearningSamples(openingKey, 100)
      .then((samples) => {
        if (!cancelled) setSiblings({ key: openingKey, samples });
      })
      .catch(() => {
        if (!cancelled) setSiblings({ key: openingKey, samples: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [openingKey]);

  // 「次の問題」で遷移してきた場合は見出しへフォーカスを移す(直接アクセス時は動かさない)。
  const autoFocusHeading = Boolean((location.state as { autoFocusHeading?: boolean } | null)?.autoFocusHeading);
  useEffect(() => {
    if (autoFocusHeading && !loading && sample) {
      headingRef.current?.focus();
    }
  }, [autoFocusHeading, loading, sample]);

  const basePosition = useMemo(() => (sample ? positionFromSfen(sample.sfen) : null), [sample]);
  const siblingSamples = siblings.key === openingKey ? siblings.samples : [];
  const currentIndex = sample ? siblingSamples.findIndex((s) => s.id === sample.id) : -1;
  const nextSample =
    currentIndex >= 0 && siblingSamples.length > 1
      ? siblingSamples[(currentIndex + 1) % siblingSamples.length]
      : null;

  if (sampleId === null) {
    return (
      <div className="next-move-page" data-testid="next-move-page">
        <Link to="/next-move">← 次の一手一覧へ</Link>
        <div className="banner banner-error" role="alert">この問題は見つかりませんでした。</div>
      </div>
    );
  }
  if (loading) {
    return (
      <div className="next-move-page" data-testid="next-move-page">
        <Link to="/next-move">← 次の一手一覧へ</Link>
        <p className="muted">問題を読み込み中...</p>
      </div>
    );
  }
  if (loadError || !sample) {
    return (
      <div className="next-move-page" data-testid="next-move-page">
        <Link to="/next-move">← 次の一手一覧へ</Link>
        <div className="banner banner-error" role="alert">{loadError ?? "この問題は見つかりませんでした。"}</div>
      </div>
    );
  }
  if (session.invalidPosition || !session.position) {
    return (
      <div className="next-move-page" data-testid="next-move-page">
        <Link to="/next-move">← 次の一手一覧へ</Link>
        <div className="banner banner-error" role="alert">この問題の局面データを読み込めませんでした。</div>
      </div>
    );
  }

  const answered = session.phase === "answered";
  const verdict = session.verdict;
  const progressLabel =
    currentIndex >= 0 ? `問題 ${currentIndex + 1} / ${siblingSamples.length}` : `問題 #${sample.sample_rank}`;
  const sideLabel = basePosition?.color === Color.BLACK ? "先手" : "後手";

  function handleRetry() {
    session.retry();
    setComparisonVisible(false);
  }

  return (
    <div className="next-move-page" data-testid="next-move-page">
      <Link to="/next-move">← 次の一手一覧へ</Link>
      <h1 tabIndex={-1} ref={headingRef} data-testid="next-move-heading">
        次の一手: {sample.opening_name}
      </h1>
      <p className="muted" data-testid="next-move-progress">
        {progressLabel}(戦型: {sample.opening_name})
      </p>
      <div className="player-layout">
        <div className="player-board">
          <div
            className={`banner ${answered && verdict && verdict.kind !== "unlisted" ? "banner-success" : "banner-info"}`}
            role="status"
            data-testid="next-move-feedback"
          >
            {answered && verdict
              ? `${verdict.label}: ${verdict.description}`
              : `${sideLabel}番です。この局面で、あなたなら次の一手をどう指しますか?盤面で1手指してください。`}
          </div>
          <ShogiBoard
            position={session.position}
            flipped={basePosition?.color === Color.WHITE}
            interactive={!answered}
            lastMoveTo={session.lastMoveTo}
            lastMoveFrom={session.lastMoveFrom}
            onUserMove={session.playMove}
          />
          {!answered && (
            <div className="board-controls next-move-controls">
              <button
                type="button"
                onClick={session.revealNextHint}
                disabled={!session.hasMoreHints}
                data-testid="next-move-hint-button"
              >
                ヒントを見る{session.revealedHints.length > 0 && `(${session.revealedHints.length}/2)`}
              </button>
            </div>
          )}
          {!answered && session.revealedHints.length > 0 && (
            <div className="hint-box" data-testid="next-move-hints">
              {session.revealedHints.map((hint) => (
                <p key={hint.stage}>ヒント{hint.stage}: {hint.text}</p>
              ))}
            </div>
          )}
          {answered && verdict && (
            <div className="post-clear-actions next-move-actions" data-testid="next-move-actions">
              <button
                type="button"
                onClick={() =>
                  nextSample && navigate(`/next-move/${nextSample.id}`, { state: { autoFocusHeading: true } })
                }
                disabled={!nextSample}
                data-testid="next-move-next-button"
              >
                次の問題
              </button>
              <button type="button" onClick={handleRetry} data-testid="next-move-retry-button">
                もう一度考える
              </button>
              <button
                type="button"
                onClick={() => setComparisonVisible((v) => !v)}
                aria-pressed={comparisonVisible}
                aria-expanded={comparisonVisible}
                data-testid="next-move-compare-button"
              >
                候補手を比較する
              </button>
              <Link to="/next-move" className="next-move-back-link">次の一手一覧へ戻る</Link>
            </div>
          )}
        </div>
        <div className="player-side">
          {answered && verdict ? (
            <>
              <NextMoveResultPanel verdict={verdict} basePosition={basePosition} source={sample.source} />
              {comparisonVisible && (
                <section className="opening-current" data-testid="next-move-comparison">
                  <h2>候補手の比較</h2>
                  <NextMoveCandidateComparison
                    candidates={sample.candidates}
                    basePosition={basePosition}
                    userMoveUsi={session.userMoveUsi}
                  />
                </section>
              )}
            </>
          ) : (
            <section className="opening-current" data-testid="next-move-question-note">
              <h2>考え方</h2>
              <p>{sideLabel}番の局面です。駒の配置と持ち駒を確認して、最善と思う一手を盤面で指してください。</p>
              <p className="muted">答え(定跡DBの候補手)は着手後に表示されます。</p>
            </section>
          )}
          <details className="next-move-details">
            <summary>局面の詳細情報(SFEN)</summary>
            <p className="muted">SFEN: <code>{sample.sfen}</code></p>
            <p className="muted">
              出典: {sample.source.name}
              {sample.source.license_name && ` / ライセンス: ${sample.source.license_name}`}
            </p>
          </details>
        </div>
      </div>
    </div>
  );
}
