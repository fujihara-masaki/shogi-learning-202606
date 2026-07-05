// 復習画面: 間違えた問題一覧とお気に入り問題一覧。
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchProblems, fetchReviewProblems, type TsumeProblem } from "../api/client";

type Tab = "wrong" | "favorite";

export default function ReviewPage() {
  const [tab, setTab] = useState<Tab>("wrong");
  const [wrongProblems, setWrongProblems] = useState<TsumeProblem[]>([]);
  const [favoriteProblems, setFavoriteProblems] = useState<TsumeProblem[]>([]);
  const [error, setError] = useState<string | null>(null);

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

  const list = tab === "wrong" ? wrongProblems : favoriteProblems;

  return (
    <div className="review-page" data-testid="review-page">
      <h1>復習</h1>
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
      </div>
      {list.length === 0 ? (
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
