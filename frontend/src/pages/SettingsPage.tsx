import { useState } from "react";
import { useAppearance } from "../appearance/useAppearance";
import { BOARD_THEMES, PIECE_THEMES } from "../appearance/catalog";
import type { BoardThemeId, PieceThemeId } from "../appearance/types";
import AppearancePreview from "../components/AppearancePreview";

export default function SettingsPage() {
  const appearance = useAppearance();
  const [announcement, setAnnouncement] = useState("");
  return (
    <main className="settings-page" data-testid="settings-page">
      <h1>表示設定</h1>
      {appearance.storageWarning && <p className="banner banner-warning" role="alert">設定を端末に保存できませんでした。このタブでは引き続き利用できます。</p>}
      <div className="settings-layout">
        <div className="settings-controls">
          <fieldset><legend>駒</legend>{Object.values(PIECE_THEMES).map((theme) => <label className="theme-option" key={theme.id}><input type="radio" name="piece-theme" value={theme.id} checked={appearance.pieceTheme === theme.id} onChange={() => { appearance.setPieceTheme(theme.id as PieceThemeId); setAnnouncement(`駒を${theme.label}に変更しました`); }} /><span>{theme.label}</span>{appearance.pieceTheme === theme.id && <strong>選択中</strong>}</label>)}</fieldset>
          <fieldset><legend>盤</legend>{Object.values(BOARD_THEMES).map((theme) => <label className="theme-option" key={theme.id}><input type="radio" name="board-theme" value={theme.id} checked={appearance.boardTheme === theme.id} onChange={() => { appearance.setBoardTheme(theme.id as BoardThemeId); setAnnouncement(`盤を${theme.label}に変更しました`); }} /><span>{theme.label}</span>{appearance.boardTheme === theme.id && <strong>選択中</strong>}</label>)}</fieldset>
          <button type="button" onClick={() => { appearance.resetToDefaults(); setAnnouncement("標準設定に戻しました"); }}>標準設定に戻す</button>
        </div>
        <AppearancePreview pieceTheme={appearance.pieceTheme} boardTheme={appearance.boardTheme} />
      </div>
      <p className="visually-hidden" aria-live="polite" aria-atomic="true">{announcement}</p>
    </main>
  );
}
