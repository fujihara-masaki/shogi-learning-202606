import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchOpeningCategories,
  fetchOpeningTags,
  fetchOpeningTypes,
  fetchOpeningTypeLines,
  fetchOpenings,
  type OpeningCategory,
  type OpeningSummary,
  type OpeningTagSummary,
  type OpeningType,
} from "../api/client";
import { OPENING_LINES, countMainLineMoves } from "../shogi/openings";

export default function OpeningsPage() {
  const [tags, setTags] = useState<OpeningTagSummary[]>([]);
  const [selectedTag, setSelectedTag] = useState("");
  const [categories, setCategories] = useState<OpeningCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);
  const [openingTypes, setOpeningTypes] = useState<OpeningType[]>([]);
  const [selectedOpeningType, setSelectedOpeningType] = useState<OpeningType | null>(null);
  const [relatedLines, setRelatedLines] = useState<OpeningSummary[]>([]);
  const [imported, setImported] = useState<OpeningSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchOpeningTags(),
      fetchOpenings(selectedTag || undefined),
      fetchOpeningCategories(),
      fetchOpeningTypes(selectedCategoryId ?? undefined),
    ])
      .then(([tagList, openingList, categoryList, typeList]) => {
        if (cancelled) return;
        setTags(tagList);
        setImported(openingList);
        setCategories(categoryList);
        setOpeningTypes(typeList);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(`定跡データの取得に失敗しました: ${e}`);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedTag, selectedCategoryId]);

  useEffect(() => {
    if (!selectedOpeningType) return;
    let cancelled = false;
    fetchOpeningTypeLines(selectedOpeningType.id)
      .then((lines) => {
        if (!cancelled) setRelatedLines(lines);
      })
      .catch((e) => {
        if (!cancelled) setError(`関連定跡ラインの取得に失敗しました: ${e}`);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedOpeningType]);

  const selectCategory = (categoryId: number | null) => {
    setSelectedCategoryId(categoryId);
    setSelectedOpeningType(null);
    setRelatedLines([]);
  };

  const selectOpeningType = (type: OpeningType) => {
    setSelectedOpeningType(type);
    setRelatedLines([]);
  };

  const hasImported = imported.length > 0;
  const staticOpenings = useMemo(() => (selectedTag || selectedCategoryId ? [] : OPENING_LINES), [selectedTag, selectedCategoryId]);

  return (
    <div className="openings-page" data-testid="openings-page">
      <h1>定跡学習</h1>
      <p className="muted">サンプル定跡・戦型一覧から序盤の流れを確認しましょう。</p>
      {error && <div className="banner banner-error">{error}</div>}

      <section className="opening-source-note" aria-label="データ出典">
        <h2>データ出典</h2>
        <p>
          戦型一覧の初期データは Wikibooks「将棋の戦法一覧」、Wikipedia「将棋の戦法」、Wikipediaカテゴリ「将棋の戦法」を参考に手作業で確認した seed データです。ライセンスは CC BY-SA です。
        </p>
      </section>

      <div className="filter-bar">
        <select value={selectedTag} onChange={(e) => setSelectedTag(e.target.value)} aria-label="戦型タグ">
          <option value="">定跡タグ: すべて</option>
          {tags.map((tag) => (
            <option key={tag.tag} value={tag.tag}>{tag.label} ({tag.count})</option>
          ))}
        </select>
      </div>

      <section>
        <h2>戦型カテゴリ</h2>
        <div className="opening-category-grid" data-testid="opening-category-list">
          <button className={!selectedCategoryId ? "opening-category-card active" : "opening-category-card"} onClick={() => selectCategory(null)} type="button">
            <strong>すべて</strong><span>全カテゴリの戦型を表示</span>
          </button>
          {categories.map((category) => (
            <button key={category.id} className={selectedCategoryId === category.id ? "opening-category-card active" : "opening-category-card"} onClick={() => selectCategory(category.id)} type="button" data-testid="opening-category-card">
              <strong>{category.name_ja}</strong><span>{category.description}</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2>戦型一覧</h2>
        <div className="opening-list" data-testid="opening-type-list">
          {openingTypes.map((type) => (
            <article key={type.id} className="opening-card" data-testid="opening-type-card">
              <div>
                <p className="opening-category">{type.category_name_ja}</p>
                <h2>{type.name_ja}</h2>
                <p>{type.description_short}</p>
                <p className="muted">かな: {type.name_kana} / English: {type.name_en}</p>
                <p className="muted">出典: {type.source_name} / ライセンス: {type.license}</p>
              </div>
              <button className="primary-link opening-type-action" type="button" onClick={() => selectOpeningType(type)}>
                関連定跡を見る
              </button>
              {type.opening_line_count > 0 ? <span className="muted">定跡ラインあり: {type.opening_line_count}件</span> : <strong className="muted">定跡手順は準備中</strong>}
            </article>
          ))}
        </div>
      </section>

      {selectedOpeningType && (
        <section className="opening-related-lines" data-testid="opening-related-lines">
          <h2>{selectedOpeningType.name_ja} の関連定跡ライン</h2>
          {relatedLines.length > 0 ? (
            <div className="opening-list">
              {relatedLines.map((line) => (
                <article key={line.id} className="opening-card" data-testid="opening-related-line-card">
                  <div>
                    <p className="opening-category">{line.opening_type}</p>
                    <h2>{line.name}</h2>
                    <p className="muted">手数: {line.move_count}手</p>
                  </div>
                  <Link className="primary-link" to={`/openings/${line.id}`}>学習する</Link>
                </article>
              ))}
            </div>
          ) : (
            <p className="muted">定跡手順は準備中</p>
          )}
        </section>
      )}

      <section>
        <h2>学習できる定跡ライン</h2>
        <div className="opening-list" data-testid="opening-list">
          {imported.map((opening) => (
            <article key={`imported-${opening.id}`} className="opening-card" data-testid="opening-card">
              <div><p className="opening-category">{opening.opening_type}</p><h2>{opening.name}</h2><p>インポート済み定跡ライン</p><p className="muted">手数: {opening.move_count}手</p>{opening.source.license_name && <p className="muted">ライセンス: {opening.source.license_name}</p>}</div>
              <Link className="primary-link" to={`/openings/${opening.id}`}>学習する</Link>
            </article>
          ))}
          {!hasImported && staticOpenings.map((opening) => (
            <article key={opening.id} className="opening-card" data-testid="opening-card">
              <div><p className="opening-category">{opening.category}</p><h2>{opening.name}</h2><p>{opening.description}</p><p className="muted">手数: {countMainLineMoves(opening)}手</p></div>
              <Link className="primary-link" to={`/openings/${opening.id}`}>学習する</Link>
            </article>
          ))}
          {!hasImported && staticOpenings.length === 0 && <p className="muted">該当する定跡ラインはありません。定跡手順は準備中です。</p>}
        </div>
      </section>
    </div>
  );
}
