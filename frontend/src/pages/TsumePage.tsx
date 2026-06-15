// 詰め将棋画面: 難易度選択・問題一覧・盤面プレイ。
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  fetchProblems,
  postProblemResult,
  setFavorite,
  type TsumeProblem,
} from "../api/client";
import TsumePlayer from "../components/TsumePlayer";
import type { SessionOutcome } from "../hooks/useTsumeSession";

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

  const selectedId = Number(searchParams.get("problem")) || null;
  const selected = problems.find((p) => p.id === selectedId) ?? null;

  const load = useCallback(async () => {
    try {
      const list = await fetchProblems(
        mateLength > 0 ? { mate_length: mateLength } : {},
      );
      setProblems(list);
      setError(null);
    } catch (e) {
      setError(`問題一覧の取得に失敗しました: ${e}`);
    }
  }, [mateLength]);

  useEffect(() => {
    // マウント時とフィルタ変更時に API から問題一覧を取得する。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const allTags = useMemo(
    () => Array.from(new Set(problems.flatMap((p) => p.tags))).sort(),
    [problems],
  );

  const visibleProblems = useMemo(
    () => (tagFilter ? problems.filter((p) => p.tags.includes(tagFilter)) : problems),
    [problems, tagFilter],
  );

  const selectProblem = (id: number | null) => {
    if (id === null) {
      searchParams.delete("problem");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ problem: String(id) }, { replace: true });
    }
  };

  const pickRandom = () => {
    if (visibleProblems.length === 0) return;
    const candidates = visibleProblems.filter((p) => p.id !== selectedId);
    const pool = candidates.length > 0 ? candidates : visibleProblems;
    const pick = pool[Math.floor(Math.random() * pool.length)];
    selectProblem(pick.id);
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
      {error && <div className="banner banner-error">{error}</div>}
      <div className="filter-bar">
        <div className="segmented">
          {MATE_LENGTHS.map((m) => (
            <button
              key={m.value}
              type="button"
              className={mateLength === m.value ? "active" : ""}
              onClick={() => setMateLength(m.value)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
          <option value="">タグ: すべて</option>
          {allTags.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button type="button" onClick={pickRandom}>
          ランダム出題
        </button>
      </div>
      <div className="tsume-layout">
        <aside className="problem-list">
          {visibleProblems.map((p) => (
            <div
              key={p.id}
              className={`problem-item ${p.id === selectedId ? "active" : ""}`}
            >
              <button type="button" className="problem-link" onClick={() => selectProblem(p.id)}>
                <span className="problem-title">{p.title}</span>
                <span className="muted">
                  {p.mate_length}手詰 / 正解{p.stats.correct_count} 不正解{p.stats.wrong_count}
                </span>
              </button>
              <Link className="edit-button" to={`/problem-editor/${p.id}`}>編集</Link>
              <button
                type="button"
                className={`fav-button ${p.is_favorite ? "fav-on" : ""}`}
                title="お気に入り"
                onClick={() => toggleFavorite(p)}
              >
                {p.is_favorite ? "★" : "☆"}
              </button>
            </div>
          ))}
          {visibleProblems.length === 0 && <p className="muted">問題がありません</p>}
        </aside>
        <main className="tsume-main">
          {selected ? (
            <TsumePlayer key={selected.id} problem={selected} onTerminal={handleTerminal} />
          ) : (
            <p className="muted">左の一覧から問題を選ぶか、ランダム出題を押してください。</p>
          )}
        </main>
      </div>
    </div>
  );
}
