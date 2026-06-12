// タイムアタック画面: 連続出題 + 経過時間計測 + 結果保存。
import { useCallback, useEffect, useRef, useState } from "react";
import { Color } from "tsshogi";
import {
  fetchProblems,
  postProblemResult,
  postTimeAttackResult,
  type TsumeProblem,
} from "../api/client";
import ShogiBoard from "../components/ShogiBoard";
import { useTsumeSession, type SessionOutcome } from "../hooks/useTsumeSession";

type Phase = "setup" | "playing" | "finished";

interface Summary {
  correct: number;
  missed: number;
  elapsedMs: number;
  total: number;
}

function formatMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function TimeAttackPage() {
  const [phase, setPhase] = useState<Phase>("setup");
  const [mateLength, setMateLength] = useState(1);
  const [totalQuestions, setTotalQuestions] = useState(10);
  const [queue, setQueue] = useState<TsumeProblem[]>([]);
  const [index, setIndex] = useState(0);
  const [correct, setCorrect] = useState(0);
  const [missed, setMissed] = useState(0);
  const [startedAt, setStartedAt] = useState(0);
  const [now, setNow] = useState(0);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<"correct" | "wrong" | null>(null);
  const advanceTimer = useRef<number | null>(null);

  useEffect(() => {
    if (phase !== "playing") return;
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [phase]);

  useEffect(() => {
    return () => {
      if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
    };
  }, []);

  const start = async () => {
    try {
      const fetched = await fetchProblems({
        mate_length: mateLength,
        random_order: true,
        limit: totalQuestions,
      });
      if (fetched.length === 0) {
        setError("この難易度の問題がありません");
        return;
      }
      // 問題数が足りない場合は循環して埋める(サンプルデータでも10問遊べるように)。
      // 同一問題が連続してもセッションがリセットされるよう、参照は問題ごとに分ける。
      const filled: TsumeProblem[] = [];
      for (let i = 0; i < totalQuestions; i += 1) {
        filled.push({ ...fetched[i % fetched.length] });
      }
      setQueue(filled);
      setIndex(0);
      setCorrect(0);
      setMissed(0);
      setSummary(null);
      setError(null);
      setFeedback(null);
      const t = Date.now();
      setStartedAt(t);
      setNow(t);
      setPhase("playing");
    } catch (e) {
      setError(`問題の取得に失敗しました: ${e}`);
    }
  };

  const finish = useCallback(
    async (finalCorrect: number, finalMissed: number) => {
      const elapsedMs = Date.now() - startedAt;
      const result: Summary = {
        correct: finalCorrect,
        missed: finalMissed,
        elapsedMs,
        total: totalQuestions,
      };
      setSummary(result);
      setPhase("finished");
      try {
        await postTimeAttackResult({
          mode: "normal",
          mate_length: mateLength,
          total_questions: totalQuestions,
          correct_count: finalCorrect,
          mistake_count: finalMissed,
          elapsed_ms: elapsedMs,
        });
      } catch (e) {
        setError(`結果の保存に失敗しました: ${e}`);
      }
    },
    [startedAt, totalQuestions, mateLength],
  );

  const currentProblem = phase === "playing" ? queue[index] ?? null : null;

  const handleTerminal = useCallback(
    (outcome: SessionOutcome) => {
      const problem = queue[index];
      if (problem) {
        // 学習履歴にも記録する(復習モードに反映される)
        postProblemResult(problem.id, {
          is_correct: outcome.cleared,
          elapsed_ms: outcome.elapsedMs,
          mistake_count: outcome.mistakeCount,
        }).catch(() => undefined);
      }
      const nextCorrect = correct + (outcome.cleared ? 1 : 0);
      const nextMissed = missed + (outcome.cleared ? 0 : 1);
      setCorrect(nextCorrect);
      setMissed(nextMissed);
      setFeedback(outcome.cleared ? "correct" : "wrong");
      advanceTimer.current = window.setTimeout(() => {
        setFeedback(null);
        if (index + 1 >= totalQuestions) {
          finish(nextCorrect, nextMissed);
        } else {
          setIndex((i) => i + 1);
        }
      }, 900);
    },
    [queue, index, correct, missed, totalQuestions, finish],
  );

  const session = useTsumeSession(currentProblem, {
    failFast: true,
    onTerminal: handleTerminal,
  });

  const interactive =
    session.status === "playing" && session.position?.color === Color.BLACK;

  return (
    <div className="time-attack-page">
      <h1>タイムアタック</h1>
      {error && <div className="banner banner-error">{error}</div>}

      {phase === "setup" && (
        <div className="ta-setup">
          <div className="form-row">
            <span>難易度:</span>
            <div className="segmented">
              {[1, 3, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  className={mateLength === n ? "active" : ""}
                  onClick={() => setMateLength(n)}
                >
                  {n}手詰
                </button>
              ))}
            </div>
          </div>
          <div className="form-row">
            <span>問題数:</span>
            <div className="segmented">
              {[5, 10].map((n) => (
                <button
                  key={n}
                  type="button"
                  className={totalQuestions === n ? "active" : ""}
                  onClick={() => setTotalQuestions(n)}
                >
                  {n}問
                </button>
              ))}
            </div>
          </div>
          <p className="muted">
            ※ 1問でも間違えるとその問題はミスとなり、次の問題に進みます。
          </p>
          <button type="button" className="primary" onClick={start}>
            スタート
          </button>
        </div>
      )}

      {phase === "playing" && currentProblem && (
        <div className="ta-playing">
          <div className="ta-status">
            <span>
              第 {index + 1} / {totalQuestions} 問
            </span>
            <span className="ta-timer">⏱ {formatMs(now - startedAt)}</span>
            <span>
              ○ {correct} / ✗ {missed}
            </span>
          </div>
          <p className="ta-problem-title">
            {currentProblem.mate_length}手詰: {currentProblem.title}
          </p>
          {feedback && (
            <div className={`banner ${feedback === "correct" ? "banner-success" : "banner-error"}`}>
              {feedback === "correct" ? "○ 正解!" : "✗ ミス!次の問題へ"}
            </div>
          )}
          {session.position && (
            <ShogiBoard
              position={session.position}
              flipped={false}
              interactive={interactive && !feedback}
              lastMoveTo={session.lastMoveTo}
              onUserMove={session.handleUserMove}
            />
          )}
        </div>
      )}

      {phase === "finished" && summary && (
        <div className="ta-result">
          <h2>結果</h2>
          <table className="data-table">
            <tbody>
              <tr>
                <th>正解数</th>
                <td>
                  {summary.correct} / {summary.total}
                </td>
              </tr>
              <tr>
                <th>ミス数</th>
                <td>{summary.missed}</td>
              </tr>
              <tr>
                <th>合計時間</th>
                <td>{formatMs(summary.elapsedMs)}</td>
              </tr>
            </tbody>
          </table>
          <div className="board-controls">
            <button type="button" className="primary" onClick={() => setPhase("setup")}>
              もう一度挑戦
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
