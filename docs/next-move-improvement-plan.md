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

```
problem_key = "v1:" + sha256(
    stable_source_key                  -- 出典の安定識別子
  + normalized_sfen                    -- 正規化局面
  + candidate_definition_fingerprint   -- 候補手定義のフィンガープリント
  + problem_definition_version         -- 問題定義のバージョン
)
```

- `stable_source_key`: 定跡ソースを安定して識別する値(`book_sources` の name / version / source_url から構成)。同一局面でもソースが異なれば候補手・評価値が異なる別問題として扱う。**ファイル全体の `file_sha256` は含めない**(ファイルの一部が更新されただけで、変更のない全局面のキーが変わってしまうため)。`file_sha256` は監査用メタデータとして別途保存する。
- `normalized_sfen`: SFENの手数(ply)フィールドを除去し、盤面・手番・持ち駒を python-shogi / tsshogi の再シリアライズで正規化する。再生成時の表記ゆれ(持ち駒の並び・空白等)でキーが変わることを防ぐ。
- `candidate_definition_fingerprint`: その局面に登録されている候補手と順位の定義を局面単位でハッシュ化した値。**`effective_rank` と `move_usi` の組の配列**を canonical JSON 化して算出する(`move_usi` の並びだけでは、候補手の並びが同じまま数値順位だけが変わるケース—例: `sort_order` が `[0, 2]`→`[0, 3]` になり第3候補が第4候補へ変わって verdict が strong→listed に変わる—を検出できないため)。

  ```json
  [
    {"effective_rank": 1, "move_usi": "2g2f"},
    {"effective_rank": 4, "move_usi": "7g7f"}
  ]
  ```

  - `effective_rank` は **API 表示と backend/frontend の判定で実際に使う順位と完全に同一の計算規則**とする(DB の rank(`sort_order + 1`)があればそれ、無ければ判定に使う並び順から補完—現行 `displayRank` と同じ規則)。`sort_order` の欠番・非連続値がある場合も、実際の判定順位をそのまま反映する。
  - 配列は `effective_rank` 昇順、同順位は `move_usi` 昇順で決定的に並べ、canonical JSON(キー順・空白を固定)にしてハッシュ化する。DB の行順に依存しない。
  - `effective_rank` の算出は共通関数に切り出し、API レスポンス・記録時の verdict/candidate_rank 算出・fingerprint・テストで同一実装を使う(規則のずれを構造的に防ぐ)。
  - score・PV は含めない(数値の微修正やPV追記のたびに別問題化するのを避ける。判定は候補手の有無と順位で決まるため、verdict に影響し得る変更=候補手・順位の変更は fingerprint で必ず検出できる)。候補手が同じでも `effective_rank` が変われば fingerprint が変わり、別問題として扱われる。
- `problem_definition_version`: problem_key の意味や fingerprint の計算方法を変更する場合に備えたバージョン(初期値 `1`)。先頭の `v1:` はキー文字列形式のバージョンで、これと合わせて管理する。

`opening_key` はキーに**含めない**: 戦型分類は分類器の改良で変わり得る表示・集計用メタデータであり、分類が変わっても問題自体は同一だからである(記録側には集計用に非正規化して保存する)。

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
- **verdict と candidate_rank は backend 側で算出する**: backend は `sample_id` から next_move.db の現在の問題・候補手・出典メタデータを読み、`problem_key` を再算出する。**クライアントが送った `problem_key` と再算出値が一致した場合のみ**、`move_usi` を候補手と突き合わせて verdict・candidate_rank を確定し保存する。クライアント申告の判定は信用しない(フロントの判定ロジックは即時表示専用とし、順位付け規則は backend と同一の `effective_rank` 規則であることをテストで担保する)。
- **problem_key 不一致時は履歴を保存せず HTTP 409 を返す**(構造化エラーコード例: `NEXT_MOVE_PROBLEM_CHANGED`)。これは、問題表示後〜解答送信の間に next_move.db が再生成・差し替えされ、同じ `learning_samples.id` が**別問題に再利用された**ケースの検出である(この場合 `sample_id` は存在するため404にも503にもならず、照合なしでは差し替え後の別問題に誤って履歴が保存されてしまう)。`next_move_results` にも `next_move_problem_refs` にも書き込まない。
- 409 を受けたフロントエンドは「問題データが更新されました。再読み込みしてください」等を表示する。**盤面上で算出済みの解答結果表示自体は妨げない**(記録されなかったことのみ控えめに伝える)。
- `sample_id` が存在しない場合は404、next_move.db が利用不可の場合は503を返す(いずれも記録は行われない)。
- 「もう一度考える」→再着手でも新しいレコードとして記録される(上書きしない)。
- 記録APIの失敗は挑戦フローを妨げない(結果表示は正常に出る。控えめなエラー表示のみ)。
- next_move.db には実行時書き込みを行わない。§4冒頭の「履歴を引き継ぐケース」(抽出件数・seed変更、無関係な局面のみの変更等)で `problem_key` が一致して記録が引き継がれ、「別問題として扱うケース」(出典・局面・候補手定義・定義バージョンの変更)で区別されることをテストで担保する。
- 記録は所要時間を含む(問題表示〜着手までのms)。

### P0-2 進捗表示

- 一覧の各戦型に「挑戦済み n / 全N問」が表示される(Nは `learning_samples` の実数、nは `problem_key` 単位のユニーク挑戦数)。
- 各カードに最新解答に基づくバッジ(未挑戦/◎最有力/○有力/△登録候補/?未登録)が表示され、`aria-label` で読み上げ可能。
- 挑戦画面の「問題 X / Y」が戦型の実件数と一致する(100件超でも正しい)。
- 一覧が30件で切れる場合、「全N問中30問を表示」の注記が出る。

### P0-3 ランダム出題・未挑戦優先

- 一覧に「ランダムに1問」「未挑戦から1問」ボタンがあり、押すと該当問題の挑戦画面へ遷移する。
- 未挑戦問題が無い場合はその旨を表示し、ランダム出題へフォールバックできる。
- 解答後の「次の問題」は現在の出題ポリシーを引き継ぐ(ランダムで来たら次もランダム)。
- 同一問題が連続して出ない(直前の問題を除外)。

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
- 既存の詰め将棋・タイムアタックの表示に影響がない(既存E2Eが通る)。

### P1-2 復習統合(再出題)

- 復習ページに「次の一手」タブが追加され、最新解答が unlisted または listed の問題が一覧表示される。
- 「再挑戦」で該当問題の挑戦画面へ遷移し、最有力候補(top)を指すと一覧から消える(次回ロード時)。
- 該当問題が0件のとき適切な空状態文言が出る。

### P1-3 均等出題

- 戦型選択ロジックを純関数(例: `choose_opening(openings, rng)`)として分離し、RNG を注入可能(seeded/mockable)にする。
- 単体テストで、**seeded RNG による決定的テスト**として次を検証する:
  - 各戦型がサンプル数によらず**同一重み**で選択されること(RNGの返す値と選択結果の対応を網羅的に確認する、または固定seedでの選択列が期待列と一致することを確認する)。
  - `exclude_id` により直前の問題が除外されること。
- 確率的な閾値判定(「n回連続で偏らない」等)はテストに用いない(正しい一様乱数でも確率的に失敗し得る flaky なテストになるため)。
- anti-streak(同一戦型の連続抑止)は**仕様としない**。エンドポイントはステートレスのままとし、履歴パラメータやセッション状態は追加しない(直前問題の除外は `exclude_id` のみ)。

### P1-4 用語説明

- 結果パネルに「評価値・PV・候補順位とは」ヘルプ(`<details>`)があり、着手前の画面には表示されない(答えの漏洩なし)。
- スクリーンリーダーで summary → 内容の順に読める。

### P1-5 a11y細部

- 一覧の見出し階層が h1→h2→h3 になる。
- disabled な「次の問題」に理由(「この戦型は1問のみです」等)が視覚+SRで提示される。
- 解答後、結果パネル先頭へ移動する手段(スキップリンク or フォーカス移動)がある。既存のキーボードE2Eは修正なしで通る。

---

## 6. 想定変更ファイル

### DBスキーマ(shogi.db のみ。next_move.db は変更しない)

- `backend/app/database.py` — 追加テーブル:

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
    opening_key TEXT NOT NULL DEFAULT '',   -- 集計用の非正規化(分類変更時は表示上のグルーピングのみ変わる)
    opening_name TEXT NOT NULL DEFAULT '',
    move_usi TEXT NOT NULL,
    verdict TEXT NOT NULL,              -- top / strong / listed / unlisted(backend算出)
    candidate_rank INTEGER,             -- 候補外は NULL(backend算出)
    hint_count INTEGER NOT NULL DEFAULT 0,
    elapsed_ms INTEGER,
    answered_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_next_move_results_key ON next_move_results(problem_key);
CREATE INDEX IF NOT EXISTS idx_next_move_results_opening ON next_move_results(opening_key, answered_at);
-- P2-1 で追加: next_move_favorites(problem_key UNIQUE REFERENCES next_move_problem_refs, created_at)
```

next_move.db 側(抽出ツールが生成。実行時は読み取り専用のまま):

- 抽出時に **抽出実行メタデータ**を保存する: `extraction_runs` テーブル(`extraction_run_key`, `extractor_version`, `limit`, `per_opening_limit`, `seed`, `source_file_sha256`, `extracted_at`)を追加し、`learning_samples` から `extraction_run_key` を参照する。`extract_learning_samples.py` と `validate_next_move_db.py` を対応させる。
- `problem_key` の構成要素(`stable_source_key`・`normalized_sfen`・candidate fingerprint)は既存の `book_sources` / `book_moves` から backend が算出できるため、**メタデータの無い旧DBでも problem_key は完全に算出可能**。旧DBでは監査用の `extraction_run_key` のみ `"unknown"` にフォールバックする(キーには影響しない)。

### API(新規ルーター `backend/app/routers/next_move.py` を想定)

| メソッド | パス | 用途 | フェーズ |
| --- | --- | --- | --- |
| POST | `/api/next-move/results` | 解答記録。入力は `sample_id`(一時参照)+`problem_key`(表示中の問題の値)+`move_usi`+`hint_count`+`elapsed_ms` の5項目。backend が problem_key を再算出して照合し、一致時のみ候補手から verdict・candidate_rank を算出・保存。不一致は 409(`NEXT_MOVE_PROBLEM_CHANGED`)で保存しない | P0-1 |
| GET | `/api/next-move/progress` | 戦型ごとの挑戦数・verdict内訳(shogi.db の結果 × next_move.db の件数を `problem_key` で突合) | P0-2 |
| GET | `/api/next-move/status?opening_key=` | `problem_key`→最新verdict のマップ(一覧バッジ用) | P0-2 |
| GET | `/api/learning-samples/next?policy=random\|unattempted\|weak&opening_key=&exclude_id=` | 出題ポリシー | P0-3 / P1-2 / P1-3 |
| GET | `/api/next-move/history` | 履歴用の集計+最近の解答 | P1-1 |
| GET | `/api/next-move/review` | 復習対象(最新が unlisted/listed のサンプル) | P1-2 |

補足:

- 既存 `GET /api/learning-samples` / `GET /api/learning-samples/{id}` のレスポンスに `problem_key` を追加する(backend が算出。一覧バッジ・status API との突合に使用)。
- 既存 `GET /api/learning-samples` に `total_count` 相当(または `X-Total-Count`)と `offset` を追加(P0-2 の注記/P2-2 のページング)。

### フロントエンド

| ファイル | 変更 | フェーズ |
| --- | --- | --- |
| `src/api/client.ts` | 上記API関数・型(POSTに `problem_key` を含む)、503 detail・409(`NEXT_MOVE_PROBLEM_CHANGED`)の取り出し | P0 |
| `src/hooks/useNextMoveSession.ts` | 経過時間計測、着手時の記録コールバック(表示中サンプルの `problem_key` を添付) | P0-1 |
| `src/pages/NextMoveStudyPage.tsx` | スキップ・完了状態・ポリシー付き「次の問題」・進捗ラベル修正・DB異常詳細表示・409時の「問題データが更新されました。再読み込みしてください」表示(結果表示は維持) | P0-1〜P0-5 |
| `src/components/NextMoveProblemList.tsx` | 進捗サマリー・バッジ・出題ボタン・件数注記・h2、DB異常詳細表示 | P0-2/3/5 |
| `src/components/NextMoveResultPanel.tsx` | 用語ヘルプ | P1-4 |
| `src/pages/HistoryPage.tsx` | 次の一手セクション | P1-1 |
| `src/pages/ReviewPage.tsx` | 次の一手タブ | P1-2 |
| `src/shogi/nextMove.ts` | verdict→バッジ表示のマッピング等の純関数追加 | P0-2 |
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
- `problem_key` の導出:
  - (a) `limit`・`per_opening_limit`・`seed` を変更して再抽出しても、同じ問題(同一出典・同一正規化局面・同一候補手定義)の `problem_key` が一致する。
  - (b) ソースファイルの**無関係な局面だけ**が変更(追加・削除・修正)されても、対象問題の `problem_key` は一致する(`file_sha256` がキーに影響しないこと)。
  - (c) 対象局面の**候補手または候補順位が変わる**と `problem_key` が変わる(fingerprint 検出)。score・PV のみの変更ではキーが変わらない。特に以下を検証する:
    - 同じ `move_usi` 配列・同じ並びでも、`effective_rank` が変わる(例: `sort_order` の変更で 3→4)と fingerprint と `problem_key` が変わる。
    - `effective_rank` と `move_usi` が同じなら、DB の行順(挿入順・id順)が異なっても同じ fingerprint になる。
    - 同順位の候補が複数ある場合も、`move_usi` による第2ソートで fingerprint が決定的になる。
    - backend の verdict/candidate_rank 算出と fingerprint が**同一の `effective_rank` 共通関数**を使っていることを検証する(同一fixtureに対する順位が一致すること)。
  - (d) **異なる出典に同一SFENが含まれる場合はキーが異なる**(`stable_source_key` の分離)。
  - (e) 手数フィールドの違いや持ち駒順・空白などの表記ゆれは正規化され、キーが一致する。
  - (f) `problem_definition_version` を変えるとキーが変わる。
  - (g) `extraction_run_key` は抽出条件(limit/seed 等)の変更で変わる(監査メタデータとしての検証。problem_key には影響しない)。
  - (h) `extraction_runs` メタデータの無い旧DBでも `problem_key` は算出でき、`extraction_run_key` のみ `"unknown"` にフォールバックする。
- `progress` / `status`: 記録なし→全て未挑戦、記録後の集計、next_move.db 差し替え(同一の問題定義)後も `problem_key` 経由で進捗が残ること。`next_move_problem_refs` が POST 時に upsert されること。
- `next?policy=`: seeded RNG を注入した決定的テスト。分離した戦型選択関数の単体テストで各戦型の均等重みと `exclude_id` の除外動作を検証する(確率的な閾値判定は用いない。§5 P1-3 参照)。unattempted(全問挑戦済み時の挙動)、weak(unlisted/listedのみ)も同様に決定的に検証。
- **next_move.db 不在時**: 出題系・`POST /api/next-move/results` は503を返し(verdict算出に候補手参照が必要なため)、shogi.db のみで完結する集計系(`history` 等)は動作すること。既存の `test_next_move_database.py` の検証(欠落テーブル・カラム・0件)を維持。

### フロントエンド(vitest)

- バッジ/進捗表示の純関数、ポリシー付き「次の問題」選択ロジック、経過時間の丸め。
- `client.ts`: 503 detail の抽出、409(`NEXT_MOVE_PROBLEM_CHANGED`)の構造化エラーの取り出し、記録API失敗時に例外を伝播させないこと。

### E2E(Playwright)— 既存アサーションは全て維持

- 着手→ `POST /api/next-move/results` が期待ペイロード(`sample_id`・`problem_key`・`move_usi`・`hint_count`・`elapsed_ms`)で発火(route captureで検証)。
- 記録APIが409(`NEXT_MOVE_PROBLEM_CHANGED`)を返すケース(モック): 「問題データが更新されました。再読み込みしてください」等の案内が表示され、かつ盤面上の解答結果表示は維持されること。
- 一覧: バッジ表示・進捗サマリー・「ランダムに1問」で挑戦画面へ遷移。
- スキップ: 着手前スキップ→次問題→見出しフォーカス(キーボードのみでも)。
- 完了: 最終問題の解答後に完了メッセージ。
- DB異常: 503 detail 別の文言表示(モック)。
- 既存の維持対象: キーボード操作一式、360px横スクロールなし(バッジ・サマリー追加後に再確認)、答えの漏洩なし(着手前に候補手/評価値/PV非表示)、ナビの `aria-current`、旧URLリダイレクト。

---

## 8. PR構成(実装フェーズ)

依存関係順。各PRは単独でテスト green を維持する。

1. **PR-A: 解答記録の基盤**(P0-1)
   - `problem_key` の定義・算出(stable_source_key・normalized_sfen・candidate_definition_fingerprint・problem_definition_version)と、`effective_rank` 共通関数(API表示・verdict算出・fingerprint で同一実装)、抽出ツール側の `extraction_runs` メタデータ保存(`extract_learning_samples.py` / `validate_next_move_db.py` 対応)。
   - shogi.db スキーマ追加(`next_move_problem_refs` + `next_move_results`)、`POST /api/next-move/results`(`problem_key` 照合→一致時のみ backend で verdict・candidate_rank を算出・保存、不一致は 409 `NEXT_MOVE_PROBLEM_CHANGED`)、learning-samples レスポンスへの `problem_key` 追加、セッションでの自動記録と409時の再読み込み案内(UI変更は最小)。
   - README の安定キー方針の更新(下記ドキュメント欄参照)。
   - backend/frontend/E2E テスト(problem_key 安定性・fingerprint 検出・DB差し替え409を含む)。ここが全ての土台。
2. **PR-B: 進捗表示と一覧の改善**(P0-2、P1-5の見出し階層)
   - `progress`/`status` API、一覧バッジ・サマリー・件数注記、挑戦画面の「X / Y」修正。
3. **PR-C: 出題ポリシーとスキップ**(P0-3、P0-4)
   - `learning-samples/next` API、ランダム/未挑戦優先ボタン、スキップ、完了状態。READMEの「既知の制限」更新。
4. **PR-D: DB異常案内と用語説明**(P0-5、P1-4)
   - 503 detail 表示+復旧手順、評価値/PVヘルプ。小さく独立しているためA〜Cと並行可能(P0-5のみ先行切り出しも可)。
5. **PR-E: 履歴・復習統合**(P1-1、P1-2、P1-3)
   - 履歴セクション、復習タブ、weak/均等ポリシー。PR-A〜Cに依存。
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
