// 定跡学習トップの、戦型を入口にした手順選択セクション。
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchOpeningCategories,
  fetchOpeningTags,
  fetchOpeningTypeLines,
  fetchOpeningTypes,
  fetchOpenings,
  type OpeningCategory,
  type OpeningSummary,
  type OpeningTagSummary,
  type OpeningType,
} from "../api/client";
import { OPENING_LINES, countMainLineMoves, type OpeningLine } from "../shogi/openings";
import { availableOpeningLineCount, expandedImportedLinesForType, importedLinesForType } from "./openingTypeLines";

// static lineにも学習入口となる戦型を明示する。API/DBのlineと同じカード内に表示する。
const STATIC_OPENING_TYPE_NAMES: Record<string, string> = {
  "static-rook-rapid-attack": "相掛かり",
  "yagura-foundation": "矢倉",
  "fourth-file-rook": "四間飛車",
};

function staticLinesForType(type: OpeningType): OpeningLine[] {
  return OPENING_LINES.filter((line) => STATIC_OPENING_TYPE_NAMES[line.id] === type.name_ja);
}

export default function OpeningLineStudySection() {
  const [tags, setTags] = useState<OpeningTagSummary[]>([]);
  const [selectedTag, setSelectedTag] = useState("");
  const [categories, setCategories] = useState<OpeningCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);
  const [openingTypes, setOpeningTypes] = useState<OpeningType[]>([]);
  const [matchingLines, setMatchingLines] = useState<OpeningSummary[]>([]);
  const [selectedType, setSelectedType] = useState<OpeningType | null>(null);
  const [typeLines, setTypeLines] = useState<OpeningSummary[]>([]);
  const [loadingTypeLines, setLoadingTypeLines] = useState(false);
  const [typeCatalogFailed, setTypeCatalogFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchOpeningTags()
      .then((tagList) => { if (!cancelled) setTags(tagList); })
      .catch((e) => { if (!cancelled) setError(`タグの取得に失敗しました: ${e}`); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchOpeningCategories()
      .then((categoryList) => { if (!cancelled) setCategories(categoryList); })
      .catch((e) => { if (!cancelled) setError(`カテゴリの取得に失敗しました: ${e}`); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchOpeningTypes(selectedCategoryId ?? undefined)
      .then((typeList) => {
        if (cancelled) return;
        setOpeningTypes(typeList);
        setTypeCatalogFailed(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setTypeCatalogFailed(true);
        setError(`戦型一覧の取得に失敗しました: ${e}`);
      });
    return () => { cancelled = true; };
  }, [selectedCategoryId]);

  useEffect(() => {
    let cancelled = false;
    fetchOpenings(selectedTag || undefined)
      .then((lines) => { if (!cancelled) setMatchingLines(lines); })
      .catch((e) => { if (!cancelled) setError(`学習手順の取得に失敗しました: ${e}`); });
    return () => { cancelled = true; };
  }, [selectedTag]);

  useEffect(() => {
    if (!selectedType) return;
    if (selectedType.opening_line_count === 0) return;
    let cancelled = false;
    fetchOpeningTypeLines(selectedType.id)
      .then((lines) => {
        if (!cancelled) setTypeLines(lines);
      })
      .catch((e) => {
        if (!cancelled) setError(`学習手順の取得に失敗しました: ${e}`);
      })
      .finally(() => {
        if (!cancelled) setLoadingTypeLines(false);
      });
    return () => { cancelled = true; };
  }, [selectedType]);

  const visibleTypes = useMemo(() => {
    if (!selectedTag) return openingTypes;
    return openingTypes.filter((type) => importedLinesForType(type, matchingLines).length > 0);
  }, [matchingLines, openingTypes, selectedTag]);

  function resetSelectedTypeLines() {
    setSelectedType(null);
    setTypeLines([]);
    setLoadingTypeLines(false);
  }

  function handleTypeLinesClick(type: OpeningType) {
    if (selectedType?.id === type.id) {
      resetSelectedTypeLines();
      return;
    }
    setSelectedType(type);
    setTypeLines([]);
    setLoadingTypeLines(type.opening_line_count > 0);
  }

  const selectedStaticLines = selectedType && !selectedTag ? staticLinesForType(selectedType) : [];
  const selectedImportedLines = selectedType
    ? expandedImportedLinesForType(selectedType, typeLines, matchingLines, Boolean(selectedTag))
    : [];

  return (
    <section data-testid="opening-line-study-section">
      <h2>戦型から学ぶ</h2>
      <p className="muted">戦型を選び、その戦型の手順を一手ずつ盤面でなぞって覚えましょう。</p>
      {error && <div className="banner banner-error" role="alert">{error}</div>}

      <section className="opening-filters" aria-labelledby="opening-filter-heading">
        <div>
          <h3 id="opening-filter-heading">戦型を探す</h3>
          <p className="muted">カテゴリやタグで戦型一覧を絞り込めます。</p>
        </div>
        <div className="opening-category-filter" data-testid="opening-category-list" role="group" aria-label="カテゴリで絞り込む">
          <button className={selectedCategoryId === null ? "active" : ""} aria-pressed={selectedCategoryId === null} onClick={() => { setSelectedCategoryId(null); resetSelectedTypeLines(); }} type="button">すべて</button>
          {categories.map((category) => (
            <button key={category.id} className={selectedCategoryId === category.id ? "active" : ""} aria-pressed={selectedCategoryId === category.id} onClick={() => { setSelectedCategoryId(category.id); resetSelectedTypeLines(); }} type="button" data-testid="opening-category-card">
              {category.name_ja}
            </button>
          ))}
        </div>
        <label className="opening-tag-filter">
          <span>タグでさらに絞り込む</span>
          <select value={selectedTag} onChange={(e) => { setSelectedTag(e.target.value); resetSelectedTypeLines(); }}>
            <option value="">すべてのタグ</option>
            {tags.map((tag) => <option key={tag.tag} value={tag.tag}>{tag.label} ({tag.count})</option>)}
          </select>
        </label>
      </section>

      {typeCatalogFailed ? (
        <section aria-labelledby="static-opening-fallback-heading" data-testid="opening-static-fallback">
          <h3 id="static-opening-fallback-heading">基本の学習手順</h3>
          <p className="muted">戦型一覧を読み込めないため、基本の手順を表示しています。</p>
          <div className="opening-list">
            {OPENING_LINES.map((opening) => (
              <article key={opening.id} className="opening-card" data-testid="opening-static-fallback-card">
                <div>
                  <p className="opening-category">{opening.category}</p>
                  <h4 data-testid="opening-card-title">{opening.name}</h4>
                  <p>{opening.description}</p>
                  <p className="muted">{countMainLineMoves(opening)}手</p>
                </div>
                <Link className="primary-link" to={`/openings/${opening.id}`}>学習する</Link>
              </article>
            ))}
          </div>
        </section>
      ) : (
      <section aria-labelledby="opening-types-heading">
        <h3 id="opening-types-heading">戦型一覧</h3>
        <p className="muted">学びたい戦型を選んでください。</p>
        <div className="opening-list" data-testid="opening-type-list">
          {visibleTypes.map((type) => {
            const staticCount = selectedTag ? 0 : staticLinesForType(type).length;
            const availableCount = availableOpeningLineCount(type, matchingLines, Boolean(selectedTag), staticCount);
            const isExpanded = selectedType?.id === type.id;
            return (
              <article key={type.id} className={`opening-card opening-type-card${isExpanded ? " active" : ""}`} data-testid="opening-type-card">
                <div>
                  <p className="opening-category">{type.category_name_ja}</p>
                  <h4 data-testid="opening-type-card-title">{type.name_ja}</h4>
                  <p>{type.description_short}</p>
                  {availableCount > 0
                    ? <p className="opening-availability available"><strong>{availableCount}つの手順を学べます</strong></p>
                    : <p className="opening-availability pending"><strong>定跡手順は準備中</strong></p>}
                </div>
                {availableCount > 0 && (
                  <button type="button" className="primary-link" aria-expanded={isExpanded} aria-controls={`opening-type-lines-${type.id}`} onClick={() => handleTypeLinesClick(type)}>
                    {isExpanded ? "手順を閉じる" : "手順を見る"}
                  </button>
                )}
                {isExpanded && (
                  <div id={`opening-type-lines-${type.id}`} className="opening-type-lines" data-testid="opening-type-line-list">
                    <h5>{type.name_ja}の学習手順</h5>
                    {loadingTypeLines && <p className="muted" role="status">手順を読み込み中です。</p>}
                    {!loadingTypeLines && [...selectedImportedLines, ...selectedStaticLines].map((opening) => {
                      const isStatic = "description" in opening;
                      const id = String(opening.id);
                      return (
                        <div key={id} className="opening-line-item" data-testid="opening-type-line-card">
                          <div>
                            <strong data-testid="opening-card-title">{opening.name}</strong>
                            <span className="muted">{isStatic ? opening.description : `${opening.move_count}手`}</span>
                            {isStatic && <span className="muted">{countMainLineMoves(opening)}手</span>}
                          </div>
                          <Link className="primary-link" to={`/openings/${id}`}>学習する</Link>
                        </div>
                      );
                    })}
                  </div>
                )}
              </article>
            );
          })}
          {visibleTypes.length === 0 && <p className="muted" data-testid="opening-types-empty">条件に合う戦型はありません。</p>}
        </div>
      </section>
      )}
    </section>
  );
}
