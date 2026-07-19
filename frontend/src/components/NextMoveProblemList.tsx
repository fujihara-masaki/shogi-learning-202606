// 「次の一手」一覧ページ(/next-move)の問題一覧。ページ見出し・説明は NextMovePage が持つ。
// 出題前に答えが分かってしまわないよう、候補手・評価値・SFEN はここでは表示しない。
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchLearningSampleOpenings,
  fetchLearningSamples,
  fetchNextMoveProgress,
  fetchNextMoveStatus,
  isNextMoveUnavailable,
  type LearningSample,
  type LearningSampleOpeningSummary,
  type NextMoveProgressItem,
  type NextMoveStatusItem,
} from "../api/client";

interface OpeningsState {
  loaded: boolean;
  data: LearningSampleOpeningSummary[];
  error: string | null;
}

interface SamplesState {
  /** どの絞り込みに対する結果か(選択中と異なる間は loading 扱い) */
  key: string | null;
  data: LearningSample[];
  error: string | null;
  total: number;
}

const badges = { top: ["◎ 最有力", "最有力"], strong: ["○ 有力", "有力"], listed: ["△ 登録候補", "登録候補"], unlisted: ["? 未登録", "未登録"] } as const;

export default function NextMoveProblemList() {
  const [openings, setOpenings] = useState<OpeningsState>({ loaded: false, data: [], error: null });
  const [selectedOpening, setSelectedOpening] = useState("");
  const [samples, setSamples] = useState<SamplesState>({ key: null, data: [], error: null, total: 0 });
  const [progress, setProgress] = useState<NextMoveProgressItem[]>([]);
  const [statuses, setStatuses] = useState<NextMoveStatusItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchLearningSampleOpenings()
      .then((list) => {
        if (cancelled) return;
        setOpenings({ loaded: true, data: list, error: null });
        // 全戦型を混ぜた取得はAPIの並び順の都合で特定の戦型に偏るため、
        // 先頭の戦型を初期選択して常に戦型単位で出題する。
        setSelectedOpening((prev) => prev || list[0]?.opening_key || "");
      })
      .catch((e) => {
        if (!cancelled) setOpenings({ loaded: true, data: [], error: isNextMoveUnavailable(e)
          ? "次の一手データを利用できません。専用DBの設定を確認してください。"
          : `戦型一覧の取得に失敗しました: ${e}` });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => { fetchNextMoveProgress().then((x) => setProgress(x.openings)).catch(() => setProgress([])); }, []);

  useEffect(() => {
    if (!selectedOpening) return;
    let cancelled = false;
    fetchLearningSamples(selectedOpening, 30)
      .then(async (page) => {
        if (!cancelled) setSamples({ key: selectedOpening, data: page.items, total: page.total, error: null });
        try {
          const status = await fetchNextMoveStatus(selectedOpening);
          if (!cancelled) setStatuses(status.items);
        } catch {
          // Status is supplementary: keep the problem list usable and show unknown as unattempted.
          if (!cancelled) setStatuses([]);
        }
      })
      .catch((e) => {
        if (!cancelled) setSamples({ key: selectedOpening, data: [], total: 0, error: isNextMoveUnavailable(e)
          ? "次の一手データを利用できません。専用DBの設定を確認してください。"
          : `問題一覧の取得に失敗しました: ${e}` });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedOpening]);

  const samplesLoading = selectedOpening !== "" && samples.key !== selectedOpening;
  const noOpenings = openings.loaded && !openings.error && openings.data.length === 0;
  const summary = progress.find((x) => x.opening_key === selectedOpening);
  const statusMap = new Map(statuses.map((x) => [x.problem_key, x.verdict]));

  return (
    <section data-testid="next-move-section">
      {openings.error && <div className="banner banner-error" role="alert">{openings.error}</div>}
      {!openings.error && !noOpenings && (
        <div className="filter-bar">
          <select
            value={selectedOpening}
            onChange={(e) => setSelectedOpening(e.target.value)}
            aria-label="戦型を選ぶ"
            data-testid="next-move-opening-filter"
          >
            {openings.data.map((opening) => (
              <option key={opening.opening_key} value={opening.opening_key}>
                {opening.opening_name}({opening.sample_count}問)
              </option>
            ))}
          </select>
        </div>
      )}
      {!samplesLoading && samples.error && <div className="banner banner-error" role="alert">{samples.error}</div>}
      {samplesLoading && <p className="muted">問題を読み込み中...</p>}
      {!samplesLoading && summary && <div className="next-move-summary" data-testid="next-move-summary">
        <strong>挑戦済み {summary.answered} / 全{summary.total}問</strong><span>最有力率 {Math.round(summary.top_rate * 100)}%</span>
      </div>}
      {!samplesLoading && samples.total > samples.data.length && <p className="muted count-note">全{samples.total}問中{samples.data.length}問を表示</p>}
      <h2>問題一覧</h2>
      <div className="opening-list" data-testid="next-move-problem-list">
        {!samplesLoading &&
          samples.data.map((sample, index) => (
            <article key={sample.problem_key} className="opening-card" data-testid="next-move-problem-card">
              <div>
                <p className="opening-category">{sample.opening_name}</p>
                <h3 data-testid="next-move-problem-title">問題 {index + 1}</h3>
                {(() => { const verdict = statusMap.get(sample.problem_key); const badge = verdict ? badges[verdict] : ["未挑戦", "未挑戦"];
                  return <span className={`next-move-status status-${verdict ?? "unattempted"}`} aria-label={`最新状態: ${badge[1]}`}>{badge[0]}</span>; })()}
                <p>局面を見て次の一手を考えましょう。</p>
                <p className="muted">
                  出典: {sample.source.name}
                  {sample.source.license_name && ` / ${sample.source.license_name}`}
                </p>
              </div>
              <Link className="primary-link" to={`/next-move/${sample.id}`}>
                挑戦する
              </Link>
            </article>
          ))}
        {!samplesLoading && !openings.error && !samples.error && samples.data.length === 0 && (
          <div className="muted" data-testid="next-move-empty-state">
            <p>出題できる問題がまだありません。定跡DBを取り込み、学習用サンプルを抽出すると問題が追加されます。</p>
            <p>詳しくはREADMEの「やねうら王定跡からの学習用サンプル抽出」を参照してください。</p>
          </div>
        )}
      </div>
    </section>
  );
}
