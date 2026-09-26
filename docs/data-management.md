# データ管理ガイド

## データとDBの区分

| データ | 保存先／供給元 | 初回起動 |
| --- | --- | --- |
| 詰め将棋、学習履歴、タイムアタック、次の一手の解答履歴 | `SHOGI_DB_PATH`（既定 `backend/data/shogi.db`） | DB作成。空なら`[sample]` 7問を投入 |
| 戦型カタログ、定跡手順 | 通常DB、フロントエンド固定手順 | カタログ、38件のローカルseed、同梱canonical artifactを適用 |
| 外部定跡候補、学習サンプル | `NEXT_MOVE_DB_PATH`（既定 `backend/data/next_move.db`） | 作成・更新しない。実行時は読み取り専用 |
| Shogi Images | `frontend/public/assets/shogi/` | リポジトリに同梱 |

件数は現在のseed実装を説明するもので、ユーザーがデータを追加・削除したDBを上書きして固定件数へ戻す契約ではありません。Wikipedia/Wikibooks由来の戦型カタログは名称と短い説明の入口で、canonical artifactは出典上で確認できた手順だけを収録します。戦法全体の網羅を意味しません。

## 定跡手順の取り込みと検証

### Canonical Wikipedia artifact

D1b schemaに従うartifactをリポジトリルートで検証します。D0のlegacy監査JSONは入力対象外です。

```bash
backend/.venv/bin/python backend/scripts/validate_wikipedia_opening_artifact.py path/to/artifact.json
```

成功は終了コード0と `{"valid": true, "errors": []}`、schema／semantic違反は1、ファイル・UTF-8・JSON・bundled schemaなどの運用エラーは2です。検証だけではDBへ適用しません。

### SFEN/USI定跡

再利用許諾を確認したファイルを `data/openings/*.sfen` に置きます。形式は次のいずれかです。

```text
startpos moves 7g7f 3c3d 2h5h
sfen <盤面> <手番> <持ち駒> <手数> moves ...
```

`backend/` で通常DBの対象パスとライセンスを明示して取り込みます。

```bash
SHOGI_DB_PATH=./data/shogi.db .venv/bin/python scripts/import_openings.py \
  ../data/openings --license-name CC0 --license-url https://example.com/license
```

各手の前後SFEN、USI、出典、ライセンス、簡易分類を保存します。分類不能な手順は「未分類」になります。KIF/CSAの取り込みには対応していません。

## 外部定跡と次の一手サンプル

大規模な外部DBは同梱していません。容量だけでなく再配布・利用条件を確認し、出典URL、ライセンス、著作権表示を登録してください。以下は `backend/` で実行します。

### 書き込まずに調査

```bash
NEXT_MOVE_DB_PATH=./data/next_move-staging.db \
PYTHONPATH=. .venv/bin/python -m app.importers.yaneuraou_book /path/to/book.db \
  --name "Book name" --license-name "License name" --dry-run
```

`--dry-run` はSHA-256、局面・候補手・不正行・重複の件数を表示し、DBへ書き込みません。

### 小規模取り込みとサンプル抽出

本番パスへ直接書かず、staging DBを作成します。

```bash
NEXT_MOVE_DB_PATH=./data/next_move-staging.db \
PYTHONPATH=. .venv/bin/python -m app.importers.yaneuraou_book /path/to/book.db \
  --name "Book name" --source-url https://example.com/book \
  --license-name "License name" --limit 100

NEXT_MOVE_DB_PATH=./data/next_move-staging.db \
.venv/bin/python -m app.scripts.extract_learning_samples \
  --source-id 1 --limit 100 --per-opening-limit 20 --seed 1
```

`--limit` は上限であり、標準搭載件数ではありません。候補数、戦型ごとの上限、重複などにより実件数は変わります。抽出を試すだけなら `extract_learning_samples` にも `--dry-run` を付けます。同一sourceの保存済みサンプルは再抽出時に置き換わるため、既存DBで安易に試さないでください。

### 検証

`backend/` で読み取り検証します。

```bash
.venv/bin/python scripts/validate_next_move_db.py ./data/next_move-staging.db
```

integrity／foreign key、孤立参照、必須項目、出典・ライセンス、重複、件数を確認します。通常は期待件数を固定しません。厳密に照合する必要がある場合だけ、抽出結果の `selected` を `--expected-learning-samples` に渡します。

## 詰め将棋データの取り込み

本アプリは `tokuhirom/tanuki-tsume-shogi` の `puzzles/1.json`、`3.json`、`5.json` を取り込めます。利用条件と著作権表示は [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) を確認してください。取り込み前に通常DBをバックアップし、対象パスを明示します。スクリプトはディレクトリを展開しないため、JSONファイルまたはURLを引数ごとに指定します。`--dry-run` でも通常DBの初期化処理を呼ぶため、試行時も必ず隔離した `SHOGI_DB_PATH` を指定してください。

```bash
cd backend
SHOGI_DB_PATH=/tmp/shogi-tanuki-import.db \
  .venv/bin/python scripts/import_tanuki_tsume.py \
  /path/to/puzzles/1.json \
  /path/to/puzzles/3.json \
  /path/to/puzzles/5.json \
  --dry-run
```

上はmacOS/Linux向けの検証例です。`/tmp/shogi-tanuki-import.db` は新規の一時パスに置き換え、通常DBを指定しないでください。本取り込みでは、バックアップ後に意図する通常DBのパスへ変更し、`--dry-run` を外します。コマンドの引数詳細は `.venv/bin/python scripts/import_tanuki_tsume.py --help` で確認してください。

## バックアップ、差し替え、復旧

DBの削除は通常セットアップや一般的な復旧手段ではありません。`shogi.db` には自作問題・お気に入り・履歴があり、削除すると失われます。`next_move.db` にも取り込み元・ライセンス・抽出結果があります。

1. backendを停止し、書き込み中でないことを確認します。
2. シェルの `SHOGI_DB_PATH` と `NEXT_MOVE_DB_PATH` を確認します。未設定なら既定パスです。
3. 対象DBを日時付きの別ファイルへコピーします。同じディレクトリの `-wal` / `-shm` がある状態なら、単純コピーよりSQLiteのbackup機能を使用してください。
4. 次の一手DBは別名のstaging DBとして生成・検証してから、停止中に置き換えます。
5. backendを起動し、`/api/health`、通常画面、次の一手画面を別々に確認します。

SQLite CLIを利用できる場合の安全なバックアップ例です。

```bash
sqlite3 backend/data/shogi.db ".backup 'backend/data/shogi-20260926.db'"
sqlite3 backend/data/next_move.db ".backup 'backend/data/next_move-20260926.db'"
```

次の一手DBの欠落・不正・サンプル不足は、backend全体の起動失敗とは区別されます。ログと画面の復旧案内を確認し、パス修正、staging DBの再生成、検証済みバックアップへの差し替えを選びます。通常DBを巻き添えで削除しないでください。
