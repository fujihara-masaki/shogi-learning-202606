// 「次の一手」問題一覧ページ。一覧本体は既存の NextMoveProblemList を再利用する。
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { ApiError, fetchNextMoveProblem, isNextMoveUnavailable } from "../api/client";
import { NextMoveDatabaseError } from "../components/NextMoveDatabaseError";
import { errorMessage } from "../components/nextMoveError";
import NextMoveProblemList from "../components/NextMoveProblemList";

export default function NextMovePage() {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<unknown | null>(null);
  const [startStatus, setStartStatus] = useState<string | null>(null);
  async function startAll() {
    if (starting) return;
    setStarting(true); setStartError(null); setStartStatus(null);
    try {
      const problem = await fetchNextMoveProblem({ policy: "random" });
      if (problem) navigate(`/next-move/${problem.id}?policy=random`);
      else setStartStatus("出題できる問題がありません。");
    } catch (error) {
      setStartError(error);
    } finally {
      setStarting(false);
    }
  }
  return (
    <div className="openings-page" data-testid="next-move-list-page">
      <h1>次の一手</h1>
      <p className="muted">
        実戦形の局面を見て、次の一手を自分で考える練習問題です。答え(定跡DBの候補手と評価値)は着手後に表示されます。
      </p>
      <button type="button" onClick={startAll} disabled={starting}>
        {starting ? "問題を選択中..." : "全戦型からランダムに1問"}
      </button>
      {startStatus && <p role="status" aria-live="polite">{startStatus}</p>}
      {startError instanceof ApiError && isNextMoveUnavailable(startError)
        ? <NextMoveDatabaseError error={startError} />
        : Boolean(startError) && <div className="banner banner-error" role="alert">{errorMessage(startError, "問題の取得に失敗しました")}</div>}
      <NextMoveProblemList />
    </div>
  );
}
