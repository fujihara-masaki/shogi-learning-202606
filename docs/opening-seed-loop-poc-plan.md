# Wikipedia Seed拡張ループ：1件限定PoC実行計画

作成日：2026-11-09 JST。対象：`fujihara-masaki/shogi-learning-202606`。
基盤PR：[#78](https://github.com/fujihara-masaki/shogi-learning-202606/pull/78)。
参照HEAD：`b438609f4bd7c04ff812d64e7de74718b935a39f`。
本書は**実行前の計画**であり、L2b実装・新規出典レビュー・Seed追加・PoC実行の完了報告ではない。
作成時にGitHubで #78 の Open / Draft / 未マージと上記HEADの一致を確認した。
将来の実行時には再照合し、この確認や過去のusageを開始許可に流用しない。

## 1. 目的・範囲と正本

Wikipediaの1記事・1節または密接な分岐群について、出典確認、Codexによる構造化抽出、
独立した出典レビュー、canonical artifactへの追加、検証、必要時の限定修正、Draft PR作成までを実証する。
Seedの実装タスクは1件、同時実装も1件、PoC最終成果物は**Draft・未マージのPR 1件**とする。
候補に根拠がなければ保留し、成功件数を作るために別候補へ自動で移らない。

複数候補の連続処理、複数Stacked PRの自動生成、Ready化、マージ、auto-mergeは対象外。
基盤 #78 に依存する子ブランチは用いるが、これは複数候補の自動stack管理の実証ではない。
今回の文書作成では本番artifact、fixture、通常DB、backend/frontend、runner、既存文書を変更せず、
Wikipediaの新しい手順抽出、Seed実装、実usage取得、推論turnの起動を行わない。#78 のHEADも更新しない。

| 正本・参照先 | 本書との対応 |
| --- | --- |
| [運用基盤計画](opening-seed-loop-plan.md) | L0/L1/L2a、CLI、usage、状態・保存・復帰、CI、後続L2bの正本。本書は1件PoCの実行条件を追加する |
| [Wikipedia import計画](opening-branch-learning-wikipedia-import-plan.md) §10〜12 | provenance、D1b/D1c、PR-E2h/E2i、Seed受入の正本。古い推奨commandより現行script・基盤profileを優先する |
| [キュー見本](opening-seed-loop-queue.example.json) | 1候補の調査待ち見本。`enabled:false`、revision/節/接続親等は未確定。実行済みキューと扱わない |
| [開発ガイド](development.md) | 依存導入、通常DB隔離、E2E起動の参照先。PoC検証は基盤のPython 3.12 / Node 24 profileを使用する |
| [CI workflow](../.github/workflows/seed-validation.yml) | 全base・Draft対応のvalidation-only CIと証拠保存の実装。推論やPR作成は行わない |
| [`scripts/seed_loop/`](../scripts/seed_loop/)・[関連試験](../scripts/tests/) | 実装の裏付け。文書上の将来契約を、動作済み機能に読み替えない |

schema、coverage列挙値、CLI/終了コード、D1b/D1cの定義はここで再設計しない。
以下の「採用済み」は参照HEADの仕様、「PoC提案」は未実装・未採用の追加条件、
「未決」は実行前に判断記録が必要な事項を表す。計画書の作成だけではPoC提案の採用を意味しない。

## 2. 実装済み基盤とL2bの不足機能

| レイヤー・機能 | 参照HEADで実装済み／確認先 | PoCで追加する最小機能（未実装） |
| --- | --- | --- |
| L0：作業・出典契約 | 節/密接な分岐群、A優先、独立レビュー証拠、調査待ちキュー見本 | 確定した1 taskだけを読み、未確定・複数taskを拒否するconsumer |
| L1：検証 | `validation.py` がbundled artifactを動的列挙して実D1b CLI実行。`full` は基盤unittest、D1b、backend、Vitest、lint、build、Chromium | 新しい対象差分に対する独立期待値・旧版からの移行試験を追加。D1cは既存backend比較を利用する |
| L1：CI | Draft含む全baseの`pull_request`、`contents:read`、Linux full、Windows基盤試験、ログ等14日保存 | 対象PR/HEADの実run起動・完了照合。CI自体には推論・GitHub書込権限を追加しない |
| L2a：実usage adapter | `usage.py`：stdio handshakeと`account/rateLimits/read`、bucket/window選択、25/30%判定、unknown/stale停止 | 採用した監視方針の固定と、LLM turn中の監視・中断・終了確認 |
| L2a：checkpoint・pause/resume | `controller.py` / `state.py`：原子的保存、OS lock、入力digest、検証stageの停止復帰、明示simulated replay | 取得・抽出・レビュー・変更・修正・remote操作を管理する別のtask台帳と、副作用ごとの復帰処理 |
| L2a：所有プロセス監督 | `supervisor.py` / `process_tree.py` / `ownership.py`：検証子の所有確認、cleanup、lease/journalによる重複拒否 | 推論子とremote turnへの適用を別途実証。検証子の終了保証をremote推論の停止保証へ流用しない |
| L2b：出典・抽出・修正 | **未実装**。`source_review:not_performed`、`repair_attempts:0`は実行機能ではない | 取得証拠、Codex抽出、別担当レビュー、許可pathへの適用、限定修正と証拠の結合 |
| L2b：GitHub操作 | **未実装**。stateの`pr:null`、runnerにcommit/push/PR操作なし | 1ブランチ・1 Draft PR、既存PR照合、応答喪失時の照合、CI待ちのcheckpoint |

既存 `run` / `resume` は固定検証のみであり、このまま新Seedを実行できるCLIとは記載しない。
既存のv1 stateはvalidation/validatedを前提とする。L2b用の状態形式・CLIは後続実装で版管理し、
v1のphaseを無断で増やしたり、予約fieldを成功へ書き換えたりしない。

## 3. Step 1：実usage取得と監視条件の決定

### 3.1 確認済み事実と証拠の位置付け

次は依頼時に提示された**過去の観測スナップショット**である。本書作成のための再接続・推論は行わない。
管理LinuxのEOF履歴は基盤計画とも対応する。Windowsの後続観測は本書で履歴として追記し、
#78 当時の「live疎通未確認」を当時の誤記として書き換えない。

| 環境 | 過去の観測 | 判断できること／限界 |
| --- | --- | --- |
| 管理Linux | Codex CLI `0.159.0-alpha.3`、`CODEX_HOME`がread-only、App ServerのSQLite初期化に失敗、`usage_unknown / eof`。新規処理を開始せず停止 | 当該環境では開始許可なし。SQLite失敗の観測とEOFを記録するが、全EOFの原因が同じとは断定しない |
| Windowsローカル | Codex CLI `0.167.0`。Pythonから`codex.cmd`を明示して起動成功、実App Server usage API応答取得成功 | read-only取得経路の疎通実績。controllerによる推論・修正・停止復帰成功の証拠ではない |
| Windowsの枠 | `codex` bucketの`primary`は10,080分（週次）、`secondary:null` | primary/secondaryの名前だけで5時間枠/週次枠を決めない。未提供枠の使用率を0%と推定しない |
| 2026-11-09の値 | 週次使用率1%、当時の次回resetは2026-11-12 13:43:51 JST | 過去値であり、将来の開始・再開を許可しない。reset時刻から0%を推定しない |
| 同応答の診断 | primary単独の一時的な読み取り診断では判定上の停止理由なし。厳格な2枠監視では`window_unavailable`のため停止 | 単独診断で停止理由なしでも、2枠必須方針の開始許可にはならない |

依頼には生応答ファイル・checksum・正確な取得時刻の証拠一式は添付されていないため、
上表は利用者申告の履歴として扱う。PoCでは実行環境・CLI版・取得時刻・選択bucket/window・
sanitize済み応答・正規化結果・判定・設定hashを新たに保存し、履歴の1%をfixture fallbackに使わない。

### 3.2 監視方針の比較（採用判断は未決）

| 案 | 安全性と開始条件 | 必要な追加試験 | 未解決の制限・判断 |
| --- | --- | --- | --- |
| A：既定のprimary/secondary両枠必須を維持 | 両方の有効なfresh値が必要。片方nullでもfail-closed | 既存の複数枠・null・閾値・stale/reset試験を維持し、実応答形を用いたsanitize済み回帰と実環境preflightを確認 | 現在報告されたWindows応答では停止し、PoCを進められない。**採用変更まではこの案が有効** |
| B：APIが提供する枠だけを明示条件付きで監視 | 実行前にAPI/CLI・account条件・bucket・期待window集合を確認し、採用記録と設定を固定。毎回の欠落を自動で監視対象から除外しない | primaryのみ/secondaryのみ/両方、明示nullとkey欠落、不正値、bucket不一致、提供集合の増減、版変更、25/30境界、120秒・reset跨ぎ、resume、Windows起動を検査 | APIが表さない制限枠は監視できず、2枠の保証と同等ではない。nullが恒常的な非提供か一時障害かは1応答で判別できない。利用者の方針採用判断が必要 |

既存設定は非空の `windows:["primary"]` 等を受け付け、`normalize`も明示選択を扱う。
**設定可能であることと、その単独監視を運用として採用済みであることは別**である。
案Bでは「非提供と確認した枠」を別記し、key欠落・空集合・意味不明のnullを自動許可しない。
期待集合やCLI/API条件の変化を検出したら停止して方針を再確認し、実行中の自動縮退は行わない。
提供集合の監査・非提供根拠の保持は現adapterにない追加要件である。

推奨は、まず案Aを維持したまま案Bの根拠・試験・制限をレビューし、案Bを採用する場合だけ
PoC固有の明示設定として固定すること。採用前にprimary単独診断を実行許可へ昇格させない。

#### 3.2.1 L2b-0の受入要件：正規化前の枠集合監査

案Bの採否は未決のままとする。L2b-0では、案Bの実行を有効化する前提として、以下の監査と
模擬応答による試験を必須受入要件に含める。試験成功だけでは案Bを採用したことにならず、
未採用の案B設定では開始を拒否する。既存L2a adapterや既定2枠の契約を今回変更しない。

現行 `normalize` は設定で選択したwindowだけを出力するため、正規化結果から提供集合を復元できない。
L2b-0は、要求IDを照合済みの**正規化前のAPI応答**から、既存規則で選んだbucket全体を監査し、
監査成功後に既存の正規化・25/30%判定へ渡す。`rateLimitsByLimitId`に指定bucketがなければ停止し、
互換viewへ逃げない。選択外windowも監査対象とし、`windows:["primary"]`だけを見て許可しない。

| raw応答の状態 | 監査記録と停止条件 |
| --- | --- |
| 有効なwindow object | `primary` / `secondary`各keyの存在と型、有効値を記録し、有効objectの集合を提供集合Sとする。採用済み期待Sと完全一致し、その全枠を監視する必要がある |
| 明示null | keyが存在して値がnullである状態として記録する。非提供の根拠と利用者の採用記録がその枠について揃う場合だけ、案Bの期待状態にできる。null単独・過去の低使用率では許可しない |
| キー欠落 | 明示nullと区別して記録し、期待上非提供とした枠でも停止する。欠落から非提供を推定しない |
| 不正object・未知の形式 | 不正な使用率、型、bucket、未知のwindow形式等は停止。objectを非提供へ分類し直して監視から除外しない |
| 集合・状態の変更 | Sの増減、null↔object、null↔欠落、window key集合・CLI/API条件の変化は停止する。新たなsecondaryが有効objectになった場合も自動追加で続行しない |

採用記録には期待S、各windowの期待状態（object/明示null）、非提供根拠、CLI/API・account条件、bucket、
判断者・日時、設定hashを持たせる。各readではrawのkey存在/状態一覧、S、取得時刻、sanitize済み資料の
保管先/SHA-256、監査結果・停止理由、正規化結果を同じrequest/attemptへ結合する。
sanitizeでnullと欠落の区別や選択外枠を失わないことを確認し、認証値・生応答の無差別出力は行わない。
空のS、期待Sとの不一致、根拠/採用記録/監査証拠の欠落もfail-closedとする。

L2b-0の必須試験は、primaryのみ/secondaryのみ/両方、明示nullと欠落、不正object、Sの増減、
Sが同じでもnullから欠落へ変わる場合、選択外枠の出現、版/bucket変化、監査証拠の保存失敗、resumeを含む。
特に「primary単独の正規化結果は同じでもrawのsecondaryが変化した2応答」で開始を拒否できることを検査する。
正常時は監査後に既存25/30%・freshness/reset判定が必ず実行され、監査成功だけで開始できないことも確認する。
停止後は原因解消・期待状態の再確認、集合変更時は利用者による方針再採用と設定更新を要し、
旧証拠を失効させて新validation runで再検証する。fresh raw応答の再監査と明示resumeなしに再開しない。

### 3.3 維持する停止条件とL2b提案

採用済みの使用済み**絶対割合25%以上は新規開始禁止、30%以上は`budget_stop`**を維持する。
監視枠のいずれかが該当すれば停止し、追加消費割合や残量へ読み替えない。
unknown/unsupported、取得不能、不正値、120秒超の古い値、未来時刻、観測後reset跨ぎはfail-closed。
停止後は自動復帰せず、明示resume時にfresh readする。残stageが0でも再評価する。

PoC提案では新規開始の単位を、抽出・独立レビュー用推論・修正turn・artifact適用・commit/push/PR等の
副作用を伴うstageまで広げ、各開始前と結果保存後に確認する。停止要求・証拠保存・終了確認は継続可能とする。
25%以上では次stageへ進まず、30%以上/unknown等では実行中推論にも中断を要求し、途中出力を未採用で隔離する。
PoC初期値の提案はusage poll 15秒、1 turn上限120秒、read timeoutは既存15秒。
これは未実装の値であり、採用時に設定hashへ含める。応答中断時はremote turnの終端状態と所有子群の終了を
両方確認し、不明なら停止を維持する。通常の手動pauseは上限内でdrainする。
計測遅延、read中の消費、cancel到達遅延による超過があり、厳密な30%消費上限は保証しない。
ローカルApp Server子の終了だけをremote推論停止の証拠にしない。

## 4. Step 2：Wikipedia候補の確定

最初の候補は**PR-E2i以降の横歩取り△2三歩の変化**に固定する。
キュー見本の `investigate-e2i-yokofudori-2c-pawn` を調査IDとして引き継ぎ、確定後も実装taskを増やさない。

参照HEADの既存artifactは
[`backend/app/wikipedia_opening_artifacts/yokofudori-2c-pawn.json`](../backend/app/wikipedia_opening_artifacts/yokofudori-2c-pawn.json)、
line/record keyは `wikipedia.yokofudori.pawn-2c`、記事は「横歩取り2三歩」。
26 node、semantic main 16手、最大深さ23手、4 leafであり、これは既存データの読取確認である。

| 既存接続点・終端 | 既存値 | PoCでの扱い |
| --- | --- | --- |
| `main-16` | `B*2e`（16手目△2五角）、親`main-15`。to SFENは `lnsgk1snl/1r4g2/p1pppp1pp/6R2/1p5b1/2P6/PP1PPPP1P/1SG6/LN2KGSNL b B2P 17` | import計画の17手目▲3二飛成／▲3六飛と後続は**調査候補名**。本文・親との接続・終端確認後に1節/密接な群だけを選ぶ |
| `bishop-4e-23` | 23手目▲4八角まで | 既存範囲として保持。以後の着手を推測しない |
| `rook-2h-13` / `rook-2f-13` | 親`main-12`、13手目▲2八飛／▲2六飛で終了 | E2hの当該出典箇所に14手目以降の具体手順がないという既存記録を維持。相掛かりという説明から補完しない |

固定revision **`92929426` は既存の出典候補**である。今回必要な後続着手が存在すると断定しない。
PoC実行時に取得した固定版と必要な範囲を照合し、別revisionが必要なら差異・選定理由を記録して再レビューする。
記事・節・revision・接続親・範囲が確定しない場合は調査待ちのまま停止する。
既存の `complete_for_cited_sequence` は既引用範囲の完了であり、記事・小節・E2全体の完了ではない。

PoCで保存する証拠一式は次とする。取得した原文はGit管理外に保管し、PRへの大量転載を避ける。

| 証拠 | 必須内容と照合方法 |
| --- | --- |
| 取得原文・固定版 | 要求URL/最終URL、HTTP結果、取得日時（UTC offset付き）、記事title、oldid/revision、本文中の版ID、節階層・根拠段落。版ID不一致・不完全本文は停止 |
| 資料SHA-256 | 取得原文の実byte列のhashとbytes数。抽出用に整形した本文には別hash・変換方法・元資料hashを持たせる。再取得で変われば同一資料とみなさない |
| 接続と収録範囲 | 基準artifactのHEAD/hash、line key、親node key/to SFEN、最初の追加手、各着手の順序・USI・from/to SFEN・根拠位置、各branchの収録終端と未収録境界 |
| 構造化抽出 | 入出力hash、prompt/モデル・実行設定、thread/turn ID、A/B/C/M判定、候補artifact hash。既存canonical schemaへ変換し、別canonical schemaを作らない |
| 独立レビュー | §5.4で採用するAI別セッションまたは人間レビューの方式・担当、確認日時、原資料hash、親・各手・終端との対応、明示的な合否・承認記録、不一致点、候補artifact/hashと対象diff hash |

Step 2は範囲を確定する事前調査、Step 3の独立レビューは生成された全追加edgeを照合する受入gateである。
同一担当の自己確認やD1b合法性成功で独立レビューを代替しない。
本文に明示されない中間手・応手を、図、一般知識、別記事、engine評価から補完しない。
このPoCはAの本文明示列だけを対象とし、B/Mしか得られない場合は保留して別計画へ分ける。Cからmoveを作らない。

## 5. Step 3：L2b最小実装と実行境界

### 5.1 1件のcontroller経路（未実装）

以下をcontrollerが順番に管理する。外部担当のレビュー待ちもcheckpointとし、レビュー未了を通過させない。
実装時にCLI・台帳schema・固定worker APIを定義するまで、以下を現行CLIの動作例として使用しない。

| stage | PoCで実装する範囲 | 非対象・停止境界 |
| --- | --- | --- |
| usage・task開始 | Step 1の採用設定、1 taskの確定入力、親HEAD、許可path、task hashを照合。開始前にattemptを保存 | 調査待ち見本の直接実行、複数task、無制限の任意shell commandを拒否 |
| 出典・構造化抽出 | 固定版取得証拠を結び、Codexの実turnで1候補を生成。途中出力は隔離し、成功・保存済み結果だけ採用候補へ | 推論失敗時の手動生成物への無記録置換、未明示手の補間なし |
| 独立出典レビュー | §5.4で採用した方式の担当が原文・親・全追加手・終端を照合。承認記録を台帳に取り込み、担当・対象hash・明示合格を検査 | 方式未決・自己承認・単なる合法性確認・過去review流用では通過しない。不一致は適用前に停止 |
| canonical適用 | 確定した許可pathだけにpatch適用し、既存stable key/tree・分類・帰属を保持。適用前後hashを保存 | 別line、新schema、DB migration、汎用UI/importer/validatorの拡張は含めない。必要なら保留 |
| 検証 | 実D1b、D1c、関連backend/frontendと最終full profileを既存runnerで実行 | 診断parserエラー、not_run/skip/pendingを成功扱いしない。通常DBは操作しない |
| 限定修正 | 診断・元資料・許可pathに基づき同じtaskだけを修正。回数/原因/差分を保存し再レビュー・再検証 | 出典不明を知識で埋める修正、試験の弱体化、上限到達後の別runによる回数回避なし |
| 停止・再開 | 手動pause、usage、通信断、異常終了を記録。所有確認・入力一致・fresh usage後に明示resume | 不明なremote結果やcleanupを成功へ書き換えない。入力変更時は古い成功を継承しない |

許可pathはStep 2完了時に具体化する。Seed部分の初期候補は対象artifact、対象専用backend/Vitest/Chromium試験、
必要な新規旧版snapshot・監査文書だけ。既存fixtureの書換え、本番DB、対象外lineは許可しない。
次の実装PRで追加するL2bコード・基盤試験のpathも事前に列挙し、実行中workerが自分のcontrollerを変更しない。

L2b台帳にはtask/run/attempt ID、親HEAD、controllerコードhash、設定/task/queue hash、原資料hash、
抽出・review・適用前後・修正ごとのhash、thread/turn ID、検証run ID、usage履歴、停止理由、
repair累計、remote intent/result、PR URL/番号、CI run/job/checkout SHAを結び付ける。
既存のGit管理外 `.seed-loop/` の原子的保存・lock方式を再利用し、機密値・環境変数一覧を保存しない。
取得原文・詳細ログの保管先とhash、PRに載せる短い監査要約を分け、CIの14日期限前に必要証拠を退避する。

### 5.2 入力変更・異常終了と復帰

L2aはコード/artifact/config/HEADが変われば `inputs_changed` となり、新run IDでの検証を要求する。
L2bのartifact適用・修正は意図した入力変更なので、変更前成功を持ち越すためにidentityを上書きしない。
**1つのPoC task台帳に、内容固定ごとの別validation runを紐付ける**。修正後は新IDでfull検証し、
taskの修正累計とremote履歴は維持する。実行途中の予期しないファイル変更・親HEAD変更は停止する。

副作用前にintentと入力hashを保存し、結果の永続化前に落ちた処理は結果不明とする。
検証だけは既存の所有終了確認後に再実行できるが、推論は保存したthread/turnの状態を照合してから再試行を判断する。
patch/commit/push/PRは実ファイル・Gitオブジェクト・remote状態を照合し、未完了と確定するまで再発行しない。
台帳破損・未確定journal・所有子残存では停止し、lock削除や新ID/別portで迂回しない。
検証子のPID名前空間不整合等は既存の起動拒否原因を保持し、隔離・権限を変更して回避しない。

### 5.3 検証・限定修正

対象のbackend試験 `backend/tests/test_yokofudori_2c_pawn_artifact.py` と
Vitest `frontend/src/shogi/yokofudori2cPawnArtifact.test.ts`、
Chromium `frontend/e2e/shogi-learning.spec.ts` の既存検査を拡張する。
D1bはschema/合法性/tree/coverage/metadata、D1cはruntime投影の比較という責務を維持する。
source reviewは別gateであり、artifact由来の期待値だけでは抽出精度を証明しない。

新edgeをpython-shogi/tsshogi双方で再生し、独立したSFEN・手番・持駒・親子・本線/表示順期待値と照合する。
基準HEADの実artifactから新しい旧版snapshotを取得してchecksumを記録し、fresh、初回upgrade、再実行で
既存26 keyのID/direct parent/comment、対象外line、分類を保持することを検査する。E2f/E2g fixtureも維持する。
新範囲のcoverage/出典/終端、360px・keyboard・分岐選択/jump/undo/終端停止・帰属表示を検査する。
最後は依存導入済みPythonでrootから `python -m scripts.seed_loop validate --profile full --run-id ID` を実行し、
PoC controller側でusage gateと検証中の監視を管理する。validation-onlyの成功だけではusage監視成功と扱わない。
DB隔離、固定command、全gateの詳細は基盤計画と開発ガイドを参照する。

| 修正上限 | 位置付け・根拠 |
| --- | --- |
| 最大3回 | 既存基盤計画の後続worker初期案。現runnerに実装された上限ではない |
| **最大2回を推奨** | 今回の1件PoC提案。初回生成を除き追加の修正turn最大2回、合計生成最大3回。予算・原因追跡・小さい差分の維持を優先する |
| 共通停止条件 | 同一原因で改善なし2回、または採用上限到達で停止。明らかな出典不足は修正を待たず保留。通信/環境障害を内容修正で直そうとしない |

2回/3回の採用は未決。実行前に固定し、resumeやvalidation run更新でresetしない。
修正attemptはturn起動前に消費を保存し、応答喪失も未消費へ戻さない。
内容が変われば対象diffの独立reviewを取り直す。インフラ再試行はrepairと別記し、同じ操作の
自動連続再試行は行わず、原因解消と結果照合後の明示resumeだけにする。

### 5.4 独立出典レビューの方式選択・承認・停止再開

PoCで**AIの別セッション方式と人間レビュー方式のどちらを採用するかは未決**である。
実行前に利用者が方式・担当・独立性の条件を選び、判断者・日時・理由・本計画の固定版を採用記録へ残す。
方式の採用記録と、個別の抽出結果に対する出典レビュー合格記録は別物であり、両方をcontrollerが検査する。
いずれの方式も原文・親・全追加edge・終端の確認条件は同じで、レビュー合格はReady化やmerge承認を意味しない。

| 方式 | 承認記録・合格条件 | 不合格・未完了時の停止と再開 |
| --- | --- | --- |
| AIの別セッション | 抽出セッションと異なるthread/session ID、モデル/設定、prompt hash、入力資料・artifact・diff hash、出力と判定・時刻を保存。原資料を直接参照して照合した明示的な合格と、そのsessionを担当として採用した記録を結合する。同じAI/モデルである場合の限界も記載する | 不合格、不一致、応答喪失、独立sessionを確認できない場合はartifact適用・PR作成前に停止。結果不明なら同じturnを照合し、必要な再レビューを記録する。内容修正後は新hashについて別セッションで再レビューし、明示合格後だけresumeできる |
| 人間レビュー | 抽出担当と異なる確認者を特定し、本人の判断と確認できるレビュー記録の所在（コメントURLまたは保管ファイル/hash）、日時、原資料・artifact・diff hash、各手/親/終端の照合結果、明示的な承認を保存。PR作成前にも取得できる形式を使い、沈黙を承認とみなさない | 不合格/差戻し、返答待ち、本人性・対象hashを照合できない記録では停止。指摘を保存し、内容修正後は新hashに対する人間の再承認を得る。待ち時間経過やAIへの自動切替では再開しない |

共通して不合格理由・対象hash・判定者・修正履歴を保持し、不合格を削除して合格で上書きしない。
修正可能な不一致は残り修正枠内で直し、再レビューする。本文根拠不足は保留、修正上限到達は§8.2に従う。
レビュー方式・担当の変更は利用者の新たな採用記録を要し、不合格を回避するための無記録切替は認めない。
修正・原資料・接続親・対象diffが変われば旧承認を失効させる。記録の不足だけを復旧した場合も、
本人/セッション・入力hash・明示合格を照合するまで停止し、未確認の承認を推定しない。
再開には有効な採用記録と現入力に対する合格、所有終了確認、fresh usage、明示resumeが必要である。
両方式の合格/不合格/結果不明/古いhash/方式未採用のgateを模擬試験し、実PoCは選んだ方式だけを実証する。

## 6. Step 4：Draft PR作成・CI確認

### 6.1 計画書PR・L2b-0・PoC実装PRの依存と取り込み

本書の提出PRは [#79](https://github.com/fujihara-masaki/shogi-learning-202606/pull/79) であり、
現在のbaseは `codex/wikipedia-seed-loop-foundation`、親HEADは
`b438609f4bd7c04ff812d64e7de74718b935a39f`（#78）である。
今回レビューの開始HEADは `f67640b88251f37a3c35920456278b40596212c4` で、今回の修正も#79だけへpushする。
**現段階で#78へのpush、#78/#79のmerge、retarget、新規PR作成は行わない。**

将来の準備は次の依存順を推奨する。以下は手動で準備する依存関係の計画であり、controllerによる
複数Stacked PR自動生成の対象追加ではない。#79を取り込まずに#78だけから実装を開始しない。

| 対象 | 計画書の取り込み方・固定する親 | Draft段階のbaseと将来のマージ先 |
| --- | --- | --- |
| 計画書 #79 | #78の固定HEADから作成。本書のレビュー後、使用する#79のhead commitをPとして固定し、ファイルSHA-256も記録する。今回の開始HEADをレビュー後の最終版とみなさない | 現在のbaseは#78のbranch。今は未マージ。将来の統合先Iへretarget・再検証後に取り込む |
| L2b-0準備PR | Pから専用branchを作り、本書をGit履歴ごと継承する。Pのancestryと本書hashを検査し、#79へコードをpushしない | 未マージ依存を比較する場合のbaseは#79のbranch。ここへmergeして#79を更新せず、将来の統合先Iへretargetして取り込む |
| PoC実装PR | 独立提出するL2b-0のレビュー済み固定head Lから専用branchを作り、本書と準備コードを履歴ごと継承する。必要な後続workerも確定してから実行する | 未マージ依存を比較する場合のbaseはL2b-0のbranch。将来の統合先Iへretargetして再検証する。PoC成果物はDraft・未マージを維持し、mergeは本PoCの対象外 |

L2b-0を独立PRにせず同じPoC branchで準備する場合は、Pをそのbranchの固定親とし、準備完了時の
コードHEAD/hashも台帳へ保存する。いずれも#79は計画書のみとし、別の正本コピーを作らない。
依存PRが既に統合先Iへ取り込まれている場合は、その内容を含むIの固定HEADから子branchを作り、
元のP/Lと取り込みcommitの対応・本書hashを照合する。履歴の異なる古い親へ自動的に戻さない。
本書を将来変更する必要が生じた場合は変更理由・差分をレビューして計画版を更新し、旧版を黙って置換しない。

将来の統合先Iの候補は、#78の現在のbase **`claude/clever-hopper-bphezm`** とする。
これは依存PRの比較用baseとは別で、default branchとは仮定しない。実際の取り込み先・方式は将来別途承認して固定する。
取り込みを承認した段階では、#78をIへ取り込む→#79をIへretarget・再検証して取り込む→
独立したL2b-0をIへretarget・再検証して取り込む、の順とする。PoC PRも親の取り込み後にIへretarget・再検証するが、
Draft・未マージを維持する。子PRを#78/#79等の依存branchへmergeして親PRのHEADを更新する手順にはしない。
この将来手順は今回のmerge/retargetを許可するものではない。

開始前にP/L・本書hash・基盤SHA、実際のbase名/期待SHA/実SHA、実装コードHEADを依存台帳へ保存する。
開始・resume・push/PR作成前・CI照合時は直接のbaseだけでなく、未マージの#78/#79/L2b-0各refも
固定値と照合する。直接のbaseが動いていなくても上流の計画版・基盤が変われば停止する。
親の更新・merge/squash・base変更時は新規stageを止め、旧検証証拠を失効させる。
再開は、取り込み元/先と方式の承認記録、新しい親SHAでの再統合、本書の継承・内容hashと依存差分の確認、
出典の接続親とreview対象hashの再照合、新validation runによる全gate、最新head/baseのCI取得の順で行う。
squash等でancestryが変わる場合は元commitと取り込みcommit・本書hashの対応も記録する。
古いhead単体やmerge結果の成功を新しい組合せへ持ち越さず、fresh usageと明示resumeを要求する。

### 6.2 固定した親に対するPR作成・CI確認

§6.1で選んだ依存経路の実際のbase/固定親SHAを使用する。#78のHEADは基盤の識別子として残すが、
計画書・L2b-0を含む実行時の親HEADと取り違えない。
GitHubのbaseは可変refなので、台帳に固定SHAを持つだけでは固定されない。開始・resume・push前・PR作成前・
CI照合時にGitHub refを再読し、期待SHAとの差異で停止する。親の更新・merge・削除時に自動retarget/rebaseしない。
合意した再統合後に新しい親SHAを記録し、出典接続・全検証・CI証拠を取り直す。

1. 親をfetchしてSHAとancestryを確認し、別のPoC専用branchを作る。#78 のbranchへpushしない。
   head branch名・repo・task IDを台帳へ固定し、current diffが許可pathに収まることを確認する。
2. **commit/push/PR作成前に**変更ファイル一覧、base名/期待SHA/実SHA、ローカルHEAD・予定head branch、
   diff check、必須検証と独立reviewの対象hashを報告する。push後はremote head SHAも照合する。
3. GitHub上で全状態（open/closed/merged）の既存PRを確認する。repo＋head branch＋base＋task IDを照合し、
   同一taskの別base PRも調べる。一致1件なら再利用、複数・不整合・closed/mergedなら停止して判断する。
4. task単位の排他と永続intentを保存し、Draft指定で1回だけ作成する。PR本文に依存 #78/#79と該当するL2b-0、計画版P・固定親SHA、
   task ID、出典/抽出/review/検証の証拠と制限を載せる。番号・URL・base/head SHA・Draft/未マージを再取得して保存する。
5. 応答喪失・timeout・controller終了後は、作成済みか不明なままcreateを再送しない。
   同じtask/head/baseの既存PRをGitHubで再照合する。存在しないと確定しない通信断では停止を維持する。
6. `seed-validation.yml` の実runと両jobが対象PRの最新head/baseに対応することを確認する。
   PR head、base、`GITHUB_SHA`、実checkout（通常merge結果）、run ID/attemptを別項目で保存する。
   過去HEADの成功やhead単体ローカル成功をmerge結果のCI成功に読み替えない。

CIはDraftを除外しておらず全baseで起動するが、定義があるだけでは起動成功ではない。
使用credentialのイベント抑制（例：`GITHUB_TOKEN`）、GitHub承認待ち、workflow/branchの所在を確認する。
未起動/承認待ち/skip/pendingは未完了。PoC提案のCI待ち上限はrun検出5分・完了60分とし、
超過時はcheckpointして停止、後で同じPR/runを照合してresumeする。上限は実装時に採用して設定へ固定する。
default branch導入前の `workflow_dispatch` を回避経路として前提にしない。
CI失敗ではjobログを保存し、内容原因は残り修正枠内で直して新HEADの全gateを再取得する。
環境・通信原因は原因解消後に同じSHAのrerunを明示実行し、attemptを区別する。
必須gateが成功してもPRはDraft・未マージを維持し、Ready/merge/auto-mergeを呼ばない。

## 7. Step別の開始・完了・停止条件と証拠

全Step共通で、設定採用記録、1 task制約、固定親HEAD、現在入力hash、所有確認、許可pathを検査する。
Step 1以外の開始・resumeにもStep 1のfresh usage判定を適用する。

| Step | 開始条件 | 完了条件 | 停止条件 | 保存証拠 |
| --- | --- | --- | --- | --- |
| 1：usage | 監視方針を採用済み、CLI/API/実行環境を特定。read-only取得を実行する段階であること | 採用した全監視枠のfresh値が有効・25%未満。設定と採用判断が結合 | EOF/unknown/unsupported、不正/古い値、枠不一致、25%以上/30%以上。方針未決では後続へ進まない | CLI/OS、時刻、bucket/window/duration/reset、sanitize済み応答、判定・設定hash |
| 2：候補 | Step 1通過、候補は横歩取り△2三歩の1件のみ、参照artifact/lineを固定 | 固定原文/revision/節/親/範囲が確定し、Aとして追加可能な連続列が根拠付きで特定 | 取得不能・版不一致・親不明・本文に手順なし・B/M/Cのみ。候補変更で迂回しない | 原文とSHA-256、取得結果、節、親key/SFEN、境界、事前確認者・結果 |
| 3：実装・検証 | L2b最小機能と試験が準備済み、Step 2確定、修正上限とpath固定、独立review方式・担当の採用記録あり | Codex抽出、現入力の独立review合格記録、canonical差分が対応しD1b/D1c・関連試験・最終fullすべて成功。停止復帰証拠がある | 方式未決・不合格/レビュー待ち、抽出不一致、検証失敗、通信断、controller終了、入力/親変更、所有不明、修正上限。原因別に保留/修正待ち | task/attempt/turn台帳、入出力/diff hash、方式採用・review承認記録、修正累計、各validation run/log/result/cleanup |
| 4：Draft PR | Step 3完了、最新usage許可、変更ファイル/base/HEAD報告済み、remote親/head一致・重複照合済み | Draft PRが1件だけ存在し、最新head/baseのLinux full・Windows基盤jobが成功、証拠保存済み、未マージ | PR結果不明、重複/remote不一致、親変更、CI失敗/未起動/待ち上限、Draft解除/merge検出 | remote intent/result、PR照合、URL/番号/Draft状態、base/head/checkout SHA、CI run/job/attempt・artifact |

## 8. 試験計画とPoC受入基準

### 8.1 継承する試験と追加する試験

基盤試験の `test_seed_loop.py` はusage境界・protocol・検証・保存・入力変更・復帰、
`test_seed_loop_boundaries.py` は所有子cleanup・controller強制終了・read中pause・末尾resume等、
`test_seed_loop_preflight_locks.py` はlaunch lock順序/上限とLinux起動前前提確認を扱う。
これらはL2a検証経路の試験であり、新しいLLM/PR経路の試験済み証拠ではない。

| ケース | 追加試験・期待する観測 | 受入上の停止・復帰 |
| --- | --- | --- |
| 正常系1件 | 模擬workerで順序・証拠hashを検査した後、実usage・実Codex抽出・独立review・実検証・実Draft PR/CIを1経路で確認 | 2件目のtask・PR作成呼出は0。最終taskとPRのhash対応が追える |
| usage不明/不正/古い値 | EOF、null、API error、bucket/window欠落、不正値、120秒超、未来、reset跨ぎ。24.99/25/29.99/30%境界、枠集合変化 | 未開始turn/副作用0、実行中turn中断・途中出力隔離、fresh readと明示resumeまで停止 |
| 案Bの正規化前監査（L2b-0受入） | §3.2.1のraw応答を用い、正規化結果が同じでも選択外枠の出現・null/欠落・状態/集合変更を検知する。未採用の案B、監査保存失敗、resumeも検査 | 監査成功と有効な採用記録がなければ停止。既存の閾値判定も必須。採否未決のまま模擬試験できるが、案Bを有効化しない |
| 出典取得不能・版違い | HTTP失敗、通信切断、別revision、壊れた/部分本文、資料hash不一致 | canonical変更/推論による補完0。原資料確定・再レビュー後に再開 |
| 抽出不一致 | 原文にない着手、親/順序/成/駒打ち/終端違い、review対象diff hash違い | D1bが合法でも適用拒否。残り修正枠内で修正・独立再レビュー |
| 独立review方式・承認 | §5.4の両方式について未採用、自己レビュー、不合格、記録喪失/本人・session不明、古いhashの承認を模擬する | canonical適用/PR作成を拒否。方式採用記録と現入力の明示合格、fresh usage、明示resumeでだけ復帰 |
| 検証失敗 | D1b違反/運用error、D1c差分、両ライブラリ不一致、旧ID/comment退行、E2E失敗 | 失敗以後は未実施。上限内修正後に新validation run、試験の弱体化なし |
| 通信断・結果保存失敗 | turn送信/応答、push/PR作成直後、CI取得中、atomic replace失敗を注入 | 成功を捏造せず結果不明で保存。remote照合前に再送しない。秘密値をログへ出さない |
| controller異常終了 | turn起動後、patch適用後、commit/push/PR直後、結果保存の前後で強制終了 | lease/所有子とremote turnを照合し重複実行0。不明時停止、確定成功は同一入力なら再利用 |
| pause競合・復帰 | usage read中、attempt予約前後、最終stage後にpause。2 worker/resume競合、壊れた台帳も試す | 既存A〜E/lock境界を保持。停止解除をreset経過で推測せず、修正回数も維持 |
| 親HEAD/入力変更 | Step 3途中・push直前・PR作成後・CI待ちに親refを変更。#79の計画版変更、依存PR取り込み後のretarget/squashも一時repoで検査 | 子の旧検証を失効させ新規stage停止。自動rebase/retargetなし。§6.1の継承/hash確認と再統合後に全検証 |
| CI失敗・未起動 | failed/cancelled/skip/pending、承認待ち、run未検出、古いhead成功、job欠落、rerunを模擬 | 成功に変換しない。同一PRに復帰し新HEAD/run attemptを正しく照合 |
| 重複PR防止 | 作成応答喪失後に既存PRが見つかる/不存在/照合不能/複数一致、closed/merged PR、二重起動 | 一致PR再利用、create再送を抑止。照合不能・複数・履歴衝突は停止。実repositoryに重複PRを作って試さない |

異常注入は模擬usage・模擬LLM・模擬GitHubと一時repoを基本とし、`simulated:true`と実行環境を記録する。
1件の実経路では少なくとも抽出結果保存後のpause→別controllerプロセスでの明示resumeを実証し、
成功済みturnの再実行なし・最新usage再読・最終PR1件を示す。
強制終了と応答喪失の境界は模擬試験で広く検査し、実PoCで観測していない障害を実証済みと呼ばない。
実usageを消費する障害の大量反復や、GitHub上の破壊的な異常注入は行わない。

### 8.2 最終判定

| 判定 | 条件 |
| --- | --- |
| **成功** | Step 1〜4がすべて完了。controllerが実抽出から実装・レビューgate・検証・Draft PR/CIまでを1 taskとして管理し、停止→別プロセスresume・証拠連結・重複防止が確認できた。実Draft PR1件、必須CI成功、未マージ |
| **部分成功** | 根拠付きSeedと必須検証・Draft PR1件は揃ったが、Codexが人手相当で各作業を個別実行しcontroller管理/復帰を証明できない、またはcontrollerは途中まで実証できたが最終PR/CIに未到達。完了Stepと不足証拠を列記し、全体成功と呼ばない |
| **保留** | 監視方針未決、usage不明/予算停止、出典不足、レビュー待ち、親変更、環境/通信障害、CI未起動等で安全に停止。解消条件を特定し、成功実績には数えない |
| **失敗** | 根拠なし着手の採用、停止条件の無視、重複PR、対象外変更、無断Ready/merge等の制約違反、または確定した検証/抽出不一致を修正上限内に解消できない。証拠を保全し新規処理を止める |

制約違反があれば他の成果より失敗判定を優先する。安全停止だけのrunは保留、途中成果がある場合も
未完了理由を併記する。模擬replay成功や過去PRの検証件数だけで実PoC成功としない。
案Bを採用して成功した場合も「明示したAPI提供枠内の監視」と制限を残し、全制限枠の監視成功と表現しない。

## 9. 確定事項・未決事項と次の最小PR

| 項目 | 現在の扱い・実行前に必要な判断 |
| --- | --- |
| 基盤/候補/成果物 | 参照HEADのL0/L1/L2a、横歩取り△2三歩候補、Seed task1件・Draft PR1件・未マージを確定条件とする |
| usage方針 | 既定2枠必須は有効。API提供枠のみを監視する案Bの採否・非提供判定の根拠が未決。単独診断で代替しない |
| 出典と実装範囲 | revision `92929426` は候補。今回の節・後続手・親・終端・許可path・資料hash・独立review担当はStep 2/3で確定する |
| 独立出典レビュー方式 | AIの別セッション方式/人間方式の採否・担当・独立性条件は未決。§5.4の方式採用記録と対象hash付き承認記録を別に要求する |
| 計画版・依存の取り込み | #79は文書のみ、現在は#78依存でDraft・未マージ。§6.1の計画版P、L2b-0を独立提出するか、将来の統合先I・取り込み方式・新親SHAは実行前に承認・固定する。今は#78を更新/mergeしない |
| 修正上限 | 既存初期案3回に対しPoC推奨2回。同一原因で改善なし2回停止は維持。採用値を実行前に記録する |
| L2b実行契約 | task台帳/CLI、推論turnの監視・中断確認、poll/turn上限、CI待ち上限、remote照合方式を後続実装で採用・試験する |
| remote操作 | 専用head branch名、credentialのイベント起動条件、証拠保管先を実行前に確定。親SHAが変われば再計画する |

次に実装する最小PRは **「L2b-0：1件task台帳・監視方針gate・再開境界」** を推奨する。
§6.1の固定計画版Pを継承し、#78への依存も保持する。1 task制約、版付き台帳、既存usage adapterへの接続、明示した監視集合の固定、
入力hash・pause/resume・修正累計の保持、模擬worker境界と障害注入試験に限定する。
新しいlive取得、推論worker、canonical変更、GitHub書込はこの準備PRでは実行しない。
§3.2.1の正規化前監査と停止・復帰試験をL2b-0の受入要件とし、案B未採用時の開始拒否も検査する。
監査試験成功と案B採用を区別し、既定2枠を黙って緩和しない。
この最小PRだけでは本書のStep 3/4を実行できない。続く実worker・独立review gate・remote照合の実装と
試験が揃ってからPoCを開始し、準備段階の模擬成功をPoC成功に数えない。

準備コードをPoC最終Draft PRの同一branchで積み上げる場合、最終成果物はL2bコードと1件Seed差分を含む1 PRとなる。
L2b-0を独立提出する場合はPoC実行前の準備PRとして件数を区別し、いずれも§6.1の取り込み・親固定・再検証手順に従う。
本書は準備PRを含む複数Stacked PRの自動生成を許可しない。

## 10. 次段階への移行条件

1件PoC成功後も直ちに連続処理へ広げず、証拠と制限をレビューし、次を満たす別計画を採用する。

- 複数候補キュー：調査待ち/実行可/停止中の区別、task hash、依存・重複、出典と許可pathを検査し、
  1件失敗で次候補へ進める条件を明文化する。1件の成功を未確認revisionや別記事へ一般化しない。
- 未マージPR上限：GitHub実在PRと台帳を再照合して枠を予約し、応答喪失・手動作成・closed/mergedも扱う。
  既存の「実装同時1・未マージ上限3」は初期案であり、実装・採用済み制限と呼ばない。
- Stacked PR自動生成：依存DAG、固定親SHA、親変更時の子証拠失効、再統合/再検証、CI起動・重複防止を検査する。
  既存stack深さ3も初期案として改めて採否を判断し、2〜3件の未マージPR試行はこの後続段階で行う。
- 実推論中断の到達時間、usage計測遅延・超過幅、復帰成功、レビュー負荷と修正回数を評価し、
  1件PoCで残った制限・保留を解消する。merge/auto-mergeは次段階のloop機能にも含めない。

本書の作成に対する確認は参照文書・実装・関連試験との整合性、変更path、Markdownリンク、
`git diff --check` に限定する。PoCの試験結果・live usage・新規source review実績とは区別する。
