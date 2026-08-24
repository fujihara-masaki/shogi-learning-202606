# 定跡分岐学習 UX・多段分岐・Wikipedia seed 拡張 実装計画

- 対象: `fujihara-masaki/shogi-learning-202606`
- 調査基準: PR #52（PR-A0）/ #53（PR-A）merge 後の現作業ツリー（2026-08-13）
- 対象履歴: PR #19、#20、#22、#23、#40、#52、#53（ローカルの merge commit と構成 commit を確認）
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
| 本線 | frontend の再生 helper では sibling 配列の `choices[0]`。表示上は `variation_group == "main"` も本線ラベルに使う | **[部分実装]**。PR-Aで操作ラベルは明確になったが、「本線である」という意味と表示順が未分離。PR-Bで独立した契約にする |
| 分岐 | 同じ `from_sfen` を持つ複数 move。seed の `branches` は本線の `from_ply` から派生 | **[部分実装]** 一次分岐は扱える |
| 分岐点 | `currentChoices.length > 1`、または通過 step の `choices.length > 1` | **[実装済み]** |
| `variation_group` | `main` または人間向け変化名。branch 行を束ね、表示ラベルにも転用 | **[部分実装]** 構造上の親と表示名が混在 |
| `parent_move_id` | branch の最初の行等に本線の分岐元 move ID を保存 | DB/API **[実装済み]**、frontend **[未使用]**。現 seed では branch 内の全行が同じ本線親を持ち得るため「直接親」としては未確立 |
| `from_sfen` / `to_sfen` | 各手の前後局面。API から frontend へ渡りツリー接続に使用 | **[実装済み]**。局面の同一性と手順上の親子を同一視している |
| `sort_order` | DB/APIの安定表示順。現frontendでは結果的に先頭を本線として再生 | **[部分実装]**。PR-Bで「同一parent配下の表示順」だけに限定し、本線指定と切り離す |
| `path: number[]` | root から各 sibling 配列で選んだ index の列 | **[実装済み]**。DB ID に依存せず軽量だが、tree 再構築で順序が変わると不安定 |
| `currentChoices` | root なら `opening.moves`、進行後なら末尾 node の `next` | **[実装済み]** |
| `expectedOpeningMove` | path をたどった先の `choices[0]` | **[実装済み]**。PR-A後は本線のhint/自動再生用であり、盤上の正解判定には使わない |
| `chooseBranch(index)` | 現在の `path` へ任意 index を追加 | **[実装済み]** |
| `switchBranch(stepIndex, branchIndex)` | 過去 path を分岐点直前で切り、別 index を追加 | **[実装済み]** |
| `stepForward()` | `expected` を表示し常に `0` を追加 | **[実装済み]**、本線固定 |
| `continueOpeningMainLine()` / `goToEnd()` | 選択済みpathを保持し、以後の各階層で先頭候補を終端まで追加 | **[実装済み]**（PR #53）。表示順と本線意味の分離後は、先頭でなく明示的mainを選ぶ |

### 1.3 PR #52 / #53 後の分岐 UI と検証済み事項

**PR #52（PR-A0）で実装済み**

- seed後の全lineを対象に、同一 `line_id` / `from_sfen` / USI の重複 sibling を検出する validator を追加し、seed処理自体も重複時に失敗する。
- 原始鬼殺しを含む現seedを検査した結果、疑われていた同一USI siblingは存在しないことをbackend testで固定した。したがって「△6二銀を共通nodeへ正規化する作業」を未実装課題として残さない。
- DB制約への固定は避け、将来のdirect-parent treeでも検査単位を更新できるPython validatorとしている。

**PR #53（PR-A）で実装済み**

- 盤上着手は `findOpeningChoiceIndex(currentChoices, move)` で全登録候補を照合し、0以外の候補も正解として選択pathへ記録する。boardと分岐cardの正解集合の不一致は解消済み。
- 分岐点card（本線/変化、表記、USI、説明、coverage/source）、現在の分岐path、通過した分岐、過去分岐切替を表示する。
- 「本線を一手進む」「ここから本線を最後まで再生」「直前の分岐点へ戻る」を実装し、最後まで再生は現在pathを保持する。
- 選択中の過去分岐buttonは `aria-current="step"` とdisabled/選択中表示を持ち、feedbackはlive regionで通知する。
- Vitestで3候補照合・path helperを、Playwrightでboard/cardの3分岐、戻る、過去切替、現在path保持再生、360pxを検査する。

**なお未実装**

- direct `parent_move_id` による任意深さtree契約（PR-B）。
- 本線の意味と表示順の独立指定（PR-B）。
- 通常は折りたたまれた補助的な全分岐一覧と任意node jump（PR-C）。

## 2. PR-A後に残る問題

1. **本線意味と表示順の結合**: PR-Aの `expectedOpeningMove` / 自動再生 / cardは先頭indexを本線とみなす。編集上の表示順を変えるだけで学習上の本線が変わり得る。
2. **構造契約不足**: `variation_group`、`parent_move_id`、SFEN、`sort_order` の責務が重なり、branch-of-branchのseed表現がない。
3. **transpositionの曖昧さ**: 同じSFENへの合流は現builderで後続を共有し得て、異なる由来・ラベルの意味を保存できない。
4. **補助的な全体像不足**: 現在局面のcardと通過分岐は主操作として十分だが、別の分岐点を探し、現在path/祖先を確認し、任意nodeへjumpする折りたたみ一覧がない。
5. **「この分岐点の本線へ」の不足**: 過去の任意分岐には切り替えられるものの、一覧上の分岐点を基準に後続を破棄し、その分岐点の明示的mainへ戻す専用操作が未定義。
6. **provenance / coverage粒度不足**: 自由文と実move数の整合を機械検査できず、segmentごとの根拠も未確立。
7. **大規模treeの境界**: 500 node程度の測定、折りたたみ、DOM量の方針が必要。ただし横レーン型visual treeやvirtualizationはfollow-upとする。

## 3. 目標 UX

### 3.1 正解判定を currentChoices 全体へ統一（PR #53で実装済み）

**[実装済み]** `expected` を「本線表示用」として残しても、判定は次のように全候補から行う。

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
- 同一分岐点に同一USIのsiblingが複数あるとboard操作だけでは区別不能である。**PR #52では既存seedに重複がないことを確認し、seed validator / backend testで再発を禁止済み**。将来、説明や後続だけが違う同じ手をimportする場合は一nodeに統合し、分岐はその着手後に表現する。
- `currentChoices.length === 0` の時だけ completed とする。
- unit test は `findIndex` 相当を純粋 helper（例: `findOpeningChoiceIndex`）へ抽出して board component を介さず検査する。

### 3.2 分岐点カード（PR #53で実装済み）

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

- PR-Aの現実装は先頭cardを「本線」とする。PR-B後は表示位置にかかわらずexplicit mainのcardだけに「本線」、その他に「変化」を表示する。色だけで区別せずtext / icon / borderを併用する。
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
| `sort_order` | **表示順**: 同一 `parent_move_id` 配下の sibling 表示順。semantic main を表す `is_main` とは別概念 |
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

`move_nodes` の `is_main` は sibling 集合ごとの semantic main を表し、
`sort_order=0` であることから推論してはならない。sole-child chain では、唯一の
child の `is_main` を省略でき、その場合は `true` と推論する。sibling が複数ある
場合は semantic main となる node に `is_main=true` を明示しなければならない
（それ以外の node は `false` を明示するか、省略できる）。複数 sibling の全 node
で `is_main` が省略された曖昧な入力は拒否する。明示された値は表示順にかかわらず
そのまま使用するため、`sort_order=0` 以外の node を main に指定できる。

validator は key 一意、親の存在、同一 line、acyclic、root、ply、sibling sort order、sibling ごとに exactly one `is_main=true`、sibling USI 一意、全手合法、親 `to_sfen == 子 from_sfen`、生成 SFEN と格納 SFEN の一致を検査する。upsert は key を自然キーとして ID を解決する。既存 DB に stable key がない場合、PR-B migration が必要になる可能性が高い。

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

## 6. PR-C: 補助的な「この定跡の変化」一覧 UI

メジャーな棋譜再生ソフトに共通する、棋譜リストを主表示に保ちつつ分岐選択・分岐点復帰を行うUXを参考にする。PR-Aの盤面、再生control、現在局面の分岐cardを主操作として残し、一覧はそれを置き換えない**補助navigation**とする。ShogiHome等に見られる横レーン型visual branch treeそのものは本PRに含めず、別follow-up計画へ分離する。

- section全体を`details/summary`等で**通常は折りたたむ**。初回表示で巨大treeを展開せず、summaryには分岐数、現在手数、現在branch程度を簡潔に示す。
- 開いた内部はsemanticなnested `ol/li` とnative `button`を基本とし、branch単位も必要に応じて折りたためる。盤面横の棋譜リストを模した逐手表示は可能だが、横レーン描画はしない。
- **current path**をrootから現在nodeまでの一本道として明示する。現在nodeは`aria-current="step"`と強いhighlight、ancestorは別の弱いhighlightおよびscreen reader textで区別し、currentとancestorを同じ見た目にしない。
- node buttonは手数、notation/USI、branch labelを一意なaccessible nameに含め、押すとrootからそのnodeまでのpathを設定する（**node jump**）。前方・後方・別branchのいずれへのjumpも同じ規則でboard、history、sourceを同期する。
- 各分岐点には **「この分岐点の本線へ切り替える」** を設ける。対象分岐点より後のpathを破棄し、そのparent配下でPR-Bが明示したmain nodeを選ぶ。すでにそのmain上なら選択中状態を示し、別branchから切り替えた場合は破棄と移動をlive通知する。
- `sort_order`は一覧の見せる順序にのみ使い、main badge、main切替、自動再生の決定にはPR-Bの明示的main契約を使う。
- coverage/sourceは簡潔なbadge/linkに留め、詳細は既存「データ出典」sectionへ委ねる。
- 360pxではindentを浅くし、深い階層はborder/level labelへ切替え、水平scrollに依存しない。focusを含むsubtreeを閉じる場合はsummaryへ戻す。
- 500 node fixtureで初期折りたたみ時と展開時のrender時間・DOM数を測定する。閾値設定、virtualization、overview/minimap、横レーン型treeは測定結果をfollow-upへ渡し、PR-Cの完了条件にはしない。

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

この表以外の現行 line（角交換四間飛車、対振り飛車急戦、三間飛車、角交換振り飛車、相振り飛車、嬉野流、筋違い角、雁木、矢倉棒銀、美濃囲い、穴熊、舟囲い、左美濃、向かい飛車）も、D1cで新canonical artifactへ移す対象をmachine-readableな一覧/fixtureとして突合する。これは過去のWikipediaとの完全一致を遡及証明する作業ではなく、レビュー済みartifactと移行後seed/import結果の差分を管理するためのものとする。既定の `source_note` が全 line を Wikipedia 再構成と読ませる一方、`OPENING_TYPE_SEEDS` には `local seed` / Wikibooks が混在するため、line provenance と catalog provenance を分離する。

### 7.2 coverage status の改善

自由文だけでなく列挙値を導入する（DB enum 制約は不要、schema validator で検査）。

- `complete_for_cited_sequence`: 引用sectionに連続明示された列を終端まで収録。
- `partial_explicit_sequence`: 本文明示列の途中まで。
- `diagram_reconstruction`: 図と周辺説明から再構成。
- `name_only`: 名称/catalogのみ、move seedなし。
- `mixed`: AとBが混在。node/segment単位 provenance が必要。

さらに `covered_through_ply`、`covered_through_move`、`omitted_after`（構造化fieldを正とし、必要なら表示文も併記）、Wikipedia `revision_id` / `oldid` を記録する案を PR-D0 で決める。coverage と実movesの整合はこれらの構造化fieldから検査する。`source_note` / `evidence_note` に含まれる「収録」「未収録」などの自然言語をPythonで解釈して正否を推測することは、正規validatorの責務にしない。表示用`source_note`は、可能な範囲で検証済みの構造化metadataから決定論的に生成する。

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

PR-E以降の外部調査・structured extractionでは Wikipedia の曖昧さ回避ページ、redirect、section 見出し、記事 revision を記録し、(1) 名称が現行記事にある、(2) 個別記事がある、(3) 初期局面から連続手順がある、を別 boolean にする。名称だけなら `opening_types` catalog への「準備中」追加は可能だが `opening_lines` / moves は作らない。

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
| 原始鬼殺し | main 19手目▲7三歩成、branchは1手/3手 | A暫定 | Wikipedia本文上のmainと各branch（△6二銀/△6二金）のcoverage範囲 | 0 | PR #52でsibling USI一意性は確認済み。本文上の各経路の範囲を確認してから延長 |

この「0」は延長不能という意味ではなく、**現行版本文を確認せずに安全と断定できる手数が0**という gate である。PR-E 以降はLLMによるstructured extractionで、監査artifactに実際の「本文明示終端」「追加手数」「分岐 ply」「revision ID」を埋め、PR-D1b/D1cのvalidatorを通してからseed/importへ進む。

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
9. coverageの正規情報は構造化metadataに持たせ、表示用`source_note`は可能な範囲でそこから生成する。手書きする場合も、実際にmovesへ入れた終端と未収録の後続を書き分ける。ただしvalidatorはその日本語を自然言語解析せず、構造化fieldを検査する。
10. `coverage_status` と moves を test で対応付ける。`covered_through_ply > len(moves)`、終端USI不一致、Aなのにsection/revisionがない状態を失敗させる。
11. branch は各 edge/segment の出典を持つ。mainの出典を根拠なくbranchへ継承しない。
12. 取得時に記事 title、section、retrieved date、revision ID、確認者、合法性検査結果を review artifact に残す。

### 10.3 升田式石田流の即時監査事項

現 seed は7手目 `5i4h`（▲4八玉）で終わるが、`source_note` は「および実戦以下▲7六飛を手順化」と読める。実際の `moves` に `7h7f` はない。PR-D1aは既知のこのmetadata不整合だけを対象とし、noteを「▲4八玉まで収録。本文に記載された実戦以下▲7六飛は未収録」のように事実へ合わせ、**movesは変更しない**。本文の連続性・合法性を再確認して手を追加する場合は、PR-D1aではなく石田流系PR-Eに分離する。

## 11. PR 分割と実装順序

基本のPR分割は維持する。PR #52/#53でA0/Aは完了したため、残るUX/構造系のcritical pathは **B → C** である。

```text
完了:               A0 (#52) → A (#53)
UX / 構造系:                    B → C
provenance 系:       D0 → D1a → D1b → D1c → D1d（D1dは再評価後）
Wikipedia seed 系:                   LLM extraction → D1b → D1c → E-linear
                              B → C ────────────────→ E-branch-heavy（推奨gate）
follow-up:                         現計画完了 → visual branch tree検討
```

- A0は重複を「修正した」のではなく、現seedに重複がないことと再発防止validatorを実装済み。Aは全候補照合、card、明示的な再生ラベル、path保持、直前分岐復帰まで実装済みである。
- D0/D1a〜D1dはB/Cと並行できる。PR-E以降は、ChatGPT等のLLMがWikipedia本文の意味理解、棋譜抽出、A/B/C/M判定を行ってstructured artifactを生成し、プログラムがD1b/D1cでschema、将棋合法性、tree、coverage、metadata整合を決定論的に検証した後、seed/importする。線形またはごく小さい一次分岐seedはD1b/D1c後に追加可能。ただしレビュー・操作対象が多い **branch-heavy seed（多数のsibling、複数分岐点、多段分岐）を追加する前にB/Cを完了することを強く推奨**する。
- B前にbranch-heavy seedを入れるとSFEN接続と配列先頭本線の暫定契約へ新データを固定し、B migration/backfillの範囲を増やす。C前に入れると既存card/通過履歴だけでは全体監査と任意node到達が難しい。例外は「多段構造を検証する最小fixture」であり、production Wikipedia seedではない。
- PR-Eごとに `linear/small-branch` か `branch-heavy` をPR本文で宣言する。branch-heavyの判定例はbranch-of-branchを含む、複数の分岐点を含む、または一覧なしではreviewが困難な規模である。

### PR-A0: 既存分岐の一意性検証 — **完了（PR #52）**

- seed後の同一line / `from_sfen` / USI siblingを全件検査するvalidatorとbackend testを追加済み。
- 原始鬼殺しを含む現seedに重複はなく、到達可能手順を変更する正規化は不要だった。今後の重複はseed時に失敗する。
- PR-Bでsiblingの同一性をdirect parent基準へ変える際、validatorのgroupingも `parent_move_id` / stable key基準へ更新する。

### PR-D0: provenance/coverage 契約文書と監査器の設計固定

- **目的**: A/B/C/M、coverage列挙値、必須metadata、監査表の機械可読形式を固定。
- **変更対象**: `docs/`、必要なら後続用validator test fixture。DB/API/frontend/seed変更なし。
- **依存**: B/Cと並行可能。現在記事のURL/section/revisionを記録する。

### PR-A: 分岐学習 UX 改善 — **完了（PR #53）**

- board/cardの全候補照合、3候補feedback、分岐card、現在path、通過分岐切替、直前分岐点復帰を実装済み。
- 「本線を一手進む」「ここから本線を最後まで再生」を明示し、最後まで再生は選択済みpathを保持する。
- Vitest/Playwrightでhelper、board/card同値、過去切替、360pxを検査済み。PR-BはこのUXを退行させない。

### PR-B: 多段分岐データモデルと本線意味の分離

- **目的**: direct parentでA/A1/A2・B/B1/B2を安定再構築し、**本線であること（semantic main）とsibling表示順（presentation order）を独立させる**。
- **責務**:
  - `parent_move_id` / stable parent key = 構造。
  - `is_main`相当 = 各parent配下で学習上どれを本線とするか。各sibling集合で正確に1件（空集合を除く）をvalidatorで保証する。
  - `sort_order` = 同一parent配下の表示順だけ。mainが常に0番/先頭である必要はなく、同値時はstable key/idで決定的にする。
  - `variation_group` / branch label = 人間向け表示・出典groupであり、構造・main・順序を兼用しない。
- **変更対象**: `backend/app/database.py`, `backend/app/seed.py`, `backend/app/routers/openings.py`, `backend/app/schemas.py`（該当時）, `frontend/src/api/client.ts`, `frontend/src/shogi/openings.ts`, backend/frontend tests。
- **DB migration**: spikeで決定。stable `move_key` / `is_main`追加、direct `parent_move_id` backfill、現行UNIQUE制約とNULL root semanticsを検証する。
- **API/frontend**: move `id`, direct `parent_move_id`, explicit main, stable display orderをadditiveに契約。builderはparent IDを使い、legacy SFEN fallbackは移行期間だけ許す。`expectedOpeningMove`、step、continue-to-end、badgeは配列index 0でなくexplicit mainを使う一方、card/listは`sort_order`順に並べる。
- **seed**: `move_nodes` / `parent_key`新形式とlegacy adapter。Wikipedia move追加なし。
- **tests**: mainが表示順の途中/末尾にあるfixture、multi-level branch、main一意性、migration、idempotency、invalid parent/cycle/SFEN/legal move、legacy互換、transposition非merge。

### PR-C: 折りたたみ式「この定跡の変化」補助一覧 UI

- **目的**: PR-Aの主操作を保ったまま、全体treeの探索、current path確認、任意node jump、分岐点単位のmain復帰を補助する。
- **変更対象**: `OpeningStudyPage.tsx`または新`OpeningVariationList.tsx`、CSS、Vitest/Playwright。DB/API/seed変更なし（PR-B契約を利用）。
- **frontend**: 通常collapsedのdisclosure、semantic nested list、current/ancestorを別々にhighlight、current path表示、node jump、**「この分岐点の本線へ切り替える」**、coverage/source link、responsive/a11y。
- **動作**: node jumpとmain切替はrootからのpathを一意に再構築し、board/history/sourceを同期する。main切替は対象分岐点より後を破棄してPR-Bのexplicit mainを選び、配列先頭を仮定しない。
- **tests**: path変換、current/ancestor、別branchの前後jump、各深さでのmain切替、collapsed初期状態、focus、deep tree、keyboard、360px、500-node fixtureの初期/展開時測定。
- **非目標**: 横レーン型visual branch tree、棋譜リストとの双方向手数同期、branch比較、大規模tree virtualization。これらはfollow-up文書で扱う。

### PR-D1a: 升田式石田流 metadata 整合

- **目的と範囲**: 既知の升田式石田流のmetadata不整合だけを修正する小PR。`source_note`等を実データの終端（7手目▲4八玉）に合わせ、▲7六飛は未収録であることを明確にする。
- **非目標**: movesの追加・削除・並べ替え、他lineの監査、汎用validatorの実装。**movesは一切変更しない**。

### PR-D1b: Structured Wikipedia opening validator

- **目的**: LLMが生成したstructured artifactを、Wikipedia本文の再解釈なしに決定論的に検証する正規validatorを実装する。
- **artifact契約**: D1bで導入する `backend/app/wikipedia_opening_artifact.schema.json` を、今後LLM/人間レビューが生成しD1b/D1cへ渡すcanonical structured artifactのschemaとする。D0で作成した `docs/opening-wikipedia-provenance-audit.schema.json` と既存audit JSON/fixturesは、当時のseed棚卸しを保存するlegacy audit formatであり、新schemaと同時にcanonicalとは呼ばない。legacy auditから新canonical artifactへの移行・差分比較はPR-D1cで扱い、D1bでは旧artifactのimport adapterやseed比較を実装しない。
- **検査範囲**: JSON Schema、USI構文、全着手の合法手再生、initial SFEN、direct-parent tree（root/orphan/親子SFENを含む）、cycle、同一parent配下のsibling USI / `sort_order`一意性、semantic mainのexactly-one規則、coverage boundary、A/B/C/M provenance、mixed segment境界とnode/segment metadata。
- **責務境界**: Wikipedia本文の意味理解・棋譜抽出・A/B/C/M判定はChatGPT等のLLM/人間レビュー側が担う。プログラムはartifactのschema、将棋合法性、tree、coverage、metadata整合だけを検証する。`source_note` / `evidence_note`の「収録」「未収録」等をPythonで自然言語解析して正しさを判定しない。
- **表示metadata**: `source_note`は可能な範囲でcoverage/provenance/終端等の構造化metadataから生成し、自由文を正規データの代用にしない。

### PR-D1c: canonical artifact ↔ seed 整合

- **目的**: 新しいcanonical structured artifactとseed/import結果が一致することを保証する。stable key、繰り返しimport時のidempotency、既存対象を安全に置換できること（欠落・重複・parent drift・意図しないID driftを起こさないこと）を重視する。
- **歴史的seedの扱い**: 既存seedが過去のある時点のWikipedia本文と完全一致していたことを遡及的に証明することは主目的にしない。現在レビューされたcanonical artifactを移行基準とし、差分と置換方針を明示する。
- **runtime投影境界**: `line_key` / `line_name` / `initial_sfen`、nodeのstable key・parent・USI・表示順・main・variation group・SFEN、および既存列が保持するsource URL/title/section/license/retrieved date/source noteをDBに投影する。`line_key` はrenameでidentityを失わないための最小additive列である。旧rowは名前が一意に合う初回だけclaimし、以後は名前でなくkeyをidentityとする。
- **ownership境界**: bundled static seed は `seed_key`、canonical importer は `line_key` をowner identityとする。既存static lineをcanonicalがclaimした場合は両keyを保持し、以後の通常seedはそのlineをcanonical-managedとしてskipする。これによりcanonical rename後も旧static名のlineを再生成せず、canonical treeやruntime-owned node commentを巻き戻さない。canonical artifactは学習commentの正本ではないため、stable node keyが残るcommentは保持し、新規nodeだけ空commentとする。
- **static seed identity制約**: 現行 `seed_key` の `sample:{name}` は既存display nameからownership aliasをbackfillする移行形式であり、bundled seed自体のrenameまで独立に扱える恒久stable IDではない。`SAMPLE_OPENING_LINES` のname変更は禁止し、必要な場合は先に明示的なdisplay非依存seed IDと既存`seed_key`移行を別follow-upで導入する。canonical renameは永続化済みの旧aliasと`line_key`の組で安全に扱う。
- **source type投影**: D1bで許可・検証済みの `source.url` のhostだけを用い、`wikipedia.org` 系を `wikipedia`、`wikibooks.org` 系を `wikibooks` としてruntime `source_type`へ決定論的に投影・比較する。本文やnoteの意味解析は行わない。
- **canonicalのみの監査情報**: revision、node provenance/source section/evidence、segment、正規化coverage status/boundaryはartifactに残す。特に正規化coverage statusをlegacy自由文の `opening_lines.coverage_status` へ書かず、同義として比較しない。非対応fieldのために大量のDB列も追加しない。
- **適用と差分**: D1b validatorでartifact全体を先にgateし、move-lineごとのsavepoint内でstable-key upsert、sort order退避、parent再設定、最後のobsolete削除を行う。catalog-onlyはmovesにしない。legacy auditはcanonicalとしてvalidate/変換せず、既知値のunchanged/added/removed/content/parent/order/metadata差分と、revision/section/review等の「確認不能」を報告する。

### PR-D1d: validator CLI / CI hardening

- **目的**: malformed JSON、invalid UTF-8、missing file、invalid schema、machine-readable errors、module経由でないdirect CLI execution、URL validation等、validator外周の堅牢性を整える。
- **再評価結果（採用）**: D1b/D1c完了後の利用経路に合わせ、canonical schema固定のdirect CLI、file/UTF-8/JSON/schema definition error処理、1個のmachine-readable JSON diagnostics、終了code契約、URL userinfo/explicit port拒否、subprocess回帰testを採用する。終了codeは`0`=valid、`1`=読み込み済みartifactのschema/semantic違反、`2`=artifact/schemaの読み込み・encoding・JSON parse・validator設定の運用エラーとする。外周codeは`artifact_not_found`、`artifact_not_file`、`artifact_invalid_utf8`、`artifact_json_invalid`、`artifact_read_error`、`schema_not_found`、`schema_not_file`、`schema_invalid_utf8`、`schema_json_invalid`、`schema_read_error`、`schema_definition_invalid`を安定した識別子とする。
- **再評価結果（不採用）**: D0 legacy audit adapter、Wikipedia本文取得、自由文の自然言語解析、D1c import/DB検証のCLI統合、新規GitHub Actions workflow、PR-E用canonical artifact追加は行わない。現リポジトリには既存GitHub Actions workflowがなく、PR-Eでgateする実artifact pathも未確定のため、workflowによる実artifact gateはPR-EまたはCI基盤導入時へ延期する。
- **責務境界**: D1bのschema/tree/合法手/coverage/provenance検査を唯一の検証実装として再利用し、D1cのimport・stable-key upsert・DB projectionは変更しない。CLIはD0 legacy schemaとの互換や任意schemaを選択する公開optionを持たない。

### PR #58 の扱い

PR #58はWikipedia provenance validatorの実装・レビューを通して責務過大と判明したため**マージしない**。最終状態はtag `pr58-before-d1-split-20260818` に保存済みであり、その成果と知見はD1a〜D1dへ必要な単位で再構成する。本計画がPR #58の従来計画をsupersedeする。

### PR-E以降: Wikipedia seed追加

1. **PR-E1 石田流・早石田系**
2. **PR-E2 横歩取り系**
3. **PR-E3 角換わり系**
4. **PR-E4 棒銀系**
5. **PR-E5 ゴキゲン・対ゴキゲン**
6. **PR-E6 鬼殺し系**
7. **PR-E7以降**: 矢倉、相掛かり、四間、三間、向かい飛車をarticle/section単位の小PR。

各seed PRは一つの出典sectionまたは密接なbranch群を原則とし、巨大な一括PRを禁止する。すべてのPR-Eは **LLMによるWikipediaからのstructured extraction → D1b validator → D1c canonical artifact/seed整合 → seed/import** を必須gateとする。D1aは既知metadata修正として先行し、D1dは外周要件の再評価結果に応じてgate範囲を定める。branch-heavyなPR-EはB/C完了後を推奨順序とし、先行させる場合は暫定構造を増やす理由と後続migration/UI監査方法を明記する。

## 12. テスト戦略と各 PR の受け入れ条件

### 12.1 共通 test matrix

| 検査 | A0 | A | B | C | D0/D1a | D1b | D1c | D1d | E群 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| backend unit/pytest | 必須 | 関連なし | 必須 | 関連時 | D1aは必須 | 必須 | 必須 | 必須 | 必須 |
| frontend Vitest | 関連なし | 必須 | 必須 | 必須 | metadata UI時 | 関連なし | 関連なし | 関連なし | 必須 |
| frontend lint/build | 関連なし | 必須 | 必須 | 必須 | frontend変更時 | 関連なし | 関連なし | 関連なし | 必須 |
| Playwright / 360px | seed smoke | 必須 | 必須/smoke | 必須 | 表示変更時 | 関連なし | import smoke | 関連なし | 必須/branch追加時 |
| git diff check | 必須 | 必須 | 必須 | 必須 | 必須 | 必須 | 必須 | 必須 | 必須 |
| Wikipedia provenance review | 継承確認 | 表示退行のみ | 継承確認 | 表示確認 | 契約/既知差分 | artifact入力 | canonical差分 | URL外周 | 必須 |

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

#### PR-A0（PR #52で完了）

- [x] 全既存lineで同一 `from_sfen` の sibling USI重複が0件であることを検証した。
- [x] 原始鬼殺しを含む現seedに疑われた重複がないことを固定した。
- [x] seed時validatorとbackend testで再発を禁止した。

#### PR-A（PR #53で完了）

- [x] 3候補の0/1/2番目をboardで指すと各 path index が選ばれ、正解feedbackになる。
- [x] 候補外合法手は不正解でposition/pathを変えない。
- [x] card操作とboard操作が同じnode、source、historyを表示する。
- [x] 「本線を一手進む」「ここから本線を最後まで再生」の挙動が文言通り。
- [x] undo、直前分岐、過去分岐switch、reset後のfocus/live通知が一貫。
- [x] PR-A0の一意性検証済みfixtureを前提に、duplicate sibling USIを再発検知するtestがある。
- [x] Vitest、lint、build、Chromium E2E、360pxを通過。

#### PR-B

- [ ] 本線→A→A1/A2、B→B1/B2 fixtureがDB→API→frontendで同じtreeになる。
- [ ] explicit mainと`sort_order`を分離し、mainが表示順の先頭でないfixtureでも自動再生・badge・main切替が正しい。
- [ ] 各sibling集合のmainは正確に1件で、0件/複数件をvalidatorが拒否する。
- [ ] 全非root rowの`parent_move_id`が直接親で、親to_sfenと子from_sfenが一致。
- [ ] 現行UNIQUE `(line_id, ply, variation_group, sort_order)` をdirect-parent fixtureで評価し、維持または変更の根拠、NULL rootの扱い、migration/backfill手順を記録する。
- [ ] orphan、cycle、duplicate key/USI/order、illegal moveを明確なerrorで拒否。
- [ ] 同一SFENの異なるpathを自動mergeしないfixtureがある。
- [ ] legacy seed/DBをmigration後も既存line ID/URLから再生可能。
- [ ] seedの2回実行でrow重複・ID drift・parent driftがない。
- [ ] pytest、migration tests、Vitest、lint、build、Chromiumを通過。

#### PR-C

- [ ] 一覧は通常collapsedで、PR-Aの盤面/card/replayを主操作として維持する。
- [ ] semantic nested list/disclosureで全nodeへ到達可能。
- [ ] current pathを表示し、currentとancestorを異なる視覚表現・screen reader textで示す。`aria-current="step"`はcurrentだけに付ける。
- [ ] node jump後にboard/history/current branch/sourceが一致。
- [ ] 各分岐点の「この分岐点の本線へ切り替える」が後続pathを破棄し、表示順に依存せずexplicit mainへ移動する。
- [ ] collapseしてもfocus消失や同名button ambiguityがない。
- [ ] 360pxでhorizontal overflowなし、touch targetと長文折返しを確認。
- [ ] 500 node fixtureのrender時間/DOM数を測定してPR本文に記録する。初回は厳格な合否閾値を設けず、結果から最適化課題または将来の基準設定要否を判断する。
- [ ] accessibility自動検査の利用手段を実装時に具体化し、その検査、Vitest、lint、build、Chromium E2Eを通過する。

#### PR-D0 / PR-D1a

- [ ] D0でA/B/C/M、coverage enum、必須metadata、artifact境界を文書化する。
- [ ] D1aは升田式石田流の既知metadataだけを修正し、▲7六飛を未収録と明記する。
- [ ] D1aのbefore/afterでmovesがbyte-for-byteまたはfixture上同一である。
- [ ] metadata-only再seedとAPI responseのpytestを通過する。

#### PR-D1b

- [ ] JSON Schema違反、invalid USI、illegal move、initial SFEN不整合を決定論的なerrorで拒否する。
- [ ] initial positionをimplicit rootとし、`parent_key: null` nodeをそのchildrenであるroot sibling集合として扱う。root siblingは1件以上を許し、他のsibling集合と同じUSI/`sort_order`一意性・semantic main exactly-oneを課す。orphan、cycle、root sibling集合欠落、root siblingのinitial SFEN不整合、親子SFEN不整合を拒否する。
- [ ] 同一parent配下のsibling USIと`sort_order`重複、semantic mainの0件/複数件を拒否する。
- [ ] coverage boundary、A/B/C/M provenance、mixed segmentの境界・必須metadataを検証する。
- [ ] `source_note` / `evidence_note`の日本語自然言語解析に依存するtestまたは正規判定を持たない。
- [ ] 同じartifactから常に同じ検証結果とmachine-consumableな診断位置を得る。

#### PR-D1c

- [ ] canonical artifactとseed/import後のmove、SFEN、tree、coverage、metadataが一致する。
- [ ] stable keyで同じartifactを2回importしても重複、ID/parent driftがない。
- [ ] 更新artifactによる置換が対象範囲外を変更せず、途中失敗時も安全である。
- [ ] 歴史的seedとWikipediaの完全一致証明をgateにせず、canonicalとの差分と移行判断を記録する。

#### PR-D1d

- [x] D1b/D1c後にCLI/CI hardeningの必要範囲を再評価し、採用範囲と延期事項を記録した。
- [x] malformed JSON、invalid UTF-8、missing file/directory、invalid canonical schemaを安定した終了codeと1個のmachine-readable JSON errorで報告する。
- [x] repository rootと`backend`からのdirect CLI execution、既存scheme/host/oldid規則、userinfo/explicit port（非数値・範囲外を含む）の拒否を検査する。
- [x] `sys.executable`・`shell=False`・一時fileを使うsubprocess testでvalid/schema/semantic/各運用errorとtraceback非出力を固定する。
- [x] D0 adapter、本文取得/自然言語解析、import/DB統合、新規workflow、PR-E artifactをこのPRへ含めない。

#### 各 PR-E

- [ ] ChatGPT等のLLMでWikipedia本文を解釈・棋譜抽出・A/B/C/M判定し、review可能なstructured artifactを生成する。
- [ ] structured artifactがD1bを通過し、D1cでcanonical artifactとseed/import結果の一致を確認する。
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
| 自由文noteの機械解釈 | 表現揺れで誤判定、責務肥大 | 正規判定はstructured metadataのみ。表示noteは可能な範囲で生成 |
| 記事改訂/section rename | 再現不能 | oldid/revision、取得日、section記録 |
| source noteとmoves乖離 | coverage誤表示 | 構造化された終端ply/USIを検証しnoteを可能な範囲で生成。升田式を先行修正 |
| 同一USI sibling | boardでbranchを識別不能 | sibling USI一意制約/validator |
| 巨大tree | mobile可読性/性能低下 | branch disclosure、祖先のみ展開、性能fixture |
| migrationで既存line破損 | 学習URL/進捗退行 | additive schema、backfill、idempotency/legacy E2E |
| 「最後まで」の期待差 | 選択変化が失われる | 現path維持、未選択部分のみ本線、ラベル明示 |
| license表示欠落 | attribution不備 | API→node→UIのcontract testsとnotices監査 |

## 14. 完了条件

この取り組み全体は次を満たした時に完了とする。

1. PR #52のvalidatorで既存seedの同一局面・同一USI siblingが0件と確認され、再発が禁止されている。PR #53によりboardで同一分岐点の全登録候補が正解になり、選んだbranch index/path/history/sourceが一致する。
2. 自動再生、undo、分岐点復帰、switchの仕様とラベルが一致し、keyboard/ARIA/360pxで利用できる。
3. direct parentによる任意深さtreeがDB→API→frontendで保持され、semantic mainと表示順が分離され、SFENは合法性・整合性の検査に使われる。
4. transpositionを意図せずmergeせず、異なる学習pathを保持する。
5. 通常collapsedの補助的な「この定跡の変化」でcurrent pathとcurrent/ancestorを区別でき、任意nodeへjumpし、各分岐点のexplicit mainへ切り替えられる。
6. canonical structured artifactにA/B/C/Mと正規化coverageが付き、D1bでschema・合法性・tree・coverage・metadataが決定論的に検証され、D1cでseed/import結果と一致する。
7. D1aで升田式石田流のnote/実moves不整合がmovesを変更せずに解消する。
8. 未収録一覧の各項目は「名称確認」と「連続手順確認」が分離され、Cからmove seedが生成されない。
9. 優先8対象は現行Wikipedia revisionに対するLLM structured extractionと監査記録を持ち、追加手数・branch・A/B境界がreview済みである。
10. 各PRのpytest/Vitest/lint/build/Chromium/360px/後方互換/provenance gateが満たされる。
11. 既存のstatic opening、learning sample、imported linear line、一次分岐、既存URLが退行しない。
12. 本書の**[要外部再確認]**項目は、ネットワーク利用可能なseed PRで一次資料（現行Wikipedia記事とrevision）に置き換え、推測を実装へ持ち込まない。

横レーン型visual branch tree、棋譜リストとの高度な手数同期、分岐比較、virtualizationを含む大規模tree UIは、上記完了条件に含めない。本計画完了後に `docs/opening-visual-branch-tree-followup-plan.md` で別途評価する。

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
- 履歴: PR #19/#20相当の playable seed、PR #22相当の metadata/branch replay、PR #23相当の長手順/branch/migration、PR #40相当の opening type中心UI、PR #52のsibling一意性validator、PR #53の分岐学習UX。
