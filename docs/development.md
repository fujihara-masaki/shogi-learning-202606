# 開発ガイド

## 技術構成

- `backend/`: FastAPI、SQLite、python-shogi。局面はSFEN、指し手はUSIで保存
- `frontend/`: React 19、TypeScript、Vite、tsshogi
- `backend/tests/`: pytestによるAPI、DB migration、import、seed/artifact検証
- `frontend/src/**/*.test.*`: Vitestによるロジック／コンポーネント検証
- `frontend/e2e/`: Playwrightによるブラウザ検証

依存関係は `backend/requirements.txt` と `frontend/package-lock.json` を基準にします。Python自体の対応バージョンはリポジトリで固定されていません。フロントエンドはlockfileのVite 8がNode.js `^20.19.0 || >=22.12.0` を要求します。

## 環境変数

| 変数 | 既定値 | 用途 |
| --- | --- | --- |
| `SHOGI_DB_PATH` | `backend/data/shogi.db` | 通常DB |
| `NEXT_MOVE_DB_PATH` | `backend/data/next_move.db` | 次の一手専用DB |
| `SHOGI_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | CORS許可origin（カンマ区切り） |
| `VITE_API_BASE` | `http://localhost:8000` | フロントエンドのAPI接続先 |
| `E2E_BACKEND_PORT` | `8000` | E2E用backendポート |
| `E2E_FRONTEND_PORT` | `5173` | E2E用frontendポート |
| `PYTHON` | Windowsは`python`、その他は`python3` | E2E起動スクリプトが使うPython |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | 未設定 | 既存Chromiumを明示する場合 |

バックエンドにはdotenv読込処理がありません。`backend/.env.example` を `.env` にコピーするだけでは反映されないため、起動プロセスの環境に設定します。Viteは `frontend/.env` の `VITE_` 変数を読み込みます。

### macOS/Linuxで別パスを使う例

`backend/` で実行します。

```bash
SHOGI_DB_PATH=./data/dev.db \
NEXT_MOVE_DB_PATH=./data/next_move.db \
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

### Windows PowerShellで別パスを使う例

`backend` ディレクトリで実行します。

```powershell
$env:SHOGI_DB_PATH = ".\data\dev.db"
$env:NEXT_MOVE_DB_PATH = ".\data\next_move.db"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

別のPowerShellで `frontend` ディレクトリへ移動し、`npm run dev` を実行します。

## 開発・テストコマンド

以下はリポジトリルートからの実行例です。

```bash
# backend
cd backend && .venv/bin/python -m pytest

# frontend unit tests
cd frontend && npx vitest run

# type checkを含むproduction build
cd frontend && npm run build

# lint
cd frontend && npm run lint
```

テスト件数は固定せず、コマンドが検出した現在のsuiteを基準にします。backendのpytest fixtureは一時ディレクトリの両DBパスを環境変数へ設定します。

## E2E（Playwright）

初回のみ `frontend/` でブラウザを用意します。

```bash
cd frontend
npx playwright install chromium
```

通常利用のサーバーを停止し、通常とは異なる未使用ポートを明示して実行する安全側の例です（`frontend/`で実行）。

```bash
E2E_BACKEND_PORT=18000 \
E2E_FRONTEND_PORT=15173 \
SHOGI_DB_PATH=./.e2e/shogi-isolated.db \
NEXT_MOVE_DB_PATH=./.e2e/next-move-isolated.db \
npm run test:e2e
```

ただし `NEXT_MOVE_DB_PATH` を明示すると起動スクリプトはそのDBを生成しません。上の例では事前に小規模DBを準備する必要があります。通常は**両DB変数を未設定**にすると、スクリプトが `frontend/.e2e/shogi-e2e.db` を通常DBに使い、fixtureから `frontend/.e2e/next-move-e2e.db` を毎回生成して次の一手DBに使います。未使用ポートだけを指定する推奨例は次の通りです。

```bash
E2E_BACKEND_PORT=18000 E2E_FRONTEND_PORT=15173 npm run test:e2e
```

Playwright設定はCI以外で `reuseExistingServer: true` です。指定ポートで既に応答するサーバーがあると、自動起動スクリプトを通らず、そのサーバーと接続済みDBをテスト対象にしてしまいます。したがって通常サーバーを停止し、未使用ポートを選び、`SHOGI_DB_PATH` / `NEXT_MOVE_DB_PATH` がシェルに残っていないことを確認してください。E2Eが作成する通常DBと次の一手DBはGit管理外です。

テストの性質は2種類あります。

- `shogi-learning.spec.ts` と `appearance.spec.ts` は自動起動したbackend、小規模seed／fixtureを使うシナリオに加え、エラーや特定分岐を作るため一部APIをブラウザ側でモックします。
- `next-move.spec.ts` は次の一手API、履歴、復習などを広くモックし、UI状態と契約を決定的に検証します。実DB全件の統合試験ではありません。

`npm run test:e2e:headed` でブラウザ表示、`npm run test:e2e:report` でHTMLレポートを開けます。WindowsでPython解決に失敗する場合は `frontend` で次のように指定します。

```powershell
$env:PYTHON = "..\backend\.venv\Scripts\python.exe"
$env:E2E_BACKEND_PORT = "18000"
$env:E2E_FRONTEND_PORT = "15173"
npm run test:e2e
```

## APIとDB

backend起動後のOpenAPI UIは <http://localhost:8000/docs> です。主要ルーターは詰め将棋、統計、タイムアタック、定跡、外部定跡候補、次の一手です。静的なAPI一覧を複製せず、実装と同期するOpenAPIを参照してください。

- 通常DB: 問題、解答・タイムアタック・次の一手履歴、戦型カタログ、定跡手順
- 次の一手専用DB: 外部定跡の出典・局面・候補手、抽出run、学習サンプル。アプリ実行時は読み取り専用

スキーマと運用手順は [データ管理ガイド](data-management.md) を参照してください。
