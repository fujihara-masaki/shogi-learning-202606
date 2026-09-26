# 将棋学習アプリ

将棋盤を操作しながら、詰め将棋・定跡・次の一手を学ぶための**ローカル利用前提**の Web アプリです。FastAPI と SQLite のバックエンド、React/Vite のフロントエンドを別々のターミナルで起動します。認証や公開サーバー向けの構成は備えていません。

## 主な機能

- **詰め将棋**: 1・3・5手詰、絞り込み、ヒント、解説、お気に入り
- **定跡学習** (`/openings`): 同梱・DB由来の手順を盤上で学習。局面の分岐選択、通過済み分岐の切り替え、本線の一手／末尾までの再生、変化一覧からの局面移動に対応
- **次の一手** (`/next-move`): 専用DBの学習サンプルを戦型別に出題し、登録候補内での順位を表示
- **タイムアタック、復習、学習記録**: 詰め将棋と次の一手の結果を記録・振り返り
- **問題作成** (`/problem-editor`): 盤面編集、SFEN入出力、解法記録、検証、保存
- **表示設定** (`/settings`): 文字駒／Shogi Images の画像駒と、標準盤／画像盤テーマを選択（ブラウザのローカルストレージに保存）

画面ごとの操作、判定の意味、制限は [利用ガイド](docs/user-guide.md) を参照してください。

## 必要環境

- Python 3 と `pip`（依存関係の下限は [`backend/requirements.txt`](backend/requirements.txt) を参照）
- Node.js **20.19.0以上、または22.12.0以上**（lockfileに含まれる Vite 8 の要件）と npm
- 次の一手を利用する場合は、別途準備した `learning_samples` 入りの SQLite DB

この文書更新時の確認環境は Linux x86_64、Python 3.14.4、Node.js 24.15.0、npm 11.4.2 です。対応OSや、それ以外のバージョンでの動作を保証する記載ではありません。

## セットアップと起動

リポジトリのルートから、macOS/Linux の例です。Python の仮想環境を推奨します。

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm ci
```

ターミナル1（リポジトリルートから）:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

ターミナル2（リポジトリルートから）:

```bash
cd frontend
npm run dev
```

ブラウザで <http://localhost:5173> を開きます。API仕様は起動後の <http://localhost:8000/docs> で確認できます。Windows PowerShell の手順、接続先やポートの変更は [開発ガイド](docs/development.md) を参照してください。

> `backend/.env.example` は設定項目の見本です。バックエンドは `.env` を自動読込しないため、環境変数は起動するシェルで設定してください。フロントエンドは Vite が `frontend/.env` を読み込みます。

## 初回起動と学習データ

- 通常DB `backend/data/shogi.db` は初回起動時に作成され、スキーマ、動作確認用の `[sample]` 詰め将棋7問、戦型カタログ、同梱の定跡手順が投入されます。
- 定跡学習にはフロントエンドの固定手順に加え、通常DBの seed／canonical Wikipedia artifact／任意にインポートした手順が表示されます。同梱artifactは監査済みの個別手順であり、各戦法全体を網羅するものではありません。
- 次の一手専用DB `backend/data/next_move.db` は自動作成されません。未配置、不正、必須テーブル不足、`learning_samples` が0件の場合もアプリ自体は起動し、次の一手関連API／画面だけが利用不可になります。
- 大規模外部定跡や「10,000件」などは同梱件数ではありません。再配布条件を確認したデータを利用者が取り込み、サンプル抽出する際の指定例です。

2つのDBの役割、準備、検証、バックアップ、安全な差し替えは [データ管理ガイド](docs/data-management.md) を必ず確認してください。通常のセットアップや一時的なエラーの解消目的でDBを削除しないでください。

## 基本的な使い方

1. ホームから「詰め将棋」「定跡学習」「次の一手」を選びます。
2. 駒はクリックして移動先を選ぶか、ドラッグして動かします。持ち駒は駒台で選んでから移動先を選びます。
3. デスクトップでは上部メニュー、モバイルでは主要項目と「その他」の下部メニューを使います。「その他」から「表示設定」「データ出典」も開けます。
4. 次の一手を使う前に、専用DBが準備済みであることを確認します。

## 開発・テスト

各コマンドはリポジトリルートから実行します。テスト件数は更新で変わるため固定していません。

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npx vitest run
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm run test:e2e
```

E2Eは専用の小規模DBを生成しますが、既存サーバー再利用設定があります。通常利用中のサーバーやDBとの混同を避ける安全な実行方法、APIモックを使う検証との違いは [開発ガイドのE2E節](docs/development.md#e2eplaywright) を参照してください。

## ドキュメント

- [ドキュメント索引](docs/README.md)
- [利用ガイド](docs/user-guide.md)
- [開発ガイド](docs/development.md)
- [データ管理ガイド](docs/data-management.md)

既存の実装計画・監査資料は、現行仕様ではなく検討時点の記録を含みます。分類と読み方はドキュメント索引にまとめています。

## ライセンス・出典

- アプリ本体のソースコード: GPL-3.0-only。詳細は [`LICENSE`](LICENSE)
- 取り込みデータ: 各提供元のライセンスに従い、出典・ライセンス情報をDBとアプリの「データ出典」に保持
- Wikipedia／Wikibooksを参考にした戦型カタログと定跡artifact: CC BY-SA。個々の収録範囲はデータ内の provenance／coverage 情報を参照
- Shogi Images の駒・盤素材: CC0 1.0
- `tokuhirom/tanuki-tsume-shogi` から取り込み可能な問題: MIT License

著作権表示、加工内容、素材ごとの詳細は [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) を参照してください。ライセンス確認が済んでいない外部データはリポジトリに含めません。
