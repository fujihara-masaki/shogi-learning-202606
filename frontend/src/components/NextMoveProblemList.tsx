// 「次の一手」一覧ページ(/next-move)の問題一覧。ページ見出し・説明は NextMovePage が持つ。
// 出題前に答えが分かってしまわないよう、候補手・評価値・SFEN はここでは表示しない。
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchLearningSampleOpenings,
  fetchLearningSamples,
  type LearningSample,
  type LearningSampleOpeningSummary,
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
}

export default function NextMoveProblemList() {
  const [openings, setOpenings] = useState<OpeningsState>({ loaded: false, data: [], error: null });
  const [selectedOpening, setSelectedOpening] = useState("");
  const [samples, setSamples] = useState<SamplesState>({ key: null, data: [], error: null });

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
        if (!cancelled) setOpenings({ loaded: true, data: [], error: `戦型一覧の取得に失敗しました: ${e}` });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedOpening) return;
    let cancelled = false;
    fetchLearningSamples(selectedOpening, 30)
      .then((list) => {
        if (!cancelled) setSamples({ key: selectedOpening, data: list, error: null });
      })
      .catch((e) => {
        if (!cancelled) setSamples({ key: selectedOpening, data: [], error: `問題一覧の取得に失敗しました: ${e}` });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedOpening]);

  const samplesLoading = selectedOpening !== "" && samples.key !== selectedOpening;
  const noOpenings = openings.loaded && !openings.error && openings.data.length === 0;

  return (
    <section data-testid="next-move-section">
      {openings.error && <div className="banner banner-error" role="alert">{openings.error}</div>}
      {!noOpenings && (
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
      <div className="opening-list" data-testid="next-move-problem-list">
        {!samplesLoading &&
          samples.data.map((sample, index) => (
            <article key={sample.id} className="opening-card" data-testid="next-move-problem-card">
              <div>
                <p className="opening-category">{sample.opening_name}</p>
                <h3 data-testid="next-move-problem-title">問題 {index + 1}</h3>
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
        {!samplesLoading && !samples.error && samples.data.length === 0 && (
          <div className="muted" data-testid="next-move-empty-state">
            <p>出題できる問題がまだありません。定跡DBを取り込み、学習用サンプルを抽出すると問題が追加されます。</p>
            <p>詳しくはREADMEの「やねうら王定跡からの学習用サンプル抽出」を参照してください。</p>
          </div>
        )}
      </div>
    </section>
  );
}
