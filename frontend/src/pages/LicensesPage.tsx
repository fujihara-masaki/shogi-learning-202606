import { useEffect, useState } from "react";
import { fetchLicenses, type LicenseResponse } from "../api/client";
import { getThemeAttributionGroups } from "../appearance/catalog";

const DISPLAY_ASSET_GROUPS = getThemeAttributionGroups();

export default function LicensesPage() {
  const [data, setData] = useState<LicenseResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchLicenses().then(setData).catch((err: Error) => setError(err.message));
  }, []);

  const bookSources = data?.book_sources ?? [];
  const tsumeSources = data?.tsume_sources ?? [];

  return (
    <section className="licenses-page" data-testid="licenses-page">
      <h1>データ出典・ライセンス</h1>
      <p className="muted">
        外部定跡・詰将棋データを取り込んだ場合は、出典、ファイルハッシュ、ライセンス本文をここに表示します。
      </p>
      <section aria-labelledby="display-assets-heading">
        <h2 id="display-assets-heading">表示素材</h2>
        {DISPLAY_ASSET_GROUPS.map(({ attribution, pieceThemes, boardThemes }) => <article className="license-source-card" id={attribution.noticeAnchor} key={`${attribution.sourceUrl}:${attribution.licenseUrl}`}>
          <h3>{attribution.sourceName}</h3>
          <dl>
            <dt>駒テーマ</dt><dd>{pieceThemes.map((theme) => theme.label).join(" / ") || "-"}</dd>
            <dt>盤テーマ</dt><dd>{boardThemes.map((theme) => theme.label).join(" / ") || "-"}</dd>
            <dt>ライセンス</dt><dd><a href={attribution.licenseUrl}>{attribution.licenseName}</a></dd>
            <dt>配布元</dt><dd><a href={attribution.sourceUrl}>{attribution.sourceName} 公式配布ページ</a></dd>
            <dt>第三者通知</dt><dd><code>THIRD_PARTY_NOTICES.md#{attribution.noticeAnchor}</code></dd>
          </dl>
        </article>)}
      </section>
      {error && <p className="error">{error}</p>}
      {!data && !error && <p>読み込み中...</p>}
      {data && bookSources.length === 0 && tsumeSources.length === 0 && <p>登録済みの外部データはありません。</p>}
      <div className="license-source-list">
        {tsumeSources.map((source) => (
          <article className="license-source-card" key={source.name}>
            <h2>{source.name}</h2>
            <dl>
              <dt>種別</dt>
              <dd>詰将棋データ</dd>
              <dt>ライセンス</dt>
              <dd>{source.license_name || "-"}</dd>
              <dt>問題数</dt>
              <dd>{source.problem_count.toLocaleString()}</dd>
              <dt>URL</dt>
              <dd>{source.source_url ? <a href={source.source_url}>{source.source_url}</a> : "-"}</dd>
            </dl>
            {source.copyright_notice && <p>{source.copyright_notice}</p>}
            <p className="muted">詰将棋データの一部は tokuhirom/tanuki-tsume-shogi を利用しています。</p>
          </article>
        ))}
        {bookSources.map((source) => (
          <article className="license-source-card" key={source.id}>
            <h2>{source.name}</h2>
            <dl>
              <dt>バージョン</dt>
              <dd>{source.version || "-"}</dd>
              <dt>ライセンス</dt>
              <dd>{source.license_name || "-"}</dd>
              <dt>局面数 / 候補手数</dt>
              <dd>{source.position_count.toLocaleString()} / {source.move_count.toLocaleString()}</dd>
              <dt>ファイル</dt>
              <dd>{source.file_name || "-"}</dd>
              <dt>SHA-256</dt>
              <dd className="hash-text">{source.file_sha256 || "-"}</dd>
              <dt>URL</dt>
              <dd>{source.source_url ? <a href={source.source_url}>{source.source_url}</a> : "-"}</dd>
            </dl>
            {source.copyright_notice && <p>{source.copyright_notice}</p>}
            {source.note && <p className="muted">{source.note}</p>}
            <h3>ライセンス表示</h3>
            <pre className="license-text">{source.license_text || source.license_name || "ライセンス本文は未登録です。"}</pre>
          </article>
        ))}
      </div>
    </section>
  );
}
