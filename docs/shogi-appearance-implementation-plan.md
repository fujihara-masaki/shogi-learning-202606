# 将棋盤・将棋駒の画像テーマ機能 実装計画

## 0. 目的と前提

本書は、既存の文字駒・CSS 盤を後方互換な標準テーマとして残しつつ、駒と盤を独立して選べる画像テーマと設定画面を段階導入するための計画である。今回は調査と設計のみを対象とし、素材の取得、アプリケーションコードの変更、将棋ロジックの変更は行わない。

基本方針は次のとおりとする。

- 局面、合法手、SFEN、指し手、成り、クリック、ドラッグ、キーボード、学習進捗は表示テーマから独立させる。
- `ShogiBoard` と `EditorBoard` の状態・操作モデルは統合せず、駒の描画と盤面表面など、表示上の小さな境界だけを共有する。
- `pieceTheme` と `boardTheme` は別々の設定として保持する。組み合わせプリセットを後日追加しても、この正規化した設定を上書きするだけとする。
- 盤画像は背景レイヤーとし、81 マスの DOM、ARIA、フォーカス、選択・合法手・直前手レイヤーを維持する。
- 初期リリースの保存先はブラウザーの `localStorage` とし、バックエンド、DB、アカウント同期は追加しない。

## 1. 現状調査

### 1.1 盤面を利用する機能

| 機能 | 入口・呼び出し経路 | 盤面 | 現状の特徴 |
| --- | --- | --- | --- |
| 詰め将棋 | `TsumePage` → `TsumePlayer` | `ShogiBoard` | `useTsumeSession` の局面を表示。反転、戻る、リセット、ヒント、解答再生を持つ |
| タイムアタック | `TimeAttackPage` | `ShogiBoard` | セッション中だけ表示し、常に非反転。問題遷移とタイマーはページ側 |
| 定跡学習 | `OpeningStudyPage` | `ShogiBoard` | 正誤判定、分岐、再生、直前手の from/to 表示。現在は非反転 |
| 次の一手 | `NextMoveStudyPage` | `ShogiBoard` | 問題の手番が後手なら初期表示を反転。回答前後の局面と学習状態は `useNextMoveSession` が管理 |
| 復習 | `ReviewPage` → `/tsume?problem=...` または `/next-move/:id?policy=weak` | 遷移先の `ShogiBoard` | 復習一覧自体には盤面がなく、詰め将棋／次の一手の既存経路を再利用 |
| 問題作成（配置） | `ProblemEditorPage` | `EditorBoard` | 独自の可変 `EditorPosition`、配置／移動／削除ツール、持ち駒数入力を持つ |
| 問題作成（解答記録） | `ProblemEditorPage` → `SolutionRecorder` | 独自の `.board-grid.editor-grid` | `EditorBoard` と別の盤 DOM・文字駒描画を持つ。全盤面適用時の見落とし防止対象 |

`ShogiBoard` の直接利用箇所は `TsumePlayer`、`TimeAttackPage`、`OpeningStudyPage`、`NextMoveStudyPage` の 4 系統である。詰め将棋の復習は `TsumePage`／`TsumePlayer`、次の一手の復習は `NextMoveStudyPage` に合流するため、テーマを各ページへ個別に渡すよりアプリ上位の appearance context から盤面が読む方が漏れにくい。

### 1.2 ルーティングとナビゲーション

`App.tsx` は `BrowserRouter` 内に全ルートと共通ナビゲーションを置く。デスクトップでは副次リンクも上部に表示し、720px 以下では主要 4 項目と「その他」の下部ナビに切り替える。`MorePage.tsx` には復習、学習記録、作成、データ出典がカードとして並ぶ。設定は `/settings` を追加し、まず「その他」のカードに置く。デスクトップで常時表示するかはナビ項目の過密を避けるため初期 PR では見送り、「その他」を共通の入口とする。

### 1.3 出典・ライセンス

- `/licenses` の `LicensesPage` は API の `book_sources` と `tsume_sources` を表示する、取り込みデータ向けの動的画面である。
- ルートの `THIRD_PARTY_NOTICES.md` は配布物に同梱する第三者通知を記録する場所として既に存在する。
- 画像素材はデータベース取り込み物ではなく静的配布物なので、一次情報は `THIRD_PARTY_NOTICES.md` とテーマ catalog のメタデータに置く。画面上では `/licenses` に「表示素材」節を追加するか、設定画面から同ファイル相当の静的情報へ誘導する。既存 API レスポンスへ無理に混在させない。

### 1.4 テスト構成

- Vitest は `frontend/vitest.config.ts` で `src` 配下の `*.test.ts(x)` を実行できる。現状は将棋ロジック、API、ページソースの回帰テストが中心で、React DOM 用の Testing Library 依存はない。
- Playwright は Chromium 1 project、実バックエンド／Vite を起動する構成で、`frontend/e2e/shogi-learning.spec.ts` と `next-move.spec.ts` に主要フローがある。盤のクリック、持ち駒、キーボード、Escape、成りダイアログ、定跡、タイムアタック、ライセンス、360px 幅のナビ・盤・エディタを既に検証している。
- 品質ゲートは `npm run lint`、`npm run build`、`npx vitest run`、`npm run e2e` とする（`package.json` には現時点で Vitest 専用 script がないため明示的に `npx vitest run` を使う）。

## 2. 現行盤面コンポーネント構成

### `ShogiBoard`

- 入力は tsshogi の `ImmutablePosition`、反転、操作可否、直前手、`onUserMove`。
- コンポーネント内部で盤上／持ち駒の選択、合法な移動先、成り選択、roving tabindex、フォーカス復帰、ドラッグ＆ドロップを管理する。
- 9 個の `role="row"` と 81 個の `role="gridcell"` を維持し、マスごとに座標・駒・状態を含む `aria-label` を生成する。
- ローカル `PieceFace` は tsshogi の `Piece` を漢字へ変換し、後手と盤反転の関係から 180 度回転する。盤上と持ち駒で共用されている。

### `EditorBoard`

- API 編集用の独自 `EditorPosition` を受け、配置、移動、削除と持ち駒数の編集結果を `onChange` へ返す。
- 81 マスは `button` で、`ShogiBoard` の合法手、成りダイアログ、反転、roving tabindex、ドラッグ処理を共有しない。
- `PIECE_LABEL` を直接描画しており、パレット、盤上の駒、持ち駒の数値入力ラベルという異なる表示箇所がある。

### 共通化範囲の判断

両者を一つの Board コンポーネントへ統合すると、tsshogi と editor 独自モデル、ゲーム操作と配置ツール、ARIA パターンの差を吸収する巨大な props/API が必要になる。これは採用しない。共有候補は以下に限定する。

1. 表示用の正規化済み `PieceVisual` と、それを描く `PieceFace`。
2. `TextPieceFace`、`ImagePieceFace` と画像失敗時のフォールバック。
3. CSS class／CSS custom properties を付与する `BoardSurface`（既存の子 DOM をそのまま受け取る薄い wrapper）。
4. theme catalog、設定の検証、piece asset resolver。

`SolutionRecorder` にも重複した文字駒描画があるため、PR-A の調査・アダプター対象に含める。ただしレコーダーの手順記録ロジックは共通化しない。

## 3. 課題

1. 駒名、王／玉、成駒、向きに関する表示判断が `ShogiBoard` と editor 系で分散している。
2. `.board-grid`、`.board-cell`、`.piece-face` はグローバル CSS で単一の色を前提とし、テーマの適用境界がない。
3. tsshogi の `PieceType` と editor の SFEN 風 code は型も成駒表現も異なる。画像パス resolver がどちらかのドメイン型に依存すると再利用できない。
4. 画像欠損・ロード失敗時の安全な経路、設定値の schema/version 検証、SSR ではないものの storage 利用不能時の扱いが未定義である。
5. 外部画像のライセンス、加工可否、再配布条件、クレジット表記は素材ごとに公式配布元で確認する必要がある。
6. 設定変更で盤コンポーネントが不用意に再 mount されると、選択、フォーカス、成りダイアログや親の学習状態を失い得る。

## 4. 推奨アーキテクチャ

想定する依存方向は以下である。

```text
AppearanceProvider ── validated settings + catalog lookup
       │
       ├── SettingsPage / AppearancePreview
       │
       ├── ShogiBoard ── PieceVisual adapter ─┐
       ├── EditorBoard ─ PieceVisual adapter ─┼─ PieceFace
       └── SolutionRecorder adapter ──────────┘   ├─ TextPieceFace
                                                  └─ ImagePieceFace → resolver

Board DOM ── BoardSurface(theme CSS variables/classes) ── background layer
```

### 表示境界

- `PieceVisual` は `{ side: "black" | "white"; kind; promoted }` のような表示専用値とする。王／玉の表記差など文字テーマ固有の決定は `TextPieceFace` に寄せる。
- 各盤は自分のモデルを `PieceVisual` へ変換する小さな純粋関数を持つ。合法手や SFEN データを表示層へ移さない。
- `PieceFace` は appearance と `PieceVisual`、表示方向、用途（board／hand／palette／preview）を受ける。操作イベントや `draggable` は親の既存 holder/button に残す。
- `BoardSurface` は `data-board-theme`、テーマ由来の CSS custom properties、背景だけを提供する。セルは透明を基本とし、既存ハイライトは半透明の上層として残す。テーマによってコントラスト不足になる場合は catalog の overlay token を使う。
- appearance の値を React `key` に使用しない。テーマ切替は同じ盤 DOM の再描画に留め、局面・選択・フォーカスを保持する。

### 画像失敗時の縮退

`ImagePieceFace` は decorative な `<img alt="" draggable={false}>` とする。読み上げ名は従来どおりセル／操作ボタン側に残す。resolver が `null`、画像の `onError`、またはテーマが不完全な場合は、その駒だけ `TextPieceFace` に切り替える。画像をセルイベントの受け手にせず、`pointer-events: none` として、壊れた画像がクリック、ドラッグ、キーボードを妨げないようにする。盤背景の失敗時は背景色と罫線が残る CSS の複数 background／fallback color を使用する。

## 5. テーマデータモデル

公開設定 ID と catalog は文字列 union を catalog から導出し、任意文字列を UI の型へ cast しない。概念例は次のとおり。

```ts
interface ShogiAppearanceSettings {
  pieceTheme: PieceThemeId;
  boardTheme: BoardThemeId;
}

interface StoredAppearanceV1 extends ShogiAppearanceSettings {
  version: 1;
}

interface ThemeAttribution {
  sourceName: string;
  sourceUrl: string;
  licenseName: string;
  licenseUrl?: string;
  copyrightNotice?: string;
  noticeAnchor: string;
}

interface PieceThemeDefinition {
  id: PieceThemeId;
  label: string;
  mode: "text" | "image";
  assets?: Partial<Record<PieceAssetKey, string>>;
  attribution?: ThemeAttribution;
}

interface BoardThemeDefinition {
  id: BoardThemeId;
  label: string;
  backgroundImage?: string;
  fallbackColor: string;
  lineColor: string;
  selectionOverlay: string;
  attribution?: ThemeAttribution;
}
```

`PieceAssetKey` は少なくとも side × 基本 8 種 × promoted state を区別する正規キーとする（成れない金・王、持ち駒には成駒がないことを型／resolver で扱う）。素材が先後別画像を持たない場合は `white` を黒画像＋CSS 回転へ alias できるが、この規則も theme 定義内の `orientation: "rotate-opponent" | "explicit-sides"` 等で宣言し、ファイル名の推測に依存しない。盤反転は「見る向き」であり駒の所有者は変えないため、resolver の asset key と最終 CSS 回転を別の純粋関数としてテストする。

標準 ID は安定した `text-standard`／`board-standard` とする。catalog の全テーマは起動時に構造検証できるようにし、未知の ID、不足 mapping、将来 version は各軸ごとに標準へ戻す。一方の値が不正でも、他方の有効な選択は保持する。

## 6. アセット配置案

```text
frontend/public/assets/shogi/
  pieces/<theme-id>/
    black/pawn.webp ...
    white/pawn.webp ...        # explicit-sides の場合
  boards/<theme-id>/board.webp
  previews/<theme-id>.webp     # 必要になった PR-D でのみ
frontend/src/appearance/
  catalog.ts
  types.ts
  pieceResolver.ts
  storage.ts
  adapters.ts
```

- Vite の `public` 配下を使い、配備 base path を考慮した URL helper を一箇所に置く。コンポーネントに `/assets/...` を直書きしない。
- ファイル名は小文字 ASCII、theme ID は永続 ID とし、表示名や配布元のファイル名変更から切り離す。
- PNG/SVG/WebP の採用、加工・変換、縮小画像の生成可否は原素材の規約を確認して決める。盤は高 DPI でも罫線がずれないよう、画像に罫線を含むか、CSS 罫線を重ねるかをテーマ単位で明示する。初期案は木目を背景、罫線を CSS として既存マスとの位置ずれを避ける。
- 未使用テーマを最初から bundle に import せず、静的 URL としてブラウザーキャッシュを利用する。最小テーマの総容量と Lighthouse/Network を確認する。

## 7. 設定保持方式

- key: `shogi.appearance.v1`
- value: `{"version":1,"pieceTheme":"...","boardTheme":"..."}`
- `loadAppearanceSettings()` は JSON parse、plain object、version、各 ID の catalog 所属を検証し、例外を外へ出さない。破損 JSON、`null`、配列、未知 ID、旧／未来 version は安全に標準値へ縮退する。
- `saveAppearanceSettings()` は UI state を先に更新し、storage 書き込み失敗（無効化、容量、privacy mode）時も当該タブでは動作を続け、設定画面に非致命的な保存警告を表示する。
- `resetAppearanceSettings()` は標準値を保存する（または key を削除して標準値へ戻す方式に統一）し、UI を即時更新する。
- 初期 mount で一度だけ同期的に lazy initializer から読む。全盤面が同じ値を得られるよう `AppearanceProvider` を `BrowserRouter` 内またはその直上に置く。
- 同一タブが初期範囲。複数タブ同期が必要なら `storage` event 対応を追加できるが、初期完了条件には含めない。
- 現時点ではサーバー同期要件がなく、設定は学習データでもないため、バックエンド API／DB migration は追加しない。

## 8. 設定画面案

`/settings` に「表示設定」ページを設け、`MorePage` に「設定 — 駒と盤の見た目を変更」カードを追加する。

初期 UI は、単純な select より比較しやすく、かつ実装を抑えたラジオカード方式を推奨する。

- 「駒」fieldset と「盤」fieldset を独立させ、各 option に名称、小さな見本、選択状態を表示する。
- 下部に 3×3 程度＋持ち駒の小型 `AppearancePreview` を置く。実ゲーム状態を生成せず、固定の表示専用 fixture に先手、後手、成駒を含める。
- 選択は即時 preview と全画面へ反映・保存する。「標準設定に戻す」は確認不要だが結果を live region で通知する。
- 現在値をテキストでも示し、画像だけで選ばせない。カードは native radio を基礎にしてキーボード操作、fieldset/legend、focus-visible を確保する。
- テーマの出典とライセンス名、および `/licenses` へのリンクを選択肢またはページ末尾に表示する。
- 360px では 1 列、preview は `max-width: 100%` と同じ cell-size 計算を使い、ページ全体に横スクロールを生じさせない。

## 9. ライセンス／出典管理

画像を実際に導入する PR-B の開始前に、**公式配布元の最新の規約**で、ライセンス名、著作者、再配布、改変、形式変換、アプリ同梱、クレジット方法を再確認する。「Shogi Images」という名称だけからライセンスを推測しない。確認 URL と確認日を PR に記録し、条件が不明なら素材を commit しない。

導入時は以下を同一 PR の必須成果物とする。

1. `THIRD_PARTY_NOTICES.md` に素材セット単位の出典 URL、著作者、正確なライセンス、著作権表示、変更内容を追記。
2. catalog の `attribution` に UI 表示用の同じ出典情報と notice anchor を登録（ライセンス本文を二重管理しない）。
3. 必要なら素材ディレクトリ内に配布元の LICENSE/COPYING を原文のまま配置。
4. `/licenses` に静的な「表示素材」情報を表示し、既存の API エラーがあっても静的通知は閲覧できる設計にする。
5. PR review checklist で catalog、実ファイル、notice の 3 者が一致することを確認する。

## 10. PR 分割（推奨 5 PR）

### PR-A: 表示レイヤーの抽出（見た目・挙動不変）

目的は文字駒と標準盤の表示責務だけを抽出し、以降の差分を小さくすることである。`ShogiBoard` の操作ロジック、`EditorBoard` の編集ロジックは動かさない。`SolutionRecorder` も共通 `PieceFace` に載せ、全盤面の適用漏れを先に解消する。

**変更対象候補**

- `frontend/src/components/ShogiBoard.tsx`
- `frontend/src/components/EditorBoard.tsx`
- `frontend/src/components/SolutionRecorder.tsx`
- 新規 `frontend/src/components/shogi/PieceFace.tsx`
- 新規 `frontend/src/components/shogi/BoardSurface.tsx`
- 新規 `frontend/src/appearance/types.ts`, `adapters.ts`
- `frontend/src/index.css`
- 新規 `frontend/src/appearance/*.test.ts`

**テスト**

- Vitest: tsshogi/editor code から `PieceVisual` への全駒・全成駒変換、王／玉表示、先後・反転時の文字向き。
- Playwright: 既存の盤クリック、持ち駒 drop/click、矢印＋Enter、Escape、成り、反転、editor 配置、solution recorder を標準テーマで回帰確認。
- DOM: 81 gridcell、既存 test id、ARIA label、roving tabindex、ハイライト class が不変。
- `npm run lint`、`npm run build`、`npx vitest run`、`npm run e2e`。

### PR-B: テーマ基盤、画像テーマ 1 組、通知

catalog、resolver、テーマ対応 `PieceFace`／`BoardSurface` を導入する。標準設定は従来表示のままにし、開発テスト用または明示的 props で画像テーマを選べる段階まで進める。正式素材を 1 駒テーマ＋1 盤テーマだけ追加し、その PR で出典を完結させる。

**変更対象候補**

- `frontend/src/appearance/catalog.ts`, `pieceResolver.ts`, `types.ts`
- `frontend/src/components/shogi/PieceFace.tsx`, `TextPieceFace.tsx`, `ImagePieceFace.tsx`, `BoardSurface.tsx`
- `frontend/public/assets/shogi/**`
- `frontend/src/index.css`
- `frontend/src/pages/LicensesPage.tsx`
- `THIRD_PARTY_NOTICES.md` と必要な素材 LICENSE
- resolver／catalog の Vitest、既存 E2E spec

**テスト**

- Vitest: 先手／後手、基本駒、全成駒、持ち駒、explicit/rotate 方針、反転の resolver table test。不足 mapping と未知 theme の文字 fallback。
- Playwright: テスト用選択状態で画像 `src`／theme data attribute を確認し、クリック・drag・キーボード・反転後も局面と操作が同じことを確認。
- 画像 404 を route interception で発生させ、文字駒と CSS 背景に縮退して着手できることを確認。
- notice と catalog attribution の整合をレビューし、全 asset URL が build output で解決することを確認。

### PR-C: 設定保存と `/settings`

Provider、versioned localStorage、設定画面、More からの導線、リセットを追加し、全盤面がグローバル設定を読むようにする。この時点で利用者向け機能として完成させる。

**変更対象候補**

- 新規 `frontend/src/appearance/AppearanceProvider.tsx`, `storage.ts`
- 新規 `frontend/src/pages/SettingsPage.tsx`
- 新規 `frontend/src/components/AppearancePreview.tsx`
- `frontend/src/App.tsx`, `frontend/src/pages/MorePage.tsx`
- `ShogiBoard.tsx`, `EditorBoard.tsx`, `SolutionRecorder.tsx`（context 接続のみ）
- `frontend/src/index.css`
- storage Vitest、Playwright specs

**テスト**

- Vitest: 正常 V1、欠損、破損 JSON、未知 ID、各軸だけ不正、旧／未来 version、storage read/write 例外、reset。
- Playwright: `/settings` のラジオと preview、駒だけ／盤だけの独立変更、reload 復元、標準へ戻す、More 導線。
- テーマ変更前後の SFEN 相当の DOM 配置、手数／フィードバック、選択中マスを比較し、学習状態が変わらないことを確認。
- キーボードのみで設定を変更でき、fieldset/label/live region が読み取れることを確認。

### PR-D: テーマ拡張と preview 改善

ライセンス確認済みの追加テーマを小数追加し、必要ならおすすめ組み合わせボタンを提供する。プリセットは `{ pieceTheme, boardTheme }` を一括設定するだけで、永続モデルに `presetTheme` を追加しない。

**変更対象候補**

- `frontend/src/appearance/catalog.ts`
- `frontend/public/assets/shogi/**`
- `frontend/src/components/AppearancePreview.tsx`, `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/index.css`
- `THIRD_PARTY_NOTICES.md`, `LicensesPage.tsx`
- catalog tests、設定 E2E

**テスト**

- 全 catalog entry の ID 一意性、asset mapping 完備、attribution 必須項目、プリセット適用後も両軸を個別変更できること。
- preview と実盤の resolver が同一であること、テーマ間を連続切替しても盤を再 mount しないこと。
- 各追加素材の 360px、通常／高 DPR、読み込みサイズを確認する。

### PR-E: 全導線回帰とテスト強化

テーマ機能を別実装する PR ではなく、全利用箇所の適用監査、アクセシビリティ、レスポンシブ、障害時の回帰テストを固める stabilization PR とする。ここで見つかった適用漏れだけを小さく修正する。

**変更対象候補**

- `frontend/e2e/shogi-learning.spec.ts`, `frontend/e2e/next-move.spec.ts` または新規 `appearance.spec.ts`
- 必要に応じて各盤面／CSS の小規模修正
- テスト fixture／helper
- 実装との差異が見つかった場合の本計画書更新

**テスト**

- 詰め将棋、タイムアタック、定跡、次の一手、両復習経路、EditorBoard、SolutionRecorder の smoke matrix を標準／画像テーマで実行。
- クリック、ドラッグ、キーボード、成り、盤面反転、持ち駒、選択／合法手／直前手、回答・戻る・リセットを検証。
- 360px で `documentElement.scrollWidth <= innerWidth`、盤・設定・editor が収まることを確認。
- 画像障害、localStorage 破損／利用不可、直接 URL `/settings`、reload を確認。
- `npm run lint`、`npm run build`、`npx vitest run`、`npm run e2e` を最終 gate とする。

## 11. テスト戦略の補足

### スクリーンショット比較

初期実装では全面的な pixel-perfect screenshot snapshot を主軸にしない。OS フォント、Chromium、画像デコード、device scale factor によるノイズが大きく、盤操作の回帰を見逃しやすいためである。主軸は以下とする。

- DOM 構造、ARIA、focus、theme ID、CSS custom property、`img src`／fallback の検証。
- 着手前後の座標別駒 descriptor、手数、フィードバックがテーマ変更で不変であること。
- 360px の scroll width と bounding box。

一方、各正式テーマについて「設定 preview＋実盤」の少数（デスクトップ 1、360px 1）の screenshot を PR review 用／緩い snapshot として採用する余地はある。固定 Chromium、フォント、DPR、animation 無効化が CI で保証できる場合に限定し、盤面ごとの大量 snapshot は作らない。

### Vitest の範囲

純粋関数（adapter、resolver、catalog、storage codec）を Vitest の中心とする。Context と設定 UI の細部を unit test するために React Testing Library を新規導入するかは PR-C 冒頭で判断する。依存を増やさない場合も、Provider の reducer/initializer を純粋関数として十分に検証し、統合は Playwright で担保できる。

## 12. 後方互換性

- default は `text-standard + board-standard` とし、初回訪問時の見た目、駒文字、盤色、操作を変えない。
- 既存の `ShogiBoardProps`、親の session hook、`onUserMove`、SFEN、API payload、DB schema は変更しない。appearance props を必須化せず context default を持たせる。
- 81 マス、座標 `data-square`、role、ARIA label、test id、選択／合法手／直前手 class を維持する。
- editor の `EditorPosition` と tsshogi の `ImmutablePosition` は変換・統合しない。
- 未知・削除済みテーマ、破損 storage、欠損／404 asset は標準表示へ戻し、操作不能にしない。
- 保存 key を versioned にし、将来の migration は `v2` reader または明示的 migration で追加する。catalog ID は一度公開したら安易に変更しない。

## 13. リスクと対策

| リスク | 対策 |
| --- | --- |
| 画像とセル境界がずれる | 木目と罫線を分け、81 DOM の CSS grid を基準にする。各 viewport で bounding box を検証 |
| 後手・成駒・反転の組み合わせ誤り | semantic asset key と orientation rule を分離し、全組み合わせ table test |
| 画像が pointer/drag を奪う | 操作 handler は既存 holder/cell、画像は `draggable=false` と `pointer-events:none` |
| 画像ロード失敗で空の駒になる | per-piece `onError` で文字 fallback。盤は fallback color/line を常設 |
| テーマ変更で学習状態や focus が消える | appearance を component key にせず表示だけ差し替え、切替中の局面・選択・focus を E2E 比較 |
| 木目上でハイライトや文字のコントラスト不足 | theme token と半透明 overlay、focus ring をテーマ横断で確認。画像だけに状態を依存させない |
| localStorage 例外／古い値 | codec で検証、各軸 fallback、try/catch は storage 操作時だけ、非致命警告 |
| asset 容量による初期表示悪化 | 1 セットから開始、適切な形式・寸法、遅延取得、Network/サイズ予算を PR-B で記録 |
| ライセンス違反や出典の重複不整合 | 公式配布元で導入時再確認し、notice/catalog/UI の checklist を必須化 |
| `SolutionRecorder` など適用漏れ | PR-A で盤描画 inventory を固定し、PR-E の全導線 matrix に含める |
| グローバル CSS の theme 漏れ | `.board-surface[data-board-theme]` 配下に scope し、標準 token を default にする |

## 14. 今回対象外

- 将棋エンジン、合法手、詰み判定、SFEN 仕様、指し手形式の変更
- 学習 DB schema、appearance 用バックエンド API、アカウント／クラウド同期
- 利用者による任意画像 upload、URL 指定、テーマ作成機能
- 初回からの大量テーマ導入、marketplace／download 機構
- `ShogiBoard` と `EditorBoard`（および `SolutionRecorder`）の状態・操作ロジックの完全統合
- 動的な OS dark mode 自動選択、複数タブ即時同期（将来拡張）
- 今回の計画 PR での素材 download や実装開始

## 15. 実装開始前に判断が必要な事項

1. 初回採用する駒・盤素材の公式配布 URLと、再配布・改変・形式変換・クレジット条件。条件を確認できなければ PR-B は標準／テスト fixture のみとする。
2. 素材が先後別画像を提供するか、同一画像の回転を許すか、王／玉を別画像にするか。
3. 盤画像に罫線が含まれるか。推奨は木目背景＋CSS 罫線だが、素材の構造と改変条件で確定する。
4. `/licenses` に静的表示素材を併記するか、別の「出典・ライセンス」ページへ拡張するか。初期推奨は既存 `/licenses` の節追加。
5. 設定 UI を即時保存とするか「適用」ボタン式にするか。局面を変えず比較しやすい即時保存を推奨する。
6. PR-C で React Testing Library を追加するか。純粋関数＋Playwright で不足する UI unit coverage と依存コストを比較して決める。

## 16. 実装完了条件

- 標準テーマが現行と同じ見た目・挙動であり、既存操作・ARIA・テスト selector が維持される。
- 利用者が `/settings` で駒と盤を独立選択し、組み合わせ preview、標準へ戻す操作を利用できる。
- `shogi.appearance.v1` から reload 後に復元し、破損、古い／未来 version、未知 ID、storage 利用不能時に標準へ安全に縮退する。
- `ShogiBoard` の全 4 直接利用系統、両復習経路、`EditorBoard`、`SolutionRecorder` に同じ設定が適用される。
- 先手、後手、全基本駒、成駒、持ち駒、盤面反転が resolver tests と E2E で確認される。
- テーマ切替前後で局面、手番、指し手履歴、問題進捗が変わらず、クリック、drag、keyboard、成り、focus、選択・合法手・直前手表示が動作する。
- asset 失敗時にも文字駒／標準盤へ縮退し、着手可能である。
- 360px 幅で盤、設定、editor にページ横スクロールがなく、focus と状態表示のコントラストが保たれる。
- 導入素材ごとに公式条件を導入時点で再確認し、asset、catalog、`THIRD_PARTY_NOTICES.md`、画面上の出典が一致する。
- 各 PR の対象テストに加え、最終的に lint、build、全 Vitest、全 Playwright が通る。

