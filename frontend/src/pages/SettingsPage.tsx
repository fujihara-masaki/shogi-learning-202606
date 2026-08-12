import { useState } from "react";
import { Link } from "react-router-dom";
import { useAppearance } from "../appearance/useAppearance";
import { APPEARANCE_PRESETS, BOARD_THEMES, getThemeAttributionGroups, PIECE_THEMES } from "../appearance/catalog";
import type { BoardThemeId, PieceThemeId } from "../appearance/types";
import AppearancePreview, { AppearanceCompactPreview } from "../components/AppearancePreview";

const ATTRIBUTION_GROUPS = getThemeAttributionGroups();

export default function SettingsPage() {
  const appearance = useAppearance();
  const [announcement, setAnnouncement] = useState("");
  return (
    <main className="settings-page" data-testid="settings-page">
      <h1>表示設定</h1>
      {appearance.storageWarning && <p className="banner banner-warning" role="alert">設定を端末に保存できませんでした。このタブでは引き続き利用できます。</p>}
      <div className="settings-layout">
        <div className="settings-controls">
          <section className="appearance-presets" aria-labelledby="appearance-presets-title">
            <h2 id="appearance-presets-title">おすすめの組み合わせ</h2>
            <div className="appearance-preset-buttons">
              {Object.values(APPEARANCE_PRESETS).map((preset) => <button type="button" key={preset.id} onClick={() => { appearance.setAppearance({ pieceTheme: preset.pieceTheme, boardTheme: preset.boardTheme }); setAnnouncement(`おすすめの組み合わせ「${preset.label}」を適用しました`); }}>{preset.label}</button>)}
            </div>
          </section>
          <fieldset><legend>駒</legend>{Object.values(PIECE_THEMES).map((theme) => <label className="theme-option" key={theme.id}><input type="radio" name="piece-theme" value={theme.id} checked={appearance.pieceTheme === theme.id} onChange={() => { appearance.setPieceTheme(theme.id as PieceThemeId); setAnnouncement(`駒を${theme.label}に変更しました`); }} /><span className="theme-option-content"><span>{theme.label}</span><AppearanceCompactPreview pieceTheme={theme.id} boardTheme={appearance.boardTheme} /></span>{appearance.pieceTheme === theme.id && <strong>選択中</strong>}</label>)}</fieldset>
          <fieldset><legend>盤</legend>{Object.values(BOARD_THEMES).map((theme) => <label className="theme-option" key={theme.id}><input type="radio" name="board-theme" value={theme.id} checked={appearance.boardTheme === theme.id} onChange={() => { appearance.setBoardTheme(theme.id as BoardThemeId); setAnnouncement(`盤を${theme.label}に変更しました`); }} /><span className="theme-option-content"><span>{theme.label}</span><AppearanceCompactPreview pieceTheme={appearance.pieceTheme} boardTheme={theme.id} /></span>{appearance.boardTheme === theme.id && <strong>選択中</strong>}</label>)}</fieldset>
          <button type="button" onClick={() => { appearance.resetToDefaults(); setAnnouncement("標準設定に戻しました"); }}>標準設定に戻す</button>
        </div>
        <AppearancePreview pieceTheme={appearance.pieceTheme} boardTheme={appearance.boardTheme} />
      </div>
      <section className="settings-attributions" aria-labelledby="settings-attributions-title">
        <h2 id="settings-attributions-title">テーマの出典・ライセンス</h2>
        <ul>{ATTRIBUTION_GROUPS.map(({ attribution }) => (
          <li key={`${attribution.sourceUrl}:${attribution.licenseUrl}`}>
            <a href={attribution.sourceUrl} target="_blank" rel="noreferrer">{attribution.sourceName}</a>
            {" — "}
            <a href={attribution.licenseUrl} target="_blank" rel="noreferrer">{attribution.licenseName}</a>
          </li>
        ))}</ul>
        <p><Link to="/licenses">データ出典・ライセンス</Link></p>
      </section>
      <p className="visually-hidden" aria-live="polite" aria-atomic="true">{announcement}</p>
    </main>
  );
}
