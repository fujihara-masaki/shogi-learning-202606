// 「次の一手」解答後の結果表示と候補手比較。
// 評価値・順位は定跡DBの記録値をそのまま表示し、有利/不利などの解釈は加えない。
import type { Position } from "tsshogi";
import type { BookCandidate, LearningSampleSource } from "../api/client";
import { displayRank, notationForUsi, type NextMoveVerdict } from "../shogi/nextMove";

const VERDICT_ICON: Record<NextMoveVerdict["kind"], string> = {
  top: "◎",
  strong: "○",
  listed: "△",
  unlisted: "?",
};

export const SCORE_NOTE =
  "評価値は取り込み元の定跡DBに記録された数値をそのまま表示しています。数値の基準・単位は出典データに依存します。";

interface NextMoveResultPanelProps {
  verdict: NextMoveVerdict;
  /** 着手前の局面(指し手の日本語表記に使用) */
  basePosition: Position | null;
  source: LearningSampleSource;
}

function moveLabel(position: Position | null, usi: string): string {
  return position ? notationForUsi(position, usi) : usi;
}

export function NextMoveResultPanel({ verdict, basePosition, source }: NextMoveResultPanelProps) {
  const { candidate, best } = verdict;
  const isBestMove = verdict.kind === "top";
  return (
    <section
      className={`next-move-result next-move-result-${verdict.kind}`}
      data-testid="next-move-result"
      aria-labelledby="next-move-result-heading"
    >
      <h2 id="next-move-result-heading">判定結果</h2>
      <p className="next-move-verdict">
        <span aria-hidden="true">{VERDICT_ICON[verdict.kind]}</span> {verdict.label}
      </p>
      <p>{verdict.description}</p>
      <dl className="next-move-result-meta">
        <dt>あなたの手</dt>
        <dd>
          {moveLabel(basePosition, verdict.moveUsi)} <span className="move-usi">({verdict.moveUsi})</span>
        </dd>
        {verdict.candidateRank !== null && (
          <>
            <dt>候補順位</dt>
            <dd>第{verdict.candidateRank}候補</dd>
          </>
        )}
        {candidate?.score !== null && candidate?.score !== undefined && (
          <>
            <dt>評価値</dt>
            <dd>{candidate.score}</dd>
          </>
        )}
        {best && !isBestMove && (
          <>
            <dt>最上位候補</dt>
            <dd>
              {moveLabel(basePosition, best.move_usi)} <span className="move-usi">({best.move_usi})</span>
              {best.score !== null && <span>(評価値 {best.score})</span>}
            </dd>
          </>
        )}
        {verdict.scoreDiffFromBest !== null && !isBestMove && (
          <>
            <dt>最上位候補との評価値の絶対差(参考)</dt>
            <dd>{verdict.scoreDiffFromBest}</dd>
          </>
        )}
        {candidate?.pv && (
          <>
            <dt>この後の進行例(PV)</dt>
            <dd className="next-move-pv">{candidate.pv}</dd>
          </>
        )}
      </dl>
      {(candidate?.score !== null && candidate?.score !== undefined) || (best && best.score !== null) ? (
        <p className="muted next-move-score-note">{SCORE_NOTE}</p>
      ) : null}
      <p className="muted">
        出典: {source.name}
        {source.license_name && ` / ライセンス: ${source.license_name}`}
      </p>
    </section>
  );
}

interface NextMoveCandidateComparisonProps {
  candidates: BookCandidate[];
  basePosition: Position | null;
  userMoveUsi: string | null;
}

export function NextMoveCandidateComparison({ candidates, basePosition, userMoveUsi }: NextMoveCandidateComparisonProps) {
  if (candidates.length === 0) {
    return <p className="muted">この局面に登録されている候補手はありません。</p>;
  }
  return (
    <div className="next-move-candidate-table-wrapper">
      <table className="next-move-candidate-table" data-testid="next-move-candidate-table">
        <caption className="visually-hidden">この局面の定跡DB候補手一覧</caption>
        <thead>
          <tr>
            <th scope="col">順位</th>
            <th scope="col">候補手</th>
            <th scope="col">評価値</th>
            <th scope="col">深さ</th>
            <th scope="col">進行例(PV)</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate, index) => {
            const isUserMove = candidate.move_usi === userMoveUsi;
            return (
              <tr key={`${candidate.move_usi}-${index}`} className={isUserMove ? "next-move-user-row" : undefined}>
                <td>第{displayRank(candidate, index)}候補</td>
                <td>
                  {moveLabel(basePosition, candidate.move_usi)} <span className="move-usi">({candidate.move_usi})</span>
                  {isUserMove && <span className="next-move-your-move-badge">あなたの手</span>}
                </td>
                <td>{candidate.score ?? "—"}</td>
                <td>{candidate.depth ?? "—"}</td>
                <td className="next-move-pv">{candidate.pv || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted next-move-score-note">{SCORE_NOTE}</p>
    </div>
  );
}
