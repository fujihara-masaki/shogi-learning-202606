import { Link } from "react-router-dom";
import { OPENING_LINES, countMainLineMoves } from "../shogi/openings";

export default function OpeningsPage() {
  return (
    <div className="openings-page" data-testid="openings-page">
      <h1>定跡学習</h1>
      <p className="muted">サンプル定跡を選び、盤面上で期待手を指して流れを覚えましょう。</p>
      <div className="opening-list" data-testid="opening-list">
        {OPENING_LINES.map((opening) => (
          <article key={opening.id} className="opening-card" data-testid="opening-card">
            <div>
              <p className="opening-category">{opening.category}</p>
              <h2>{opening.name}</h2>
              <p>{opening.description}</p>
              <p className="muted">手数: {countMainLineMoves(opening)}手</p>
            </div>
            <Link className="primary-link" to={`/openings/${opening.id}`}>
              学習する
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}
