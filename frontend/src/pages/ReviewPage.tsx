// 復習画面: 間違えた問題一覧とお気に入り問題一覧。
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, fetchNextMoveProblem, fetchNextMoveReview, fetchProblems, fetchReviewProblems, isNextMoveUnavailable, nextMoveVerdictLabel, type NextMoveReviewItem, type TsumeProblem } from "../api/client";
import { useNavigate } from "react-router-dom";
import { NextMoveDatabaseError } from "../components/NextMoveDatabaseError";
import { errorMessage } from "../components/nextMoveError";
import TsumeModeNav from "../components/TsumeModeNav";

type Tab = "wrong" | "favorite" | "next-move";

export default function ReviewPage() {
  const [tab, setTab] = useState<Tab>("wrong");
  const [wrongProblems, setWrongProblems] = useState<TsumeProblem[]>([]);
  const [favoriteProblems, setFavoriteProblems] = useState<TsumeProblem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [nextMoveProblems, setNextMoveProblems] = useState<NextMoveReviewItem[]>([]);
  const [nextMoveError, setNextMoveError] = useState<string | null>(null);
  const [startingWeak, setStartingWeak] = useState(false);
  const [weakStartError, setWeakStartError] = useState<unknown | null>(null);
  const [weakStartStatus, setWeakStartStatus] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const [wrong, fav] = await Promise.all([
        fetchReviewProblems(),
        fetchProblems({ favorite: true }),
      ]);
      setWrongProblems(wrong);
      setFavoriteProblems(fav);
      setError(null);
    } catch (e) {
      setError(`一覧の取得に失敗しました: ${e}`);
    }
  }, []);

  useEffect(() => {
    // マウント時に API から一覧を取得する。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);
  useEffect(() => {
    fetchNextMoveReview().then((data) => setNextMoveProblems(data.items))
      .catch((e) => setNextMoveError(`次の一手復習の取得に失敗しました: ${e}`));
  }, []);

  const list = tab === "wrong" ? wrongProblems : favoriteProblems;

  async function startWeak() {
    if (startingWeak) return;
    setStartingWeak(true); setWeakStartError(null); setWeakStartStatus(null);
    try {
      const problem = await fetchNextMoveProblem({ policy: "weak" });
      if (problem) navigate(`/next-move/${problem.id}?policy=weak`);
      else setWeakStartStatus("出題できる復習対象がありません。");
    } catch (error) {
      setWeakStartError(error);
    } finally {
      setStartingWeak(false);
    }
  }

  return (
    <div className="review-page" data-testid="review-page">
      <h1>復習</h1>
      <TsumeModeNav />
      {error && <div className="banner banner-error" role="alert">{error}</div>}
      <div className="segmented">
        <button
          type="button"
          className={tab === "wrong" ? "active" : ""}
          aria-pressed={tab === "wrong"}
          onClick={() => setTab("wrong")}
        >
          間違えた問題 ({wrongProblems.length})
        </button>
        <button
          type="button"
          className={tab === "favorite" ? "active" : ""}
          aria-pressed={tab === "favorite"}
          onClick={() => setTab("favorite")}
        >
          お気に入り ({favoriteProblems.length})
        </button>
        <button type="button" className={tab === "next-move" ? "active" : ""}
          aria-pressed={tab === "next-move"} onClick={() => setTab("next-move")}>
          次の一手 ({nextMoveProblems.length})
        </button>
      </div>
      {tab === "next-move" ? <section aria-labelledby="next-move-review-heading">
        <h2 id="next-move-review-heading">次の一手</h2>
        {nextMoveError && <div className="banner banner-error" role="alert">{nextMoveError}</div>}
        <button type="button" onClick={startWeak} disabled={startingWeak}>
          {startingWeak ? "問題を選択中..." : "復習対象から1問"}
        </button>
        {weakStartStatus && <p role="status" aria-live="polite">{weakStartStatus}</p>}
        {weakStartError instanceof ApiError && isNextMoveUnavailable(weakStartError)
          ? <NextMoveDatabaseError error={weakStartError} />
          : Boolean(weakStartError) && <div className="banner banner-error" role="alert">{errorMessage(weakStartError, "復習問題の取得に失敗しました")}</div>}
        {nextMoveProblems.length === 0 ? <p className="muted" role="status">復習対象の次の一手はありません。</p> :
          <div className="table-scroll"><table className="data-table"><thead><tr><th>戦型</th><th>最新判定</th><th>指した手</th><th>日時</th><th></th></tr></thead>
          <tbody>{nextMoveProblems.map((p) => <tr key={p.problem_key}><td>{p.opening_name}</td><td>{nextMoveVerdictLabel(p.verdict)}</td><td>{p.move_usi}</td><td>{p.answered_at}</td><td>{p.available && p.sample_id != null ? <Link className="button-link" to={`/next-move/${p.sample_id}?policy=weak`}>再挑戦</Link> : <span className="muted">利用不可: {p.unavailable_reason}</span>}</td></tr>)}</tbody></table></div>}
      </section> : list.length === 0 ? (
        <p className="muted">
          {tab === "wrong"
            ? "間違えた問題はありません。"
            : "お気に入り登録された問題はありません。"}
        </p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>問題</th>
              <th>手数</th>
              <th>正解</th>
              <th>不正解</th>
              <th>平均時間</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.id}>
                <td>{p.title}</td>
                <td>{p.mate_length}手</td>
                <td>{p.stats.correct_count}</td>
                <td>{p.stats.wrong_count}</td>
                <td>
                  {p.stats.avg_elapsed_ms != null
                    ? `${(p.stats.avg_elapsed_ms / 1000).toFixed(1)}秒`
                    : "-"}
                </td>
                <td>
                  <Link className="button-link" to={`/tsume?problem=${p.id}`}>
                    再挑戦
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
