# 定跡分岐学習 UX・多段分岐・Wikipedia seed 拡張 実装計画

- 対象: `fujihara-masaki/shogi-learning-202606`
- 調査基準: `claude/clever-hopper-bphezm` 相当の履歴を含む現作業ツリー（2026-08-12）
- 対象履歴: PR #19、#20、#22、#23、#40（ローカルの merge commit と構成 commit を確認）
- 本書の範囲: 調査、設計、PR 分割、受け入れ条件。アプリ本体、DB schema、seed の変更は行わない。

> **事実・提案・外部確認の表記**
>
> - **[実装済み]**: 現在のコードまたはテストで確認できたもの。
> - **[部分実装]**: 構成要素はあるが、要求する UX / 多段構造 / テストまで完結していないもの。
> - **[未実装]**: 対応コードまたはカバレッジを確認できないもの。
> - **[提案]**: 後続 PR で採用を判断する設計。
> - **[要外部再確認]**: Wikipedia の現行本文・版 ID を seed 追加 PR の調査時に再取得すべきもの。本計画作成環境では Wikipedia への HTTP 接続が拒否されたため、現行コードが記録する URL・section・取得日と既存履歴以上の本文断定をしない。

## 1. 現状

### 1.1 アーキテクチャとデータフロー

```text
backend/app/seed.py
  SAMPLE_OPENING_LINES / branches / OPENING_TYPE_SEEDS
        │ seed_opening_lines(): tsshogi/python-shogi で合法手・SFENを生成
        ▼
SQLite
  opening_categories ─ opening_types
  opening_lines ─ opening_line_moves
        │              ├ from_sfen / to_sfen
        │              ├ variation_group / sort_order
        │              └ parent_move_id
        ├ opening_positions
        └ opening_tags
        ▼
backend/app/routers/openings.py
  GET /api/openings, GET /api/openings/{id}, match 等
        ▼
frontend/src/api/client.ts
  ImportedOpeningLine / ImportedOpeningMove
        ▼
frontend/src/shogi/openings.ts
  openingFromImportedLine()
  from_sfen -> moves の Map と to_sfen による再帰
        ▼
OpeningLine.moves: OpeningMoveNode[]
  OpeningMoveNode.next: OpeningMoveNode[]
        ▼
path: number[]
  各 ply の sibling 配列に対する選択 index
        ▼
applyOpeningPath() -> position / steps / moves
expectedOpeningMove() -> current choices[0]
        ▼
frontend/src/pages/OpeningStudyPage.tsx
  currentChoices / board / branch buttons / replay / source
```

`opening_positions` は line に属する局面の検索・照合、`opening_tags` は一覧の分類・絞り込みに使われる。再生ツリーそのものは `opening_line_moves` から作られ、現 frontend は `parent_move_id` ではなく SFEN 接続を使う。

### 1.2 データ項目の現行意味

| 要素 | 現状コード上の意味 | 状態 / 留意点 |
|---|---|---|
| 本線 | sibling の `sort_order` が先頭、frontend では事実上 `choices[0]` | **[実装済み]** だが「本線」の永続的な意味は `variation_group == "main"` と配列順の二重表現 |
| 分岐 | 同じ `from_sfen` を持つ複数 move。seed の `branches` は本線の `from_ply` から派生 | **[部分実装]** 一次分岐は扱える |
| 分岐点 | `currentChoices.length > 1`、または通過 step の `choices.length > 1` | **[実装済み]** |
| `variation_group` | `main` または人間向け変化名。branch 行を束ね、表示ラベルにも転用 | **[部分実装]** 構造上の親と表示名が混在 |
| `parent_move_id` | branch の最初の行等に本線の分岐元 move ID を保存 | DB/API **[実装済み]**、frontend **[未使用]**。現 seed では branch 内の全行が同じ本線親を持ち得るため「直接親」としては未確立 |
| `from_sfen` / `to_sfen` | 各手の前後局面。API から frontend へ渡りツリー接続に使用 | **[実装済み]**。局面の同一性と手順上の親子を同一視している |
| `sort_order` | DB の同一 line / ply / group 内の安定順、frontend sibling の本線優先順 | **[実装済み]**。将来は「同一 parent の表示順」と明文化が必要 |
| `path: number[]` | root から各 sibling 配列で選んだ index の列 | **[実装済み]**。DB ID に依存せず軽量だが、tree 再構築で順序が変わると不安定 |
| `currentChoices` | root なら `opening.moves`、進行後なら末尾 node の `next` | **[実装済み]** |
| `expectedOpeningMove` | path をたどった先の `choices[0]` | **[実装済み]**、本線のみを正解にする原因 |
| `chooseBranch(index)` | 現在の `path` へ任意 index を追加 | **[実装済み]** |
| `switchBranch(stepIndex, branchIndex)` | 過去 path を分岐点直前で切り、別 index を追加 | **[実装済み]** |
| `stepForward()` | `expected` を表示し常に `0` を追加 | **[実装済み]**、本線固定 |
| `goToEnd()` | root から各階層の `choices[0]` を最後まで選ぶ | **[実装済み]**、現在 path を捨て本線終端へ移動 |

### 1.3 現在の分岐 UI

**[実装済み]**

- 「分岐あり」badge、現在局面の分岐候補 button、現在の分岐パス。
- `chooseBranch` による現在局面からの任意分岐選択。
- 「通過した分岐」と `switchBranch` による過去の分岐点への復帰・切替。
- 一手戻る、最初に戻る、一手進む、最後まで進む、ヒント。
- 現在手に対応する Wikipedia 出典、section、license、取得日、coverage、note の表示。
- Vitest の二択 imported tree 構築・両経路再生。
- Playwright の通常本線に対する正解/不正解、undo/reset、自動再生。

**[部分実装]**

- PR #22 の出典 metadata / 分岐再生と PR #23 の長手順・分岐 seed は一次分岐の学習を可能にしたが、盤上操作と button 操作の正解集合が一致しない。
- `OpeningMoveNode.next` 自体は任意深さを表せるが、seed 記法と親子復元契約が多段分岐を保証しない。
- API は `parent_move_id` を返すが、型変換と tree builder は使わない。

### 1.4 盤上で分岐候補を指した現行挙動

`handleUserMove` は `expectedOpeningMove(opening, path)` の返す `choices[0]` だけを `isExpectedOpeningMove` で比較する。たとえば候補が「本線 △8四歩 / △6二銀 / △6二金」の順なら、盤上の △6二金 は合法かつ登録済みでも「不正解」になり、hint は △8四歩を示す。一方、同じ △6二金 は分岐 button なら進める。正解時も `path` に常に `0` を追加する。この不整合が最優先の UX defect である。

## 2. 問題

1. **正解集合の不一致**: board は本線一手、buttons は全分岐を正解として扱う。
2. **用語と動作の曖昧さ**: 「一手進む」「最後まで進む」が本線固定であることをラベルから判断できない。特に `goToEnd` は現在選択中の変化を継続せず root 本線へ戻る。
3. **分岐説明不足**: 現在の button は branch label を中心にし、各変化の意味・出典・本線である理由を比較しにくい。
4. **構造契約不足**: `variation_group`、`parent_move_id`、SFEN、`sort_order` の責務が重なり、branch-of-branch の seed 表現がない。
5. **transposition の曖昧さ**: 同じ SFEN への合流は `movesByFrom` を共有するため、異なる由来・ラベルの後続が意図せず合流し得る。`seen` は循環を止めるが DAG の意味を保存しない。
6. **全体像不足**: 現在局面と通過分岐は見えるが、定跡全体の変化構造を開始前・途中に俯瞰できない。
7. **provenance 粒度不足**: 既定 metadata の「局面図を参考に再構成」と個別の「本文明示」が自由文に埋まり、機械検査できない。
8. **coverage の誤読余地**: `coverage_status` は列挙値でなく、note と実際の move 数の整合を保証する検査がない。
9. **E2E 不足**: 盤上から非0分岐、多段分岐、一覧ジャンプ、360px、keyboard/accessibility の回帰検査がない。

## 3. 目標 UX

### 3.1 正解判定を currentChoices 全体へ統一

**[提案]** `expected` を「本線表示用」として残しても、判定は次のように全候補から行う。

```ts
const branchIndex = currentChoices.findIndex(
  (choice) => choice.usi === move.usi,
);
if (branchIndex < 0) {
  // 登録候補のどれにも一致しない: 不正解
  return;
}
setPath((prev) => [...prev, branchIndex]);
```

- 一致した node を feedback / source / last move の対象にする。
- hint は「本線の一手」だけを暴露せず、初回は候補数または共通の着手目的、明示要求後は本線を示す。
- 同一分岐点に同一 USI の sibling が複数あると board 操作だけでは区別不能なので、**PR-A の前提として PR-A0 で既存データを正規化**し、seed validator / backend test で再発を禁止する。説明や後続だけが違う同じ手は一 node に統合し、分岐はその着手後に表現する。
- `currentChoices.length === 0` の時だけ completed とする。
- unit test は `findIndex` 相当を純粋 helper（例: `findOpeningChoiceIndex`）へ抽出して board component を介さず検査する。

### 3.2 分岐点カード

分岐が2件以上なら見出しを「この局面には N つの進行があります」とし、次のカードを sibling ごとに表示する。

```text
本線  △8四歩
本文の基本進行
[この変化を見る]

変化  △6二銀
銀で受ける変化
[この変化を見る]

変化  △6二金
有効な受け
[この変化を見る]
```

- `sort_order` 先頭かつ main のカードに「本線」。その他は「変化」。色だけで区別せず text / icon / border を併用。
- 現在選択中は `aria-current="step"` 相当の明示、button は disabled にせず「選択中」と読める状態にする（再選択が無動作なら disabled + 状態説明でもよい）。
- card 名は「本線 △8四歩、この変化を見る」のように一意な accessible name を持つ。
- branch label、notation/USI、短い explanation、provenance/coverage badge を表示。長い source note は出典 section に置く。
- 360px では一列、button は44px程度の target、長い日本語・USI・URLで横 overflow を起こさない。
- focus は分岐選択後に feedback または盤へ唐突に飛ばさない。切替後は対応する node/card へ維持し、`aria-live="polite"` で結果を通知。

### 3.3 操作仕様

| 操作 | 仕様 | 推奨ラベル |
|---|---|---|
| 盤上で指す | `currentChoices` の任意 USI を正解にし、その index を追加 | 盤面案内「登録されたいずれかの定跡手を指してください」 |
| 現在の分岐を選ぶ | card で index を path に追加し一手進める | 「この変化を見る」 |
| 一手進む | 分岐がない時は唯一手。分岐点では main / sort先頭へ進むことを明示 | 「本線を一手進む」 |
| 最後まで | **現在 path は維持**し、現在局面以降を各階層の本線で終端まで追加。root へ戻さない | 「ここから本線を最後まで再生」 |
| 一手戻る | path の末尾を1件除く。branch 選択も通常の一手 | 「一手戻る」 |
| 分岐点まで戻る | 現 path を後方検索し、直近の `choices.length > 1` の直前まで切る | 「直前の分岐点へ戻る」 |
| 別分岐へ切替 | 対象分岐 step より後を破棄し sibling index を置換。確認 dialog は不要だが破棄を live 通知 | 「△6二金へ切り替える」 |
| 最初へ | path を空にする | 「最初に戻る」 |

「選択中変化の続きを自動再生」と「各階層で本線を選ぶ」は区別する。本計画では、現在 path は保持し、未選択の先だけ `main` 優先で進む。分岐点で勝手に変化を選ばせたくない学習 mode は、将来「次の分岐点まで再生」を別操作として追加し、初期 PR-A では増やし過ぎない。

keyboard は board の既存 roving/focus 操作と card の native button を維持する。shortcut を加えるなら undo/replay と入力中要素の衝突を避け、画面表示・テストを必須にする。初期実装では独自 shortcut は非目標とする。

## 4. データモデル

### 4.1 推奨する責務

| 項目 | 将来の正規な責務 |
|---|---|
| `parent_move_id` | **構造**: 同じ line 内の直接親 move。root は `NULL`。各非root move は直前手の ID |
| `from_sfen` / `to_sfen` | **局面整合性**: 合法性、再生前後、検索・診断。親子決定の唯一の根拠にはしない |
| `variation_group` | **表示/出典**: 変化の人間向け stable slug/label。親子構造を表さない |
| `sort_order` | **順序**: 同一 `parent_move_id` 配下の sibling 表示順。0 を main 推奨とするだけでなく `is_main` の要否も PR-B で決定 |
| `ply` | root からの深さ。診断・表示用。親子構造の代用にしない |

`variation_group == "main"` だけでは branch A 内の main と全体本線を区別しづらい。必要十分な案は、move ごとの `branch_key` / `branch_label` と sibling ごとの `is_main` を seed DTO に持たせ、DB は当面 `variation_group` と `sort_order=0` へ写像すること。DB migration を避けられるかを fixture で検証し、曖昧なら小さな migration で `branch_key` と `is_main` を追加する。

### 4.2 seed 記法

現行 `moves` + `branches[{from_ply,...}]` を読み取る compatibility adapter を残し、新形式は DB ID を直書きしない stable key ベースとする。

```py
"move_nodes": [
  {"key": "m1", "parent_key": None, "usi": "7g7f", "sort_order": 0, "branch_key": "main"},
  {"key": "m2", "parent_key": "m1", "usi": "3c3d", "sort_order": 0, "branch_key": "main"},
  {"key": "a",  "parent_key": "m2", "usi": "...", "sort_order": 1, "branch_key": "a", "branch_label": "A"},
  {"key": "a1", "parent_key": "a", "usi": "...", "sort_order": 0, "branch_key": "a1", "branch_label": "A1"},
]
```

validator は key 一意、親の存在、同一 line、acyclic、root、ply、sibling sort order、sibling USI 一意、全手合法、親 `to_sfen == 子 from_sfen`、生成 SFEN と格納 SFEN の一致を検査する。upsert は key を自然キーとして ID を解決する。既存 DB に stable key がない場合、PR-B migration が必要になる可能性が高い。

## 5. 多段分岐

### 5.1 現状のままで扱える範囲

`OpeningMoveNode.next`、`path`、`applyOpeningPath`、`chooseBranch`、`switchBranch` は tree が正しく構築されれば A→A1/A2、B→B1/B2 を任意深さで扱える。`from_sfen` / `to_sfen` が全経路で異なる純粋 tree なら現 builder も多段分岐を偶然構築できる。

### 5.2 制約

- `branches.from_ply` は本線 ply を指し、branch 内の特定 node を親として別 branch を生やす表現がない。
- seed の `parent_move_id` 解決は本線の `main_move_id_by_ply` 中心で、直接親を一貫して保存しない。
- API は flat 配列を `variation_group, ply, sort_order` で返し、親順を保証しない。
- frontend interface は imported move の `parent_move_id` を受け取る API 型があっても `ImportedOpeningLike` / builder で利用しない。
- 同じ `from_sfen` の手をすべて sibling とするため、異なる履歴の同一局面を区別できない。

### 5.3 提案する構築順

1. API move に `id` と `parent_move_id` を必須（root のみ null）として返す。
2. frontend は `id -> node` と `parent_move_id -> children` で tree を作り、`sort_order`, stable tie-break (`id`) で sibling を整列。
3. SFEN は各 edge の assertion とする。不一致は API/seed test で失敗し、production UI では line load error と診断 ID を表示。
4. legacy 行で親が欠ける間だけ SFEN fallback を許可し、telemetry/test で件数を0へ近づけた後に削除する。
5. API version を変えない場合も field 追加は additive。既存 static opening と learning sample の linear tree は維持する。

### 5.4 transposition

初期段階では一般 DAG を導入しない。同一 SFEN に到達しても、異なる学習履歴・出典・branch label は別 node/edge として保持し、必要なら後続 move を重複記述する。

- `from_sfen/to_sfen` の一致は合法な合流候補として監査 report に出す。
- 自動 merge しない。merge すると path、解説、出典、戻り先が曖昧になる。
- `parent_move_id` は常に一つなので UI は tree のまま保つ。
- 後続重複が実運用上問題になった時だけ `position_id` と reusable continuation の DAG を別 RFC にする。Wikipedia seed 数十〜数百 node の段階では過剰な一般化である。

## 6. 「この定跡の変化」一覧 UI

初期版は専用 Tree View widget を使わず semantic HTML を優先する。

```html
<section aria-labelledby="opening-variations-title">
  <h2 id="opening-variations-title">この定跡の変化</h2>
  <details open>
    <summary>本線（19手・本文明示）</summary>
    <ol>...<li><button>7手目 ▲7五歩の局面へ</button>...</li></ol>
  </details>
</section>
```

- `details/summary` は branch 単位、手順は nested `ol/li`、移動は native `button`。
- 各 node に手数、notation/USI、本線/変化、branch label、coverage badge。出典詳細は既存「データ出典」section へのリンク/参照にし重複させない。
- 現在 node は `aria-current="step"`、visual highlight、screen reader text の三つで示す。
- node click は root からその node までの path を設定し局面へ移動。現在より前後どちらでも同じ決定規則。
- 初期展開は現在 path の祖先と root main。その他は折りたたむ。「すべて開く」は巨大 tree では付けず、branch 数/深さの閾値を計測して後続検討。
- 360px は indent を浅くし、深い階層では border/level label へ切替。水平 scroll に依存しない。
- lazy rendering は初期非目標。まず 500 node 程度の fixture で render 性能を計測し、問題時のみ subtree virtualization を検討。

## 7. Wikipedia coverage 監査

### 7.1 現行 Wikipedia 系 seed

手数は `SAMPLE_OPENING_LINES[*].moves` の実数。A/B/C は後述の分類で、A は個別 metadata が本文明示を主張する3 lineだけを暫定 A、既定 note が「局面図を参考に再構成」とするものは B とした。**A の確定は seed 追加/修正 PR で現行版本文と版 ID を再確認する。**

| 戦法・変化名 | 現在の seed | 現在の手数 | 分岐 | Wikipedia情報量/分類 | 延長可能性 | 新規追加候補 | 優先度 | 備考 |
|---|---:|---:|---|---|---|---|---|---|
| 棒銀 | あり | 11 | なし | B: 既定note、個別URL | 要本文確認 | 防御側応手 | 中 | source metadata は「局面図参考の短い手順」 |
| 原始棒銀 | あり | 9 | なし | B: 局面図参考 | 高そうだが要確認 | 典型的な受けの分岐 | 高 | 本文明示の連続列と混同しない |
| 中飛車 | あり | 8 | なし | B: 既定note | 要確認 | 基本進行 | 低 | Wikibooks/catalogとの出典境界も監査 |
| 四間飛車 | あり | 8 | なし | B | 要確認 | 対四間各戦法 | 中 | 総称 seed |
| 矢倉 | あり | 9 | なし | B | 要確認 | 個別矢倉系 | 中 | 現行手順の出典粒度が粗い |
| 角換わり | あり | 8 | なし | B: 短い手順 | 高 | 一手損、棒銀、早繰り銀、腰掛け銀 | 高 | 各派生 seed は別行あり |
| 相掛かり | あり | 8 | なし | B | 高 | 塚田スペシャル等 | 中 | 現 seed 後半はひねり飛車含み |
| 横歩取り | あり | 13 | なし | B: 基本局面まで | 高 | △3三角ほか | 高 | 13手目▲3四飛まで |
| 石田流 | あり | 8 | なし | B: 短い手順 | 高 | 本組・各派生 | 高 | 7手目▲7六飛、8手目△5二金 |
| ゴキゲン中飛車 | あり | 8 | なし | B: 短い手順 | 高 | 超急戦、超速、丸山ワクチン | 高 | 現行列自体の本文連続性を再監査 |
| 原始鬼殺し（明示手順） | あり | 19 | 2（3手目） | A暫定: section・図1-1〜1-4 | 本文範囲内で分岐精査 | △6二銀/金の続き | 高 | main 4手目も△6二銀で同一USI重複の疑いを監査 |
| 新・早石田（鈴木流急戦） | あり | 7 | なし | A暫定: 第7手まで | 高 | 第7手以降の本文記載分 | 最優先 | note が「本文・図示」と混在。A/Bを分ける |
| 升田式石田流 | あり | 7 | なし | A暫定と記載 | 高 | ▲7六飛以降 | 最優先（metadata修正） | **note は「および実戦以下▲7六飛を手順化」と書くが moves は7手目▲4八玉で終了。▲7六飛は未収録。note と実データが不整合** |
| 早石田 | あり | 7 | なし | B | 高 | 新・早石田との統合/区別 | 高 | 7手目▲7六飛、明示seedとは別 line |
| 角換わり棒銀 | あり | 9 | なし | B | 要確認 | 攻防の分岐 | 中 | local type metadata と Wikipedia line metadata の不一致も監査 |
| 角換わり早繰り銀 | あり | 11 | なし | B | 要確認 | 仕掛け | 中 | 同上 |
| 角換わり腰掛け銀 | あり | 13 | なし | B | 要確認 | 主要分岐 | 中 | 出典は「腰掛け銀」 |
| 右四間飛車 | あり | 8 | なし | B | 要確認 | 対四間/矢倉 | 低 | Wikibooksとの境界あり |
| 居飛車穴熊 | あり | 13 | なし | B | 要確認 | 対四間 | 低 | 戦法/囲いの分類を維持 |
| 鬼殺し（短手順） | あり | 9 | なし | B | 原始鬼殺しと整理 | 新・鬼殺し等 | 中 | Wikipedia明示lineとは別 |

この表以外の現行 line（角交換四間飛車、対振り飛車急戦、三間飛車、角交換振り飛車、相振り飛車、嬉野流、筋違い角、雁木、矢倉棒銀、美濃囲い、穴熊、舟囲い、左美濃、向かい飛車）も PR-D で全件 machine-readable CSV/fixture と突合する。既定の `source_note` が全 line を Wikipedia 再構成と読ませる一方、`OPENING_TYPE_SEEDS` には `local seed` / Wikibooks が混在するため、line provenance と catalog provenance を分離する。

### 7.2 coverage status の改善

自由文だけでなく列挙値を導入する（DB enum 制約は不要、schema validator で検査）。

- `complete_for_cited_sequence`: 引用sectionに連続明示された列を終端まで収録。
- `partial_explicit_sequence`: 本文明示列の途中まで。
- `diagram_reconstruction`: 図と周辺説明から再構成。
- `name_only`: 名称/catalogのみ、move seedなし。
- `mixed`: AとBが混在。node/segment単位 provenance が必要。

さらに `covered_through_ply`、`covered_through_move`、`omitted_after`（自由文）、Wikipedia `revision_id` / `oldid` を記録する案を PR-D で決める。source note に未収録手を「収録した」と書けない validator/test fixture を追加する。

## 8. Wikipedia 未収録一覧

以下は「将棋の戦法」・個別記事での名称候補として監査 queue に置く。現アプリの `OPENING_TYPE_SEEDS` / `SAMPLE_OPENING_LINES` に同名 line がないことはコード照合済み。**Wikipedia の現在の本文で名称・連続手順を再取得できていない項目は、すべて暫定 C（名称候補）であり、この表だけから move seed を作ってはならない。** 個別 PR で A/B/C を確定する。

| 系統 | 未収録の戦法・変化 | 現時点の扱い | seed化条件 / 優先度 |
|---|---|---|---|
| 矢倉 | 加藤流、▲4六銀・3七桂型、脇システム、森下システム、早囲い、雀刺し、四手角、三手角、土居矢倉、米長流急戦矢倉、阿久津流急戦矢倉、矢倉中飛車、カニカニ銀 | C暫定、seed未作成 | 個別sectionに連続手順があればA、図のみならB。中 |
| 角換わり | 後手一手損角換わり、その他個別記事の明示変化 | C暫定 | 基本角換わりとの手順差を本文で確認。高 |
| 相掛かり | 塚田スペシャル、新旧対抗型、飛車先交換早繰り銀、中原流相掛かり、中原飛車、飛車先交換腰掛け銀、鎖鎌銀、ひねり飛車 | C暫定 | 現 seed がひねり飛車「含み」であり収録済み扱いにしない。中 |
| 横歩取り | △3三角、空中戦法、中原流、中座飛車/△8五飛、△3三桂、△2三歩、△4五角、相横歩取り | C暫定 | 分岐点からの連続列を確認。高 |
| 対ゴキゲン | ▲5八金右超急戦、超速▲3七銀、丸山ワクチン | C暫定 | ゴキゲン main と別 branch/line の境界を決定。高 |
| 四間飛車 | 藤井システム、立石流、4六銀左、山田定跡、4五歩早仕掛け、鷺宮定跡、ミレニアム | C暫定 | 対四間側の先後・初期手順を明示。中 |
| 三間飛車 | 石田流本組、中田功XP、トマホーク、カナケン、久保システム、初手▲7八飛、2手目△3二飛 | C暫定 | 石田流既存lineとの重複を避ける。中 |
| 向かい飛車 | メリケン向かい飛車、ダイレクト向かい飛車、阪田流向かい飛車、筋違い角向かい飛車、升田流向かい飛車、大野流向かい飛車 | C暫定 | 名称確認だけならcatalog `name_only`。中 |
| 鬼殺し | 新・鬼殺し、鬼殺し向かい飛車、対振り飛車用鬼殺し、相振り飛車用鬼殺し | C暫定 | 原始鬼殺しと混同せず個別 provenance。中 |

PR-D の外部監査では Wikipedia の曖昧さ回避ページ、redirect、section 見出し、記事 revision を記録し、(1) 名称が現行記事にある、(2) 個別記事がある、(3) 初期局面から連続手順がある、を別 boolean にする。名称だけなら `opening_types` catalog への「準備中」追加は可能だが `opening_lines` / moves は作らない。

## 9. 既存 seed の延長候補

「Wikipediaでどこまで」は本文を取得して確定するまで推測しない。下表は現行終端と、安全に延長するための調査境界である。

| 優先対象 | 現在どこまで | 現行分類 | Wikipediaで確認する終端/分岐 | 現時点の安全な追加手数 | 判定 |
|---|---|---|---|---:|---|
| 新・早石田 | 7手目▲7四歩 | A/B混在暫定 | 「新・早石田」sectionで第8手以降が連続記法か、図からの補間かを分離 | 0（再確認前） | 最優先監査。本文連続分だけAとして延長 |
| 早石田 | 7手目▲7六飛 | B | 個別の「早石田」記述と新・早石田との差 | 0 | generic lineを無理に長手順へ統合しない |
| 石田流 | 8手目△5二金 | B | 石田流本組までの本文連続列 | 0 | 図再構成ならBの独立line |
| 升田式石田流 | 7手目▲4八玉 | A暫定 | note の「実戦以下▲7六飛」が本文連続か、何手目か | 0 | まずnoteを実データに合わせる。追加後のみ収録表現可 |
| 横歩取り | 13手目▲3四飛 | B | 基本局面から△3三角、△8五飛等の各sectionの最初の明示列 | 0 | branchごとに独立レビュー |
| 角換わり | 8手目△2二銀 | B | 基本局面、一手損、棒銀/早繰り銀/腰掛け銀の連続列 | 0 | 既存派生3lineとの重複整理が先 |
| 原始棒銀 | 9手目▲2六銀 | B | 棒銀記事で攻防が連続手順として明示される範囲 | 0 | 一般知識で相手応手を補完しない |
| ゴキゲン中飛車 | 8手目△8四歩 | B | 初期手順の本文整合、▲5八金右超急戦/超速/丸山ワクチンの分岐点 | 0 | 現行列の先後と手順を先に再監査 |
| 原始鬼殺し | main 19手目▲7三歩成、branchは1手/3手 | A暫定 | mainと△6二銀が同じ4手目になる重複、△6二金枝の本文範囲 | 0 | sibling同一USIを解消してから延長 |

この「0」は延長不能という意味ではなく、**現行版本文を確認せずに安全と断定できる手数が0**という gate である。PR-E 以降は監査記録に実際の「本文明示終端」「追加手数」「分岐 ply」「revision ID」を埋めてから実装へ進む。

## 10. インポート規則

### 10.1 provenance 分類

| code | 分類 | 許される内容 | seed化 |
|---|---|---|---|
| A `explicit_sequence` | Wikipedia本文明示手順 | 記事本文で順番を追って連続して確認できる着手のみ | 可。全手検証必須 |
| B `diagram_reconstruction` | Wikipedia局面図再構成 | 図のSFEN相当と周辺説明から再現。本文にない中間手は「本文手順」と称さない | 独立line/segmentとしてレビュー後可 |
| C `name_only` | Wikipedia戦法名のみ | catalog 名称、説明、出典 | move seed不可。「準備中」可 |
| M `mixed` | A/B混在 | segment/nodeごとにA/Bと根拠を持つ | 一括の「本文明示」表示は禁止 |

### 10.2 必須ルール

1. Wikipedia に記載されていない中間手を推測して追加しない。
2. 一般的な定跡知識、棋譜DB、将棋engineの候補だけを根拠に補完しない。
3. 本文で連続して確認できる A を最優先する。
4. 図から再構成した B は A と別 line/segment/metadata にする。
5. C は `opening_types` catalog の「準備中」にできるが move を持たせない。
6. 各手を tsshogi（frontend）と backend の `python-shogi` validator の双方で合法性確認し、初期SFEN、手番、成/不成、駒打ち、前後SFENを固定 fixture で照合する。
7. `source_url`, `source_title`, `source_section`, `source_license`, `source_retrieved_at`, `source_note`, `coverage_status`, provenance code を必須にする。可能なら `revision_id` / `oldid` も保存する。
8. 日本語 Wikipedia の CC BY-SA 表記と source link を UI / API / notices で維持する。短い手順の事実性と、文章・図の翻案に必要な帰属を別問題として扱い、本文を大量コピーしない。
9. `source_note` は「実際にmovesへ入れた終端」を具体的に書く。未収録の後続は「本文には続きがあるが未収録」と書き分ける。
10. `coverage_status` と moves を test で対応付ける。`covered_through_ply > len(moves)`、終端USI不一致、Aなのにsection/revisionがない状態を失敗させる。
11. branch は各 edge/segment の出典を持つ。mainの出典を根拠なくbranchへ継承しない。
12. 取得時に記事 title、section、retrieved date、revision ID、確認者、合法性検査結果を review artifact に残す。

### 10.3 升田式石田流の即時監査事項

現 seed は7手目 `5i4h`（▲4八玉）で終わるが、`source_note` は「および実戦以下▲7六飛を手順化」と読める。実際の `moves` に `7h7f` はない。PR-D は最低限 note を「▲4八玉まで収録。本文に記載された実戦以下▲7六飛は未収録」のように事実へ合わせる。もし本文の連続性・合法性を再確認して手を追加するなら、その seed 追加は PR-D ではなく石田流系 PR-E に分離する。

## 11. PR 分割

依存関係は一本の直列ではなく、次の二系統を並行して進められる。

```text
UX / 構造系:       A0 → A → B → C
provenance 系:     D0 → D1
Wikipedia seed 系: D1 ─┬→ E（単純な一次分岐・線形 seed）
                       └→ B → E（多段分岐を必要とする seed）
```

`A0 → A` は board の `findIndex` が一意な sibling を返すための必須依存である。B は A の UX helper を前提に進めると衝突が少なく、C は B の direct-parent tree 契約に依存する。一方、D0/D1 は UX 系と並行可能である。各 PR-E は D1 の provenance 監査完了を必須とし、branch-of-branch を含むものだけ B にも依存する。したがって旧表記の `D0 → A → B → C → D1 → E` を絶対的な直列順とは扱わない。

### PR-A0: 既存分岐構造正規化

- **目的**: 現行 seed / DB / API が返す各分岐点を監査し、同一局面・同一 USI の sibling を原則1 nodeへ正規化して PR-A の一意な着手照合を成立させる。
- **確認対象**: 特に原始鬼殺しの3手目▲7七桂後について、main 4手目と「△6二銀の対応」がともに `7a6b` となる重複疑いを、seed生成後の `from_sfen` / USI / parentで確認する。
- **正規化規則**: 同じ `from_sfen` と USI の着手は一 nodeに統合する。説明・branch label・後続が異なる場合、共通着手nodeの `next` で分岐させる。provenanceが異なる場合も着手を複製せず、node/edge metadataの保持方法を明記する。
- **変更対象**: `backend/app/seed.py`, `backend/tests/test_openings_import_api.py`、必要に応じて監査script/fixture。アプリの分岐UIは変更しない。
- **DB migration**: 原則なし。既存DBの再seedだけで安全に直せない場合は、データmigration要否をPR本文で明示して小さく分離する。
- **API/frontend**: response shapeの変更なし / 変更なし。
- **seed**: 構造正規化のみ。Wikipediaの新しい手や本文解釈を追加しない。
- **tests**: 全lineの各 `from_sfen` について sibling USI一意、原始鬼殺しの△6二銀が一 node、正規化後もmain/△6二金の合法な再生と出典が維持されることをpytestで検査。
- **後方互換**: line ID、opening type、既存URL、到達可能な合法手順を維持する。
- **provenance**: 既存metadataを失わないことだけ確認し、本文の再解釈はD1へ送る。

### PR-D0: provenance/coverage 契約文書と監査器の設計固定

- **目的**: A/B/C/M、coverage列挙値、必須metadata、監査表の機械可読形式を固定。
- **変更対象**: `docs/`、必要なら後続用 validator test fixture（実装する場合は `backend/app/seed.py` を触らず独立script）。
- **DB migration**: なし（新列採用判断だけをADR化）。
- **API/frontend/seed**: なし。
- **tests**: 文書 link/check。Wikipedia revision の取得手順をdry-run。
- **provenance**: 必須。現在記事を取得できる環境でURL/section/revisionを記録。

### PR-A: 分岐学習 UX 改善

- **目的**: board と card の正解集合を統一し、再生操作を明確化。
- **変更対象**: `frontend/src/pages/OpeningStudyPage.tsx`, `frontend/src/shogi/openings.ts`, tests, `frontend/src/index.css`, `frontend/e2e/shogi-learning.spec.ts`。
- **DB migration/API/seed**: なし / なし / なし。
- **frontend**: choice matching helper、分岐点cards、現在branch、ラベル、直前分岐へ戻る、現在pathを保つgo-to-end。
- **tests**: 3候補の任意USI、誤手、undo、過去切替、main replay、mobile/a11y。
- **後方互換**: linear/static/sample opening、既存URL、既存APIを維持。
- **provenance**: 表示の退行確認のみ。Wikipedia本文変更なし。

### PR-B: 多段分岐データモデル

- **目的**: parent-childを正規化し、A/A1/A2・B/B1/B2を安定再構築。
- **変更対象**: `backend/app/database.py`, `backend/app/seed.py`, `backend/app/routers/openings.py`, `backend/app/schemas.py`（該当時）, `frontend/src/api/client.ts`, `frontend/src/shogi/openings.ts`, backend/frontend tests。
- **DB migration**: **要否をspikeで決定**。stable `move_key` / `is_main` 追加なら要。既存 `parent_move_id` を直接親にbackfillする migration はいずれにせよ必要になり得る。あわせて、現行 UNIQUE `(line_id, ply, variation_group, sort_order)` が direct `parent_move_id` + sibling `sort_order` モデルでも正しい重複防止になるかを検証する。親が異なる同ply・同groupの合法nodeを誤って拒否する、または同一親の重複orderを許す場合は、`UNIQUE(line_id, parent_move_id, sort_order)` 相当（rootのNULL semanticsを含む）やstable key制約へのmigrationを設計する。
- **API**: move `id` と direct `parent_move_id` の契約、stable orderingをadditiveに明記。
- **frontend**: parent ID builder、legacy SFEN fallback、cycle/orphan error。
- **seed**: `move_nodes`/`parent_key` 新形式とlegacy adapter。Wikipedia move追加なし。
- **tests**: migration、idempotent seed、multi-level branches、invalid parent/cycle/SFEN/legal move、legacy互換、transposition非merge。
- **provenance**: metadataが各node/segmentで欠落しないことだけ確認。

### PR-C: 「この定跡の変化」一覧 UI

- **目的**: 全体 tree の俯瞰と任意局面ジャンプ。
- **変更対象**: `OpeningStudyPage.tsx` または新 `OpeningVariationList.tsx`、CSS、Vitest/Playwright。
- **DB migration/API/seed**: なし（PR-B APIを利用）。
- **frontend**: details/summary、nested list、current highlight、jump、fold、coverage/source link、responsive/a11y。
- **tests**: path変換、current node、deep tree、500-node fixtureのrender時間・DOM数の測定と記録、keyboard、360px。現段階では根拠のない厳格な性能閾値を置かず、測定結果から最適化要否と将来の基準を判断する。accessibilityの自動検査は、実装時に採用可能な手段（例: Playwright + axe-core、既存test stackのmatcher）を確認して具体化する。
- **後方互換**: linear lineでは単一の簡潔なlist。JSなしのnative disclosure semanticsを優先。
- **provenance**: label/coverageが正しいbranchに表示されること。

### PR-D1: Wikipedia coverage監査・metadata整合

- **目的**: 全seedのA/B/C/M確定、source note/coverage修正。升田式石田流の不整合を解消。
- **変更対象**: `backend/app/seed.py` のmetadataのみ、tests、監査文書/CSV、必要ならAPI/clientのmetadata field。
- **DB migration**: provenance/revisionを列追加する決定なら要。JSON/既存列に収めるなら不要だが型安全性を比較。
- **API/frontend**: 新metadataを表示する場合additive。
- **seed**: **手順追加なし**。metadataのみ。
- **tests**: 全Wikipedia lineの必須field、URL、license、coverage enum、note終端、revision、再seed idempotency。
- **provenance**: reviewerが記事revisionと監査artifactを照合。

### PR-E以降: Wikipedia seed 追加

1. **PR-E1 石田流・早石田系**: 新・早石田、早石田、石田流、升田式。metadata defect解消後、A/B別line/branch。
2. **PR-E2 横歩取り系**: 基本局面から各応手を小さなbranch群に分割。大きければ△3三角/△8五飛とその他を分ける。
3. **PR-E3 角換わり系**: 基本、一手損、既存棒銀/早繰り銀/腰掛け銀の重複整理。
4. **PR-E4 棒銀系**: 原始棒銀を優先。本文連続の攻防のみ。
5. **PR-E5 ゴキゲン・対ゴキゲン**: mainの再監査後、超急戦、超速、丸山ワクチンを別branch/line。
6. **PR-E6 鬼殺し系**: 原始鬼殺しの同一USI branchを正規化後、新・鬼殺し等をA/B/C判定。
7. **PR-E7以降**: 矢倉、相掛かり、四間、三間、向かい飛車をarticle/section単位の小PR。

各seed PRは一つの出典sectionまたは密接なbranch群を原則とし、巨大な「Wikipedia全追加」PRを禁止する。

## 12. テスト戦略と各 PR の受け入れ条件

### 12.1 共通 test matrix

| 検査 | A0 | A | B | C | D0/D1 | E群 |
|---|---:|---:|---:|---:|---:|---:|
| backend unit/pytest | 必須 | 関連なし | 必須 | 関連時 | 必須 | 必須 |
| frontend Vitest | 関連なし | 必須 | 必須 | 必須 | metadata UI時 | 必須 |
| frontend lint | 関連なし | 必須 | 必須 | 必須 | frontend変更時 | 必須 |
| frontend build | 関連なし | 必須 | 必須 | 必須 | frontend変更時 | 必須 |
| Playwright Chromium | seed smoke | 必須 | 必須 | 必須 | 表示変更時 | 必須 |
| 360px mobile | 関連なし | 必須 | smoke | 必須 | 表示変更時 | branch追加時 |
| git diff check | 必須 | 必須 | 必須 | 必須 | 必須 | 必須 |
| Wikipedia provenance review | 継承確認 | 表示退行のみ | 継承確認 | 表示確認 | 必須 | 必須 |

推奨command（実際の `package.json`/README のscript名を各PR時に再確認）:

```bash
cd backend && pytest
cd frontend && npm test -- --run
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npx playwright test --project=chromium
# 360px viewport projectまたはpage.setViewportSize({ width: 360, height: 800 })
git diff --check
```

### 12.2 PR別 acceptance checklist

#### PR-A0

- [ ] 全既存lineを監査し、同一 `from_sfen` の sibling USI重複が0件である。
- [ ] 原始鬼殺しの3手目後の `7a6b` は一 nodeだけで、異なる進行はその着手後に表現される。
- [ ] 正規化で既存の合法手順、line ID、出典metadataが失われない。
- [ ] 再seedを2回実行しても重複が再発せず、backend pytestとseed smoke E2Eを通過する。

#### PR-A

- [ ] 3候補の0/1/2番目をboardで指すと各 path index が選ばれ、正解feedbackになる。
- [ ] 候補外合法手は不正解でposition/pathを変えない。
- [ ] card操作とboard操作が同じnode、source、historyを表示する。
- [ ] 「本線を一手進む」「ここから本線を最後まで再生」の挙動が文言通り。
- [ ] undo、直前分岐、過去分岐switch、reset後のfocus/live通知が一貫。
- [ ] PR-A0の正規化済みfixtureを前提に、duplicate sibling USIを再発検知するtestがある。
- [ ] Vitest、lint、build、Chromium E2E、360pxを通過。

#### PR-B

- [ ] 本線→A→A1/A2、B→B1/B2 fixtureがDB→API→frontendで同じtreeになる。
- [ ] 全非root rowの`parent_move_id`が直接親で、親to_sfenと子from_sfenが一致。
- [ ] 現行UNIQUE `(line_id, ply, variation_group, sort_order)` をdirect-parent fixtureで評価し、維持または変更の根拠、NULL rootの扱い、migration/backfill手順を記録する。
- [ ] orphan、cycle、duplicate key/USI/order、illegal moveを明確なerrorで拒否。
- [ ] 同一SFENの異なるpathを自動mergeしないfixtureがある。
- [ ] legacy seed/DBをmigration後も既存line ID/URLから再生可能。
- [ ] seedの2回実行でrow重複・ID drift・parent driftがない。
- [ ] pytest、migration tests、Vitest、lint、build、Chromiumを通過。

#### PR-C

- [ ] semantic nested list/disclosureで全nodeへ到達可能。
- [ ] 現在位置と祖先が視覚・`aria-current`双方で分かる。
- [ ] node jump後にboard/history/current branchが一致。
- [ ] collapseしてもfocus消失や同名button ambiguityがない。
- [ ] 360pxでhorizontal overflowなし、touch targetと長文折返しを確認。
- [ ] 500 node fixtureのrender時間/DOM数を測定してPR本文に記録する。初回は厳格な合否閾値を設けず、結果から最適化課題または将来の基準設定要否を判断する。
- [ ] accessibility自動検査の利用手段を実装時に具体化し、その検査、Vitest、lint、build、Chromium E2Eを通過する。

#### PR-D0/D1

- [ ] 全Wikipedia由来lineがA/B/C/M、coverage enum、section、retrieved date、licenseを持つ。
- [ ] catalog provenance と move-line provenance を混同しない。
- [ ] source noteの終端表現が`len(moves)`/終端USIと一致。
- [ ] 升田式石田流は▲7六飛を未収録と明記するか、別seed PRで実際に追加されるまで収録済みと書かない。
- [ ] current Wikipedia revision/oldidを監査artifactに記録し、リンク切れ/redirectを確認。
- [ ] metadata-only再seedとAPI responseのpytestを通過。
- [ ] frontend変更があればVitest/lint/build/Chromium/360pxを通過。

#### 各 PR-E

- [ ] Aの各着手が指定revisionの同一sectionで連続確認できる。Bは図番号・再構成手順を別記。Cからmoveを作らない。
- [ ] source URL/title/section/license/retrieved/revision/note/coverage/provenanceが揃う。
- [ ] 全手をbackendとfrontend両validatorで検証し、全edgeのSFEN snapshotをassert。
- [ ] branch label、main、sort order、direct parentがreview可能なfixtureに一致。
- [ ] 既存lineを削除/改名せず、必要ならalias/redirectを用意。
- [ ] pytest、Vitest、lint、build、Chromium branch E2E、360pxを通過。
- [ ] Wikipedia本文の大量copyを含まず、CC BY-SA attributionを表示。

## 13. リスク

| リスク | 影響 | 対策 |
|---|---|---|
| SFENだけで親子推定 | 異なる履歴の意図しない合流 | direct `parent_move_id` を正規化、SFENはassertion |
| transpositionをDAG化 | 戻り先・解説・出典が曖昧 | 初期はnode重複を許すtree |
| seedがDB ID依存 | 再seedで壊れる | stable logical key→ID解決 |
| `variation_group`の多義性 | branch-of-branch表示崩れ | 構造・表示・順序を別責務にする |
| sort変更で`path:number[]`が別nodeを指す | URL/stateの不安定 | pathはsession内、永続jumpはstable node keyを利用 |
| Wikipedia本文/図/一般知識の混同 | 根拠のないseed | A/B/C/M gateとrevision review |
| 記事改訂/section rename | 再現不能 | oldid/revision、取得日、section記録 |
| source noteとmoves乖離 | coverage誤表示 | 終端ply/USI validator。升田式を先行修正 |
| 同一USI sibling | boardでbranchを識別不能 | sibling USI一意制約/validator |
| 巨大tree | mobile可読性/性能低下 | branch disclosure、祖先のみ展開、性能fixture |
| migrationで既存line破損 | 学習URL/進捗退行 | additive schema、backfill、idempotency/legacy E2E |
| 「最後まで」の期待差 | 選択変化が失われる | 現path維持、未選択部分のみ本線、ラベル明示 |
| license表示欠落 | attribution不備 | API→node→UIのcontract testsとnotices監査 |

## 14. 完了条件

この取り組み全体は次を満たした時に完了とする。

1. PR-A0の監査で既存の同一局面・同一USI siblingが解消され、共通着手後に分岐する正規形になっている。その上で、boardで同一分岐点の全登録候補が正解になり、選んだbranch index/path/history/sourceが一致する。
2. 自動再生、undo、分岐点復帰、switchの仕様とラベルが一致し、keyboard/ARIA/360pxで利用できる。
3. direct parentによる任意深さtreeがDB→API→frontendで保持され、SFENは合法性・整合性の検査に使われる。
4. transpositionを意図せずmergeせず、異なる学習pathを保持する。
5. 「この定跡の変化」から全体構造、main/variation、手数、現在位置、coverageを把握し任意nodeへ移動できる。
6. 既存全seedにA/B/C/Mと正規化coverageが付き、source metadataと実moves終端が一致する。
7. 升田式石田流のnote/実moves不整合が解消する。
8. 未収録一覧の各項目は「名称確認」と「連続手順確認」が分離され、Cからmove seedが生成されない。
9. 優先8対象は現行Wikipedia revisionに対する監査記録を持ち、追加手数・branch・A/B境界がreview済みである。
10. 各PRのpytest/Vitest/lint/build/Chromium/360px/後方互換/provenance gateが満たされる。
11. 既存のstatic opening、learning sample、imported linear line、一次分岐、既存URLが退行しない。
12. 本書の**[要外部再確認]**項目は、ネットワーク利用可能なseed PRで一次資料（現行Wikipedia記事とrevision）に置き換え、推測を実装へ持ち込まない。

---

### 調査根拠（リポジトリ内）

- UI/状態: `frontend/src/pages/OpeningStudyPage.tsx`
- tree/helper: `frontend/src/shogi/openings.ts`
- API型: `frontend/src/api/client.ts`
- frontend unit: `frontend/src/shogi/openings.test.ts`
- E2E: `frontend/e2e/shogi-learning.spec.ts`
- schema/migration: `backend/app/database.py`
- API: `backend/app/routers/openings.py`
- seed/metadata/合法手生成: `backend/app/seed.py`
- backend tests: `backend/tests/test_openings_import_api.py`, `backend/tests/test_database_migrations.py`
- provenance方針: `README.md`, `THIRD_PARTY_NOTICES.md`
- 履歴: PR #19/#20相当の playable seed、PR #22相当の metadata/branch replay、PR #23相当の長手順/branch/migration、PR #40相当の opening type中心UI。
