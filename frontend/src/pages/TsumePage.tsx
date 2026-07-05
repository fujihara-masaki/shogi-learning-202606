// 詰め将棋画面: 難易度選択・問題一覧・盤面プレイ。
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  fetchProblem,
  fetchProblems,
  fetchTsumeTags,
  postProblemResult,
  setFavorite,
  type TsumeProblem,
  type TsumeTagSummary,
} from "../api/client";
import TsumePlayer from "../components/TsumePlayer";
import type { SessionOutcome } from "../hooks/useTsumeSession";

const PROBLEM_PAGE_SIZE = 50;

const MATE_LENGTHS = [
  { value: 0, label: "すべて" },
  { value: 1, label: "1手詰" },
  { value: 3, label: "3手詰" },
  { value: 5, label: "5手詰" },
];

export default function TsumePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [problems, setProblems] = useState<TsumeProblem[]>([]);
  const [mateLength, setMateLength] = useState(0);
  const [tagFilter, setTagFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selectedProblem, setSelectedProblem] = useState<TsumeProblem | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [allTags, setAllTags] = useState<TsumeTagSummary[]>([]);

  const selectedId = Number(searchParams.get("problem")) || null;
  const selected = selectedId ? (problems.find((p) => p.id === selectedId) ?? selectedProblem) : null;

  const query = useMemo(
    () => ({
      ...(mateLength > 0 ? { mate_length: mateLength } : {}),
      ...(tagFilter ? { tag: tagFilter } : {}),
    }),
    [mateLength, tagFilter],
  );

  const loadPage = useCallback(
    async (offset: number) => {
      setIsLoading(true);
      try {
        const list = await fetchProblems({ ...query, limit: PROBLEM_PAGE_SIZE, offset });
        setProblems((prev) => (offset === 0 ? list : [...prev, ...list]));
        setHasMore(list.length === PROBLEM_PAGE_SIZE);
        setError(null);
      } catch (e) {
        setError(`問題一覧の取得に失敗しました: ${e}`);
      } finally {
        setIsLoading(false);
      }
    },
    [query],
  );

  useEffect(() => {
    // マウント時とフィルタ変更時は先頭ページだけ取得し、1,000件以上を一括描画しない。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadPage(0);
  }, [loadPage]);

  useEffect(() => {
    let ignore = false;
    fetchTsumeTags(mateLength > 0 ? { mate_length: mateLength } : {})
      .then((tags) => {
        if (!ignore) {
          setAllTags(tags);
          setTagFilter((current) => (current && !tags.some((t) => t.tag === current) ? "" : current));
        }
      })
      .catch((e) => {
        if (!ignore) setError(`タグ一覧の取得に失敗しました: ${e}`);
      });
    return () => {
      ignore = true;
    };
  }, [mateLength]);

  useEffect(() => {
    let ignore = false;
    if (!selectedId) return;
    if (problems.some((p) => p.id === selectedId)) return;
    fetchProblem(selectedId)
      .then((problem) => {
        if (!ignore) setSelectedProblem(problem);
      })
      .catch((e) => {
        if (!ignore) setError(`問題の取得に失敗しました: ${e}`);
      });
    return () => {
      ignore = true;
    };
  }, [problems, selectedId]);

  const visibleProblems = problems;

  const selectProblem = (id: number | null) => {
    if (id === null) {
      searchParams.delete("problem");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ problem: String(id) }, { replace: true });
      const problem = problems.find((p) => p.id === id);
      if (problem) setSelectedProblem(problem);
    }
  };

  const pickRandom = () => {
    if (visibleProblems.length === 0) return;
    const candidates = visibleProblems.filter((p) => p.id !== selectedId);
    const pool = candidates.length > 0 ? candidates : visibleProblems;
    const pick = pool[Math.floor(Math.random() * pool.length)];
    selectProblem(pick.id);
  };

  // クリア後の「次の問題」: 一覧の次を選ぶ。末尾ならランダムに切り替える。
  const selectNext = () => {
    if (visibleProblems.length === 0) return;
    const index = visibleProblems.findIndex((p) => p.id === selectedId);
    if (index >= 0 && index + 1 < visibleProblems.length) {
      selectProblem(visibleProblems[index + 1].id);
    } else {
      pickRandom();
    }
  };

  const handleTerminal = useCallback(
    async (outcome: SessionOutcome) => {
      if (!selectedId) return;
      try {
        await postProblemResult(selectedId, {
          is_correct: outcome.cleared,
          elapsed_ms: outcome.elapsedMs,
          mistake_count: outcome.mistakeCount,
        });
      } catch {
        // 個人利用のため記録失敗は致命的でない。コンソールにも出さず無視する。
      }
    },
    [selectedId],
  );

  const toggleFavorite = async (p: TsumeProblem) => {
    try {
      const updated = await setFavorite(p.id, !p.is_favorite);
      setProblems((prev) => prev.map((x) => (x.id === p.id ? updated : x)));
    } catch (e) {
      setError(`お気に入りの更新に失敗しました: ${e}`);
    }
  };

  return (
    <div className="tsume-page">
      <h1>詰め将棋</h1>
      {error && <div className="banner banner-error" role="alert">{error}</div>}
      <div className="filter-bar">
        <div className="segmented" data-testid="difficulty-filter">
          {MATE_LENGTHS.map((m) => (
            <button
              key={m.value}
              type="button"
              className={mateLength === m.value ? "active" : ""}
              aria-pressed={mateLength === m.value}
              onClick={() => setMateLength(m.value)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <select value={tagFilter} aria-label="タグで絞り込み" onChange={(e) => setTagFilter(e.target.value)}>
          <option value="">タグ: すべて</option>
          {allTags.map((t) => (
            <option key={t.tag} value={t.tag}>
              {t.tag}（{t.count}）
            </option>
          ))}
        </select>
        <button type="button" onClick={pickRandom}>
          ランダム出題
        </button>
      </div>
      <div className="tsume-layout">
        <aside className="problem-list" data-testid="problem-list">
          {visibleProblems.map((p) => (
            <div
              key={p.id}
              className={`problem-item ${p.id === selectedId ? "active" : ""}`}
              data-testid="problem-item"
            >
              <button type="button" className="problem-link" data-testid={`problem-select-${p.id}`} onClick={() => selectProblem(p.id)}>
                <span className="problem-title" data-testid="problem-title">{p.title}</span>
                <span className="muted">
                  {p.mate_length}手詰 / 正解{p.stats.correct_count} 不正解{p.stats.wrong_count}
                </span>
                {p.source_name && <span className="muted problem-source">出典: {p.source_name}</span>}
              </button>
              <Link className="edit-button" to={`/problem-editor/${p.id}`}>編集</Link>
              <button
                type="button"
                className={`fav-button ${p.is_favorite ? "fav-on" : ""}`}
                title="お気に入り"
                aria-label={p.is_favorite ? "お気に入りを解除" : "お気に入りに追加"}
                aria-pressed={p.is_favorite}
                onClick={() => toggleFavorite(p)}
              >
                {p.is_favorite ? "★" : "☆"}
              </button>
            </div>
          ))}
          {visibleProblems.length === 0 && !isLoading && <p className="muted">問題がありません</p>}
          {hasMore && (
            <button type="button" className="load-more-button" disabled={isLoading} onClick={() => loadPage(problems.length)}>
              {isLoading ? "読み込み中…" : "もっと読み込む"}
            </button>
          )}
          {isLoading && visibleProblems.length === 0 && <p className="muted">読み込み中…</p>}
        </aside>
        <main className="tsume-main">
          {selected ? (
            <TsumePlayer key={selected.id} problem={selected} onTerminal={handleTerminal} onNext={selectNext} />
          ) : (
            <p className="muted">左の一覧から問題を選ぶか、ランダム出題を押してください。</p>
          )}
        </main>
      </div>
    </div>
  );
}
