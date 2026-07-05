// 履歴画面: 解答履歴・タイムアタック履歴・正答率・平均解答時間。
import { useEffect, useState } from "react";
import {
  fetchStats,
  fetchTimeAttackResults,
  type StatsResponse,
  type TimeAttackResult,
} from "../api/client";

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function sec(ms: number | null): string {
  return ms != null ? `${(ms / 1000).toFixed(1)}秒` : "-";
}

function formatMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  return `${Math.floor(totalSec / 60)}:${String(totalSec % 60).padStart(2, "0")}`;
}

export default function HistoryPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [taResults, setTaResults] = useState<TimeAttackResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [s, ta] = await Promise.all([fetchStats(), fetchTimeAttackResults()]);
        setStats(s);
        setTaResults(ta);
      } catch (e) {
        setError(`履歴の取得に失敗しました: ${e}`);
      }
    })();
  }, []);

  return (
    <div className="history-page" data-testid="history-page">
      <h1>履歴</h1>
      {error && <div className="banner banner-error" role="alert">{error}</div>}

      {stats && (
        <>
          <h2>成績サマリー</h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>区分</th>
                <th>解答数</th>
                <th>正解</th>
                <th>不正解</th>
                <th>正答率</th>
                <th>平均解答時間</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>全体</th>
                <td>{stats.overall.total_answers}</td>
                <td>{stats.overall.total_correct}</td>
                <td>{stats.overall.total_wrong}</td>
                <td>{pct(stats.overall.accuracy)}</td>
                <td>{sec(stats.overall.avg_elapsed_ms)}</td>
              </tr>
              {Object.entries(stats.by_mate_length)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([len, s]) => (
                  <tr key={len}>
                    <th>{len}手詰</th>
                    <td>{s.total_answers}</td>
                    <td>{s.total_correct}</td>
                    <td>{s.total_wrong}</td>
                    <td>{pct(s.accuracy)}</td>
                    <td>{sec(s.avg_elapsed_ms)}</td>
                  </tr>
                ))}
            </tbody>
          </table>

          <h2>最近の解答</h2>
          {stats.recent_results.length === 0 ? (
            <p className="muted">まだ解答履歴がありません。</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>日時</th>
                  <th>問題</th>
                  <th>結果</th>
                  <th>時間</th>
                  <th>ミス</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_results.map((r) => (
                  <tr key={r.id}>
                    <td>{r.answered_at}</td>
                    <td>{r.title}</td>
                    <td className={r.is_correct ? "ok" : "ng"}>
                      {r.is_correct ? "○ 正解" : "✗ 不正解"}
                    </td>
                    <td>{sec(r.elapsed_ms)}</td>
                    <td>{r.mistake_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <h2>タイムアタック履歴</h2>
      {taResults.length === 0 ? (
        <p className="muted">まだタイムアタックの記録がありません。</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>日時</th>
              <th>難易度</th>
              <th>問題数</th>
              <th>正解</th>
              <th>ミス</th>
              <th>合計時間</th>
            </tr>
          </thead>
          <tbody>
            {taResults.map((r) => (
              <tr key={r.id}>
                <td>{r.played_at}</td>
                <td>{r.mate_length}手詰</td>
                <td>{r.total_questions}</td>
                <td>{r.correct_count}</td>
                <td>{r.mistake_count}</td>
                <td>{formatMs(r.elapsed_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
