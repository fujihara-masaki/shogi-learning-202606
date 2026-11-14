# L2b-0：1件task台帳・監視gate・模擬再開の操作説明

本書は[固定PoC計画](opening-seed-loop-poc-plan.md) §3.2.1、§5.2〜5.4、§6.1、§8、§9に対する
**準備実装の操作説明**。正本のコピーやPoC完了報告ではない。出典・Seed・LLM・remote workerは未接続。
案B、独立レビュー方式/担当、実PoCの修正上限2/3、実行環境、将来の統合先/方式は未決のまま。

## 固定した依存と内容識別

| 対象 | 固定値 |
| --- | --- |
| #78 / `codex/wikipedia-seed-loop-foundation` | `b438609f4bd7c04ff812d64e7de74718b935a39f` |
| #79 / `codex/opening-seed-loop-poc-plan` / P | `d9299b4d897849c218695f0cf1d5057e43e30af2` |
| Pの計画書blob SHA-256 | `bfe9187863c66828c3f7edee175ee1b718a37651c6b213db9e031b748e076924` |
| 本準備PRのbase | `codex/opening-seed-loop-poc-plan` |

計画書は変更していない。hashは `git show P:docs/opening-seed-loop-poc-plan.md` の**実byte列**から計算する。
Windowsのテキストpipelineを通すと文字コード/改行変換が入るため、次のPythonを使う。

```text
python -c "import hashlib,subprocess; b=subprocess.check_output(['git','show','d9299b4d897849c218695f0cf1d5057e43e30af2:docs/opening-seed-loop-poc-plan.md']); print(len(b),hashlib.sha256(b).hexdigest())"
```

台帳は別途、working treeの全対象file hash/HEAD/digest、実装Python moduleのbyte hashを保存する。
CRLF checkoutの内容digestがLinuxと異なっても、Git blob hashとは混同しない。
実リポジトリで計画書pathが存在すれば、PのancestryとGit blob hashも実際に確認する。
計画書のない一時repoは `not_present_in_temporary_simulated_repo` と記録し、GitHub依存の実証とはしない。

## 実装と既存契約

- `scripts/seed_loop/l2b.py`：専用CLI、kind/version付きtask台帳、hash照合、pause/resume、予約・照合。
- `l2b_inputs.py`：1件制約、架空入力、案A/Bの採用記録とraw監査、固定契約。
- `l2b_mock.py`：固定stdio App Serverと、要求を返すだけの固定worker。任意commandやshellを受け付けない。
- `usage.py`：既存 `read()` の戻り値/既定設定/unknown/cleanupを保持し、`read_audited(auditor)` だけ追加。
  同じprotocol処理の要求ID=2成功応答を監査し、監査成功後だけ同じ応答を既存normalizeへ渡す。
- `scripts/tests/test_seed_loop_l2b0.py`：既存unittest discoverで検出される追加試験。

L2aのCLI、v1 state、replay、予約field、既存fixture、DB隔離、25/30%判定、A〜E、lock/PID事前確認を変更しない。
模擬workerのローカル所有監督には既存 `validation.execute` / supervisor / execution leaseを再利用する。
これは実remote turnの中断・復旧保証ではない。`codex.cmd`を明示できる既存adapterの起動方法も変更せず、
`shell=True`や認証環境の変更はない。既存workflowも変更しない。

## 入力と保存形式

L2b入力は `kind:seed-loop-l2b0-input / version:1 / simulated:true`。
既存の無効キュー見本を直接読んだり、`awaiting_research`を昇格させたりしない。
`queue.tasks`は厳密に1件。0件、複数/重複、未知field、無効queue/task、未確定path、実taskを拒否する。
模擬taskも `status:simulated_ready`、`enabled:true`、明示 `simulated:true` が必要。
許可pathは架空の `work/l2b0-mock-output.json` のみで、workerはそのfileさえ変更しない。

模擬stepは初回generate 1件＋repair最大3件。operation/outcome/cause/improvedの限定列挙だけを受け付ける。
設定・taskからshell command、実行ファイル、URL、Codex binaryを指定する機能はない。
監視条件・修正上限未採用の入力は初期化して保留できるが、開始許可は出さない。

保存先は `.seed-loop/l2b0/tasks/TASK_ID/`。L2aの `.seed-loop/runs/` とは分離する。
`ledger.json` は `kind:seed-loop-l2b0-task / version:1 / payload / sha256`。
安定したtask IDの `anchor.json`、task OS lock、launch lock、pause marker、audits、attempt request、
supervisor所有/結果journal、ログを保持する。run IDは履歴であり保存先や修正累計を変えない。
同じtaskを別runで再初期化できない。anchorだけ残る台帳欠落も自動初期化しない。

payloadにはtask/run/attempt ID、時刻、`phase:mock_worker`、execution status、停止理由、provider、
計画/依存/コード/queue/task/config/許可範囲/方針/採用記録hash、usage監査・正規化・判定の対応、
修正上限/累計/同一原因履歴、予約/結果不明/確定結果を持つ。
`future`のsource material/extraction/review/artifact/validation runs/remote/PoCはすべて
`not_performed`と証拠接続用listのまま。空listや `mock_completed` は実検証成功を意味しない。

保存は既存atomic UTF-8 JSON（fsync＋同一directory内replace）、排他は既存OS lockを使う。
台帳破損、版違い、証拠欠落/hash不一致、保存失敗は停止/終了2で保全し、成功へ書き換えない。
秘密値・環境変数一覧・認証file・実account IDを台帳へ保存しない。raw全体も保存しない。
ファイル削除やtask IDの手動改ざんに耐える外部改ざん防止DBではないため、証拠directoryを保持する。

## raw監査と予算判定

1. 既存adapterがinitialize/initialized/readを実行し、通知・別IDを捨てる。RPC error/EOFでは監査を呼ばない。
2. ID照合済みのraw応答から指定bucketを選ぶ。`rateLimitsByLimitId`が存在すればnull/指定bucket欠落も停止し、
   compatibility viewへfallbackしない。bucket ID不一致、未知の枠形式も停止する。
3. primary/secondary双方のkey存在・型をobject/null/missing/invalidとして記録。有効なSと期待S、期間を完全照合する。
   選択外枠も監査し、null→object/null→missing、Sの増減を停止する。
4. sanitized資料とSHA-256、request ID/取得時刻、入力/設定/方針/採用hash、run/次attempt indexを保存する。
   資料保存と台帳保存が成功して初めて監査が通る。
5. 同じ応答を既存normalize/decisionへ渡し、正規化結果と判定を同じaudit IDで保存する。
6. pause・入力・証拠を開始境界でも照合して、開始予約を保存する。

案Aが既定で両枠必須。L2bでは期間・resetも有効な正の整数を要求する（L2aの任意metadata契約は変更しない）。
名前から週次/短時間を決めず、入力の期待durationと照合する。
案Bは期待null枠ごとの架空非提供根拠hash/由来、判断者・offset付き日時、P/config/policy/protocol結合を要求する。
`kind:simulated-adoption`、`simulated:true`、架空判断者だけを受理し、実承認を表す型は未接続。
例示入力の架空採用値2は模擬試験専用で、実PoCの2/3の決定ではない。

25%以上 `no_new_task`、30%以上 `budget_stop`、いずれかの枠の不正/unknown/staleも停止する。
bool/NaN/無限/範囲外は許可しない。120秒超、未来時刻、観測後reset跨ぎは既存decisionで拒否する。
reset経過から0%を推定しない。2026-11-09の週次1%は使っていない。

## pause・予約・異常終了・resume

同taskのcontrollerは別プロセス間のtask lockで排他する。二重simulate/resumeは終了2。
pause publicationとattempt予約は同じlaunch lock（最大5秒待機）を使う。

- pauseが先なら未開始attempt/worker呼出は0。usage read中のpauseもread後に確認する。
- 予約が先なら、その1 attemptを所有監督内でdrainする。pauseは次の予約を防ぐ。
- 最終結果後/全step完了後でも停止理由を評価し、停止を完了に読み替えない。
- lock待機上限ではcontrollerは `launch_lock_timeout`、pause側は `pause request not published` を返す。
- repairは起動前に累計へ加算する。応答喪失・run ID変更・失敗・resumeで返却しない。
  `repair_limit_reached` と `same_cause_no_improvement`（同一原因の直近2修正が改善なし）を区別する。
- 予約後にcontrollerが終了し結果がなければ `result_unknown / worker_result_unknown`。自動再送しない。
  既存execution leaseが使用中なら `previous_attempt_active`、所有終了を証明できなければ `cleanup_unconfirmed`。
- worker完了後・台帳結果保存前にcontrollerが終了しても、正しいrequest/input/attempt、supervisor token、
  終端成功とcleanup確認、固定command、worker出力を照合できれば、その結果を回収できる。
  保存済み成功は再実行しない。確定結果のjournal byte hashも後で照合する。
- 明示resumeは入力/コード/依存観測/所有/証拠を再照合し、新しいstdio usage応答を必ず読む。
  完了済みで残step=0でも同じ。再起動・reset経過だけでは解除しない。

入力・P・計画blob・依存HEAD・コード・Git HEAD/content・許可範囲の変更は旧証拠を失効させる。
rawの集合・状態・期間・bucket条件の変化でも旧監査を失効させる。
変更を戻しても同じ台帳を再許可しない。上限や採用条件の変更で累計を消す移行機能はない。
意図した将来artifact変更は `future.validation_runs` に別validation runを接続する設計とし、
本版はその接続操作自体を提供しない。L2a identityの書換えや旧成功の持越しはしない。

`--dependencies`は毎回与える**模擬依存観測**（kind/version/simulatedと4固定値）。
CLIは入力fileとこのfileをread後・予約前・worker後にも再読する。
controllerにremote自動fetchはない。GitHub refの継続監視や新しいupstream照合の実証ではない。
実準備PRの提出時は開発作業として別途GitHubで#78/#79を再取得する。

## 実行例（Python 3.12・Git、リポジトリroot）

以下はLinux/Windows双方で使える1行コマンド。Pythonには既存依存を導入する。
実候補や通常DBに触れないよう、最初に架空の一時repoを作る。既存directoryには上書きしない。

```text
python -c "from pathlib import Path; import subprocess; p=Path('work/l2b0-demo-repo'); p.mkdir(parents=True,exist_ok=False); (p/'.gitignore').write_text('work/\n.seed-loop/\n',encoding='utf-8'); subprocess.run(['git','init','-q',str(p)],check=True); subprocess.run(['git','-C',str(p),'add','.'],check=True); subprocess.run(['git','-C',str(p),'-c','user.name=Simulated','-c','user.email=simulated@example.invalid','commit','-qm','fictional demo'],check=True)"
python -m scripts.seed_loop.l2b example --directory work/l2b0-demo-repo/work/inputs
python -m scripts.seed_loop.l2b --root work/l2b0-demo-repo init --input work/l2b0-demo-repo/work/inputs/input.json --dependencies work/l2b0-demo-repo/work/inputs/dependencies.json --run-id demo-1 --simulated
python -m scripts.seed_loop.l2b --root work/l2b0-demo-repo simulate --input work/l2b0-demo-repo/work/inputs/input.json --dependencies work/l2b0-demo-repo/work/inputs/dependencies.json --run-id demo-1 --simulated --usage-fixture work/l2b0-demo-repo/work/inputs/usage.json
python -m scripts.seed_loop.l2b --root work/l2b0-demo-repo status --task-id fictional-l2b0
python -m scripts.seed_loop.l2b --root work/l2b0-demo-repo pause --task-id fictional-l2b0
python -m scripts.seed_loop.l2b --root work/l2b0-demo-repo resume --input work/l2b0-demo-repo/work/inputs/input.json --dependencies work/l2b0-demo-repo/work/inputs/dependencies.json --run-id demo-2 --simulated --usage-fixture work/l2b0-demo-repo/work/inputs/usage.json
```

resumeは別のPython/controllerプロセスになる。成功attemptは1件のまま、新usage監査とrun履歴が追加される。
CLI終了値は成功/状態表示/pause受理0、模擬実行の停止3、入力・保存等の運用error2。
模擬workerの業務失敗も停止3で表す。L2aの終了コード契約は変更しない。

```text
python -m scripts.seed_loop.l2b --help
python -m unittest discover -s scripts/tests -v
python -m scripts.seed_loop validate --profile full --run-id l2b0-final
```

Linuxで既存システムChromiumを明示する場合は従来どおり
`PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium` を設定する。Windows jobはアプリfullではなく基盤試験。
実際に実行したHEAD/content digest/command/件数/skip理由とCI run/job/checkout SHAは本準備PRに記録する。
ローカルとCI、head単体とmerge結果、模擬時刻/採用/結果と実ローカルI/O/プロセスを区別する。

## 後続へ残す条件

実usage/LLM/Wikipedia/出典レビュー/Seed追加/canonical適用/commit/push/PR/Ready/merge/auto-mergeの
controller経路は実装・実行していない。15秒poll、120秒turn上限、実推論中断の実績もない。
開発者がこの準備PRをcommit/pushする操作はcontrollerの機能と区別する。

実worker接続前には、未決の監視方針/非提供根拠・実採用記録、修正上限、独立review方式/担当、
実行環境、出典・範囲・親・許可pathを確定し、実providerと実承認の別契約・試験を追加する。
計画§6.1の将来取り込み方式/親固定・全検証・最新CI再取得にも従う。
結果不明を解消できない台帳は証拠を保管して停止を維持し、手書き成功や別IDによる回避をしない。
本準備の模擬完了をPoC全体成功、実推論30%以内の制御実績と呼ばない。
この実装を行うCodex自身の消費は、controllerが扱う架空usageの数値に含まれない。
