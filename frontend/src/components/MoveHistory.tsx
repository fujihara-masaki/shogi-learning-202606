// 指し手履歴の表示。
import type { AppliedMove } from "../shogi/tsume";

export default function MoveHistory({ moves }: { moves: AppliedMove[] }) {
  return (
    <div className="move-history">
      <h3>指し手履歴</h3>
      {moves.length === 0 ? (
        <p className="muted">まだ指し手はありません</p>
      ) : (
        <ol>
          {moves.map((m, i) => (
            <li key={`${i}-${m.usi}`}>
              <span className="move-number">{i + 1}.</span> {m.text}
              <span className="move-usi">({m.usi})</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
