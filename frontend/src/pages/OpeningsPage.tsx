import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchOpeningTags, fetchOpenings, type OpeningSummary, type OpeningTagSummary } from "../api/client";
import { OPENING_LINES, countMainLineMoves } from "../shogi/openings";

export default function OpeningsPage() {
  const [tags, setTags] = useState<OpeningTagSummary[]>([]);
  const [selectedTag, setSelectedTag] = useState("");
  const [imported, setImported] = useState<OpeningSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchOpeningTags(), fetchOpenings(selectedTag || undefined)])
      .then(([tagList, openingList]) => {
        if (cancelled) return;
        setTags(tagList);
        setImported(openingList);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(`インポート定跡の取得に失敗しました: ${e}`);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedTag]);

  const hasImported = imported.length > 0;
  const staticOpenings = useMemo(() => (selectedTag ? [] : OPENING_LINES), [selectedTag]);

  return (
    <div className="openings-page" data-testid="openings-page">
      <h1>定跡学習</h1>
      <p className="muted">サンプル定跡またはインポート済み定跡を選び、盤面上で流れを確認しましょう。</p>
      {error && <div className="banner banner-error">{error}</div>}
      <div className="filter-bar">
        <select value={selectedTag} onChange={(e) => setSelectedTag(e.target.value)} aria-label="戦型タグ">
          <option value="">戦型: すべて</option>
          {tags.map((tag) => (
            <option key={tag.tag} value={tag.tag}>
              {tag.label} ({tag.count})
            </option>
          ))}
        </select>
      </div>
      <div className="opening-list" data-testid="opening-list">
        {imported.map((opening) => (
          <article key={`imported-${opening.id}`} className="opening-card" data-testid="opening-card">
            <div>
              <p className="opening-category">{opening.opening_type}</p>
              <h2>{opening.name}</h2>
              <p>インポート済み定跡ライン</p>
              <p className="muted">手数: {opening.move_count}手</p>
              {opening.source.license_name && (
                <p className="muted">ライセンス: {opening.source.license_name}</p>
              )}
            </div>
            <Link className="primary-link" to={`/openings/${opening.id}`}>再生する</Link>
          </article>
        ))}
        {!hasImported && staticOpenings.map((opening) => (
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
        {!hasImported && staticOpenings.length === 0 && <p className="muted">該当する定跡がありません</p>}
      </div>
    </div>
  );
}
