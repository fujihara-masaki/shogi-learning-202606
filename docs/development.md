# 開発ガイド

## 技術構成

- `backend/`: FastAPI、SQLite、python-shogi。局面はSFEN、指し手はUSIで保存
- `frontend/`: React 19、TypeScript、Vite、tsshogi
- `backend/tests/`: pytestによるAPI、DB migration、import、seed/artifact検証
- `frontend/src/**/*.test.*`: Vitestによるロジック／コンポーネント検証
- `frontend/e2e/`: Playwrightによるブラウザ検証

依存関係は `backend/requirements.txt` と `frontend/package-lock.json` を基準にします。Python自体の対応バージョンはリポジトリで固定されていません。lockfileではVite 8がNode.js `^20.19.0 || >=22.12.0`、ESLint 10と関連パッケージが `^20.19.0 || ^22.13.0 || >=24` を要求します。そのため、Lint・ビルド・テストを含む開発環境全体の共通範囲は**20系の20.19.0以上、22系の22.13.0以上、または24以上**です。これは依存関係が許容する範囲であり、この文書更新時に実際に確認した環境はLinux x86_64、Node.js 24.15.0、npm 11.4.2です。

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

## Windows PowerShellでの初期セットアップと起動

以下はWindows実機では未確認です。PowerShellを開き、リポジトリルートで初期セットアップを行います。

```powershell
py -3 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
npm ci
Pop-Location
```

ターミナル1はリポジトリルートからbackendを起動します。

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

別のターミナル2はリポジトリルートからfrontendを起動します。

```powershell
Set-Location frontend
npm run dev
```

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

以下はリポジトリルートから個別にコピーして実行する例です。Bashのサブシェルを使うため、作業ディレクトリはコマンド終了後にルートへ戻ります。

```bash
# backend
(cd backend && .venv/bin/python -m pytest)

# frontend unit tests
(cd frontend && npx vitest run)

# type checkを含むproduction build
(cd frontend && npm run build)

# lint
(cd frontend && npm run lint)
```

テスト件数は固定せず、コマンドが検出した現在のsuiteを基準にします。backendのpytest fixtureは一時ディレクトリの両DBパスを環境変数へ設定します。

## E2E（Playwright）

初回のみ `frontend/` でブラウザを用意します。

```bash
cd frontend
npx playwright install chromium
```

通常利用のサーバーを停止し、リポジトリルートから次のBash例を実行します。`env -u` はこのコマンドに限って通常用の両DBパスと残存するCORS設定を除外し、`PYTHON` はセットアップ済み仮想環境の絶対パスになります。両DBパスを未指定にするため、起動スクリプトは `frontend/.e2e/` の通常DBを使い、小規模fixtureから次の一手専用DBを毎回生成します。

```bash
(cd frontend && \
  env -u SHOGI_DB_PATH -u NEXT_MOVE_DB_PATH -u SHOGI_CORS_ORIGINS \
    CI=1 \
    PYTHON="$PWD/../backend/.venv/bin/python" \
    E2E_BACKEND_PORT=18000 \
    E2E_FRONTEND_PORT=15173 \
    npm run test:e2e)
```

例の `CI=1` はPlaywrightの `reuseExistingServer` を無効にします。18000／15173が未使用であることを事前に確認してください。使用中ならテストは既存サーバーを再利用せず失敗するため、別の未使用ポートを選びます。`SHOGI_CORS_ORIGINS` を除外すると起動スクリプトがE2E frontendポートに合う値を生成します。`env` で与えた変更はコマンド終了後のシェルには残りません。E2Eが作成する両DBはGit管理外です。

`NEXT_MOVE_DB_PATH` を明示すると起動スクリプトはfixture DBを生成しません。事前作成済みDBを意図的に検証する場合だけ使用し、親のnpmプロセス（`frontend/`）ではなくbackend子プロセスの作業ディレクトリが `backend/` であることを踏まえ、曖昧な相対パスではなく絶対パスを指定してください。

テストの性質は2種類あります。

- `shogi-learning.spec.ts` と `appearance.spec.ts` は自動起動したbackend、小規模seed／fixtureを使うシナリオに加え、エラーや特定分岐を作るため一部APIをブラウザ側でモックします。
- `next-move.spec.ts` は次の一手API、履歴、復習などを広くモックし、UI状態と契約を決定的に検証します。実DB全件の統合試験ではありません。

`npm run test:e2e:headed` でブラウザ表示、`npm run test:e2e:report` でHTMLレポートを開けます。WindowsでE2Eを実行する場合も `PYTHON` に仮想環境のPythonを指定し、通常DB関連の環境変数を一時退避して終了後に復元してください。Windows実機でのE2E手順は未確認です。

## APIとDB

backend起動後のOpenAPI UIは <http://localhost:8000/docs> です。主要ルーターは詰め将棋、統計、タイムアタック、定跡、外部定跡候補、次の一手です。静的なAPI一覧を複製せず、実装と同期するOpenAPIを参照してください。

- 通常DB: 問題、解答・タイムアタック・次の一手履歴、戦型カタログ、定跡手順
- 次の一手専用DB: 外部定跡の出典・局面・候補手、抽出run、学習サンプル。アプリ実行時は読み取り専用

スキーマと運用手順は [データ管理ガイド](data-management.md) を参照してください。
