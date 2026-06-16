# 将棋学習アプリ(個人利用)

将棋盤 GUI で駒を操作しながら詰め将棋を学習するローカル Web アプリです。
第1段階(詰め将棋 MVP)として、詰め将棋・タイムアタック・復習・学習履歴を実装しています。

- フロントエンド: React + Vite + TypeScript + [tsshogi](https://www.npmjs.com/package/tsshogi)(局面管理・合法手判定)
- バックエンド: FastAPI + SQLite + [python-shogi](https://pypi.org/project/python-shogi/)(問題データの検証)
- 局面は SFEN、指し手は USI 形式で保存

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

# フロントエンド (8件: 局面・指し手ロジック)
cd frontend && npx vitest run

# 型チェック + ビルド / Lint
cd frontend && npm run build && npm run lint

# E2E (Playwright)
cd frontend && npm run e2e
```

### E2Eテスト (Playwright)

E2Eテストは、ブラウザ上でホーム、詰め将棋プレイ、問題作成UI、盤面からの手順記録、作成問題のプレイ、編集・削除、タイムアタックの基本表示を自動確認するためのテストです。

初回セットアップ:

```bash
cd frontend
npm install
npx playwright install chromium
```

実行コマンド:

```bash
# ヘッドレス実行
npm run e2e

# ブラウザを表示して実行
npm run e2e:headed

# 失敗時などのHTMLレポート確認
npm run e2e:report
```

Playwright設定で backend と frontend を自動起動します。事前に手動起動する必要はありません。E2E実行時の backend は `frontend/.e2e/shogi-e2e.db` を `SHOGI_DB_PATH` に指定するため、通常利用のSQLite DBとは分離されます。テストは開始前・終了後にタイトルが `[e2e]` で始まる問題を削除します。

Windows / macOS / Linux のいずれでも動くように、Playwright の `webServer.command` では `SHOGI_DB_PATH=... command` のようなシェル依存の環境変数指定を使わず、`frontend/scripts/start-e2e-backend.mjs` と `frontend/scripts/start-e2e-frontend.mjs` から Node.js 経由で環境変数を渡しています。WindowsでPythonランチャー名が異なる場合は、`PYTHON` 環境変数に `python` / `py` / 仮想環境内の実行ファイルを指定してから `npm run e2e` を実行してください。ポートを変更したい場合は `E2E_BACKEND_PORT` / `E2E_FRONTEND_PORT` を指定できます。

## 画面

| 画面 | 内容 |
| --- | --- |
| ホーム | 各機能へのメニュー(定跡学習は Coming Soon) |
| 詰め将棋 | 難易度(1/3/5手詰)・タグで絞り込み、問題選択、ランダム出題、ヒント、答えを見る、解説、お気に入り |
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

## DB スキーマ

SQLite に以下のテーブルを作成します(`backend/app/database.py`)。

- `tsume_problems` — 問題(SFEN 初期局面、USI 手順の JSON、タグ、解説、お気に入り)
- `problem_results` — 問題ごとの解答履歴(正解/不正解、解答時間、ミス数)
- `time_attack_results` — タイムアタック結果
- `opening_lines` — 第2段階の戦型別定跡学習用(SFEN + USI 手順 + 手ごとのコメント。テーブルのみ作成済み)

## 既知の制限

- **正解判定は登録された手順との完全一致**です。別解(複数の詰み手順)があっても登録手順以外は不正解になります。サンプル問題は初手の別解がないことを検証済みです。
- **玉方の応手は登録された手を自動実行**します(最善応手の自動探索はしません)。サンプル問題は応手が唯一の合法手であることを検証済みです。
- 合法手判定(二歩・行き所のない駒・自玉放置など)は tsshogi に準拠しています。**打ち歩詰めの禁止は移動候補のハイライトには反映されません**が、正解判定が手順照合のため実害はありません。
- タイムアタックで問題数が選択数に満たない難易度では、同じ問題が循環して出題されます。
- 戦型別定跡学習は未実装です(`opening_lines` テーブルと拡張しやすい構成のみ用意)。

## 今後の拡張案

1. 戦型別定跡学習(矢倉・角換わり・四間飛車など): `opening_lines` への定跡ツリー登録、手順再生、次の一手クイズ、分岐表示
2. 別解(複数解)対応: 解答判定をサーバー側の詰み探索で行う
3. 盤面エディタの合法配置チェック強化とKIF/CSA読み込み
4. 棋譜(KIF/CSA)の読み込み・再生
5. 間隔反復(SRS)による出題スケジューリング
6. 駒画像への差し替え(`ShogiBoard.tsx` の `PieceFace` を変更)
