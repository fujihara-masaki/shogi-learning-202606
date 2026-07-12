// 定跡学習トップの「次の一手に挑戦する」一覧。
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
        if (!cancelled) setOpenings({ loaded: true, data: list, error: null });
      })
      .catch((e) => {
        if (!cancelled) setOpenings({ loaded: true, data: [], error: `戦型一覧の取得に失敗しました: ${e}` });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchLearningSamples(selectedOpening || undefined, 30)
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

  const samplesLoading = samples.key !== selectedOpening;

  return (
    <section data-testid="next-move-section">
      <h2>次の一手に挑戦する</h2>
      <p className="muted">
        実戦形の局面を見て、次の一手を自分で考える練習問題です。答え(定跡DBの候補手と評価値)は着手後に表示されます。
      </p>
      {openings.error && <div className="banner banner-error" role="alert">{openings.error}</div>}
      <div className="filter-bar">
        <select
          value={selectedOpening}
          onChange={(e) => setSelectedOpening(e.target.value)}
          aria-label="戦型で絞り込む"
          data-testid="next-move-opening-filter"
        >
          <option value="">戦型: すべて</option>
          {openings.data.map((opening) => (
            <option key={opening.opening_key} value={opening.opening_key}>
              {opening.opening_name}({opening.sample_count}問)
            </option>
          ))}
        </select>
      </div>
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
              <Link className="primary-link" to={`/openings/next-move/${sample.id}`}>
                挑戦する
              </Link>
            </article>
          ))}
        {!samplesLoading && !samples.error && samples.data.length === 0 && (
          <p className="muted">出題できる問題がまだありません。定跡DBを取り込むと問題が追加されます。</p>
        )}
      </div>
    </section>
  );
}
