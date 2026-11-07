# Wikipedia Seed 拡張ループ：検証・停止再開基盤 v1

## 対象と開始時の確認（2026-11-06 JST）

対象は `fujihara-masaki/shogi-learning-202606`、base は
`claude/clever-hopper-bphezm`、実際の開始 SHA は
`49e45f45bd03bb958cfef1088f1fa44b67c15cdd`（PR #77 merge）。
初期 worktree は clean、適用される AGENTS.md は見つからず、既存 open PR 検索に同一依頼なし。
古いローカル HEAD `55f86b2` から最新 base を fetch し、E2h の artifact・旧 fixture・
backend/frontend/E2E・計画書の差分を確認して作業ブランチを作成した。
開始時の canonical artifact は9件、`.github/workflows/` はなかった。runner の件数は固定しない。

| レイヤー | この基盤が実行すること | 後続に残すこと |
| --- | --- | --- |
| L0 | 作業・出典・予算・状態・将来PR運用の契約 | 新しい出典レビューの実施 |
| L1 | 同梱 artifact の実 D1b CLI、既存全体 gate、read-only CI | 新しいSeed専用テストの自動生成 |
| L2a | App Server使用量read、予算判定、検証checkpoint、status/pause/resume、模擬replay | 推論turn、修正loop、commit/push/PR操作 |

この runner に Wikipedia取得・抽出・独立レビュー・モデル処理・remote変更は存在しない。
今回の基盤変更を1件の未マージPRへ提出する作業は、runnerの機能とは別である。

## 出典と作業キューの契約

1作業は1出典節または密接な分岐群とし、一定手数まで伸ばす目標は置かない。
後続のキューは task ID、対象line/artifact、記事・revision・節、接続親、収録範囲、依存task、
変更許可path、必須検証を持つ。[見本](opening-seed-loop-queue.example.json)は実行無効・調査待ち。
revision・接続先未確認なら実装へ進めない。L2aはこのキューを消費せず、既存bundled artifactを
ソートして検証する暗黙のキューを持ち、`queue_hash: null` と理由をstateへ保存する。

初期の追加候補はA（本文明示手順）中心。B/Mは専用レビュー、Cからmoveを作らない。
原文と親局面・各着手・終端の対応は合法性試験と独立してレビューし、取得日時、固定revision、
根拠箇所、資料SHA-256、レビュー担当・結果・対象差分のhashを結び付ける。
一般知識、図、別記事、engine評価で未明示の中間手を補わない。大量転載を避け、
既存の帰属表示と CC BY-SA 方針を維持する。

D1bは構造化artifactのschema・合法性・tree・coverage・metadataを検査する。
Wikipedia本文を読み直して着手の存在を証明するものではない。
D1cはruntimeへ投影する項目を比較し、canonicalだけに残すrevision/provenance等のDB完全一致を要求しない。
既存の両将棋ライブラリ、独立期待値、E2f/E2g実旧版fixture、移行・idempotency・分岐操作の試験を再利用する。
artifactから作った期待値だけで抽出精度を証明しない。今回のstateは常に
`source_review: not_performed`、`pr: null`。既存review metadataは変更せず、再検証ログと区別する。
`source_verified` や `ready_for_review` を自動付与しない。

## 公開CLI v1

Python **3.12**、Node.js **24**と既存requirements/lockfileを使う。
`python` は既存backend依存を導入したPythonを指すこと。新packageは標準ライブラリのみ。
Codexは `run` / controlled `resume` / `preflight --live-usage` だけで必要。
開始環境では Python 3.12.14、Node 24.19.0、npm 11.9.0、Codex 0.159.0-alpha.3 のhelpを確認した。

すべてリポジトリルートから実行する。global option `--root PATH`、`--config PATH` はサブコマンドの前。
`--root` に空白・日本語を含むpathを渡せる。

| コマンド | 動作・副作用 |
| --- | --- |
| `preflight` | Git内容識別、Python依存、Node/npm、frontend導入、artifact件数を診断。検証は未実行 |
| `preflight --live-usage` | 上記＋read-only App Server接続。推論・ログイン変更なし |
| `dry-run --profile artifacts\|full` | 固定コマンド計画だけを表示、すべてnot_run。stateなし |
| `validate --profile artifacts\|full [--run-id ID]` | 認証不要の実検証と保存。ID省略時UUID。Codexを起動しない |
| `run --run-id ID [--profile artifacts\|full]` | 使用量を評価し実検証をcheckpoint実行。モデル処理なし |
| `status --run-id ID` | 追加LLM/使用量接続なし。state・worker有無・pause要求を表示 |
| `pause --run-id ID` | 停止要求を原子的保存。実行中stageは時間上限内で完了させる |
| `resume --run-id ID [--profile artifacts\|full] [--validation-only]` | lock取得、同一入力確認、controlledなら最新usage再評価。validateの復帰は`--validation-only`必須 |
| `replay PATH` | 明示fixtureから模擬遷移を再現して別ディレクトリへ保存。実検証はnot_run |

CLI/設定/state/replay入力の `schema_version` は1。未知の設定key/versionは拒否する。
終了コードは **0**＝操作成功（dry-run等では検証成功を意味しない）、**1**＝検証失敗、
**2**＝設定・I/O・D1b運用/診断parserエラー、**3**＝pause/入力変更/中断。
`status` は状態表示できれば0、`replay` は模擬再生できれば0。状態の成否はJSONを参照する。
D1b子プロセスの0＝valid、1＝読込済み制約違反、2＝読込/JSON/schema等の運用エラーは
各attemptのexit_code・diagnosticへそのまま残す。

Linux / Bash:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
(cd frontend && npm ci && npx playwright install chromium)
backend/.venv/bin/python -m scripts.seed_loop preflight
backend/.venv/bin/python -m scripts.seed_loop dry-run --profile full
backend/.venv/bin/python -m scripts.seed_loop validate --profile full --run-id local-validation
backend/.venv/bin/python -m scripts.seed_loop --config docs/opening-seed-loop-config.example.json preflight --live-usage
backend/.venv/bin/python -m scripts.seed_loop run --run-id budget-check
# 別ターミナルから要求できる。既に完了していれば完了のまま。
backend/.venv/bin/python -m scripts.seed_loop pause --run-id budget-check
backend/.venv/bin/python -m scripts.seed_loop status --run-id budget-check
backend/.venv/bin/python -m scripts.seed_loop resume --run-id budget-check
backend/.venv/bin/python -m scripts.seed_loop replay scripts/tests/fixtures/pause-reset-resume.json
```

Windows / PowerShell（手順、Windows CIの実行結果とは区別する）:

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
npm ci
npx playwright install chromium
Pop-Location
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop preflight
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop dry-run --profile full
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop validate --profile artifacts --run-id windows-validation
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop --config docs/opening-seed-loop-config.example.json preflight --live-usage
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop run --run-id budget-check
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop pause --run-id budget-check
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop status --run-id budget-check
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop resume --run-id budget-check
.\backend\.venv\Scripts\python.exe -m scripts.seed_loop replay scripts/tests/fixtures/pause-reset-resume.json
```

## 実検証とプロセス

`artifacts` は `backend/app/wikipedia_opening_artifacts/*.json` を動的列挙し各D1b CLIを実行する。
0件は運用エラー。stdoutの単一JSON、valid/errors構造、終了コードとの整合性も検証する。
`full` は専用unittest、全artifact、既存backend pytest、`npm exec --no -- vitest run`
（ローカルVitest、`npx vitest run`相当）、lint、build、既存Chromium E2Eの順。
失敗以後はnot_runで保存する。既存package.jsonにtest scriptはなく、E2Eの実scriptは `test:e2e`。

任意の自由文コマンド設定はない。引数配列・shell=False、Windowsのnpm起動だけ既存と同様に
固定 `cmd.exe /d /s /c npm.cmd` を使う。cwd・対象・時刻・終了コード・stdout/stderr path・
Python/Node/npm/OSを保存する。環境変数一覧や認証応答の丸ごと出力は行わない。

通常DB関連の `SHOGI_DB_PATH` / `NEXT_MOVE_DB_PATH` / `SHOGI_CORS_ORIGINS` は継承しない。
非E2Eの子にはrun専用のDBパスを渡す。E2Eには両DBパスを渡さず、現行起動scriptの
`frontend/.e2e/` と小規模fixture生成を利用する。`NEXT_MOVE_DB_PATH`明示でfixture生成を
無効にしない。`CI=1`、依存導入済みの `sys.executable` を `PYTHON`、専用18000/15173を既定とする。
ポート衝突は事前bindで診断し、起動時競合も既存サーバーを再利用せず失敗する。
Chromiumはlockfile対応のPlaywrightで導入する。既存branch/360pxシナリオをそのまま実行する。
今回のローカル環境では標準download先 `cdn.playwright.dev` が許可ドメイン外で403となった。
既存設定の `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium` による代替検証は、
同梱ブラウザの導入成功とは区別する（導入済みChromium 151.0.7922.173、要求build v1228）。
CIでは標準downloadを試みる。ローカルの代替指定をworkflowへ固定しない。

stage timeoutは既定900秒。通常pauseは現在の検証をdrainし、結果保存後に停止する。
SIGINT/SIGTERMでは中断を記録し、専用supervisorへlifecycle pipeのEOFを通知する。
検証はLinux（pidfd/subreaper対応kernel・`/proc`）またはWindows Job Objectsで監督する。
これらを利用できないOSでは、検証プロセスを起動せずoperational_errorになる。
Linux supervisorはsubreaperとして別process groupのPlaywright webServerも子孫として回収する。
`/proc`の親子関係・start_ticksを再確認し、pidfdで参照した所有プロセスだけへTERM/KILLを送る。
終了確認は`/proc`列挙だけに依存せず、subreaperのwaitpidでECHILDを確認する。
Windowsはsuspendedで生成したrootを非breakaway Jobへ割り当ててから再開し、
Jobの終了とActiveProcesses=0を確認する。kill-on-closeでsupervisor終了時も所有子群を終了させる。
通常終了時も残った所有子孫を後片付けし、timeout/中断時のcleanupは最大8秒を別途確保する。
controller側は起動/cleanup余裕を含めstage timeout+15秒を待ち、キャンセル後は最大12秒待つ。
終了を確認できなければoperational_error/cleanup_unconfirmedとして保存し、成功扱いしない。
ownership journalのI/O失敗でも、診断保存とは独立して所有子群のcleanupを試みる。
子群の終了に成功してもjournalが未確定なら自動resumeを拒否し、失敗証拠を保持する。
判定は保存済みの裸PIDへのkill、ポート番号でのkill、全node/pythonの一括killに依存しない。
App Server readの終了処理は別経路で、close/終了の想定I/Oエラーをsanitizeしたcleanup_errorsへ残す。
timeout、interrupted、failed、operational_error、not_runを区別する。

## 使用量と25/30%の意味

[設定見本](opening-seed-loop-config.example.json)で監視bucket（既定`codex`）と
primary/secondaryを明示する。時間枠を5時間/週次へ固定しない。
使用済みの**絶対割合**が25%以上なら新stageを始めず、30%以上なら`budget_stop`。
追加消費30ポイントや残量30%ではない。複数の監視枠のいずれかで停止条件が成立する。
L2aでは各固定検証stageを開始単位とし、開始前と結果保存後に明示readする。
現在の検証はtimeoutまで完了可能で、推論のlive中断は実装していない。
厳密な30%上限、計測遅延や超過幅の保証はしない。この実装作業を行うCodex自身も制御しない。

実adapterは `codex app-server --listen stdio://` のJSONL接続で
`initialize`応答→`initialized`通知→`account/rateLimits/read`を行う。
要求IDに対応する応答だけを採用し、通知や別IDの応答をusageへ混ぜない。
更新通知は部分情報で減少を推測せず無視し、必ず明示readで再確認する。
`rateLimitsByLimitId`があれば指定keyだけを使い、指定key欠落で互換viewへ逃げない。
古い単一 `rateLimits` はlimitId一致、またはcodexに限定した歴史的implicit IDを認め、
selectionと選択IDを記録する。usedPercent、利用可能なduration/reset、観測時刻、provider、CLI versionを正規化する。
任意のduration/resetの欠落はnullのまま。指定監視windowやusedPercentのnull/欠落はunknown。
未認証等のRPC error、EOF、timeout、壊れた応答はunknown、method未対応はunsupported。
理由はsanitizeした分類で保存し、real失敗時のfixture fallbackはない。
initialize前後の入力側切断は実stdio試験で確認し、BrokenPipeはclosed_stdinとしてunknownにする。
stream.closeの再flush等のI/Oエラーで元の診断を上書きせず、cleanup_errorsへ分類だけを残す。
通常のEOFとは別経路であり、以前の実アカウントEOFの原因をこの不具合とは断定しない。

unknown/unsupported、120秒を超えるstale、未来の観測、観測後のreset跨ぎは開始を拒否する。
reset時刻を過ぎたという理由だけで0%を推定しない。
pausedは再起動・期間reset・replayのobserveだけでは解除せず、明示resumeで最新readする。
controlled resumeは、全stage成功済みでnext_stageが末尾でも最新usageを評価する。
budget_stop/unknown/staleが残れば停止を維持し、回復時は保存済み成功を再実行せず完了できる。
usage readの前後でpause要求を確認し、read待ち中に要求されたpauseで未開始stageを起動しない。
pause publicationとnot_run→runningの開始記録は短いlaunch lockで直列化する。
開始記録が済んだattemptは進行中としてdrainする。この境界前のpauseではattemptも追加しない。
status/pauseは追加LLMなし。ログイン・購入・利用枠reset操作・thread/turn起動はない。

公式確認先は [App Server](https://learn.chatgpt.com/docs/app-server)、
[公式Codex repository](https://github.com/openai/codex/tree/main/codex-rs/app-server)、
[公式protocol](https://github.com/openai/codex/tree/main/codex-rs/app-server-protocol)。
実装時、learn.chatgpt.comは環境のHTTP 403で取得できなかったため、公式repositoryと
CLIの `--version` / `--help` / `app-server --help` / `app-server generate-json-schema --out ...`
でhandshake、rateLimitsByLimitId、nullable項目を照合した。生成schemaは作業用で非同梱。
実アカウントreadはこの環境でEOFとなりunknown。live疎通は未検証であり、
独立した模擬App Serverプロセスのprotocol試験と混同しない。

## 状態・保存・復帰

Git管理外 `.seed-loop/runs/ID/state.json` とattempt別 `.stdout.log` / `.stderr.log` を使用する。
通常の将棋DBは使わない。UTF-8 JSONを同一directoryの一時ファイルへfsyncしos.replaceする。
ローカルfilesystem上のatomic replaceとOS lockが前提。電源断に対するdirectory永続化や
共有network filesystem上のlockを保証する実装ではない。
同じrunはOSの非待機exclusive lockで二重起動・二重resumeを拒否する。lock fileは削除しない。
worker強制終了でworker.lockが解放されても、独立supervisorのexecution.lockとownership journalを確認する。
controllerの死をpipe EOFで検出したsupervisorは、所有子群をcleanupしてからexecution.lockを解放する。
resumeはexecution.lockが有効ならprevious_attempt_activeで停止し、新attemptを起動しない。
lease解放後もjournalがcleaned/cleanup_confirmed:trueでなければcleanup_unconfirmedで停止する。
supervisor自体の強制終了、起動前後の不確実な保存、壊れたjournalも再開許可に変換しない。
PID再利用を無視した自動killや、lockファイルの手動削除で再開する実装ではない。

phase（validation/validated）、execution_status（running/paused/failed/completed）、stop_reasonを分離する。
次stage、attempt、config/version/hash、対象artifact/hash、Git HEAD、実内容digest、環境、usage履歴を保存する。
内容digestはtrackedとignore対象外untrackedの全ファイルをbyte単位でhashする。
`.seed-loop/` と作業用 `work/` は対象から除外し、そこへ検証コードを置かない。
dirtyでもHEADだけで識別しない。CRLFも実内容の変更となり、別checkoutへ成功を持ち越さない。
base/head/checkoutはCIから与えられた別項目で保持する。

開始前にrunningを保存し、結果確定後にsuccess等を保存する。
保存前に落ちたstageはrunningのまま（成功ではない）。明示resumeでinterrupted/worker_lostとし、
所有プロセスの終了確認が済んだ場合に限り、通常DBを変更しない固定検証だけ再実行する。
保存後に落ちたsuccessは同一入力なら再利用できる。
exactly-onceは保証しない。state破損はエラーとし、黙って初期化しない。
対象artifact・コード（未追跡含む）・config・HEAD・profile/modeの変化は旧成功を再利用せず、
入力変更理由を示す。変更後は新run IDで全検証を行う。

各attemptには `.spec.json`（引数/cwd/timeout、環境変数一覧は含めない）、
`.ownership.json`（attempt token、supervisor/root、所有情報、cleanup確定状態）、
`.result.json`、`.supervisor.log` を追加保存する。resultとjournalのtokenを照合して旧結果の混入を拒否する。

pause後の復帰は、まずstatusとログで原因を確認する。予算停止なら利用枠回復後にresume、
未認証・未対応なら環境を直してlive preflight、検証失敗なら修正後に新run IDを使う。
previous_attempt_activeならsupervisorのcleanup完了を待ち、statusのprocess_recoveryがnullになってからresumeする。
cleanup_unconfirmedなら自動再実行を止める。stateのrecoveryと該当ownership/result/supervisor logを確認し、
所有情報を根拠にOS側で当該検証と子孫が全て終了したか調べる。Linuxのstart_ticksは`/proc/PID/stat`、
Windowsの実プロセスはJobの監督範囲で確認し、裸PIDだけで終了対象を決めない。
Windowsのroot記録はcreation_filetimeも保持し、現在のPIDと生成時刻を照合できる。
判定できなければ停止を維持する。終了を確認できた場合も壊れたjournalを手で成功へ書き換えず、
runを証拠ごと保管して新IDで検証する。未確認のまま新IDや別portで回避しない。
workerだけを強制終了した通常ケースはsupervisorが自動cleanupするため、終了確認後の同一run resumeが可能。

validation-onlyの中断を同一内容で再実行する例:

```bash
backend/.venv/bin/python -m scripts.seed_loop resume --run-id local-validation --profile full --validation-only
```

壊れたstateは保持・調査し、新run IDを使用する。run IDを変えるだけでfailed結果が成功になるわけではない。
replayは `.seed-loop/replays/UUID.json` に `mode: replay` / `simulated: true` / `validation: not_run` を記録する。
fixtureはstart/observe/pause/resumeと明示read応答を持ち、reset後もpauseを維持する遷移を再現する。
この模擬記録を実検証・live usage・新規source reviewの証拠にはしない。

## CIと検証範囲

[workflow](../.github/workflows/seed-validation.yml)は全baseのpull_request（Draft含む）で起動する。
contents:read、同じPRの古いrunをcancel、job timeout、continue-on-errorなし。
Linuxで実full profile、Windowsで小さな実D1b＋状態/file/path/lock/protocol/replay試験を行う。
Node24/Python3.12、npm ci、既存requirements、対応Chromiumを使用し、Codex/API keyは不要。
ログ・診断・state・checkout contextと失敗traceはCI artifactへ14日保存する。
PR head、base、checkout、GITHUB_SHAを別記し、pull_requestのmerge結果をhead単体試験と呼ばない。
workflow_dispatchも定義するが、default branchにworkflowが入る前は手動dispatch利用を前提にしない。
PRで新workflowが承認待ち/未起動/skip/pendingならsuccessとせず、実runの状態を確認する。

専用試験は実D1bの0/1/2・壊れた診断・対象0・timeout/中断、25/30境界・複数枠・null/stale/reset、
実adapter対模擬stdio server、保存失敗・worker終了/再起動・二重lock・入力変更・破損、
日本語/空白path・CRLFを確認する。追加の境界試験は実Playwrightの404 readiness待ちtimeout、
別groupの所有server終了・port解放・無関係serverの生存、実子起動後のcontroller強制終了とresume、
不確実な所有情報での再開拒否、実stdioの入力切断、read中pause、最終stage後の停止継続と回復を確認する。
実Playwright小試験はLinux full CIで依存導入後に必須実行する。Windows jobはアプリ依存を入れず
このLinux専用試験をskipし、Job Objectsを使う実子起動/worker終了の試験とC〜Eは実行する。
Linux上のpath/CRLF試験はWindows実機確認ではない。
ローカル実行件数・対象commit/digest・CI状態はPR本文へ記録し、証拠更新のためにコードを変更し続けない。
必須gate失敗/未実施ならDraft維持。live usageだけ未確認ならその制限を明示してコードレビューを依頼できる。

## 後続L2b以降の接続点・受け入れ条件（未実装）

- 取得/抽出/独立source review worker: キューの確定したrevision・親・範囲・許可pathを消費し、
  独立レビュー証拠と現diff hashが揃って初めて実装可能にする。B/M・Cのgateを実証する。
- 推論/修正worker: 現usage readerと予算判定の前後へ接続し、実turn起動・中断、計測遅延・超過幅、
  状態復帰、途中生成物の隔離をlive試験する。初期案は修正上限3回、同一原因で改善なし2回で停止。
  回数はresumeでresetしない。現在のrepair_attempts=0は予約情報で機能の実装ではない。
- PR管理worker: artifact連続拡張はStacked、独立対象は同baseの独立PRも可。
  初期案は実装同時1、未マージPR上限3、stack深さ3。現在これらのremote制限を執行するcodeはない。
  task/head/baseで応答喪失後の既存PRを照合し、重複作成を防ぐ。
- 親HEADが変われば子の証拠を失効させ、後続新規着手を止め、再統合/再検証する。
  Readyは現在diffのsource review・必須gate・設定reviewが揃う状態。人間承認/mergeとは別。
  CI未起動/承認待ち/skip/pending/失敗をsuccessへ変換しない。GITHUB_TOKEN等でのPR作成後は
  [公式イベント仕様](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)と
  [起動仕様](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)に従い実起動を確認する。
- PR-E2i以降の新Seedと2〜3件の未マージPR試行で、上記接続点を実証する。
  今回runnerで実repositoryへPR作成試験はしない。merge/auto-mergeは将来loopの機能にも含めない。
