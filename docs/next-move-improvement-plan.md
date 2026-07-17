# 「次の一手」UX/UIレビューと次期改善計画

対象: PR #30(次の一手学習モード追加)、PR #31(独立機能化)、PR #32(専用SQLite DB導入)後のコードベース
(基準ブランチ `claude/clever-hopper-bphezm`、2026-07 時点)

本ドキュメントはコード変更を伴わない調査・計画であり、実装は後続PRで行う。

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
- `candidate_definition_fingerprint`: その局面に登録されている候補手と、**判定に実際に使う候補順序**を局面単位でハッシュ化した値。前提として、候補の順序決定を共通関数 **`canonicalize_candidates_for_judgment(candidates)`** に一元化し、(1) API の候補返却順、(2) frontend の `judgeNextMove`、(3) backend の verdict / candidate_rank 算出、(4) fingerprint、(5) テスト、のすべてで同一実装(同一規則)を使う。

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
| P2-2 | 問題一覧の検索・絞り込み・ページング | 一覧の「さらに表示」(offset)、状態(未挑戦のみ等)での絞り込み。テキスト検索は問題にテキスト属性がほぼ無いため保留 |
| P2-3 | 戦型内の順次出題の明示化 | P0-3のポリシーに `sequential` を追加し、一覧に出題モード切替UI(順番/ランダム/未挑戦優先)を明示 |
| P2-4 | 候補手比較の強化 | 比較テーブル行クリックでPVを盤面再生(ミニ盤 or 既存盤の閲覧モード) |
| P2-5 | 一覧カードの局面プレビュー | ミニ盤サムネイル(答えは漏れない=局面自体が問題)。件数が多いと描画コストがあるため遅延描画前提 |

分類の補足:

- 「戦型内の順次出題」は現状の「次の問題」が実質これなので、新規実装ではなく **P0-4 の完了処理と P2-3 のモード明示化** に分解した。
- 「解答後の候補手比較」は実装済み。強化(PV再生)のみ P2-4 とした。

---

## 5. 各項目の受け入れ条件

### P0-1 解答記録

- 挑戦画面で合法手を指すと `POST /api/next-move/results` が1回呼ばれる。クライアントが送るのは `sample_id`(**一時参照**)・`problem_key`(**問題取得APIが返した値**)・`move_usi`・`hint_count`・`elapsed_ms` の5項目のみ。
- **verdict と candidate_rank は backend 側で算出する**: backend は `sample_id` から next_move.db の現在の問題・候補手・出典メタデータを読み、`problem_key` を再算出する。**クライアントが送った `problem_key` と再算出値が一致した場合のみ**、`canonicalize_candidates_for_judgment` の結果順で `move_usi` を突き合わせて verdict・candidate_rank・judgment_position を確定し保存する。クライアント申告の判定は信用しない(フロントの判定ロジックは即時表示専用とし、候補順序・順位規則は backend と同一の共通関数規則であることをテストで担保する)。
- **同順位候補がある場合の判定の意味**(candidate_rank と judgment_position の分離):
  - `judgment_position` = `canonicalize_candidates_for_judgment` の結果順の位置(1始まり)。**top は judgment_position = 1 の候補**(現行 `judgeNextMove` の「先頭候補 = top」と同じ)。
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
- 各カードに最新解答に基づくバッジ(未挑戦/◎最有力/○有力/△登録候補/?未登録)が表示され、`aria-label` で読み上げ可能。
- 挑戦画面の「問題 X / Y」が戦型の distinct `problem_key` 数と一致する(100件超でも正しい)。
- 一覧が30件で切れる場合、「全N問中30問を表示」の注記が出る。

### P0-3 ランダム出題・未挑戦優先

- 一覧に「ランダムに1問」「未挑戦から1問」ボタンがあり、押すと該当問題の挑戦画面へ遷移する。
- 未挑戦問題が無い場合はその旨を表示し、ランダム出題へフォールバックできる。
- 解答後の「次の問題」は現在の出題ポリシーを引き継ぐ(ランダムで来たら次もランダム)。
- **同一問題が連続して出ない(直前問題の除外は `problem_key` 基準)**: frontend は表示中の問題の `problem_key` を `exclude_problem_key` として送り、backend は distinct `problem_key` 単位の候補集合からそのキーを除外してから選択する。`exclude_id`(sample_id基準)は正式な除外契約に**しない** — 同一 `problem_key` に複数 `sample_id` がある場合(例: 表示中が sample_id=10、代表が sample_id=20)や、DB差し替えで同じ問題の `sample_id` が変わった場合に、ID除外では同一問題が再出題されてしまうため。
  - 直前問題の `problem_key` が次回の候補集合から除外される。同一 `problem_key` に複数 `sample_id` があっても、またDB差し替えで `sample_id` が変わっても、同一問題は再出題されない。
  - distinct 候補が2件以上なら必ず別の `problem_key` が返る。
  - **distinct 候補が1件のみで、除外すると0件になる場合は「次の問題がありません」として 204 を返す**(同じ問題を返し直すより、完了・他戦型への導線を示す既存UX(P0-4の完了メッセージ)と整合するため)。frontend は完了状態の表示に切り替える。
  - `exclude_problem_key` が現在DBに存在しないキーの場合は、除外対象なしとして通常どおり選択する。
  - 形式が不正な `problem_key`(`v1:` プレフィックス無し等)も「存在しないキー」と同じ扱いで通常選択し、backend ログに警告を残す(GETの利便性を優先し、エラーにはしない)。
  - `policy=random`(戦型指定あり/全戦型)・`unattempted`・`weak` のすべてで共通して `problem_key` 単位の除外を行う。

### P0-4 スキップと完了

- 着手前に「スキップして次へ」が表示され、押すと記録なしで次の問題へ遷移し、見出しへフォーカスが移る。
- 順次モードで最後の問題を終えると「この戦型を一巡しました」メッセージと、他戦型・復習・一覧への導線が表示される(無限巡回しない)。
- キーボードのみでスキップ→次問題まで操作できる。

### P0-5 DB異常時の案内

- 未配置・スキーマ不正・サンプル0件のそれぞれで異なる説明が表示される(backend detail を反映)。
- 画面に復旧手順(READMEの該当セクション名、importer/抽出/検証コマンドの要点)が表示される。
- 503以外のエラー(ネットワーク等)は従来どおり一般エラーとして表示される。

### P1-1 履歴統合

- 履歴ページに「次の一手」セクションが追加され、総解答数・verdict別内訳・最有力率・最近の解答(日時/戦型/手/判定)が表示される。
- 表示する戦型は resolver による**現在の分類**。現在の next_move.db に存在しない問題のみ解答時スナップショットで表示し、「現在の問題データには存在しません」等の状態を付ける。
- 既存の詰め将棋・タイムアタックの表示に影響がない(既存E2Eが通る)。

### P1-2 復習統合(再出題)

- 復習ページに「次の一手」タブが追加され、最新解答が unlisted または listed の問題が一覧表示される。戦型は現在の分類で表示する。
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
CREATE INDEX IF NOT EXISTS idx_next_move_results_key ON next_move_results(problem_key);
CREATE INDEX IF NOT EXISTS idx_next_move_results_answered ON next_move_results(answered_at);
-- P2-1 で追加: next_move_favorites(problem_key UNIQUE REFERENCES next_move_problem_refs, created_at)
```

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
- 書き込みは**抽出ツールによる生成時のみ**(`extract_learning_samples.py` が新スキーマを生成する)。アプリ実行時の `mode=ro` 接続は維持し、実行時書き込みは一切行わない。
- **旧DBの後方互換を維持**する: `extraction_runs` メタデータの無い旧DBでも、`problem_key` の構成要素(`stable_source_key`・`normalized_sfen`・candidate fingerprint)は既存の `book_sources` / `book_moves` から backend が算出できるため **problem_key は完全に算出可能**。旧DBでは監査用の `extraction_run_key` のみ `"unknown"` にフォールバックする(キーには影響しない)。
- `validate_next_move_db.py` を新旧両形式に対応させる(新形式では `extraction_runs` の整合、旧形式では不在を許容。あわせて重複 `problem_key`・メタデータ不整合の検出を追加)。

この shogi.db 側と next_move.db 生成側の両方を **PR-A に含める**(§8。片方だけ実装してスキーマ不整合になることを避ける)。

### API(新規ルーター `backend/app/routers/next_move.py` を想定)

| メソッド | パス | 用途 | フェーズ |
| --- | --- | --- | --- |
| POST | `/api/next-move/results` | 解答記録。入力は `sample_id`(一時参照)+`problem_key`(表示中の問題の値)+`move_usi`+`hint_count`+`elapsed_ms` の5項目。backend が problem_key を再算出して照合(不一致は 409 `NEXT_MOVE_PROBLEM_CHANGED`)→ SFENから局面を復元して合法性を検証(構文不正 422 `NEXT_MOVE_MOVE_FORMAT_INVALID` / 違法手 422 `NEXT_MOVE_ILLEGAL_MOVE`)→ 合法時のみ候補手から verdict・candidate_rank を算出・保存 | P0-1 |
| GET | `/api/next-move/progress` | 戦型ごとの挑戦数・verdict内訳(分子・分母とも **distinct `problem_key`** 基準。shogi.db の結果 × next_move.db を `problem_key` で突合し、戦型は**現在の分類**で集計) | P0-2 |
| GET | `/api/next-move/status?opening_key=` | `problem_key`→最新verdict のマップ(一覧バッジ用。**distinct な現在の `problem_key`** と突合) | P0-2 |
| GET | `/api/learning-samples/next?policy=random\|unattempted\|weak&opening_key=&exclude_problem_key=` | 出題ポリシー。処理順: (1) resolver から distinct `problem_key` 単位の候補集合を構築 → (2) `exclude_problem_key` と一致する問題を候補集合から除外 → (3) policy に応じて戦型・問題を選択 → (4) 選択された `problem_key` の代表 sample を返す(レスポンスに `sample_id` と `problem_key` の両方を含む)。直前問題の除外キーは **`problem_key`**(`sample_id` は画面遷移・解答POSTの一時参照専用で、除外の正式なキーには使わない) | P0-3 / P1-2 / P1-3 |
| GET | `/api/next-move/history` | 履歴用の集計+最近の解答(戦型は現在分類を resolver で解決。削除済み問題は解答時スナップショット+利用不可表示) | P1-1 |
| GET | `/api/next-move/review` | 復習対象(最新が unlisted/listed のサンプル。現在分類で表示し、削除済み問題は再挑戦不可として除外または無効表示) | P1-2 |

補足:

- 既存 `GET /api/learning-samples` / `GET /api/learning-samples/{id}` のレスポンスに `problem_key` を追加する(backend が算出。一覧バッジ・status API との突合に使用)。
- 候補手の返却順を `canonicalize_candidates_for_judgment` に統一する。既存の ORDER BY との差分は最終 tie-breaker のみ(`bm.id` → `move_usi`。行IDはDB再生成で変わるため安定キーの順序決定に使わない)。
- 既存 `GET /api/learning-samples` に `total_count` 相当(または `X-Total-Count`)と `offset` を追加(P0-2 の注記/P2-2 のページング)。

### フロントエンド

| ファイル | 変更 | フェーズ |
| --- | --- | --- |
| `src/api/client.ts` | 上記API関数・型(POSTに `problem_key` を含む)、503 detail・409(`NEXT_MOVE_PROBLEM_CHANGED`)の取り出し | P0 |
| `src/hooks/useNextMoveSession.ts` | 経過時間計測、着手時の記録コールバック(表示中サンプルの `problem_key` を添付) | P0-1 |
| `src/pages/NextMoveStudyPage.tsx` | スキップ・完了状態・ポリシー付き「次の問題」(表示中の `problem_key` を `exclude_problem_key` として送信し、204は「次の問題がありません」=完了表示にする)・進捗ラベル修正・DB異常詳細表示・409時の「問題データが更新されました。再読み込みしてください」表示(結果表示は維持) | P0-1〜P0-5 |
| `src/components/NextMoveProblemList.tsx` | 進捗サマリー・バッジ・出題ボタン・件数注記・h2、DB異常詳細表示 | P0-2/3/5 |
| `src/components/NextMoveResultPanel.tsx` | 用語ヘルプ | P1-4 |
| `src/pages/HistoryPage.tsx` | 次の一手セクション | P1-1 |
| `src/pages/ReviewPage.tsx` | 次の一手タブ | P1-2 |
| `src/shogi/nextMove.ts` | 判定用候補順序を共通規則(`canonicalize_candidates_for_judgment` 相当)に合わせる、verdict→バッジ表示のマッピング等の純関数追加 | P0-1 / P0-2 |
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
    - 同じ `effective_rank` の候補が複数ある場合、`canonicalize_candidates_for_judgment` によって判定順が決定的になる(score降順→depth降順→move_usi昇順。NULL は非NULLの後)。
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
- next_move.db のスキーマ形式(新旧両対応):
  - 新形式DBで `extraction_runs` と `learning_samples.extraction_run_key` の参照が機能する。
  - 旧形式DB(メタデータ無し)では `extraction_run_key` が `"unknown"` にフォールバックする。
  - アプリ実行中に next_move.db への書き込みが一切発生しない(`mode=ro` の担保)。
  - 抽出ツール(`extract_learning_samples.py`)が新スキーマを生成する。
  - `validate_next_move_db.py` が新旧形式を判定し、それぞれで検証が通る。
- `move_usi` の合法性検証(422系):
  - USI 構文が不正な手は 422(`NEXT_MOVE_MOVE_FORMAT_INVALID`)となり、`next_move_results`・`next_move_problem_refs` のどちらにも書き込まれない。
  - 空きマスからの移動など局面上の違法手は 422(`NEXT_MOVE_ILLEGAL_MOVE`)となる。
  - 手番と異なる側の駒を動かす手は 422 となる。
  - 不正な駒打ち(持っていない駒・打てないマス)は 422 となる。
  - 成り規則に反する手(成れない位置での成り・強制成りの無視)は 422 となる。
  - 合法だが候補一覧にない手は従来どおり `unlisted` として保存される。
  - 合法な候補手は従来どおり保存される。
  - `problem_key` 不一致の場合は**合法性検証より先に** 409 となる。
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
- `client.ts`: 503 detail の抽出、409(`NEXT_MOVE_PROBLEM_CHANGED`)の構造化エラーの取り出し、記録API失敗時に例外を伝播させないこと。

### E2E(Playwright)— 既存アサーションは全て維持

- 着手→ `POST /api/next-move/results` が期待ペイロード(`sample_id`・`problem_key`・`move_usi`・`hint_count`・`elapsed_ms`)で発火(route captureで検証)。
- 記録APIが409(`NEXT_MOVE_PROBLEM_CHANGED`)を返すケース(モック): 「問題データが更新されました。再読み込みしてください」等の案内が表示され、かつ盤面上の解答結果表示は維持されること。
- 通常UI(盤面)からは合法手しか送信されない既存仕様の維持(盤面は合法手のみ着手可能という既存E2Eのアサーションを保持。422系は backend APIテストで担保し、E2Eでは通常フローに422が現れないことを前提とする)。
- 一覧: バッジ表示・進捗サマリー・「ランダムに1問」で挑戦画面へ遷移。
- スキップ: 着手前スキップ→次問題→見出しフォーカス(キーボードのみでも)。
- 完了: 最終問題の解答後に完了メッセージ。
- DB異常: 503 detail 別の文言表示(モック)。
- 既存の維持対象: キーボード操作一式、360px横スクロールなし(バッジ・サマリー追加後に再確認)、答えの漏洩なし(着手前に候補手/評価値/PV非表示)、ナビの `aria-current`、旧URLリダイレクト。

---

## 8. PR構成(実装フェーズ)

依存関係順。各PRは単独でテスト green を維持する。

1. **PR-A: 解答記録の基盤**(P0-1)
   - `problem_key` の定義・算出(stable_source_key・normalized_sfen・candidate_definition_fingerprint・problem_definition_version)、**canonical serialization 共通関数**(キー辞書順・UTF-8・NFC・null/空文字区別。golden test 付き)、判定用候補順序の共通関数 `canonicalize_candidates_for_judgment`(API返却順・frontend判定・backend判定・fingerprint で同一実装。APIの最終 tie-breaker を `bm.id`→`move_usi` に変更)、抽出ツール側の `extraction_runs` メタデータ保存(`extract_learning_samples.py` / `validate_next_move_db.py` 対応)。
   - **shogi.db 側と next_move.db 生成側の両方を本PRに含める**: shogi.db スキーマ追加(`next_move_problem_refs` + `next_move_results`)と、next_move.db 生成スキーマの更新(`extraction_runs` + `learning_samples.extraction_run_key`。旧DB後方互換・validate 新旧対応込み)。`POST /api/next-move/results`(`problem_key` 照合 409 → SFEN復元による `move_usi` 合法性検証 422 → 合法時のみ backend で verdict・candidate_rank を算出・保存)、learning-samples レスポンスへの `problem_key` 追加、セッションでの自動記録と409時の再読み込み案内(UI変更は最小)。
   - README の安定キー方針の更新(下記ドキュメント欄参照)。
   - backend/frontend/E2E テスト(problem_key 安定性・fingerprint 検出・DB差し替え409を含む)。ここが全ての土台。
2. **PR-B: 進捗表示と一覧の改善**(P0-2、P1-5の見出し階層)
   - `progress`/`status` API と分類 resolver(`problem_key`→現在の代表 sample_id / opening_key / opening_name。**distinct `problem_key` 基準**の集計・重複排除・代表 sample の決定的選択)、一覧バッジ・サマリー・件数注記、挑戦画面の「X / Y」修正(distinct `problem_key` 数ベース)。
3. **PR-C: 出題ポリシーとスキップ**(P0-3、P0-4)
   - `learning-samples/next` API(distinct `problem_key` 候補集合+`exclude_problem_key` 除外+候補1件時の204)、ランダム/未挑戦優先ボタン、スキップ、完了状態(204時の「次の問題がありません」表示を含む)。frontend は表示中の `problem_key` を送る。READMEの「既知の制限」更新。
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
