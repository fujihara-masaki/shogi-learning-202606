# 将棋学習アプリ

将棋盤 GUI で駒を操作しながら詰め将棋を学習するローカル Web アプリです。
詰め将棋・タイムアタック・復習・学習履歴に加え、固定データによる定跡学習MVPと、定跡DBから出題する「次の一手」を実装しています。

- フロントエンド: React + Vite + TypeScript + [tsshogi](https://www.npmjs.com/package/tsshogi)(局面管理・合法手判定)
- バックエンド: FastAPI + SQLite + [python-shogi](https://pypi.org/project/python-shogi/)(問題データの検証)
- 局面は SFEN、指し手は USI 形式で保存


## ライセンス

このリポジトリは、現時点では個人学習用の将棋学習アプリとして開発しています。将来的には無償配布も検討しています。

- アプリ本体のソースコードは GPL-3.0-only で扱う方針です。詳細は root の `LICENSE` を参照してください。
- 定跡データ、将来的に追加する詰め将棋データ、戦型一覧 seed データなどのデータ類は、アプリ本体のコードライセンスとは別に、各データ提供元のライセンスに従います。
- Wikipedia / Wikibooks 由来の内容を参考にした戦型一覧 seed データについては、CC BY-SA に基づく出典・ライセンス表示を維持します。アプリ内の「データ出典」表示および API レスポンスの `source_url` / `license` に出典とライセンスを明記する方針です。
- ライセンス確認が完了していない外部定跡データや詰め将棋データは、このリポジトリに含めません。
- 再利用許諾済みの外部データを取り込む場合は、データごとの出典、ライセンス名、ライセンス URL を記録し、既存のデータ出典・ライセンス表示方針を維持してください。

## 構成

```
backend/   FastAPI アプリ (API + SQLite + サンプル問題シード)
frontend/  React アプリ (将棋盤 GUI + 各画面)
```

## セットアップと起動

### バックエンド

```bash
cd backend
pip install -r requirements.txt          # 仮想環境の利用を推奨
uvicorn app.main:app --reload --port 8000
```

- 初回起動時に `backend/data/shogi.db` が自動作成され、テーブル初期化とサンプル問題の投入が行われます(明示的な初期化コマンドは不要)。
- DB を作り直したい場合は `backend/data/shogi.db` を削除して再起動してください。
- API ドキュメント: http://localhost:8000/docs
- 環境変数(任意): `backend/.env.example` を参照(`SHOGI_DB_PATH`, `SHOGI_CORS_ORIGINS`)。

### フロントエンド

```bash
cd frontend
npm install
npm run dev
```

- ブラウザで http://localhost:5173 を開きます。
- API の接続先を変える場合は `frontend/.env.example` を `.env` にコピーして `VITE_API_BASE` を設定してください(省略時は `http://localhost:8000`)。

### テスト・Lint

```bash
# バックエンド (15件: API とサンプル問題の詰み検証)
cd backend && python3 -m pytest

# フロントエンド (41件: 局面・指し手・次の一手判定ロジック)
cd frontend && npx vitest run

# 型チェック + ビルド / Lint
cd frontend && npm run build && npm run lint

# E2E (Playwright / backend・frontend自動起動)
cd frontend && npm run test:e2e
```

### E2Eテスト (Playwright)

E2Eテストは、ブラウザ上でホーム、詰め将棋プレイ、問題作成UI、盤面からの手順記録、作成問題のプレイ、編集・削除、定跡学習(手順学習)、次の一手、タイムアタックの基本表示を自動確認するためのテストです。次の一手のテスト(`e2e/next-move.spec.ts`)は、E2E用DBに定跡DBデータが無いため learning_samples API をモックして実行します。

初回セットアップ:

```bash
cd frontend
npm install
npx playwright install chromium
```

実行コマンド:

```bash
# ヘッドレス実行 (backend / frontend を自動起動)
npm run test:e2e

# ブラウザを表示して実行
npm run test:e2e:headed

# 失敗時などのHTMLレポート確認
npm run test:e2e:report
```

互換用に `npm run e2e` / `npm run e2e:headed` / `npm run e2e:report` も同じ内容で利用できます。

Playwright設定で backend と frontend を自動起動します。事前に手動起動する必要はありません。E2E実行時の backend は既定で `frontend/.e2e/shogi-e2e.db` を `SHOGI_DB_PATH` に指定するため、通常利用のSQLite DBとは分離されます。テストは開始前・終了後にタイトルが `[e2e]` で始まる問題を削除します。

Windows / macOS / Linux のいずれでも動くように、Playwright の `webServer.command` では `SHOGI_DB_PATH=... command` のようなシェル依存の環境変数指定を使わず、`frontend/scripts/start-e2e-backend.mjs` と `frontend/scripts/start-e2e-frontend.mjs` から Node.js 経由で環境変数を渡しています。frontend 起動時は `VITE_API_BASE=http://127.0.0.1:${E2E_BACKEND_PORT}` を `env` 経由で渡します。backend 起動時は `SHOGI_DB_PATH` と `E2E_BACKEND_PORT` を `env` 経由で渡し、`python -m uvicorn app.main:app` を起動します。

WindowsでPythonランチャー名が異なる場合や、Windows Store版 Python が先に見つかって `No module named uvicorn` になる場合は、`PYTHON` 環境変数に仮想環境内の実行ファイルを指定してから実行してください。

PowerShell例:

```powershell
$env:PYTHON = "..\backend\.venv\Scripts\python.exe"
npm run test:e2e
```

ポートやE2E用DBを変更したい場合は、`E2E_BACKEND_PORT` / `E2E_FRONTEND_PORT` / `SHOGI_DB_PATH` を指定できます。テスト内のAPI接続先は `E2E_BACKEND_PORT` から生成され、backend の CORS 許可オリジンも `E2E_FRONTEND_PORT` に合わせて自動設定されます(`SHOGI_CORS_ORIGINS` を明示した場合はそちらを優先)。

```bash
E2E_BACKEND_PORT=18000 E2E_FRONTEND_PORT=15173 SHOGI_DB_PATH=./.e2e/custom.db npm run test:e2e
```

## 画面

| 画面 | 内容 |
| --- | --- |
| ホーム | 各機能へのメニュー |
| 詰め将棋 | 難易度(1/3/5手詰)・タグで絞り込み、問題選択、ランダム出題、ヒント、答えを見る、解説、お気に入り |
| 定跡学習 | 定跡手順のなぞり学習(一覧: `/openings`、個別: `/openings/:id`) |
| 次の一手 | 実戦形の局面から一手を考える問題(一覧: `/next-move`、個別: `/next-move/:id`) |
| タイムアタック | 難易度・問題数(5/10問)選択、タイマー、正解数・ミス数・合計時間の表示と保存 |
| 復習 | 間違えたことのある問題一覧・お気に入り一覧から再挑戦 |
| 履歴 | 正答率・平均解答時間・最近の解答・タイムアタック履歴 |
| 問題作成 | 盤面エディタ、SFEN生成/復元、詰め将棋問題の作成・編集・削除 |

### 操作方法

- 駒はクリック(選択 → 移動先)またはドラッグで動かせます。移動可能マスはハイライトされます。
- 持ち駒は駒台の駒をクリックしてから打ちたいマスをクリックします。
- 成れる場合は「成る/成らず」の選択ダイアログが出ます(成りが強制の場合は自動)。
- 「盤面反転」で後手視点、「1手戻る」「最初に戻る」で局面を戻せます。
- 3手詰・5手詰では、正解手を指すと玉方の応手が自動で実行されます。

## サンプル問題について

初回起動時に 1手詰 3問・3手詰 3問・5手詰 1問が登録されます。
**いずれもタイトルに `[sample]` が付いた動作確認用の練習データです。**
詰将棋としての成立(手順の合法性・最終局面の詰み・余詰めなし・玉方応手の強制)は
python-shogi による機械検証済みですが、作品としての洗練はされていません。
本格的な問題は「問題作成」画面、または API で登録・差し替えしてください。

```bash
# 問題の追加例(登録時に手順の合法性と詰みがサーバー側で検証されます)
curl -X POST http://localhost:8000/api/tsume-problems \
  -H "Content-Type: application/json" \
  -d '{
    "title": "自作の1手詰",
    "initial_sfen": "4k4/9/5+B3/9/9/9/9/9/9 b G 1",
    "mate_length": 1,
    "solution_moves": ["G*5b"],
    "opponent_moves": [],
    "difficulty": 1,
    "tags": ["1手詰", "頭金"],
    "explanation": "解説文"
  }'
```

## 定跡データの取り込み

### Canonical Wikipedia artifact の検証

D1b canonical schema (`backend/app/wikipedia_opening_artifact.schema.json`) に従うartifactは、
リポジトリrootまたは`backend`から直接検証できます（D0 legacy audit JSONは入力対象外です）。

```bash
# repository root
python backend/scripts/validate_wikipedia_opening_artifact.py path/to/artifact.json

# または backend/
python scripts/validate_wikipedia_opening_artifact.py path/to/artifact.json
```

stdoutには常に通常結果を1個のJSON objectとして出力します。成功時は
`{"valid": true, "errors": []}`、失敗時は`errors`に安定した`path` / `code`と
説明用`message`を格納します。終了codeは、`0`が有効、`1`が読み込み済みartifactの
schema/semantic違反、`2`がfile・UTF-8・JSON・bundled schema等の運用エラーです。

再利用許諾済みの SFEN/USI 定跡データは `data/openings/*.sfen` に配置し、backend のインポートスクリプトで SQLite に取り込めます。KIF/CSA は今後の拡張対象です。

対応形式:

```text
startpos moves 7g7f 3c3d 2h5h
sfen <盤面> <手番> <持ち駒> <手数> moves ...
```

実行例:

```bash
cd backend
python scripts/import_openings.py ../data/openings --license-name CC0 --license-url https://example.com/license
```

取り込み時に、各手の前後 SFEN、USI 指し手、ライセンス情報を `opening_sources` / `opening_positions` / `opening_moves` / `opening_tags` に保存します。分類はMVPとして簡易ルールです。中飛車は「序盤40手以内に飛車が5筋にいる」場合に `nakabisha` タグを付与します。棒銀・向かい飛車も簡易的に判定します。

import時の `opening_type_id` 推定は、ファイル名・行テキストなどの取り込みメタデータと盤面ベースの簡易分類を組み合わせます。優先順位は「戦型名の一致 → alias一致 → 複合キーワード一致 → 単独キーワード一致 → 盤面ベースの既存簡易分類 → 未分類 fallback」です。表記ゆれとして、例: `棒銀戦法` は `棒銀`、`右四間` は `右四間飛車`、`角交換四間` は `角交換四間飛車`、`ゴキ中` は `ゴキゲン中飛車` に寄せます。分類不能でも import は失敗させず、`未分類` 戦型へ紐付けます。

### 戦型一覧 seed データの出典とライセンス

`opening_categories` / `opening_types` の初期 seed データは、Wikibooks「将棋の戦法一覧」、Wikipedia「将棋の戦法」、Wikipediaカテゴリ「将棋の戦法」を参考に、アプリ用に手作業で確認・短い説明文として整理したものです。実行時に外部 Web ページをスクレイピングせず、DB 初期化時にローカル seed として投入します。

代表戦型 seed には、相居飛車系の `棒銀` / `原始棒銀` / `矢倉棒銀` / `角換わり棒銀` / `角換わり早繰り銀` / `角換わり腰掛け銀` / `矢倉` / `角換わり` / `相掛かり` / `横歩取り` / `雁木`、対抗型・振り飛車系の `右四間飛車` / `対振り飛車急戦` / `四間飛車` / `三間飛車` / `中飛車` / `向かい飛車` / `石田流` / `ゴキゲン中飛車` / `角交換四間飛車`、囲い・構想の `居飛車穴熊`、fallback 用の `未分類` を含めています。各 seed は表示名、カテゴリ、親戦型、aliases、説明、source/seed由来情報を `opening_types` に保存します。

これらの参考元は CC BY-SA ライセンスのコンテンツを含むため、アプリ内の「データ出典」表示および各 API レスポンスの `source_url` / `license` に出典と `CC BY-SA` を明記しています。

## 定跡学習・次の一手の使い方

序盤学習には、目的の異なる2つの主要機能があります。上部ナビゲーション・ホーム画面・モバイル下部ナビのそれぞれから個別に開けます。

- **定跡学習**(`/openings`): 定跡の手順を一手ずつ盤面でなぞって覚える機能。
- **次の一手**(`/next-move`): 定跡DBから抽出した局面を見て、自分で一手を考える機能。

旧URLの `/openings?mode=next-move`(次の一手一覧)と `/openings/next-move/:id`(個別問題)は、それぞれ `/next-move` と `/next-move/:id` へ互換リダイレクトされます(ブックマーク・直接アクセスも有効)。

### 定跡学習(定跡手順を学ぶ)

1. ホームまたは上部ナビゲーションの「定跡学習」を開きます(`/openings`)。
2. 定跡一覧で、定跡名・戦型・説明・手数を確認し、「学習する」を押します。
3. 学習画面では、右側に現在の推奨手、USI、解説、狙いが表示されます。盤面上でその手を実際に指します。
4. 期待手と一致すると「正解」と表示され、次の局面・次の推奨手へ進みます。一致しない場合は不正解メッセージとヒントが表示されます。
5. 「ヒント」で現在手のヒントを表示できます。「1手戻る」で直前の手を取り消し、「最初から」で定跡の初期局面へ戻ります。
6. 現在の定跡データは `frontend/src/shogi/openings.ts` の固定データです。DB化、AI評価値、外部棋譜DB連携は今後の拡張対象です。

定跡データは、将来の分岐対応を考慮してノードと候補手のツリー形式にしています。各手は USI形式、表示用表記、解説、狙い、ヒントを持ちます。

### 次の一手

1. ホームまたは上部ナビゲーションの「次の一手」を開きます(`/next-move`)。
2. 戦型を選び(初期状態では先頭の戦型が選択されます)、問題カードの「挑戦する」を押します(`/next-move/:id`)。
3. 着手前は盤面・戦型名・進捗のみ表示され、候補手・評価値・PVなどの答えは表示されません。必要なら「ヒントを見る」で段階的なヒント(駒種 → 移動先)を確認できます。
4. 盤面で合法手を1手指すと、定跡DBの候補手と照合した結果が表示されます。
   - 最上位候補: 「最有力候補」
   - 第2〜3候補: 「有力候補」
   - 第4候補以下: 「その他の登録候補」
   - 候補に無い合法手: 「定跡DBには候補手として登録されていません(局面上の評価を完全に否定するものではありません)」
5. 解答後は、候補順位・評価値・最上位候補との評価値の絶対差(参考)・進行例(PV)・出典/ライセンスを確認でき、「候補手を比較する」で全候補の一覧表を表示できます。「次の問題」「もう一度考える」「次の一手一覧へ戻る」の導線があります。

一覧の「全戦型からランダムに1問」は、問題数ではなく戦型を先に均等確率で選び、その戦型内から1問を選びます。履歴画面では次の一手の総解答数・判定内訳・最有力率・最近の解答を確認できます。復習画面の「次の一手」タブには最新判定が「△ 登録候補」「? 未登録」の問題が並び、「復習対象から1問」では `weak` ポリシーで全戦型の対象から出題します。

判定は正誤の断定を避け、定跡DBに記録されたデータ(候補の並び順・rank・score)から言える範囲の表現にしています。評価値は取り込み元DBに記録された数値をそのまま表示し、向き・単位の解釈(有利/不利など)は付けません。最上位候補との比較も、方向の解釈を避けるため評価値の**絶対差**を参考値として表示します。問題データは既存の `learning_samples` / 候補手APIを再利用しており、DBスキーマの変更はありません。

#### 次の一手の既知の制限(今後の拡張候補)

- 戦型別・全戦型のランダム出題、未挑戦優先出題、weak出題、100件を超える戦型の順次学習、最終問題の完了表示に対応しています。全戦型ランダムは戦型を均等な重みで選択します。
- お気に入りとサーバー側sequential cursorは未対応です。一覧UI自体も先頭30件の表示のみで、本格的なページング・絞り込みは今後の課題です。

## 問題作成 UI の使い方

1. ホームまたは上部ナビゲーションの「問題作成」を開きます(`/problem-editor`)。
2. 盤面エディタで「配置する駒」を選び、9×9盤のマスをクリックして駒を置きます。「移動」で盤上の駒を移動、「削除」で駒を消せます。
3. 先手/後手の持ち駒は右側の数値入力で編集し、手番はフォームのセレクトで切り替えます。
4. 「現在の局面からSFEN生成」でフォームの `initial_sfen` に反映します。既存の SFEN を貼り付けた場合は「SFENを盤面へ反映」で復元できます。
5. `title`、`mate_length`、`difficulty`、`tags`、`explanation`、`is_favorite` を入力します。解法手順は「盤面で解法手順を記録」で実際に駒を動かすと、攻め方の手が `solution_moves`、玉方の応手が `opponent_moves` に自動入力されます。必要に応じて USI 形式のテキストを直接編集することもできます。
6. 「検証して保存」を押すと、ブラウザ側で SFEN/USI/手数を確認し、サーバー側でも python-shogi による合法手順と最終詰みを検証してから保存します。
7. 左の問題一覧から既存問題を選ぶと同じフォームで編集できます。削除ボタンで問題を削除できます。保存した問題は詰め将棋画面の一覧に表示され、通常の問題としてプレイできます。

## API 一覧

| メソッド | パス | 内容 |
| --- | --- | --- |
| GET | /api/tsume-problems | 問題一覧(`mate_length` / `tag` / `favorite` / `random_order` / `limit`) |
| GET | /api/tsume-problems/{id} | 問題詳細 |
| POST | /api/tsume-problems | 問題作成(詰み手順をサーバー側で検証) |
| POST | /api/tsume-problems/validate | SFEN・USI手順・手数・最終詰みの検証 |
| PUT | /api/tsume-problems/{id} | 問題更新 |
| DELETE | /api/tsume-problems/{id} | 問題削除 |
| POST | /api/tsume-problems/{id}/result | 解答結果の記録 |
| POST | /api/tsume-problems/{id}/favorite | お気に入り設定 |
| POST | /api/time-attack/result | タイムアタック結果の保存 |
| GET | /api/time-attack/results | タイムアタック履歴 |
| GET | /api/stats | 全体・難易度別の正答率、最近の解答 |
| GET | /api/review-problems | 間違えたことのある問題(復習用) |
| GET | /api/openings/tags | インポート済み定跡タグ一覧 |
| GET | /api/openings | インポート済み定跡一覧(`tag` で絞り込み可能) |
| GET | /api/openings/{id} | インポート済み定跡詳細(各手前後のSFENとUSI) |
| GET | /api/book/candidates?sfen={SFEN} | 現在局面SFENに一致する外部定跡候補手と出典・ライセンス情報 |
| POST | /api/next-move/results | 次の一手の解答記録 |
| GET | /api/next-move/history | 次の一手の集計と最近の解答 |
| GET | /api/next-move/review | 最新判定がlisted/unlistedの復習対象 |
| GET | /api/next-move/problems/next | `random` / `unattempted` / `weak` ポリシーによる出題 |

## DB スキーマ

SQLite に以下のテーブルを作成します(`backend/app/database.py`)。

- `tsume_problems` — 問題(SFEN 初期局面、USI 手順の JSON、タグ、解説、お気に入り)
- `problem_results` — 問題ごとの解答履歴(正解/不正解、解答時間、ミス数)
- `time_attack_results` — タイムアタック結果
- `opening_lines` — 戦型別定跡ライン(SFEN + USI 手順 + タグ)
- `opening_sources` — 取り込み元ファイルとライセンス情報
- `opening_positions` — 定跡ラインの各 ply の SFEN
- `opening_moves` — 各手の USI と指し手前後の SFEN
- `opening_tags` — 中飛車・棒銀・向かい飛車などの簡易分類タグ
- `book_sources` — 外部定跡データの出典・ライセンス・取り込みメタデータ
- `book_positions` — 外部定跡データの局面 SFEN
- `book_moves` — 外部定跡データの候補手 USI・評価値・深さ

## 既知の制限

- **正解判定は登録された手順との完全一致**です。別解(複数の詰み手順)があっても登録手順以外は不正解になります。サンプル問題は初手の別解がないことを検証済みです。
- **玉方の応手は登録された手を自動実行**します(最善応手の自動探索はしません)。サンプル問題は応手が唯一の合法手であることを検証済みです。
- 合法手判定(二歩・行き所のない駒・自玉放置など)は tsshogi に準拠しています。**打ち歩詰めの禁止は移動候補のハイライトには反映されません**が、正解判定が手順照合のため実害はありません。
- タイムアタックで問題数が選択数に満たない難易度では、同じ問題が循環して出題されます。
- 定跡学習MVPは固定サンプルとインポート済みSFEN/USIデータを扱えます。分岐対応を見据えたツリー構造ですが、現時点のUIは各局面の先頭候補手を期待手として扱います。AI評価値・外部棋譜DB連携・KIF/CSA取り込みは未対応です。

## 今後の拡張案

1. 定跡学習の拡張: `opening_lines` へのDB化、分岐候補の選択UI、手順再生、到達局面の復習
2. 別解(複数解)対応: 解答判定をサーバー側の詰み探索で行う
3. 盤面エディタの合法配置チェック強化とKIF/CSA読み込み
4. 棋譜(KIF/CSA)の読み込み・再生
5. 間隔反復(SRS)による出題スケジューリング
6. 駒画像への差し替え(`ShogiBoard.tsx` の `PieceFace` を変更)

## 外部定跡データの出典管理と取り込み準備

新ペタショック定跡 233万局面などの大規模な外部定跡データは、容量とライセンス確認の都合によりリポジトリへ含めません。今回の実装では、将来の本取り込みに備えて、出典管理、ライセンス表示、dry-run、少量サンプル取り込みのみを扱います。大量取り込み、局面検索 API、候補手 UI、分岐ツリー、次の一手問題化は次 PR 以降に分けます。

### dry-run の例

```bash
cd backend
PYTHONPATH=. python -m app.importers.yaneuraou_book \
  tests/fixtures/yaneuraou_book_sample.db \
  --name "Sample YaneuraOu Book" \
  --license-name "MIT License" \
  --license-text "MIT License" \
  --dry-run
```

`--dry-run` は SHA-256、読み込み局面数、候補手数、不正行数、重複局面数を表示しますが、SQLite には書き込みません。

### サンプル取り込みの例

```bash
cd backend
PYTHONPATH=. python -m app.importers.yaneuraou_book \
  tests/fixtures/yaneuraou_book_sample.db \
  --name "Sample YaneuraOu Book" \
  --version fixture \
  --source-url "https://example.test/book" \
  --license-name "MIT License" \
  --license-text "MIT License" \
  --limit 2
```

`--limit` は取り込む局面数を制限します。pytest 用 fixture は数局面の小さなファイルだけを置き、大規模な `book.db` 本体はコミットしない方針です。

### 局面候補手 API

`GET /api/book/candidates?sfen=<current_sfen>` は、`book_positions.sfen` に完全一致する局面を検索し、紐づく `book_moves` を `sort_order` などで安定ソートして返します。候補がある場合は `found: true` と `candidates` 配列に `move_usi`、`rank`、`score`、`depth`、`source_name`、`license`、`source_url` などを含め、候補がない場合は `found: false` と空配列を返します。

### ライセンス表示方針

取り込み時に `book_sources` へ出典 URL、ライセンス名、ライセンス本文、著作権表示、ファイル名、SHA-256、局面数、候補手数を保存します。フロントエンドの「データ出典」ページと `/api/licenses` は、この情報を表示して外部定跡データの出典・ライセンスを確認できるようにします。

## やねうら王定跡からの学習用サンプル抽出

大量のやねうら王定跡をそのまま学習 UI に出すと、特定戦型や類似局面に偏りやすくなります。そこで、取り込み済みの `book_sources` / `book_positions` / `book_moves` を元に、戦型別に上限を設けた学習用サンプルを `learning_samples` に抽出できます。まずは 233万局面の全件運用ではなく、1万局面・10万局面程度のサンプル作成から始める想定です。

事前にやねうら王定跡を取り込んだ後、対象の `book_source_id` を指定して実行します。

```bash
cd backend
python -m app.scripts.extract_learning_samples \
  --source-id <book_source_id> \
  --limit 10000 \
  --per-opening-limit 500 \
  --seed 1 \
  --dry-run
```

主なオプション:

- `--limit`: 抽出する学習用サンプルの全体上限です。10,000 や 100,000 など、小さめの単位から検証できます。
- `--per-opening-limit`: 1 戦型あたりの抽出上限です。棒銀・中飛車・四間飛車・向かい飛車・矢倉・角換わり・相掛かり・横歩取りなど、同じ戦型に偏りすぎないために使います。
- `--seed`: 同じ入力データと条件で再現性のある抽出順にするための乱数 seed です。
- `--dry-run`: DB に保存せず、戦型別の候補件数・抽出予定件数・未分類件数だけを表示します。

戦型分類は、YaneuraOu book の候補手と SFEN から判断できる範囲の簡易ルールです。履歴がない局面や代表的な手掛かりがない局面は `unclassified` / `未分類` として扱い、抽出処理自体は失敗させません。保存時は同じ `book_source_id` の既存サンプルを置き換えるため、条件を変えた再抽出ができます。

抽出済みサンプル数は API から確認できます。

```bash
curl http://localhost:8000/api/book/sources/<book_source_id>/learning-samples/summary
```

レスポンスには戦型別件数、未分類件数、対象 book source の出典情報が含まれます。出典・ライセンス表示は既存の book source 表示に従い、学習 UI で利用する場合も `book_sources` の `source_url` / `license_name` / `copyright_notice` を併記してください。UI への本格表示は今後、定跡候補表示や戦型別学習画面から `learning_samples` を参照する形で拡張できます。

## Third-party data and licenses

This application can import tsume-shogi puzzle data from [`tokuhirom/tanuki-tsume-shogi`](https://github.com/tokuhirom/tanuki-tsume-shogi).

- Target files: `puzzles/1.json`, `puzzles/3.json`, `puzzles/5.json`
- Copyright (c) 2026 tokuhirom
- Licensed under the MIT License
- See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for the full license text.

## 通常DBと次の一手専用DB

通常起動では用途の異なる2つのSQLite DBを使用します。

- `backend/data/shogi.db` (`SHOGI_DB_PATH`): 詰め将棋、Wikipedia等の定跡学習、履歴、統計、タイムアタック
- `backend/data/next_move.db` (`NEXT_MOVE_DB_PATH`): `book_sources`、`book_positions`、`book_moves`、`learning_samples`

外部定跡・学習サンプルAPI (`/api/book/candidates`、`/api/book/sources*`、`/api/learning-samples*`) は専用DBだけを参照します。`/api/licenses` は通常DBの詰め将棋出典と専用DBの外部定跡出典を合成します。専用DBは通常起動時に読み取り専用で開かれ、存在しない場合も空ファイルを作りません。欠落、SQLite接続エラー、必須テーブル・カラム欠落、サンプル0件の場合、backend自体は起動し、該当APIだけが原因を含むHTTP 503を返します。

パスは `backend/.env.example` の環境変数で個別に変更できます。外部定跡のimportとsample抽出は `NEXT_MOVE_DB_PATH` のDBを明示的に作成・更新します。

```bash
cd backend
NEXT_MOVE_DB_PATH=./data/next_move.db python -m app.importers.yaneuraou_book <book.db> \
  --name "YaneuraOu Book" --source-url <URL> --license-name <LICENSE>
NEXT_MOVE_DB_PATH=./data/next_move.db python -m app.scripts.extract_learning_samples \
  --source-id <ID> --limit 10000 --per-opening-limit 500 --seed 1
python scripts/validate_next_move_db.py ./data/next_move.db
```

検証コマンドはintegrity/foreign key、孤立参照、件数、出典・ライセンス、重複を読み取り専用で確認します。通常の復旧確認では `--expected-learning-samples` を省略し、サンプル件数を固定しません。抽出件数を厳密に確認する場合は、抽出コマンドの出力に表示された `selected` 件数を `--expected-learning-samples` に指定してください。元データの戦型別候補数と `--per-opening-limit` によって実際の抽出件数が変わるため、固定値10,000は指定しません。差し替え時はbackendを停止し、新DBを別名で生成・検証してから `next_move.db` を置換してください。自動テストとE2Eは数局面だけのYaneuraOuテキストfixtureから一時DBを生成し、正式な10,000件DBを複製しません。大規模な外部定跡DBは容量と再配布ライセンスの確認が必要なためGit管理せず、出典・ライセンス情報を `book_sources` に必ず登録してください。

`learning_samples.id` は再生成で変わり得る内部IDです。履歴などの永続参照には、出典、正規化SFEN、候補手定義(または対象手)、問題定義バージョンから作る安定キーを利用します。抽出件数やseedなどの抽出条件は問題キーに含めず、監査メタデータとして分離します。
