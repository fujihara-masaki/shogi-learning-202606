# 「次の一手」UX/UI改善 最終設計

対象: PR #30(次の一手学習モード追加)、PR #31(独立機能化)、PR #32(専用SQLite DB導入)後のコードベース
(基準コミット `aa3e8a6`、2026-07-19 時点)

本ドキュメントはコード変更を伴わない調査・計画であり、実装は後続PRで行う。

**本書は次の一手改善の唯一の正本であり、後続の実装PR (PR-A〜PR-F) を開始できる最終設計である。** DB・API・データ整合性・PR間依存は本書を契約とする。一方、契約を変えない内部実装の詳細は各実装PRに委ねる。

---

## 0. 設計の読み方と確定事項

### 0.1 確定する契約

| 領域 | 最終設計 |
| --- | --- |
| DB責務 | `next_move.db` は配布可能な問題データ、`shogi.db` は端末固有の解答・進捗・将来のお気に入りを保持する。アプリ実行時は前者を読み取り専用、後者を読み書きで開く |
| DB生成・検証 | importerおよび抽出・生成処理だけが `next_move.db` を生成・更新する。`validate_next_move_db.py` 等の検証処理は読み取り専用で整合性を検査する。アプリ実行時も検証時も、既存DBへ補完やスキーマ移行を書き込まない |
| 問題同一性 | 永続参照は `problem_key`、画面遷移と競合検出前の検索だけは `sample_id`。出典・正規化局面・判定に使う候補定義・定義バージョンが同じ問題だけを同一視する |
| データ世代 | `dataset_version` はDB全体の世代を表し、ページをまたぐ混在検出だけに使う。問題同一性や履歴結合には使わない |
| 整合性 | 解答の判定・合法性・`problem_key` 一致確認はbackendが行い、成功時だけ `shogi.db` の問題参照と解答を同一トランザクションで保存する |
| 一覧・移動 | backendで `problem_key` 重複排除後に決定的順序とページングを適用する。通常の順次移動は全ページを同一世代で取得できた場合だけ完了判定する |
| 優先度 | P0は記録と正確な進捗・移動の土台、P1は履歴・復習と学習支援、P2は利用実績を見て判断する任意拡張。P2は実装開始条件にしない |

### 0.2 現行実装との境界

本書の「現行」は基準コミットの観察結果、「最終設計」は後続PRが実現する契約である。差がある箇所は不具合をこの文書PRで直したものではない。§8の担当PRと§5・§7の受け入れ条件をセットで参照する。特に、現行の行ID依存、最大100件の巡回、解答未保存、旧形式の一覧レスポンスはPR-A〜Cが段階的に置き換える。

### 0.3 実装PRに委ねる事項

次は契約・データ整合性・受け入れ条件を満たす限り固定しない: 内部関数名、React hook / stateの分け方、SQLをウィンドウ関数・サブクエリ等のどれで表現するか、小規模なファイル分割、fixtureの具体値、意味を変えないUI文言・余白、任意のキャッシュ・先読み・性能最適化。最適化のために `problem_key` 単位の意味、決定的順序、トランザクション境界、API契約を変える場合だけ設計変更として別途レビューする。

---

## 1. 現状分析

### 1.1 画面と遷移

| 画面 | 実装 | 概要 |
| --- | --- | --- |
| 一覧 `/next-move` | `NextMovePage.tsx` + `NextMoveProblemList.tsx` | 戦型セレクト(先頭戦型を初期選択)+ 問題カード(最大30件)。答えの漏洩防止のため候補手・評価値・SFENは非表示 |
| 挑戦 `/next-move/:id` | `NextMoveStudyPage.tsx` + `useNextMoveSession.ts` | 着手前: 盤面・手番案内・段階ヒント(駒種→移動先の2段階)。着手後: 判定バナー・結果パネル・候補比較(トグル)・次の問題/もう一度/一覧へ |
| 判定 | `shogi/nextMove.ts` | `top`(第1候補)/`strong`(第2〜3候補)/`listed`(第4以下)/`unlisted`(DB未登録)。正誤を断定せず、評価値は絶対差のみ参考表示 |
| 次の問題 | `NextMoveStudyPage.tsx` | 同一戦型の兄弟一覧(最大100件)を取得し `(index+1) % length` で巡回。遷移時に見出しへフォーカス移動 |

### 1.2 バックエンド

- 専用DB `next_move.db`(`NEXT_MOVE_DB_PATH`)は**読み取り専用**で接続(`mode=ro`)。未配置・テーブル/カラム欠落・`learning_samples` 0件はすべて `NextMoveDatabaseUnavailable` → HTTP 503。
- API: `GET /api/learning-samples/openings`(戦型別件数)、`GET /api/learning-samples?opening_key=&limit=`(≤100、`opening_key`+`sample_rank` 順で固定)、`GET /api/learning-samples/{id}`、`GET /api/book/candidates` ほか。**書き込み系エンドポイントは無い。**
- 通常DB `shogi.db` には詰め将棋の `problem_results` / `time_attack_results` / `is_favorite` があるが、**次の一手の解答はどこにも記録されない**。

### 1.3 情報設計・役割分担(項目2)

| 機能 | データ | 記録 | 復習/履歴との関係 |
| --- | --- | --- | --- |
| 詰め将棋 | shogi.db `tsume_problems` | `problem_results`(正誤・時間・ミス)、`is_favorite` | 復習(間違え/お気に入り)・履歴(成績サマリー)に統合済み |
| 定跡学習 | フロント固定データ `openings.ts` | なし | なし |
| 次の一手 | next_move.db(読み取り専用) | **なし** | **なし(復習・履歴に一切現れない)** |

役割分担自体は明快(定跡=手順をなぞる/次の一手=局面から考える)で、ナビ・ホーム・旧URLリダイレクトも整理済み。欠けているのは「記録と振り返り」の層で、復習・履歴が詰め将棋専用のままである点が最大の構造的ギャップ。

### 1.4 DB未配置・不正・空の場合の案内(項目3)

- backend は原因別の日本語 detail(「存在しません」「必須テーブルがありません」「学習サンプルがありません」等)を503で返すが、frontend の `isNextMoveUnavailable` はステータス503かどうかしか見ず、**detail を捨てて一律「次の一手データを利用できません。専用DBの設定を確認してください。」と表示**する。未配置か破損か空かをユーザーが区別できず、アプリ内に復旧手順(README該当節、`validate_next_move_db.py`)への導線もない。
- 一方、DBは有効だが選択戦型の問題が0件の場合の空状態文言(README参照を促す)は適切。

### 1.5 アクセシビリティ・レスポンシブ(項目4)

**良好な点(維持すべき資産):**

- 盤面は WAI-ARIA Grid パターン+roving tabindex、矢印/Enter/Space/Esc 対応。成り選択はフォーカストラップ付き `role="dialog"`。
- 判定バナーは `role="status"`、エラーは `role="alert"`。候補比較テーブルに `caption`(visually-hidden)と `scope`。比較トグルに `aria-pressed`/`aria-expanded`。「次の問題」遷移時の見出しフォーカス。
- E2Eに「キーボードのみで着手→結果→次の問題」「360pxで横スクロールなし」「後手番反転・成り分岐判定」を含む。

**確認された問題・懸念:**

1. 一覧カードの見出しが `h1` 直下の `h3`(h2スキップ)。またカードのタイトルが「問題 1〜N」のみで内容の手掛かりが皆無(全カードが同文)。スクリーンリーダーでもビジュアルでも区別不能。
2. 「次の問題」ボタンは兄弟一覧の取得失敗・1問のみの場合に理由の説明なく `disabled` になる。
3. 進捗表示「問題 X / Y」は兄弟取得上限(100件)に依存し、101件以上ある戦型では実態と食い違う。
4. 一覧の取得上限30件がUI上どこにも示されず、戦型セレクトの「(N問)」と表示件数が矛盾し得る(サイレント切り捨て)。
5. 360pxでは候補比較テーブルがラッパー内横スクロールで許容範囲だが、PV列が長く1画面で読み切れない。モバイル前提ならPVの省略表示+展開が望ましい。
6. 解答直後、フォーカスは盤面セルに残る。`role="status"` で読み上げはされるが、結果パネル→比較→次の問題へ進むにはTab移動が長い(致命的ではないが改善余地)。

### 1.6 その他のコード観察

- `NextMovePage` が `className="openings-page"` を流用(実害なしの残骸)。
- 一覧は毎回同じ並び(`sample_rank` 順)で、`limit` 以外のパラメータ(offset・random・件数合計)が無い。README の「既知の制限」にも全戦型混在・ランダム・ページング未対応と明記されている。
- 解答の所要時間は計測していない(詰め将棋は `elapsed_ms` を記録している)。

---

## 2. 主なUX/UI上の問題(優先度順)

1. **学習の記録が一切残らない**: 何問解いたか、どの問題で候補外を指したかが分からず、「継続して利用しやすく、学習効果が分かりやすい」という目的に対する最大の欠落。復習・履歴とも未接続。
2. **一覧が「選ぶ理由」を提供しない**: カードが全て同文で、未挑戦/挑戦済みの区別もない。2回目以降の訪問で「どれをやればいいか」が分からない。
3. **出題ポリシーが「戦型先頭から順番」しかない**: ランダム・未挑戦優先・弱点再出題が無く、毎回同じ問題から始まる。「次の問題」は無限巡回で完了感がない。
4. **考え中にスキップできない**: 分からない問題は答えるか一覧に戻るしかない(答えを見てから進むには一度着手が必要)。
5. **DB異常時の案内が粗い**: 原因(未配置/不正/空)を区別せず、復旧手順への導線がない。
6. **評価値・PVの説明が不足**: 「出典データに依存」という注記はあるが、初学者向けに評価値・PV・候補順位が何を意味するかの説明(用語ヘルプ)がない。
7. 進捗ラベル・disabledボタン・見出し階層などの細かなa11y/整合性問題(§1.5)。

---

## 3. 想定する利用フロー(改善後)

```
[ホーム/ナビ] → [次の一手 一覧]
                 ├─ 進捗サマリー(戦型ごと: 挑戦済み n/N・最有力率)
                 ├─ 「続きから出題」(未挑戦優先) / 「ランダム出題」
                 └─ 問題カード(状態バッジ: 未挑戦/◎/○/△/?)→ [挑戦]
[挑戦画面]
  考える → (ヒント) → 着手 → 判定+結果パネル(+候補比較)
     │                         ├─ 解答を自動記録(ローカルDB)
     └─ スキップ ──────────────┴→ [次の問題](出題ポリシーに従う)
                                     └─ 一巡したら完了メッセージ+次の戦型/復習への導線
[復習] 次の一手タブ: 候補外・下位候補だった問題を再挑戦
[履歴] 次の一手セクション: 解答数・最有力率・最近の解答
```

---

## 4. 改善案と優先順位(項目5の分類を含む)

前提となる設計判断: **解答記録・お気に入りなどのユーザーデータは通常DB(shogi.db)に保存し、next_move.db は読み取り専用のまま**とする。next_move.db は再生成・差し替えされる(`learning_samples` は再抽出で DELETE→INSERT され **id が変わる**)ため、記録のキーには `id` を用いない。

記録のキーには **問題の意味(出典・局面・候補手定義)にのみ依存する安定キー `problem_key`** を用いる。SFEN + opening_key だけでは、複数の外部定跡ソースに同一局面が存在した場合に、候補手・順位・評価値が異なる**別問題を同一視してしまう**ため不可。一方で、抽出件数・seed などの**抽出実行条件はキーに含めない**。含めてしまうと、サンプルを10,000件→100,000件に増やす・seedを変えるといった問題の意味と無関係な操作だけで全履歴・進捗・復習状態・お気に入りが失われるため。抽出実行条件は後述の `extraction_run_key` として分離して保存する。

ハッシュ入力は**単純な文字列連結にしない**。連結では `(name="ab", version="c")` と `(name="a", version="bc")` のように、SHA-256の衝突ではなく**入力表現の曖昧さによる衝突**が起こり得るため、境界が一意に判別できる canonical JSON をハッシュ入力とする:

```
problem_key_payload = canonical_json({
  "candidate_definition_fingerprint": candidate_definition_fingerprint,
  "normalized_sfen": normalized_sfen,
  "problem_definition_version": 1,
  "stable_source_key": stable_source_key
})

problem_key = "v1:" + sha256(problem_key_payload)
```

**canonical JSON(canonical serialization)の共通仕様**: `problem_key`・`stable_source_key`・`candidate_definition_fingerprint` の3箇所すべてで**同一の共通シリアライズ関数**を使う。

- JSONオブジェクトのキーは辞書順に固定する
- 余分な空白を含めない(セパレータ固定)
- UTF-8 でエンコードし、その**バイト列**に対して SHA-256 を計算する
- 文字列・`null`・空文字を区別する(欠損は `null`、空値は `""` として表現し、同一視しない)
- Unicode 正規化は **NFC** に固定する(日本語のソース名等でも決定的になるように)
- 数値(`problem_definition_version` 等)は整数として表現する(文字列化しない)
- ハッシュ値の先頭に `"v1:"` の形式バージョンを付け、シリアライズ仕様を変更する場合はバージョンを上げる

- `stable_source_key`: 定跡ソースを安定して識別する値。name / version / source_url の**単純連結ではなく**、同じ canonical JSON 仕様から生成する:

  ```
  stable_source_payload = canonical_json({
    "name": source.name,
    "source_url": source.source_url,
    "version": source.version
  })

  stable_source_key = "v1:" + sha256(stable_source_payload)
  ```

  同一局面でもソースが異なれば候補手・評価値が異なる別問題として扱う。**ファイル全体の `file_sha256` は含めない**(ファイルの一部が更新されただけで、変更のない全局面のキーが変わってしまうため)。`file_sha256` は監査用メタデータとして別途保存する。
- `normalized_sfen`: SFENの手数(ply)フィールドを除去し、盤面・手番・持ち駒を python-shogi / tsshogi の再シリアライズで正規化する。再生成時の表記ゆれ(持ち駒の並び・空白等)でキーが変わることを防ぐ。
- `candidate_definition_fingerprint`: その局面に登録されている候補手と、**判定に実際に使う候補順序**を局面単位でハッシュ化した値。前提として、候補の順序決定を共通の判定用候補正規化規則に一元化し、(1) API の候補返却順、(2) frontend の `judgeNextMove`、(3) backend の verdict / candidate_rank 算出、(4) fingerprint、(5) テスト、のすべてで同一実装(同一規則)を使う。

  **判定用候補順序の規則**(現行APIの ORDER BY を安定化したもの):

  1. `effective_rank` 昇順(DB の rank = `sort_order + 1` があればそれ、無ければ判定に使う並び順から補完。`sort_order` の欠番・非連続値も実際の判定順位をそのまま反映)
  2. 同順位は `score` 降順(NULL は非NULLの後)
  3. 次に `depth` 降順(NULL は非NULLの後)
  4. 最後に `move_usi` 昇順

  **DB の行ID・挿入順は順序決定に使わない**(行IDはDB再生成で変わるため、安定キーの意味を決める tie-breaker には不適。現行APIの最終 tie-breaker `bm.id` は PR-A で `move_usi` に置き換える)。

  fingerprint の canonical 入力は、この共通関数の結果順に **`judgment_position`(判定後の位置=1始まりの連番)・`effective_rank`・`move_usi`** の組を並べた配列とし、上記の canonical serialization 共通仕様(同一のシリアライズ関数)で JSON 化してハッシュ化する:

  ```json
  [
    {"judgment_position": 1, "effective_rank": 1, "move_usi": "2g2f"},
    {"judgment_position": 2, "effective_rank": 1, "move_usi": "7g7f"}
  ]
  ```

  - score・depth の**生の数値そのものは fingerprint に含めない**(数値の微修正やPV追記のたびに別問題化するのを避ける)。ただし score/depth の変化で同順位候補の順序が入れ替わった場合は `judgment_position` と `move_usi` の対応が変わるため、fingerprint と `problem_key` も変わる。つまり: **score/depth が変わっても判定順が変わらなければキーは維持され、top候補や判定順が変われば必ずキーが変わる**(同順位候補の score 更新で top が入れ替わったのに旧キーが照合を通過し、新しい候補順の verdict で誤記録される穴を塞ぐ)。
  - 候補手・順位・判定順のいずれかが変われば fingerprint が変わり、別問題として扱われる。同順位候補は禁止しない(判定順で一意化する)。
- `problem_definition_version`: problem_key の意味や fingerprint の計算方法を変更する場合に備えたバージョン(初期値 `1`)。先頭の `v1:` はキー文字列形式のバージョンで、これと合わせて管理する。

`opening_key` はキーに**含めない**: 戦型分類は分類器の改良で変わり得る表示・集計用メタデータであり、分類が変わっても問題自体は同一だからである。この方針を集計側でも一貫させるため、**進捗・状態・復習・履歴の戦型グルーピングは「現在の next_move.db の分類」を `problem_key` 経由で参照**する。解答レコードに保存する戦型は「解答時点のスナップショット」であり、集計のグルーピングには直接使わない(詳細は §6)。

`problem_key` は backend が `learning_samples` の各レコードに対して算出し、API レスポンスに含める。クライアントは解答POST時にこの `problem_key` を送り返し、backend の再算出値と照合することで、**表示中の問題と記録対象の問題が同一であること**を保証する(next_move.db 差し替えで同じ `sample_id` が別問題に再利用された場合の誤記録防止。詳細は P0-1)。

**抽出実行メタデータ(`extraction_run_key`)の分離**: 以下は problem_key に含めず、「どの抽出実行・どのソースファイルから生成されたか」を追跡する監査用メタデータとして next_move.db 側に保存する。

```
extraction_run_key   -- 抽出実行の識別子(下記フィールドから生成)
extractor_version    -- 抽出器・分類器のバージョン
limit                -- 抽出件数上限
per_opening_limit    -- 戦型別上限
seed                 -- 抽選seed
source_file_sha256   -- 取り込み元ファイルのハッシュ(監査用)
extracted_at         -- 抽出日時
```

**履歴を引き継ぐケース**(problem_key が一致する):

- 抽出件数を増減した(例: 10,000件→100,000件)
- `limit`・`per_opening_limit`・`seed` を変更して再抽出した
- 同じ出典・同じ正規化局面・同じ候補手定義の問題が再抽出された
- ソースファイルの**別局面だけ**が変更された(対象問題の候補手定義が不変なら `file_sha256` が変わっても引き継ぐ)
- 戦型分類(opening_key)だけが変わった

**別問題として扱うケース**(problem_key が変わる):

- 出典(`stable_source_key`)が異なる
- 正規化局面が異なる
- 候補手または候補順位の定義が変わった(fingerprint が変わる)
- `problem_definition_version` を変更した

### P0 — 継続利用の土台(記録と最小限の出題改善)

| # | 項目 | 内容 |
| --- | --- | --- |
| P0-1 | 解答記録(学習履歴の基盤) | `next_move_results` テーブルを shogi.db に追加し、着手判定時に自動記録(verdict・候補順位・ヒント使用数・所要時間) |
| P0-2 | 進捗表示 | 一覧に戦型ごとの「挑戦済み n/N・最有力率」、カードに状態バッジ(未挑戦/◎/○/△/?)。挑戦画面の「問題 X / Y」を正確な件数ベースに修正 |
| P0-3 | ランダム出題・未挑戦優先 | 出題API(`policy=random\|unattempted`)と一覧の「ランダム出題」「続きから(未挑戦優先)」ボタン。「次の問題」もポリシーに追従 |
| P0-4 | 問題のスキップ | 考え中にも「スキップして次へ」を表示(記録は残さない)。一巡時は完了メッセージを表示し無限巡回をやめる |
| P0-5 | DB異常時の案内改善 | 503 detail をUIに表示し、未配置/不正/空を区別。README該当節と `validate_next_move_db.py` への手順をアプリ内に明記 |

### P1 — 学習効果の可視化と振り返り

| # | 項目 | 内容 |
| --- | --- | --- |
| P1-1 | 学習履歴画面統合 | 履歴ページに次の一手セクション(解答数・最有力率・最近の解答一覧) |
| P1-2 | 間違えた問題・候補外着手の再出題 | 復習ページに「次の一手」タブ(直近の verdict が unlisted/listed の問題)+出題ポリシー `policy=weak` |
| P1-3 | 複数戦型からの均等出題 | `policy=random` を全戦型対象にする際、戦型ごとに均等サンプリング(SQLで戦型ごとに1件ずつ→シャッフル) |
| P1-4 | 評価値・PVの説明 | 結果パネル・比較テーブルに用語ヘルプ(`<details>` で「評価値とは」「PVとは」「候補順位とは」)。既存の SCORE_NOTE と統合 |
| P1-5 | a11y細部修正 | 一覧の見出し階層(h2追加)、disabledボタンへの理由表示、解答後に結果パネルへのスキップリンク |

### P2 — 発展(P0/P1の利用状況を見てから)

| # | 項目 | 内容 |
| --- | --- | --- |
| P2-1 | お気に入り | `next_move_favorites`(`problem_key` キー)+一覧絞り込み+復習タブ統合 |
| P2-2 | 問題一覧UIの検索・絞り込み・ページング | P0で順次移動の正確性のために導入するAPIページングとは別に、一覧画面へ「さらに表示」(offset)、状態(未挑戦のみ等)での絞り込み。テキスト検索は問題にテキスト属性がほぼ無いため保留 |
| P2-3 | サーバー側 sequential 出題の検討 | 出題APIに `sequential` policy(サーバー側 cursor)を追加し、一覧に出題モード切替UI(順番/ランダム/未挑戦優先)を明示する案。**P0ではクライアント側の順次移動(既存兄弟一覧の distinct problem_key 巡回)を維持する**ため、これは「順次移動のサーバーAPI化」を意味し、P0の方針と矛盾しない。必要性を後続PRで再検討 |
| P2-4 | 候補手比較の強化 | 比較テーブル行クリックでPVを盤面再生(ミニ盤 or 既存盤の閲覧モード) |
| P2-5 | 一覧カードの局面プレビュー | ミニ盤サムネイル(答えは漏れない=局面自体が問題)。件数が多いと描画コストがあるため遅延描画前提 |

分類の補足:

- 「戦型内の順次出題」は現状の「次の問題」が実質これなので、新規実装ではなく **P0-4 の完了処理と P2-3 のモード明示化** に分解した。
- 「解答後の候補手比較」は実装済み。強化(PV再生)のみ P2-4 とした。

---

## 5. 各項目の受け入れ条件

### P0-1 解答記録

- 挑戦画面で合法手を指すと `POST /api/next-move/results` が1回呼ばれる。クライアントが送るのは `sample_id`(**一時参照**)・`problem_key`(**問題取得APIが返した値**)・`move_usi`・`hint_count`・`elapsed_ms` の5項目のみ。
- **verdict と candidate_rank は backend 側で算出する**: backend は `sample_id` から next_move.db の現在の問題・候補手・出典メタデータを読み、`problem_key` を再算出する。**クライアントが送った `problem_key` と再算出値が一致した場合のみ**、共通の判定用候補正規化規則の結果順で `move_usi` を突き合わせて verdict・candidate_rank・judgment_position を確定し保存する。クライアント申告の判定は信用しない(フロントの判定ロジックは即時表示専用とし、候補順序・順位規則は backend と同一の共通関数規則であることをテストで担保する)。
- **同順位候補がある場合の判定の意味**(candidate_rank と judgment_position の分離):
  - `judgment_position` = 共通の判定用候補正規化規則の結果順の位置(1始まり)。**top は judgment_position = 1 の候補**(現行 `judgeNextMove` の「先頭候補 = top」と同じ)。
  - `candidate_rank` = `effective_rank`(API表示の「第N候補」と同じ値)。同順位候補は同じ `candidate_rank` を持ち得る。
  - verdict 区分: judgment_position = 1 → `top`。それ以外は `effective_rank` ≤ 3 → `strong`、4以上 → `listed`(現行規則の維持。同 effective_rank = 1 の2番目の候補は `strong` になる)。
  - 記録には `candidate_rank`(表示順位)と `judgment_position`(判定位置)の**両方**を保存し、意味の曖昧さを残さない。
- **problem_key 不一致時は履歴を保存せず HTTP 409 を返す**(構造化エラーコード例: `NEXT_MOVE_PROBLEM_CHANGED`)。これは、問題表示後〜解答送信の間に next_move.db が再生成・差し替えされ、同じ `learning_samples.id` が**別問題に再利用された**ケースの検出である(この場合 `sample_id` は存在するため404にも503にもならず、照合なしでは差し替え後の別問題に誤って履歴が保存されてしまう)。`next_move_results` にも `next_move_problem_refs` にも書き込まない。
- 409 を受けたフロントエンドは「問題データが更新されました。再読み込みしてください」等を表示する。**盤面上で算出済みの解答結果表示自体は妨げない**(記録されなかったことのみ控えめに伝える)。
- **`move_usi` の合法性を backend で検証する**: APIを直接呼ぶと、USI構文としては正しくても局面上は不可能な手を送信でき、照合だけでは unlisted として記録されて進捗・弱点復習・履歴を汚染するため、保存前に問題のSFENから局面を復元して検証する。処理順序:
  1. `sample_id` から現在の問題を取得する(存在しなければ404、next_move.db 利用不可なら503)
  2. `problem_key` を再算出し、クライアント送信値と照合する(**不一致なら合法性検証より先に409**)
  3. SFEN から盤面を復元する
  4. `move_usi` を解析する(構文不正は422、エラーコード `NEXT_MOVE_MOVE_FORMAT_INVALID`)
  5. 現在の手番・駒の移動・成り・駒打ちを含めて合法手か検証する(python-shogi を使用。違法手は422、エラーコード `NEXT_MOVE_ILLEGAL_MOVE`)
  6. 合法な場合のみ候補手と照合して verdict・candidate_rank・judgment_position を算出・保存する
- 判定の区別を明確にする: **合法だが候補一覧にない手 → `unlisted` として正常に記録**/**局面上の違法手 → 記録せず422**/**USI構文自体が不正 → 記録せず422**。422 のいずれの場合も `next_move_results`・`next_move_problem_refs` に書き込まない。通常のUI(盤面)からは合法手しか送信されない既存仕様は維持し、422 は主に直接API呼び出しへの防御である。
- 「もう一度考える」→再着手でも新しいレコードとして記録される(上書きしない)。
- 記録APIの失敗は挑戦フローを妨げない(結果表示は正常に出る。控えめなエラー表示のみ)。
- next_move.db には実行時書き込みを行わない。§4冒頭の「履歴を引き継ぐケース」(抽出件数・seed変更、無関係な局面のみの変更等)で `problem_key` が一致して記録が引き継がれ、「別問題として扱うケース」(出典・局面・候補手定義・定義バージョンの変更)で区別されることをテストで担保する。
- 記録は所要時間を含む(問題表示〜着手までのms)。

### P0-2 進捗表示

- 一覧の各戦型に「挑戦済み n / 全N問」が表示される。**分子・分母とも distinct `problem_key` 基準**とする: N は現在の next_move.db から算出した **distinct `problem_key` 数**、n は解答済み distinct `problem_key` 数。`learning_samples` の行数は使わない(同じ name/version/source_url のソースを別 `file_sha256` で再取り込みした場合や、手数フィールドだけ異なるSFENなど、複数行が同一 `problem_key` に正規化され得るため。行数を分母にすると全問解いても100%に届かない)。
- 進捗率・最有力率・未挑戦判定・完了判定はすべて `problem_key` 単位で行う。
- 一覧に同一 `problem_key` の問題が重複表示されない(resolver の重複排除。§6)。戦型のグルーピングは**現在の next_move.db の分類**に基づく(解答時スナップショットでは集計しない)。
- 各カードに最新解答に基づくバッジ(未挑戦/◎最有力/○有力/△登録候補/?未登録)が表示され、`aria-label` で読み上げ可能。「最新解答」の定義は `answered_at DESC, id DESC`(§6「最新解答の決定的順序」)。
- 挑戦画面の「問題 X / Y」が戦型の distinct `problem_key` 数と一致する(100件超でも正しい)。
- 一覧が30件で切れる場合、「全N問中30問を表示」の注記が出る。

### P0-3 ランダム出題・未挑戦優先

- 一覧に「ランダムに1問」「未挑戦から1問」ボタンがあり、押すと該当問題の挑戦画面へ遷移する。
- 未挑戦問題が無い場合はその旨を表示し、ランダム出題へフォールバックできる。
- 解答後の「次の問題」は現在の出題ポリシーを引き継ぐ(ランダムで来たら次もランダム。**一覧から普通に開いた場合の「次の問題」は従来どおりの順次移動を維持**する — P0-4参照)。
- **通常の順次移動と新APIの役割分担**: 新しい `GET /api/next-move/problems/next` の policy は `random` / `unattempted` (P0) と `weak` (P1で追加) で、順序上の現在位置を持たない。そのため**通常の「次の問題」(順次移動)は新APIへ統合せず**、既存一覧APIを使ったクライアント側の順次移動を維持する。ただし**対象戦型の全 distinct `problem_key` を取得してから現在位置と完了条件を判定する**(全ページ取得方式):
  - 現行実装は兄弟一覧を最大100件で1回取得するだけ(`fetchLearningSamples(openingKey, 100)`、一覧APIの上限も100件)のため、101問以上ある戦型では取得済み配列の100問目を「最後」と誤認して完了表示してしまう。**取得済み配列の末尾を完了条件にしない。**
  - frontend は順次移動セッション開始時に、ページングAPI(§6: `offset`/`limit`/`total`/`dataset_version`)を `offset=0,100,200,...` と繰り返し取得して統合する。**複数リクエスト間で next_move.db が差し替わる可能性があるため、「`items` が空」だけを正常終了条件にしない**(例: 1ページ目が `total=101` で100件→差し替え発生→2ページ目が空、を成功扱いすると100/101件のまま100件目を最終問題と誤判定する)。取得の成功は**取得済み distinct `problem_key` 件数と期待 total の一致、かつ全ページの `dataset_version` 一致**で判定する:
    - 最初の正常レスポンスで `expected_total` と `expected_dataset_version` を確定し、以降の各ページの `total` が `expected_total`、`dataset_version` が `expected_dataset_version` と一致することを確認する。
    - 統合済み distinct `problem_key` 件数を `loaded_count` として管理し、**`loaded_count == expected_total` かつ全ページの `dataset_version` が一致した場合のみ取得完了**とする(offset ではなくこれを最終条件にする)。
    - 異常(不整合)として扱うケース: `items` が空なのに `loaded_count < expected_total`/ページの `total` が `expected_total` と異なる(増減どちらも)/ページの `dataset_version` が `expected_dataset_version` と異なる/新しいページを取得しても `loaded_count` が増えない(無限ループさせず停止)。
    - 不整合時は取得済み一覧を破棄し、取得済み配列の末尾を最終問題扱いせず、「問題データが更新されたため、一覧を再取得してください」等の表示+再試行(**`offset=0` から取得し直す**)+一覧へ戻る導線を出し、完了表示にはしない。世代不一致も同じ再取得経路で扱い、混在した世代A/Bの一覧を保持しない。
  - 完成した distinct `problem_key` 一覧(全 `expected_total` 件)上で、現在の `problem_key` の位置を基準に次へ進む。最後の distinct `problem_key` でのみ P0-4 の完了表示に切り替える(従来の `(index + 1) % length` による無限巡回は廃止)。
  - **途中ページの取得に失敗した場合も、取得済み配列の末尾を「最後の問題」と扱わない**。「次の問題一覧を最後まで取得できませんでした」等の表示+再試行ボタン+一覧へ戻る導線を出し、完了表示にはしない。
  - **DB世代識別子(`dataset_version`)はP0必須**: 一覧レスポンスに `dataset_version`(next_move.db 生成物全体を表す世代ID。`problem_key` とは別目的で、ページング中のスナップショット混在を検出するための識別子)を含め、全ページで一致しなければ取得済み一覧を破棄して `offset=0` から再取得する。`total` が同じ別DBへページ途中で差し替わった場合でも、世代Aの1ページ目と世代Bの2ページ目を成功扱いしない。
  - 実装上の検討事項: 取得中のローディング表示、二重取得防止、戦型変更時の古い取得の AbortController 等によるキャンセル(古いページ結果が新しい戦型へ混入しないように)、同一戦型の取得結果のセッション内キャッシュ。P0では実装の単純さを優先し、戦型ごとの distinct 問題数が現実的な範囲(数百件程度)である前提で開始時の全ページ一括取得とする(先読み方式への変更は必要になってから)。
  - 順次移動をサーバーAPIへ移行する場合は別PRで行う(P2-3参照)。
- **同一問題が連続して出ない(直前問題の除外は `problem_key` 基準)**: frontend は表示中の問題の `problem_key` を `exclude_problem_key` として送り、backend は distinct `problem_key` 単位の候補集合からそのキーを除外してから選択する。`exclude_id`(sample_id基準)は正式な除外契約に**しない** — 同一 `problem_key` に複数 `sample_id` がある場合(例: 表示中が sample_id=10、代表が sample_id=20)や、DB差し替えで同じ問題の `sample_id` が変わった場合に、ID除外では同一問題が再出題されてしまうため。
  - 直前問題の `problem_key` が次回の候補集合から除外される。同一 `problem_key` に複数 `sample_id` があっても、またDB差し替えで `sample_id` が変わっても、同一問題は再出題されない。
  - distinct 候補が2件以上なら必ず別の `problem_key` が返る。
  - **distinct 候補が1件のみで、除外すると0件になる場合は「次の問題がありません」として 204 を返す**(同じ問題を返し直すより、完了・他戦型への導線を示す既存UX(P0-4の完了メッセージ)と整合するため)。frontend は完了状態の表示に切り替える。
  - `exclude_problem_key` が現在DBに存在しないキーの場合は、除外対象なしとして通常どおり選択する。
  - 形式が不正な `problem_key`(`v1:` プレフィックス無し等)も「存在しないキー」と同じ扱いで通常選択し、backend ログに警告を残す(GETの利便性を優先し、エラーにはしない)。
  - `policy=random`(戦型指定あり/全戦型)・`unattempted`・`weak` のすべてで共通して `problem_key` 単位の除外を行う。
- **出題APIのURLは `/api/next-move/problems/next`**(次の一手専用 namespace): 既存の動的ルート `GET /api/learning-samples/{sample_id}` に捕捉されず、ルーターの include 順を変更しても正常に到達できる。正常時は代表 sample と `problem_key` を返し、候補なしは204を返す。

### P0-4 スキップと完了

- 着手前に「スキップして次へ」が表示され、押すと記録なしで次の問題へ遷移し、見出しへフォーカスが移る。
- **完了条件**: 同一戦型の**全ページ取得を完了した**(= `loaded_count == expected_total` かつ `dataset_version` 一致が成立した)distinct `problem_key` 一覧(P0-3の全ページ取得方式)において現在の問題が最後の場合、次へ進まず「この戦型の問題を最後まで学習しました」等の完了メッセージと、「一覧へ戻る」「もう一度取り組む」「ランダムに続ける」等の導線を表示する(先頭へループしない)。
- 一覧の全ページ取得が完了していない(途中失敗・total不整合・dataset_version不一致・空ページ未達などの)状態では完了表示にしない(P0-3のエラー時の扱い: 再試行導線を出す)。
- distinct 候補が1件のみの戦型でも、解答後の「次の問題」は完了扱いとする。
- キーボードのみでスキップ→次問題→完了表示まで操作できる。

### P0-5 DB異常時の案内

- 未配置・スキーマ不正・サンプル0件のそれぞれで異なる説明が表示される(backend detail を反映)。
- 画面に復旧手順(READMEの該当セクション名、importer/抽出/検証コマンドの要点)が表示される。
- 503以外のエラー(ネットワーク等)は従来どおり一般エラーとして表示される。

### P1-1 履歴統合

- 履歴ページに「次の一手」セクションが追加され、総解答数・verdict別内訳・最有力率・最近の解答(日時/戦型/手/判定)が表示される。
- 表示する戦型は resolver による**現在の分類**。現在の next_move.db に存在しない問題のみ解答時スナップショットで表示し、「現在の問題データには存在しません」等の状態を付ける。
- 既存の詰め将棋・タイムアタックの表示に影響がない(既存E2Eが通る)。

### P1-2 復習統合(再出題)

- 復習ページに「次の一手」タブが追加され、最新解答が unlisted または listed の問題が一覧表示される(「最新」は `answered_at DESC, id DESC`。§6)。戦型は現在の分類で表示する。
- 「再挑戦」で該当問題の挑戦画面へ遷移し、最有力候補(top)を指すと一覧から消える(次回ロード時)。
- 現在の next_move.db から削除された問題は再挑戦できない(一覧から除外するか、利用不可として導線を無効化する。誤って挑戦画面へ遷移させない)。
- 該当問題が0件のとき適切な空状態文言が出る。

### P1-3 均等出題

- 戦型選択ロジックを純関数(例: `choose_opening(openings, rng)`)として分離し、RNG を注入可能(seeded/mockable)にする。
- 単体テストで、**seeded RNG による決定的テスト**として次を検証する:
  - 各戦型がサンプル数によらず**同一重み**で選択されること(RNGの返す値と選択結果の対応を網羅的に確認する、または固定seedでの選択列が期待列と一致することを確認する)。
  - `exclude_problem_key` により直前の問題(の全 sample 行)が候補集合から除外されること。
- 戦型選択(`choose_opening`)・問題選択(`choose_problem`)の責務分担: どちらも **resolver が構築した distinct `problem_key` 単位・`exclude_problem_key` 除外後の候補集合**の上で動作する純関数とする(`learning_samples` の行集合を直接使わない)。
- 確率的な閾値判定(「n回連続で偏らない」等)はテストに用いない(正しい一様乱数でも確率的に失敗し得る flaky なテストになるため)。
- anti-streak(同一戦型の連続抑止)は**仕様としない**。エンドポイントはステートレスのままとし、履歴パラメータやセッション状態は追加しない(直前問題の除外は `exclude_problem_key` のみ)。

### P1-4 用語説明

- 結果パネルに「評価値・PV・候補順位とは」ヘルプ(`<details>`)があり、着手前の画面には表示されない(答えの漏洩なし)。
- スクリーンリーダーで summary → 内容の順に読める。

### P1-5 a11y細部

- 一覧の見出し階層が h1→h2→h3 になる。
- disabled な「次の問題」に理由(「この戦型は1問のみです」等)が視覚+SRで提示される。
- 解答後、結果パネル先頭へ移動する手段(スキップリンク or フォーカス移動)がある。既存のキーボードE2Eは修正なしで通る。

---

## 6. 想定変更ファイル

### DBスキーマ

変更対象は **shogi.db と next_move.db の両方**である。next_move.db は「変更しない」のではなく、**アプリ実行時に書き込まない**(`mode=ro` を維持)だけであり、**抽出・再生成時には抽出ツールがスキーマとメタデータを更新する**。この区別を実装時のスコープ漏れなく扱うため、以下を分けて記載する。

#### shogi.db(ユーザーデータ・実行時書き込み対象)

- `next_move_problem_refs`(問題参照)
- `next_move_results`(解答記録)
- 将来: `next_move_favorites`(P2-1)

`backend/app/database.py` — 追加テーブル:

キー構成要素を解答のたびに全カラム重複保存するのは冗長なため、**問題参照テーブル(problem_key ごとに1行)+スリムな結果テーブル**の2表構成とする。

```sql
-- 問題参照(problem_key ごとに1行。POST時に backend が upsert。デバッグ・将来のキー移行用)
CREATE TABLE IF NOT EXISTS next_move_problem_refs (
    problem_key TEXT PRIMARY KEY,
    stable_source_key TEXT NOT NULL,
    normalized_sfen TEXT NOT NULL,
    candidate_definition_fingerprint TEXT NOT NULL,
    problem_definition_version INTEGER NOT NULL DEFAULT 1,
    last_extraction_run_key TEXT NOT NULL DEFAULT '',   -- 監査用(キーには不使用)
    last_source_file_sha256 TEXT NOT NULL DEFAULT '',   -- 監査用(キーには不使用)
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 解答記録(1解答=1行。キー構成要素は problem_refs 側に持たせて重複保存しない)
CREATE TABLE IF NOT EXISTS next_move_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_key TEXT NOT NULL REFERENCES next_move_problem_refs(problem_key),
    opening_key_at_answer TEXT NOT NULL DEFAULT '',   -- 解答時点のスナップショット(集計のグルーピングには使わない)
    opening_name_at_answer TEXT NOT NULL DEFAULT '',  -- 同上。分類変更のたびに書き換えない

    move_usi TEXT NOT NULL,
    verdict TEXT NOT NULL,              -- top / strong / listed / unlisted(backend算出)
    candidate_rank INTEGER,             -- effective_rank(表示順位)。候補外は NULL(backend算出)
    judgment_position INTEGER,          -- 判定用候補順序上の位置(1始まり)。候補外は NULL(backend算出)
    hint_count INTEGER NOT NULL DEFAULT 0,
    elapsed_ms INTEGER,
    answered_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- 「最新解答」検索用(problem_key ごとの latest 1件を answered_at DESC, id DESC で引く)
CREATE INDEX IF NOT EXISTS idx_next_move_results_latest ON next_move_results(problem_key, answered_at DESC, id DESC);
-- 履歴の新しい順表示用
CREATE INDEX IF NOT EXISTS idx_next_move_results_answered ON next_move_results(answered_at);
-- P2-1 で追加: next_move_favorites(problem_key UNIQUE REFERENCES next_move_problem_refs, created_at)
```

上記2本で latest 検索と履歴表示をカバーする(SQLiteの実際のクエリプランを確認し、これ以上のインデックスは追加しない)。

**最新解答の決定的順序**: `answered_at` は SQLite の `datetime('now')` による**秒単位**の時刻であり、再挑戦や直接POSTが同一秒内に複数回行われると複数行が同じ `answered_at` を持ち得る。`answered_at DESC` だけで「最新解答」を選ぶと結果がクエリプラン依存になるため、**最新解答を選ぶすべてのクエリで次を正式な順序とする**:

```sql
ORDER BY answered_at DESC, id DESC
-- ウィンドウ関数の場合:
ROW_NUMBER() OVER (PARTITION BY problem_key ORDER BY answered_at DESC, id DESC)
```

- `answered_at` が新しい行を優先し、同一時刻なら `id` が大きい行を「後の解答」として扱う。
- `id` は**結果テーブル内の解答順 tie-breaker としてのみ**使用する(`problem_key` の構成には使わない。§4の「行IDを安定キーに使わない」方針と両立する)。
- 適用箇所: weak review 判定(review対象の出入り。listed→top で外れ、top→listed で入る)、`problem_key` ごとの latest status(一覧バッジ)、progress の最新verdict集計、history の最新状態表示、その他「最新結果」に依存するすべての表示。実装では latest 選択を共通クエリ/ヘルパーに集約し、status / progress / review が**同じ latest 行**を参照するようにする。
- `answered_at` のミリ秒精度化は任意の改善案とするが、ミリ秒でも衝突は理論上可能なため **`id DESC` の tie-breaker は必須**とする。

**戦型分類の参照方針(スナップショットと現在分類の分離)**: `next_move_results` の `opening_key_at_answer` / `opening_name_at_answer` は解答時点のスナップショットであり、**分類変更のたびに書き換えない**。進捗・状態・復習・履歴で戦型を表示・集計する際は、backend が現在の next_move.db の問題一覧から構築する **resolver(`problem_key` → 現在の代表 `sample_id` / `opening_key` / `opening_name` のマッピング。リクエスト時に構築、必要ならプロセス内キャッシュ)** を参照する。

**resolver の重複排除と代表 sample の選択**: 複数の `learning_samples` 行が同一 `problem_key` に正規化され得る(同じ name/version/source_url のソースを別 `file_sha256` で再取り込み、手数フィールドのみ異なるSFEN等)。resolver は構築時に **`problem_key` 単位で重複排除**し、進捗の分母(N)・status の対象・一覧・出題(ランダム/未挑戦/weak)・復習のすべてを distinct `problem_key` 基準にする(同一問題の重複表示・重複出題をしない)。同一 `problem_key` に複数 `sample_id` がある場合、画面表示・再挑戦に使う**代表 sample を決定的に1件選ぶ**:

1. 最新の抽出実行を優先(`extraction_runs.extracted_at` 降順。メタデータの無い旧DBでは `book_sources.imported_at` 降順で代替)
2. `sample_rank` 昇順
3. `sample_id` 昇順(最終 tie-breaker。現在DB内での決定性のためだけに使い、永続識別には使わない)

同一 `problem_key` の複数行で現在メタデータ(`opening_key` 等)が競合する場合は、**代表 sample の値を採用**して決定的にし、競合を検出したら backend ログで警告する。`validate_next_move_db.py` にも重複 `problem_key` とメタデータ不整合の検出を追加する。

- progress: 現在の next_move.db の戦型分類で集計する(分類器改良で分類だけ変わった問題は新しい戦型の側に計上される)。
- status: 現在利用可能な問題と `problem_key` で突合する。
- review / history: 現在の問題が存在する場合は現在の戦型分類で表示する。
- **next_move.db から問題が削除されている場合のみ**、解答時スナップショット(`*_at_answer`)へフォールバックして表示する。その際は「現在の問題データには存在しません」等の利用不可状態を付け、復習画面からの再挑戦導線は無効にする。
- 過去の解答レコード自体は分類変更や問題削除で書き換えない。

#### next_move.db(抽出・生成時に更新。アプリ実行時は読み取り専用)

- `extraction_runs` テーブルを追加する(`extraction_run_key`, `extractor_version`, `limit`, `per_opening_limit`, `seed`, `source_file_sha256`, `extracted_at`)。
- `learning_samples` に `extraction_run_key` の参照を追加する。
- 書き込みは**importerおよび抽出・生成ツールによる生成時のみ**(`extract_learning_samples.py` 等が新スキーマを生成する)。アプリ実行時の `mode=ro` 接続は維持し、実行時書き込みは一切行わない。`validate_next_move_db.py` 等の検証処理も読み取り専用とし、既存DBに補完・修復・スキーマ移行を書き込まず、不整合は終了ステータスと診断メッセージで報告する。
- **旧DBの後方互換を維持**する: `extraction_runs` メタデータの無い旧DBでも、`problem_key` の構成要素(`stable_source_key`・`normalized_sfen`・candidate fingerprint)は既存の `book_sources` / `book_moves` から backend が算出できるため **problem_key は完全に算出可能**。旧DBでは監査用の `extraction_run_key` のみ `"unknown"` にフォールバックする(キーには影響しない)。
- `validate_next_move_db.py` を新旧両形式に対応させる(新形式では `extraction_runs` の整合、旧形式では不在を許容。あわせて重複 `problem_key`・メタデータ不整合の検出を追加)。

- **`dataset_version` メタデータ**: 新形式 `next_move.db` では `database_metadata` テーブルを追加し、`key='dataset_version'` の単一レコードとしてDB生成物全体の世代IDを保存する。複数の `extraction_runs` が存在しても、アプリはこの単一値をページングレスポンスへ返す。
  - 生成材料: DB生成完了時に canonical JSON `{schema_version, generated_at, extractor_version, extraction_run_keys, source_file_sha256_values, row_counts}` を作り、`v1:` + SHA-256(UTF-8 bytes) とする。これは `problem_key` とは別目的で、問題の同一性ではなく「現在の next_move.db ファイル全体の生成世代」を表す。
  - アプリ実行時は引き続き `next_move.db` を `mode=ro` で開き、`dataset_version` を読み取るだけで書き込まない。抽出・再生成ツールだけが `database_metadata` を更新する。
  - 旧形式DBに `database_metadata.dataset_version` が無い場合は、DBファイル全体のSHA-256から `v1:sha256-file:<hex>` を算出してフォールバックする。同一ファイルでは安定し、ファイル差し替え時には値が変わるため、ページ途中の旧DB差し替えも検出できる。

この shogi.db 側と next_move.db 生成側の両方を **PR-A に含める**(§8。片方だけ実装してスキーマ不整合になることを避ける)。

### API(新規ルーター `backend/app/routers/next_move.py` を想定)

| メソッド | パス | 用途 | フェーズ |
| --- | --- | --- | --- |
| POST | `/api/next-move/results` | 解答記録。入力は `sample_id`(一時参照)+`problem_key`(表示中の問題の値)+`move_usi`+`hint_count`+`elapsed_ms` の5項目。backend が problem_key を再算出して照合(不一致は 409 `NEXT_MOVE_PROBLEM_CHANGED`)→ SFENから局面を復元して合法性を検証(構文不正 422 `NEXT_MOVE_MOVE_FORMAT_INVALID` / 違法手 422 `NEXT_MOVE_ILLEGAL_MOVE`)→ 合法時のみ候補手から verdict・candidate_rank を算出・保存 | P0-1 |
| GET | `/api/next-move/progress` | 戦型ごとの挑戦数・verdict内訳(分子・分母とも **distinct `problem_key`** 基準。shogi.db の結果 × next_move.db を `problem_key` で突合し、戦型は**現在の分類**で集計) | P0-2 |
| GET | `/api/next-move/status?opening_key=` | `problem_key`→最新verdict のマップ(一覧バッジ用。**distinct な現在の `problem_key`** と突合) | P0-2 |
| GET | `/api/next-move/problems/next?policy=random\|unattempted\|weak&opening_key=&exclude_problem_key=` | 出題ポリシー。処理順: (1) resolver から distinct `problem_key` 単位の候補集合を構築 → (2) `exclude_problem_key` と一致する問題を候補集合から除外 → (3) policy に応じて戦型・問題を選択 → (4) 選択された `problem_key` の代表 sample を返す(レスポンスに `sample_id` と `problem_key` の両方を含む。候補なしは204)。直前問題の除外キーは **`problem_key`**(`sample_id` は画面遷移・解答POSTの一時参照専用で、除外の正式なキーには使わない) | P0-3 / P1-2 / P1-3 |
| GET | `/api/next-move/history` | 履歴用の集計+最近の解答(戦型は現在分類を resolver で解決。削除済み問題は解答時スナップショット+利用不可表示) | P1-1 |
| GET | `/api/next-move/review` | 復習対象(最新が unlisted/listed のサンプル。現在分類で表示し、削除済み問題は再挑戦不可として除外または無効表示) | P1-2 |

補足:

- **URL namespace の方針**: 出題APIは `/api/learning-samples/next` に**しない**。既存の動的ルート `GET /api/learning-samples/{sample_id}` が先にマッチし、ルーター登録順によっては `"next"` を整数として解析しようとして 422 になり、static route に到達できないため。新規の次の一手専用APIは `results` / `progress` / `status` / `review` / `history` と同じ **`/api/next-move/*` namespace に統一**し(`/api/next-move/problems/next`)、動的ルートと衝突せず**ルーター登録順に依存しない**構成にする(OpenAPI 上も動的/静的ルートが曖昧にならない)。
- **URL継続とレスポンス互換は別契約**: 問題一覧は既存URL `GET /api/learning-samples` を継続するが、これはレスポンス形式の後方互換を意味しない。PR-Bで一覧レスポンスを既存の配列からページオブジェクト `{items, offset, limit, total, dataset_version}` へ意図的に変更する。このローカルアプリでは外部公開APIクライアントや独立した外部スクリプトとのレスポンス互換を保証しない。問題詳細 `GET /api/learning-samples/{id}` は既存URLと既存フィールドを維持する。
- 問題一覧・詳細の読み取りと **P0での通常の順次移動(クライアント側の distinct `problem_key` 巡回)** は `/api/learning-samples`、`random` / `unattempted` / `weak` の出題開始・継続(`exclude_problem_key` による直前問題除外を含む)は `/api/next-move/problems/next`、記録・集計は `/api/next-move/*` を使う。通常の順次移動を新APIへ強制統合しない(順次移動のサーバーAPI化は P2-3 で再検討し、行う場合は別PR)。**PR-Bでは新しいページングendpointを追加せず**、既存一覧URLに `offset` / `limit` queryと新レスポンスを導入する。`dataset_version` はレスポンス値であり、version queryは追加しない。
- 既存 `GET /api/learning-samples` / `GET /api/learning-samples/{id}` のレスポンスに `problem_key` を追加する(backend が算出。一覧バッジ・status API との突合に使用)。
- 候補手の返却順を共通の判定用候補正規化規則に統一する。既存の ORDER BY との差分は最終 tie-breaker のみ(`bm.id` → `move_usi`。行IDはDB再生成で変わるため安定キーの順序決定に使わない)。
- **一覧APIのページング(PR-B)**: 既存 `GET /api/learning-samples` に `offset` / `limit` / `total` / `dataset_version` を追加し、レスポンスを次の形にする:

  ```json
  {"items": [...], "offset": 0, "limit": 100, "total": 250, "dataset_version": "v1:..."}
  ```

  - `total` は `learning_samples` の行数ではなく、**現在の resolver における distinct `problem_key` 数**。
  - 各 item には順次移動に必要な `sample_id`・`problem_key`・`opening_key`・`sample_rank`(決定的な並び順情報)を含める。
  - **backend 側の処理順序**: (1) resolver 構築 → (2) `problem_key` 単位で代表 sample へ重複排除 → (3) 決定的順序付け(`sample_rank` 昇順 → `problem_key` 昇順。全ページで一貫)→ (4) `offset` / `limit` 適用 → (5) 同一DB生成物全体の `dataset_version` を付与。DBの生行をページングしてからクライアントで重複排除する方式は**採らない**(同一 `problem_key` の重複行がページ境界をまたぐと、ページ件数と `total` の意味が崩れるため)。

#### API共通レスポンス・エラー契約

- 新規 `/api/next-move/*` のエラー本文は `{"detail": "利用者向け説明", "code": "安定した機械判定コード"}` とする。frontend は分岐に `code`、表示に `detail` を使い、未知の `code` でも一般エラーへフォールバックする。FastAPI標準の入力検証エラーは既存の422形式を維持できるが、上表で定義した業務エラーはこの共通形を返す。
- 正常な作成は200、候補なしは204 (本文なし)。存在しない `sample_id` は404 `NEXT_MOVE_PROBLEM_NOT_FOUND`、表示後に問題定義が変わった場合は409 `NEXT_MOVE_PROBLEM_CHANGED`、USI構文不正は422 `NEXT_MOVE_MOVE_FORMAT_INVALID`、局面上の違法手は422 `NEXT_MOVE_ILLEGAL_MOVE`、問題DBの未配置・不正・空は503 `NEXT_MOVE_DATABASE_UNAVAILABLE` とする。予期しない障害は内部情報を露出せず500とする。
- 409 / 422 / 503、および**トランザクションcommit前**に発生した500では、トランザクションをrollbackし、`next_move_problem_refs` と `next_move_results` をどちらも変更しない。問題参照upsertと解答INSERTは `shogi.db` の単一トランザクションで行い、片方だけを保存しない。
- commit成功後のレスポンス生成、middleware、通信経路で障害が起きた場合、クライアントが500または通信エラーを受け取っても解答は保存済みの可能性がある。frontendは500・通信エラーに対して解答POSTを自動再送しない(結果表示を維持し、記録状態が不明である旨を案内できる)。
- 将来自動再送を導入する場合は、重複記録を防ぐidempotency keyをリクエストと保存処理のAPI契約へ追加してから行う。本設計のP0〜P2にはidempotency keyおよび自動再送を含めない。
- 一覧URLの継続はレスポンス互換を保証しない。PR-Bではbackendの一覧レスポンス変更と、リポジトリ内の全frontend呼び出し元・型・unit test・E2Eの更新を同時に行う。backendだけ、またはfrontendだけが旧形式のまま混在する状態を完成扱いにせず、両方の全テストがgreenの一体変更としてマージする。問題詳細APIは既存URLと既存フィールドを維持する。

### フロントエンド

| ファイル | 変更 | フェーズ |
| --- | --- | --- |
| `src/api/client.ts` | 上記API関数・型(POSTに `problem_key` を含む。出題APIは `/api/next-move/problems/next` を使用し204を「次の問題なし」として返す)、一覧APIの `{items, offset, limit, total, dataset_version}` 型と全ページ取得ヘルパー(offsetループ・AbortSignal対応。`expected_total` / `expected_dataset_version` の固定・各ページの `total` / `dataset_version` 一致確認・`loaded_count == expected_total` かつ世代一致を最終の完了条件とし、空ページ未達・total変化・dataset_version変化・進捗なしを不整合として返す。不整合時は取得済み一覧を破棄し `offset=0` から再取得する)、503 detail・409(`NEXT_MOVE_PROBLEM_CHANGED`)の取り出し | P0 |
| `src/hooks/useNextMoveSession.ts` | 経過時間計測、着手時の記録コールバック(表示中サンプルの `problem_key` を添付) | P0-1 |
| `src/pages/NextMoveStudyPage.tsx` | スキップ・完了状態(通常の順次移動は一覧APIの**全ページ取得**で対象戦型の全 distinct `problem_key` を統合してから、現在の `problem_key` の位置基準で次へ進む。最後の distinct キーでのみ完了表示。`(index+1) % length` と「取得済み配列末尾=最後」の判定を廃止。途中ページ取得失敗・`dataset_version` 不一致時は完了扱いにせず取得済み一覧を破棄して再試行導線。ローディング・二重取得防止・戦型変更時のキャンセル・セッション内キャッシュを考慮)・random/unattempted/weak モードの「次の問題」は新APIを使用(表示中の `problem_key` を `exclude_problem_key` として送信し、204は完了表示)・進捗ラベル修正・DB異常詳細表示・409時の「問題データが更新されました。再読み込みしてください」表示(結果表示は維持) | P0-1〜P0-5 |
| `src/components/NextMoveProblemList.tsx` | 進捗サマリー・バッジ・出題ボタン・件数注記・h2、DB異常詳細表示 | P0-2/3/5 |
| `src/components/NextMoveResultPanel.tsx` | 用語ヘルプ | P1-4 |
| `src/pages/HistoryPage.tsx` | 次の一手セクション | P1-1 |
| `src/pages/ReviewPage.tsx` | 次の一手タブ | P1-2 |
| `src/shogi/nextMove.ts` | 判定用候補順序を共通規則(共通の判定用候補正規化規則)に合わせる、verdict→バッジ表示のマッピング等の純関数追加 | P0-1 / P0-2 |
| `src/index.css` | バッジ・サマリー・完了メッセージのスタイル(360px確認込み) | 各PR |

### テスト

- `backend/tests/test_next_move_results.py`(新規)、`test_api.py` / `test_next_move_database.py` への追記
- `frontend/src/shogi/nextMove.test.ts`、`src/api/client.test.ts` への追記
- `frontend/e2e/next-move.spec.ts` への追記(モックに POST/status/progress を追加)

### ドキュメント

- `README.md` — 使い方・API一覧・「既知の制限」の更新(ランダム/進捗対応後に制限記述を削除)
- `README.md` の**安定キー方針の更新**: 現在は「出典、正規化SFEN、対象手、生成条件から作る安定キー」と記載されているが、次の一手は単一の対象手ではなく複数候補と順位を持ち、また抽出実行条件をキーに含めると件数・seed変更だけで履歴が失われる。本計画に合わせて「**出典・正規化SFEN・候補手定義(または対象手)・問題定義バージョン**から作り、**抽出実行条件は問題キーとは分離**して監査メタデータとする」方針へ更新する(PR-Aに含める)。

---

## 7. テスト計画

### バックエンド(pytest)

- `next_move_results` の記録: `sample_id`+`problem_key`+`move_usi` から backend が候補手を参照して verdict・candidate_rank を算出すること(top/strong/listed/unlisted の各ケース。フロント `judgeNextMove` と同一の `effective_rank` 規則であることを共通fixtureで担保)、同一問題への複数記録、存在しない `sample_id` は404。
- **problem_key 照合(DB差し替え競合)**:
  - (a) 問題表示相当のレスポンスを取得後、next_move.db を**同じ `sample_id` が別問題を指す内容**に差し替えるfixtureを作る。
  - (b) その状態でPOSTすると、クライアント送信の `problem_key` と backend 再算出値が不一致になる。
  - (c) 409(`NEXT_MOVE_PROBLEM_CHANGED`)が返り、`next_move_results` にも `next_move_problem_refs` にも1行も保存されない。
  - (d) `problem_key` が一致する通常ケースでは正常に保存される。
  - (e) 問題表示後に、**同順位候補の top 順だけが変わった**(score/depth 更新で判定順が入れ替わった)DB へ差し替えた場合も、fingerprint の差により `problem_key` 照合が409となり履歴が保存されない。
- `problem_key` の導出:
  - (a) `limit`・`per_opening_limit`・`seed` を変更して再抽出しても、同じ問題(同一出典・同一正規化局面・同一候補手定義)の `problem_key` が一致する。
  - (b) ソースファイルの**無関係な局面だけ**が変更(追加・削除・修正)されても、対象問題の `problem_key` は一致する(`file_sha256` がキーに影響しないこと)。
  - (c) 対象局面の**候補手・候補順位・判定順のいずれかが変わる**と `problem_key` が変わる(fingerprint 検出)。判定順に影響しない変更ではキーが変わらない。特に以下を検証する:
    - 同じ `move_usi` 配列・同じ並びでも、`effective_rank` が変わる(例: `sort_order` の変更で 3→4)と fingerprint と `problem_key` が変わる。
    - 同じ `effective_rank` の候補が複数ある場合、共通の判定用候補正規化規則によって判定順が決定的になる(score降順→depth降順→move_usi昇順。NULL は非NULLの後)。
    - **score または depth の変更で同順位候補の順序が入れ替わる**と、`judgment_position` の対応が変わり fingerprint と `problem_key` が変わる。
    - score / depth が変わっても**候補順が変わらなければ** fingerprint は変わらない。
    - DB の行ID・挿入順が変わっても、同じ候補定義・同じ判定順なら fingerprint は一致する。
    - API の候補返却順、frontend 判定、backend の verdict/candidate_rank 算出、fingerprint の `judgment_position` が**同一の共通関数規則**で一致することを、同一fixtureで検証する(top の一致を含む)。
  - (d) **異なる出典に同一SFENが含まれる場合はキーが異なる**(`stable_source_key` の分離)。
  - (e) 手数フィールドの違いや持ち駒順・空白などの表記ゆれは正規化され、キーが一致する。
  - (f) `problem_definition_version` を変えるとキーが変わる。
  - (g) `extraction_run_key` は抽出条件(limit/seed 等)の変更で変わる(監査メタデータとしての検証。problem_key には影響しない)。
  - (h) `extraction_runs` メタデータの無い旧DBでも `problem_key` は算出でき、`extraction_run_key` のみ `"unknown"` にフォールバックする。
- canonical serialization(共通シリアライズ関数):
  - `(name="ab", version="c")` と `(name="a", version="bc")` で `stable_source_key` が異なる(連結曖昧性の排除)。
  - `null` と空文字で生成されるキーが異なる。
  - JSONオブジェクトへの値の挿入順が異なっても同じキーになる(キー辞書順の固定)。
  - 日本語などの Unicode 文字を含んでも決定的なキーになる(NFC 正規化の固定)。
  - Python プロセスの実行を繰り返しても同じ `problem_key` になる(ハッシュランダム化等に非依存)。
  - 固定入力に対する **golden test**(期待する `problem_key` 文字列そのものを検証)を設け、シリアライズ仕様の意図しない変更を検出する。
- `progress` / `status`: 記録なし→全て未挑戦、記録後の集計、next_move.db 差し替え(同一の問題定義)後も `problem_key` 経由で進捗が残ること。`next_move_problem_refs` が POST 時に upsert されること。
- 最新解答の決定的順序(`answered_at DESC, id DESC`)。**「解答の挿入順による正しい結果の変化」と「SELECT返却順・クエリプランへの非依存」を別テストとして分離**する(挿入順を変えれば id の大小も変わり latest が変わるのが正しい仕様なので、「挿入順を変えても同じ latest」という検証はしない):
  - 解答の挿入順を検証するテスト(挿入順が変われば結果も正しく変わる):
    - 同一 `answered_at` で **listed→top の順に INSERT** すると top の `id` が大きくなり、top が latest となって review 対象から外れる。
    - 別テストとして、同一 `answered_at` で **top→listed の順に INSERT** すると listed の `id` が大きくなり、listed が latest となって review 対象に入る。
    - この2ケースで latest が異なることが正しい仕様である。
  - SQL返却順・クエリプラン非依存のテスト(**解答の挿入順と id は固定したまま**検証する):
    - fixture 作成後の物理的な取得順に依存しない。明示的な ORDER BY を持たない内部取得順を信用しない。
    - インデックスの有無や別のクエリ形(サブクエリ/ウィンドウ関数)に変えても、正式な latest ヘルパーは**同じ result id** を返す。
    - status / progress / review が**同じ latest result id** を参照する(共通ヘルパー経由。3つのAPIで一致することを同一fixtureで確認)。
    - Python 側の入力配列順を変えても、DBクエリの正式順序による結果は変わらない。
  - `answered_at` が異なる場合は時刻順が優先される。
- 戦型分類の参照(スナップショットと現在分類の分離):
  - 同一 `problem_key` の `opening_key` だけを変更した next_move.db に差し替えても、過去の解答履歴は保持される。
  - その差し替え後、progress と history の表示グループは**新しい `opening_key`** の側へ移る。
  - `next_move_results` の解答時スナップショット(`opening_key_at_answer` / `opening_name_at_answer`)は書き換えられない。
  - 現在の next_move.db から問題が削除された場合、history は解答時スナップショット+利用不可状態で表示する(フォールバック)。
  - 削除済み問題が復習画面から誤って挑戦可能にならない(除外または導線無効)。
- 重複 `problem_key` の扱い(distinct 基準の担保):
  - 複数の `learning_samples` 行が同一 `problem_key` に正規化される fixture を用意する(別 `file_sha256` での再取り込み・手数フィールドのみ異なるSFEN)。
  - progress の N が行数ではなく **distinct `problem_key` 数**になる。
  - 1つの `problem_key` を解答すると n がちょうど1増える。
  - 重複行があっても進捗が **100% に到達できる**。
  - 一覧・ランダム出題・未挑戦優先・復習で同一 `problem_key` が重複表示・重複出題されない。
  - 代表 sample の選択が DB の行順・挿入順に依存せず決定的である(選択規則: 最新抽出実行 → `sample_rank` 昇順 → `sample_id` 昇順)。
  - 同一 `problem_key` 内で現在メタデータ(`opening_key` 等)が競合する fixture で、表示が決定的(代表 sample の値)になり、`validate_next_move_db.py` が警告を出す。
- 一覧APIのページングとPR-Bの移行契約(backend / repository内client):
  - `GET /api/learning-samples` のURLは変えず、backendのレスポンスが配列から `{items, offset, limit, total, dataset_version}` のページオブジェクトへ変わる。
  - 新しいページングendpointおよびversion queryを追加しない。`dataset_version` はレスポンスで返す。
  - リポジトリ内検索と型チェックにより、旧配列レスポンスを前提とするfrontend呼び出し元・型・unit test・E2Eが残っていないことを確認する。
  - frontendの型、画面、unit test、E2Eをbackend変更と同じPR-Bで新形式へ更新し、PR-B完了時にbackend・frontendの全テストをgreenにする。片側だけの移行は完了としない。
  - `GET /api/learning-samples/{sample_id}` は既存URLと問題詳細の既存フィールドを維持し、既存の詳細APIテストを変更後も通す。
  - `total` が `learning_samples` 行数ではなく distinct `problem_key` 数になる。
  - 同一DBの複数ページで `dataset_version` が一致し、DB再生成時には `database_metadata.dataset_version` が変わる。
  - 旧形式DBではファイルSHA-256 fallbackが同一ファイルで安定し、旧DB差し替え時に変化する。
  - アプリ実行時に `next_move.db` へ書き込まず、`mode=ro` のまま `dataset_version` を返す。
  - backend で「resolver構築→重複排除→決定的順序付け(`sample_rank` 昇順→`problem_key` 昇順)→offset/limit適用」の順で処理される(重複排除後にページングされることを、重複行がページ境界付近にある fixture で検証。ページ件数と `total` が整合し、全ページを通して `problem_key` の欠落・重複がない)。
  - distinct `problem_key` が250件の場合、`offset=0/100/200` の3ページで全件取得でき、全ページで順序が一貫する。
- next_move.db のスキーマ形式(新旧両対応):
  - 新形式DBで `extraction_runs` と `learning_samples.extraction_run_key` の参照が機能する。
  - 旧形式DB(メタデータ無し)では `extraction_run_key` が `"unknown"` にフォールバックする。
  - アプリ実行中に next_move.db への書き込みが一切発生しない(`mode=ro` の担保)。
  - 抽出ツール(`extract_learning_samples.py`)が新スキーマを生成する。
  - `validate_next_move_db.py` が新旧形式を読み取り専用で判定し、それぞれで検証が通る。検証前後でDBファイルのSHA-256と内容が変化せず、不整合時にも補完・修復・スキーマ移行を書き込まない。
- `move_usi` の合法性検証(422系):
  - USI 構文が不正な手は 422(`NEXT_MOVE_MOVE_FORMAT_INVALID`)となり、`next_move_results`・`next_move_problem_refs` のどちらにも書き込まれない。
  - 空きマスからの移動など局面上の違法手は 422(`NEXT_MOVE_ILLEGAL_MOVE`)となる。
  - 手番と異なる側の駒を動かす手は 422 となる。
  - 不正な駒打ち(持っていない駒・打てないマス)は 422 となる。
  - 成り規則に反する手(成れない位置での成り・強制成りの無視)は 422 となる。
  - 合法だが候補一覧にない手は従来どおり `unlisted` として保存される。
  - 合法な候補手は従来どおり保存される。
  - `problem_key` 不一致の場合は**合法性検証より先に** 409 となる。
- 出題APIのルーティング(`/api/next-move/problems/next`):
  - 新しい static endpoint への GET が 200(正常)または 204(候補なし)になる。
  - `/api/learning-samples/next` へ誤ってアクセスしても新APIとして扱われない(既存の動的ルートの解釈のまま=422等。新エンドポイントに転送しない)。
  - 既存の `GET /api/learning-samples/{sample_id}`(問題詳細)が壊れない。
  - `main.py` のルーター登録順(include順)を入れ替えても、専用 namespace の出題APIが正常に動作する。
  - OpenAPI schema に新しい next-move エンドポイントが期待どおり登録され、動的ルートと曖昧にならない。
- `next?policy=`: seeded RNG を注入した決定的テスト。分離した選択関数(`choose_opening` / `choose_problem`)の単体テストで各戦型の均等重みを検証する(確率的な閾値判定は用いない。§5 P1-3 参照)。unattempted(全問挑戦済み時の挙動)、weak(unlisted/listedのみ)も同様に決定的に検証。seeded RNG テストも **distinct `problem_key` 単位・除外後の候補集合**の上で行う。
- `exclude_problem_key` の除外(problem_key 基準):
  - 同一 `problem_key` に異なる `sample_id` が複数ある fixture を用意する。
  - `exclude_problem_key` 指定時に、その `problem_key` に属する**全 sample 行**が候補から除外される(表示中が非代表 sample でも、代表 sample が同一問題として再出題されない — sample_id 基準の除外では防げないケースを、設計変更後は発生させない)。
  - DB差し替えで同じ問題の `sample_id` が変わっても、`problem_key` が同じなら除外される。
  - distinct 候補が2件以上なら必ず別の `problem_key` が返る。
  - distinct 候補が1件のみで除外により0件になる場合、仕様どおり 204(「次の問題なし」)を返す。
  - `exclude_problem_key` が現在DBに存在しない場合・形式不正の場合は通常選択になる(不正形式は警告ログ)。
  - 一覧・未挑戦優先・weak・復習でも同一 `problem_key` が重複しない(既存の重複排除テストと合わせて確認)。
- **next_move.db 不在時**: 出題系・`POST /api/next-move/results` は503を返し(verdict算出に候補手参照が必要なため)、shogi.db のみで完結する集計系(`history` 等)は動作すること。既存の `test_next_move_database.py` の検証(欠落テーブル・カラム・0件)を維持。

### フロントエンド(vitest)

- バッジ/進捗表示の純関数、ポリシー付き「次の問題」選択ロジック、経過時間の丸め。
- `judgeNextMove` が判定用候補順序の共通規則(同順位は score降順→depth降順→move_usi昇順、NULLは後)に従うこと(backend側テストと同一の共通fixtureを使用)。
- `client.ts`: 503 detail の抽出、409(`NEXT_MOVE_PROBLEM_CHANGED`)の構造化エラーの取り出し、記録API失敗時に例外を伝播させないこと。500・通信エラー時に解答POSTを自動再送せず、保存済みか不明な状態として扱うこと。
- 全ページ取得ヘルパーの終了条件(モックレスポンスで決定的に検証):
  - `total=101`、同一 `dataset_version` の1ページ目100件+2ページ目1件 → 正常完了(`loaded_count == expected_total` かつ世代一致)。
  - `total=101`、1ページ目100件+2ページ目が**空配列** → 失敗扱い(空ページを正常終了にしない。100件目を完了扱いしない)。
  - 途中ページの `total` が 101→100 に変わった場合、および 101→102 に変わった場合 → どちらも不整合として再取得要求。
  - `total` が同じ別DBへページ途中で差し替えられた場合でも `dataset_version` 不一致で検出し、世代Aの1ページ目と世代Bの2ページ目を成功扱いしない。
  - `loaded_count == total` に到達していても `dataset_version` が不一致なら失敗扱いにする。
  - 不一致時は取得済み一覧を破棄し、再試行は `offset=0` から開始する。再取得後は単一世代のページだけで完了する。
  - 新しいページを取得しても新規 `problem_key` が増えない場合 → 無限ループせず失敗として停止。
  - 再試行時は `offset=0` から取得し直し、成功後に101件目へ進める。
  - 取得完了判定が offset ではなく `loaded_count == expected_total` と `dataset_version` 一致を最終条件としていること。

### E2E(Playwright)— 既存アサーションは全て維持

- 着手→ `POST /api/next-move/results` が期待ペイロード(`sample_id`・`problem_key`・`move_usi`・`hint_count`・`elapsed_ms`)で発火(route captureで検証)。
- 記録APIが409(`NEXT_MOVE_PROBLEM_CHANGED`)を返すケース(モック): 「問題データが更新されました。再読み込みしてください」等の案内が表示され、かつ盤面上の解答結果表示は維持されること。
- 通常UI(盤面)からは合法手しか送信されない既存仕様の維持(盤面は合法手のみ着手可能という既存E2Eのアサーションを保持。422系は backend APIテストで担保し、E2Eでは通常フローに422が現れないことを前提とする)。
- 一覧: バッジ表示・進捗サマリー・「ランダムに1問」で挑戦画面へ遷移。
- スキップ: 着手前スキップ→次問題→見出しフォーカス(キーボードのみでも)。
- 通常の順次移動(モックで distinct `problem_key` が3件の戦型を用意):
  - 1→2→3 の順に移動し、同じ `problem_key` を2回通らない(重複 sample 行があっても)。
  - 最後の3件目では先頭へループせず、決定的に完了表示(「この戦型の問題を最後まで学習しました」+導線)になる(最終問題E2Eとして固定的に検証)。
  - distinct 候補が1件のみの戦型では解答後に完了表示となる。
  - 通常の順次移動では `/api/next-move/problems/next` を呼ばない(route capture で確認)。random / unattempted / weak の操作は新APIを経由する。
  - 既存のキーボード操作・見出しフォーカス移動のアサーションを維持する。
- 100件超の順次移動(モックで distinct `problem_key` が101件の戦型を用意。ページサイズ100):
  - 100件目で完了表示にならず、101件目へ進める(2ページ目が取得される)。
  - 101件目でのみ完了表示になる(最終問題E2Eを101件fixtureでも確認)。
  - 2ページ目の取得が失敗した場合、100件目を完了扱いにせず、「次の問題一覧を最後まで取得できませんでした」+再試行導線が表示される。再試行(`offset=0` から)成功後は101件目へ進める。
  - 2ページ目が**空配列**を返した場合(DB差し替え相当のモック)も、100件目を完了扱いにせず、「問題データが更新されたため、一覧を再取得してください」等の再取得導線が表示される。
  - 戦型を切り替えた際、進行中だった古いページ取得の結果が新しい戦型の一覧に混入しない。
  - 100件以下の既存ケース(1ページで完結)も従来どおり動作する。
- 完了: 最終問題の解答後に完了メッセージ。
- DB異常: 503 detail 別の文言表示(モック)。
- 既存の維持対象: キーボード操作一式、360px横スクロールなし(バッジ・サマリー追加後に再確認)、答えの漏洩なし(着手前に候補手/評価値/PV非表示)、ナビの `aria-current`、旧URLリダイレクト。

---

## 8. PR構成(実装フェーズ)

依存関係順。各PRは単独でテスト green を維持する。P2はどのP0/P1 PRの開始・完了もブロックしない。

| PR | 開始条件 | 完了ゲート |
| --- | --- | --- |
| A | 本設計の承認 | problem key、DB新旧互換、競合・合法性・原子的保存のbackend/frontend/E2E受け入れ条件がgreen |
| B | Aマージ | 一覧URLを維持したページオブジェクト移行、全repository内client・型・unit/E2Eの同時更新、詳細API互換、distinct集計・同一世代ページングを含むbackend/frontend全テストがgreen |
| C | A・Bマージ | random/unattempted、スキップ、順次完了、途中取得失敗・世代変更の再試行テストがgreen |
| D | 本設計の承認 (A〜Cと並行可。競合時はrebase) | 503原因別案内、復旧導線、着手後だけの用語説明、a11yテストがgreen |
| E | A〜Cマージ | 履歴・復習・weak・均等出題、削除済み問題と分類変更の整合性テストがgreen |
| F以降 | 対応するP0/P1と必要性の確認 | 各PRで独立した仕様・性能・a11y受け入れ条件を定義。未実施でもP0/P1は完了可能 |

1. **PR-A: 解答記録の基盤**(P0-1)
   - `problem_key` の定義・算出(stable_source_key・normalized_sfen・candidate_definition_fingerprint・problem_definition_version)、**canonical serialization 共通関数**(キー辞書順・UTF-8・NFC・null/空文字区別。golden test 付き)、判定用候補正規化規則(API返却順・frontend判定・backend判定・fingerprint で同一規則。APIの最終 tie-breaker を `bm.id`→`move_usi` に変更)、抽出ツール側の `extraction_runs` メタデータ保存(`extract_learning_samples.py` / `validate_next_move_db.py` 対応)。
   - **shogi.db 側と next_move.db 生成側の両方を本PRに含める**: shogi.db スキーマ追加(`next_move_problem_refs` + `next_move_results` + latest検索用インデックス)と、next_move.db 生成スキーマの更新(`extraction_runs` + `learning_samples.extraction_run_key` + `database_metadata.dataset_version`。旧DB後方互換・旧形式DBのファイルSHA-256 fallback・validate 新旧対応込み)。最新解答選択(`answered_at DESC, id DESC`)の共通クエリ/ヘルパーもここで定義し、後続PR(B/E)の status・progress・review はこれを使う。`POST /api/next-move/results`(`problem_key` 照合 409 → SFEN復元による `move_usi` 合法性検証 422 → 合法時のみ backend で verdict・candidate_rank を算出・保存)、learning-samples レスポンスへの `problem_key` 追加、セッションでの自動記録と409時の再読み込み案内(UI変更は最小)。
   - README の安定キー方針の更新(下記ドキュメント欄参照)。
   - backend/frontend/E2E テスト(problem_key 安定性・fingerprint 検出・DB差し替え409を含む)。ここが全ての土台。
2. **PR-B: 進捗表示と一覧の改善**(P0-2、P1-5の見出し階層)
   - `progress`/`status` API と分類 resolver(`problem_key`→現在の代表 sample_id / opening_key / opening_name。**distinct `problem_key` 基準**の集計・重複排除・代表 sample の決定的選択)、**既存一覧URLのページオブジェクト移行**(`offset`/`limit`/`total`/`dataset_version`。新endpoint・version queryは追加しない。backendで重複排除→順序付け→ページング)、リポジトリ内の全frontend呼び出し元・型・unit test・E2Eの同時更新、問題詳細URL・既存フィールドの維持、一覧バッジ・サマリー・件数注記、挑戦画面の「X / Y」修正。backend/frontendの全テストgreenを一体の完了条件とする。
3. **PR-C: 出題ポリシーとスキップ**(P0-3、P0-4)
   - 出題API `GET /api/next-move/problems/next`(次の一手専用 namespace。既存の動的ルート `/api/learning-samples/{sample_id}` と衝突せず登録順に非依存。distinct `problem_key` 候補集合+`exclude_problem_key` 除外+候補なし時の204)は **PR-Cでは random / unattempted、PR-Eで追加する weak の出題開始・継続に使用**。**通常の「次の問題」(順次移動)はクライアント側巡回を維持**し、**PR-Bのページング(`offset`/`limit`/`total`/`dataset_version`)に依存して全ページ取得**で対象戦型の全 distinct `problem_key` を統合してから、現在キー位置基準の前進・最終 distinct キーでの完了表示に改める(`(index+1) % length` と「取得済み配列末尾=最後」の判定を廃止。途中失敗・世代不一致時は完了扱いにせず取得済み一覧を破棄して再試行導線)。ランダム/未挑戦優先ボタン、スキップ、完了状態(204時・最終問題到達時の表示)。frontend(`client.ts`)は random 系で新URLを使用し、表示中の `problem_key` を送る。E2Eは順次移動の完了到達(101件fixture含む)と、random 系操作が新URLを経由することを確認。READMEの「既知の制限」更新。
4. **PR-D: DB異常案内と用語説明**(P0-5、P1-4)
   - 503 detail 表示+復旧手順、評価値/PVヘルプ。小さく独立しているためA〜Cと並行可能(P0-5のみ先行切り出しも可)。
5. **PR-E: 履歴・復習統合**(P1-1、P1-2、P1-3)
   - 履歴セクション、復習タブ(現在分類での表示、削除済み問題のフォールバック表示と再挑戦無効化)、weak/均等ポリシー。PR-A〜Cに依存。
6. **PR-F以降(P2)**: お気に入り → ページング/絞り込み → PV再生 → ミニ盤プレビュー。それぞれ独立PR。

---

## 9. 実装すべきでない・後回しにすべき項目

**実装しない(方針として明確に否定):**

- **アカウント機能・クラウド同期・外部サービス連携**: ローカルWebアプリの範囲を超える。全データは shogi.db に保存し、バックアップはファイルコピーで足りる。
- **next_move.db への実行時書き込み**: 読み取り専用+差し替え可能という PR #32 の設計を崩さない。ユーザーデータは通常DBへ。
- **評価値の優劣解釈(「有利」「悪手」等)の付与**: 出典データの基準・単位が不定という現行の慎重な設計(絶対差のみ表示)を維持する。エンジンによる局面解析(候補外の手の評価)も同理由+構成の大型化のため対象外。
- **learning_samples.id をキーにした記録**: 再抽出でidが変わるため、永続キーにはしない。POST時の一時参照としてのみ使い、永続キーは出典を含む正規化済み `problem_key` 方式を採る(§4冒頭)。SFEN(+opening_key)のみのキーも、出典間で別問題を同一視するため採らない。
- **クライアント申告の verdict / candidate_rank の保存**: 判定は backend が候補手を確認して算出する(改ざん・フロント/バックの判定不一致の混入を防ぐ)。

**後回し(P2以降 or 利用状況を見てから):**

- 本格的な間隔反復(SRS)アルゴリズム: まず「未挑戦優先」「weak再出題」の単純ポリシーで十分。効果が見えてから検討。
- テキスト検索: 問題に検索可能なテキスト属性がほぼ無く、戦型フィルタで代替できる。
- 一覧のミニ盤サムネイル・PV盤面再生: 価値はあるが描画コストと実装量が大きい。
- 定跡学習(固定データ)のDB化や次の一手との内部統合: 別テーマとして切り離す。


---

## 10. 文書自己レビュー結果

- 正本は本ファイルだけとし、分割文書やREADMEへの設計複製は作らない。将来の分割は文量が保守を妨げた場合の非ブロッカー候補に留める。
- 現行backend・frontend・DB生成/検証処理・README・pytest/vitest/Playwright構成と照合し、現行との差は§1、採用設計は§4〜§6、担当PRは§8、テスト可能な条件は§5・§7に対応付けた。
- `shogi.db` / `next_move.db`、`problem_key` / `sample_id` / `dataset_version`、現在分類 / 解答時スナップショット、APIページング / P2の一覧UIページングの役割を分離した。
- DB差し替え、重複行、同時刻解答、途中ページの世代変更、違法手、削除済み問題について、誤結合または部分書き込みを防ぐ契約とテストを記載した。検証処理はread-onlyとし、500はcommit前のrollback保証とcommit後の保存済み可能性を区別した。
- 内部名やSQL・React構成は固定せず、P2と任意最適化をP0/P1のブロッカーから除外した。
- この設計PRではアプリケーションコード、テスト、DB、生成・検証スクリプト、依存関係、CI、設定を変更しない。
