// 「次の一手」問題一覧ページ。一覧本体は既存の NextMoveProblemList を再利用する。
import { useNavigate } from "react-router-dom";
import { fetchNextMoveProblem } from "../api/client";
import NextMoveProblemList from "../components/NextMoveProblemList";

export default function NextMovePage() {
  const navigate = useNavigate();
  async function startAll() {
    const problem = await fetchNextMoveProblem({ policy: "random" });
    if (problem) navigate(`/next-move/${problem.id}?policy=random`);
  }
  return (
    <div className="openings-page" data-testid="next-move-list-page">
      <h1>次の一手</h1>
      <p className="muted">
        実戦形の局面を見て、次の一手を自分で考える練習問題です。答え(定跡DBの候補手と評価値)は着手後に表示されます。
      </p>
      <button type="button" onClick={startAll}>全戦型からランダムに1問</button>
      <NextMoveProblemList />
    </div>
  );
}
