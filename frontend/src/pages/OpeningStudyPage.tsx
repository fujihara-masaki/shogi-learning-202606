import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { type Move, type Square } from "tsshogi";
import { fetchBookCandidates, fetchLearningSample, fetchOpening, type BookCandidatesResponse } from "../api/client";
import MoveHistory from "../components/MoveHistory";
import ShogiBoard from "../components/ShogiBoard";
import {
  applyOpeningPath,
  expectedOpeningMove,
  findOpening,
  isExpectedOpeningMove,
  openingFromImportedLine,
  openingFromLearningSample,
  type OpeningLine,
} from "../shogi/openings";

export default function OpeningStudyPage() {
  const { id } = useParams();
  return <OpeningStudyContent key={id ?? "missing"} id={id} />;
}

function OpeningStudyContent({ id }: { id: string | undefined }) {
  const isSampleRoute = id?.startsWith("sample-") ?? false;
  const staticOpening = id ? findOpening(id) : undefined;
  const [importedOpening, setImportedOpening] = useState<OpeningLine | null>(null);
  const [sampleOpening, setSampleOpening] = useState<OpeningLine | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [path, setPath] = useState<number[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [hintVisible, setHintVisible] = useState(false);
  const [lastMoveTo, setLastMoveTo] = useState<Square | null>(null);

  useEffect(() => {
    if (!id || !isSampleRoute) return;
    const sampleId = Number(id.replace("sample-", ""));
    if (!Number.isFinite(sampleId)) return;
    let cancelled = false;
    fetchLearningSample(sampleId)
      .then((sample) => {
        if (!cancelled) setSampleOpening(openingFromLearningSample(sample));
      })
      .catch((e) => {
        if (!cancelled) setLoadError(`学習サンプルの取得に失敗しました: ${e}`);
      });
    return () => {
      cancelled = true;
    };
  }, [id, isSampleRoute]);

  useEffect(() => {
    if (!id || isSampleRoute || staticOpening || !/^\d+$/.test(id)) return;
    let cancelled = false;
    fetchOpening(Number(id))
      .then((opening) => {
        if (!cancelled) setImportedOpening(openingFromImportedLine(opening));
      })
      .catch((e) => {
        if (!cancelled) setLoadError(`定跡の取得に失敗しました: ${e}`);
      });
    return () => {
      cancelled = true;
    };
  }, [id, isSampleRoute, staticOpening]);

  const opening = staticOpening ?? (isSampleRoute ? sampleOpening : importedOpening);
  const state = useMemo(() => (opening ? applyOpeningPath(opening, path) : null), [opening, path]);
  const expected = useMemo(() => (opening ? expectedOpeningMove(opening, path) : null), [opening, path]);
  const currentChoices = state?.steps.length ? state.steps[state.steps.length - 1].node.next ?? [] : opening?.moves ?? [];
  const hasBranches = currentChoices.length > 1;
  const selectedBranchPath = state?.steps.map((step) => step.node.branchLabel).filter(Boolean).join(" → ") || "本線";
  const sourceNode = state?.steps.at(-1)?.node ?? expected;
  const currentSfen = state?.position.sfen ?? null;

  if (loadError) {
    return (
      <div className="opening-study-page" data-testid="opening-study-page">
        <Link to="/openings">← 定跡一覧へ</Link>
        <div className="banner banner-error">{loadError}</div>
      </div>
    );
  }
  if (!id) {
    return <Navigate to="/openings" replace />;
  }
  if (!opening || !state) {
    return (
      <div className="opening-study-page" data-testid="opening-study-page">
        <Link to="/openings">← 定跡一覧へ</Link>
        <p className="muted">定跡を読み込み中...</p>
      </div>
    );
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
    setLastMoveTo(move.to);
  }

  function stepForward() {
    if (!expected) return;
    setPath((prev) => [...prev, 0]);
    setFeedback(`再生: ${expected.notation}`);
    setHintVisible(false);
    setLastMoveTo(null);
  }

  function chooseBranch(index: number) {
    const node = currentChoices[index];
    if (!node) return;
    setPath((prev) => [...prev, index]);
    setFeedback(`分岐を選択: ${node.branchLabel || node.notation}`);
    setHintVisible(false);
    setLastMoveTo(null);
  }

  function switchBranch(stepIndex: number, branchIndex: number) {
    setPath((prev) => [...prev.slice(0, stepIndex), branchIndex]);
    setFeedback("分岐点まで戻して別分岐を選択しました");
    setHintVisible(false);
    setLastMoveTo(null);
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

  function goToEnd() {
    if (!opening) return;
    const nextPath: number[] = [];
    let choices = opening.moves;
    while (choices.length > 0) {
      nextPath.push(0);
      choices = choices[0].next ?? [];
    }
    setPath(nextPath);
    setFeedback("最後まで再生しました");
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
            {completed ? "この定跡手順を完了しました。Wikipediaで確認できる手順はここまでです。" : feedback ?? "盤面上で推奨手を指してください"}
            {hasBranches && <span className="branch-badge" data-testid="branch-badge">分岐あり</span>}
          </div>
          <ShogiBoard
            position={state.position}
            flipped={false}
            interactive={!completed}
            lastMoveTo={lastMoveTo}
            onUserMove={handleUserMove}
          />
          <div className="board-controls opening-replay-controls">
            <button type="button" onClick={reset} disabled={path.length === 0}>
              最初に戻る
            </button>
            <button type="button" onClick={undo} disabled={path.length === 0}>
              一手戻る
            </button>
            <button type="button" onClick={stepForward} disabled={completed}>
              一手進む
            </button>
            <button type="button" onClick={goToEnd} disabled={completed}>
              最後まで進む
            </button>
            <button type="button" onClick={() => setHintVisible((v) => !v)} disabled={completed}>
              ヒント
            </button>
          </div>
          {hintVisible && expected && <div className="hint-box">ヒント: {expected.hint}</div>}
          <section className="opening-branches" data-testid="opening-branches">
            <h2>分岐選択</h2>
            <p className="muted">現在の分岐パス: <strong>{selectedBranchPath}</strong></p>
            {hasBranches ? (
              <div className="branch-choice-list">
                {currentChoices.map((choice, index) => (
                  <button key={choice.id} type="button" onClick={() => chooseBranch(index)} className={index === 0 ? "branch-choice primary" : "branch-choice"}>
                    {choice.branchLabel || (index === 0 ? "本線" : `分岐${index + 1}`)}
                    <span>{choice.notation} ({choice.usi})</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="muted">この局面の分岐候補はありません。</p>
            )}
            {state.steps.some((step) => step.choices.length > 1) && (
              <div className="branch-history">
                <h3>通過した分岐</h3>
                {state.steps.map((step, stepIndex) => step.choices.length > 1 && (
                  <div key={`${step.node.id}-branches`} className="branch-choice-list compact">
                    {step.choices.map((choice, branchIndex) => (
                      <button key={choice.id} type="button" onClick={() => switchBranch(stepIndex, branchIndex)} disabled={path[stepIndex] === branchIndex}>
                        {choice.branchLabel || (branchIndex === 0 ? "本線" : `分岐${branchIndex + 1}`)}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </section>
          {sourceNode && (
            <section className="opening-source-note" aria-label="データ出典" data-testid="opening-source">
              <h2>データ出典</h2>
              <p>{sourceNode.sourceTitle || "出典未設定"}{sourceNode.sourceUrl && <>: <a href={sourceNode.sourceUrl} target="_blank" rel="noreferrer">{sourceNode.sourceUrl}</a></>}</p>
              {sourceNode.sourceSection && <p>セクション: {sourceNode.sourceSection}</p>}
              {sourceNode.license && <p>ライセンス: {sourceNode.sourceLicense || sourceNode.license}</p>}
              {sourceNode.sourceRetrievedAt && <p>取得日: {sourceNode.sourceRetrievedAt}</p>}
              {sourceNode.coverageStatus && <p>カバレッジ: {sourceNode.coverageStatus}</p>}
              {sourceNode.sourceNote && <p className="muted">{sourceNode.sourceNote}</p>}
            </section>
          )}
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
          {currentSfen && <BookCandidatesLoader key={currentSfen} sfen={currentSfen} />}
          <MoveHistory moves={state.moves} />
        </div>
      </div>
    </div>
  );
}

interface BookCandidatesState {
  response: BookCandidatesResponse | null;
  loading: boolean;
  error: string | null;
}

function BookCandidatesLoader({ sfen }: { sfen: string }) {
  const [state, setState] = useState<BookCandidatesState>({ response: null, loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    fetchBookCandidates(sfen)
      .then((response) => {
        if (!cancelled) setState({ response, loading: false, error: null });
      })
      .catch((e) => {
        if (!cancelled) {
          setState({ response: null, loading: false, error: `定跡候補の取得に失敗しました: ${e}` });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sfen]);

  return <BookCandidatesPanel response={state.response} loading={state.loading} error={state.error} sfen={sfen} />;
}

interface BookCandidatesPanelProps {
  response: BookCandidatesResponse | null;
  loading: boolean;
  error: string | null;
  sfen: string;
}

function BookCandidatesPanel({ response, loading, error, sfen }: BookCandidatesPanelProps) {
  return (
    <section className="opening-current book-candidates" data-testid="book-candidates">
      <h2>この局面の定跡候補</h2>
      {sfen && <p className="muted book-candidates-sfen">SFEN: <code>{sfen}</code></p>}
      {loading && <p className="muted">定跡候補を読み込み中...</p>}
      {error && <div className="banner banner-error">{error}</div>}
      {!loading && !error && response && response.candidates.length === 0 && (
        <p>この局面の定跡候補はありません。</p>
      )}
      {!loading && !error && response && response.candidates.length > 0 && (
        <ol className="book-candidate-list">
          {response.candidates.map((candidate, index) => (
            <li key={`${candidate.source_id}-${candidate.move_usi}-${index}`} className="book-candidate-item">
              <div className="book-candidate-main">
                <strong>{candidate.move_usi}</strong>
                {candidate.rank !== null && <span className="opening-category">#{candidate.rank}</span>}
              </div>
              <dl className="book-candidate-meta">
                {candidate.score !== null && (
                  <>
                    <dt>評価値</dt>
                    <dd>{candidate.score}</dd>
                  </>
                )}
                {candidate.depth !== null && (
                  <>
                    <dt>深さ</dt>
                    <dd>{candidate.depth}</dd>
                  </>
                )}
                {candidate.pv && (
                  <>
                    <dt>PV</dt>
                    <dd>{candidate.pv}</dd>
                  </>
                )}
                {candidate.raw && (
                  <>
                    <dt>コメント</dt>
                    <dd>{candidate.raw}</dd>
                  </>
                )}
                <dt>出典</dt>
                <dd>
                  {candidate.source_url ? (
                    <a href={candidate.source_url} target="_blank" rel="noreferrer">
                      {candidate.source_name}
                    </a>
                  ) : (
                    candidate.source_name
                  )}
                  {candidate.source_version && <span> ({candidate.source_version})</span>}
                </dd>
                {candidate.license_name && (
                  <>
                    <dt>ライセンス</dt>
                    <dd>{candidate.license_name}</dd>
                  </>
                )}
              </dl>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
