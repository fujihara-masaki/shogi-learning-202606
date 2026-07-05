// 指し手履歴の表示。
import { useEffect, useRef } from "react";
import type { AppliedMove } from "../shogi/tsume";

export default function MoveHistory({ moves }: { moves: AppliedMove[] }) {
  const listRef = useRef<HTMLOListElement | null>(null);

  useEffect(() => {
    // 最新手が見えるよう末尾へ自動スクロールする。
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [moves.length]);

  return (
    <div className="move-history">
      <h3>指し手履歴</h3>
      {moves.length === 0 ? (
        <p className="muted">まだ指し手はありません</p>
      ) : (
        <ol ref={listRef}>
          {moves.map((m, i) => (
            <li key={`${i}-${m.usi}`} className={i === moves.length - 1 ? "move-latest" : ""}>
              <span className="move-number">{i + 1}.</span> {m.text}
              <span className="move-usi">({m.usi})</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
