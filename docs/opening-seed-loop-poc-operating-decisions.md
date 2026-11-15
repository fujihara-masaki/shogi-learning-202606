# L2b-1a：運用方針と読み取り専用usage接続

採用日：2026-11-15 JST（実装依頼による設計方針の採用）。
[固定計画P](opening-seed-loop-poc-plan.md)が正本であり、本書は今回の採用差分と操作説明である。
Pや[L2b-0](opening-seed-loop-l2b0.md)を「当時採用済み」へ書き換えない。
本準備は実LLM turn・Wikipedia取得・Seed変更・独立レビューworker・controllerのGitHub書込を含まない。
**実workerは常に未接続、開始許可も常にfalse。PoC全体の成功ではない。**

## 固定依存と採用差分

| 対象 | 固定値 |
| --- | --- |
| #78・基盤 | `b438609f4bd7c04ff812d64e7de74718b935a39f` |
| #79・P | `d9299b4d897849c218695f0cf1d5057e43e30af2` |
| PのGit blob SHA-256 | `bfe9187863c66828c3f7edee175ee1b718a37651c6b213db9e031b748e076924` |
| #80・L・今回のbase | `75718764a5794321a55b9b01f130a1c1eb4480f5` / `codex/opening-seed-loop-l2b0` |
| 今回のbranch | `codex/opening-seed-loop-live-usage` |

| Pの未決事項 | 今回の設計採用 | 残る判断・承認 |
| --- | --- | --- |
| §3・§9：案B | PoC限定、実設定の明示承認がある場合だけAPI提供枠を監視。旧L2a/L2b-0の案A両枠既定は維持 | 現Windows応答、CLI/schema、同じアカウント/プラン、非提供根拠と監視制限を利用者が確認・承認 |
| §5.4：独立出典レビュー方式 | 抽出とは異なるAI sessionを第一採用。同一モデルでも誤りが相関するため、原文への直接照合・対象hash・session識別が必要 | 担当session・モデル・実設定はworker接続時に固定。方式採用は個別出典合格ではない |
| §5.3：修正上限 | 初回生成を除き1 task累計最大2回。同一原因で改善なし2回も停止、resume/run IDでresetしない | 今回実修正turnは0回。実workerでの執行は後続 |
| §6.1：P/L継承 | 上記P/Lを固定しLから準備Draft PRを1本 | 将来の統合先・方式は未採用。依存PRへpush/merge/Ready/retarget/force-push/auto-mergeしない |
| §4：対象候補 | 横歩取り△2三歩候補1件を維持 | revision・後続手・収録範囲・担当は未確認。今回調査しない |
| §3.3・§6.2：タイマー | poll 15秒・turn上限120秒・CI検出5分/完了60分は原計画の提案値を継承 | 今回は実推論タイマーを実装せず、制御実績とも呼ばない |

設計採用はこの実装依頼に基づく。利用者の実アカウント/取得応答/CLIに結合する**実環境承認は未実施**。
Codexが承認者・承認日時・観測値を代筆しない。新しいlive承認kindと対話確認を用い、
`simulated-adoption`を実承認へ昇格させない。

## 監視の意味と停止

2026-11-09の利用者申告に基づく初期候補は`codex / primary=object,10080分 / secondary=明示null`。
[設定見本](opening-seed-loop-live-settings.example.json)は未承認の候補で、現在の応答を断定しない。
primary/secondaryの両keyを監査し、有効objectをすべて監視する。欠落と明示nullは別であり、
object出現・消失・期間変更・bucket不一致・未知形式では停止する。期待集合を自動変更しない。
他bucket・非公開枠・課金制限の全監視は保証しない。

nullを何度観測しても恒常的非提供や他制限不存在の証明にはしない。公式schemaはnullableな形を示すだけで、
個別アカウントの非提供は証明しない。利用者は公式仕様・アカウント条件・保存済み現応答を確認し、
**APIで確認できる枠の条件付き監視に十分な根拠か**を判断する。不十分なら保留する。
条件メモには確認日、プラン/ワークスペース条件、公式資料の所在・hash、現観測ID、nullの解釈、監視外制限を書く。
生ID・メール・tokenは書かない。承認のscopeはその限界を含む固定列挙である。

既存`normalize/decision`を同じID照合済みraw応答に適用する。使用済み絶対割合25%以上で
`no_new_task`、30%以上で`budget_stop`。unknown/unsupported、不正、未来、120秒超、観測後reset跨ぎは拒否。
120秒ちょうどは有効。resetから0%を推定せず、観測時刻の書換え・fixture fallbackも行わない。
read後と最終publication lock取得後に、入力/証拠/承認を照合してから最新時計で同じusageを再判定する。
停止後の`gate`は拒否し、明示`resume`で新しいreadを行う。`observe`は停止を解除せずいつでも診断できる。
25/30%以上や未承認でも診断のread・保存・終了管理を予算gateで閉じない。

## CLI 0.167.0との契約照合

確認日：2026-11-15 JST。公式`rust-v0.167.0` tag objectは
`cb41599ccbe371272892f156286a236aa097bada`、解決したcommitは
[`086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a`](https://github.com/openai/codex/tree/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a)。
当該commitの`codex-rs/app-server-protocol/schema/`生成JSON/TypeScriptと
`src/protocol/v2/account.rs`、`protocol/common.rs`を照合した。最新mainの説明で置換していない。
生成schemaの実byte列はGitHub Contents APIのbase64をdecodeしてhash化した。

| 当該版の資料 | SHA-256 |
| --- | --- |
| `json/v2/GetAccountRateLimitsResponse.json` | `9c0def7f8ab2396122af939dffbf01b34b8d66082fe4129dd20917bfd4313fdc` |
| `json/v2/GetAccountResponse.json` | `1d44d4274ea35e1f866c4b0e3db64678fab108914c276353bdc3b1b0de286459` |
| `typescript/InitializeCapabilities.ts` | `744ccfe4b48827f351d00f4fcaf8b28596f1710f37036850ffeda1b4e4412408` |
| `typescript/v2/GetAccountParams.ts` | `73feed16e294673d984618e2264a32be4b20bfe45973fdba064bddd2e6c6c18a` |
| `typescript/v2/GetAccountRateLimitsParams.ts` | `2777710a93776ec971d9f4a016b20d8f555525d1f40de4a5e7bec6e58ce37e97` |

許可する送信methodは`initialize`、`initialized`、`account/read`、`account/rateLimits/read`のみ。
`experimentalApi=false / requestAttestation=false`。account確認はreadの前後2回、`refreshToken=false`。
usageは1回だけで、`supportsLunaReserve=false / excludeResetCreditDetails=true`。
read全体に既存15秒deadlineを共有し、その後に既存所有App Server子の終了/stream後処理を行う。
通知・別ID応答を混ぜない。`rateLimitsByLimitId`が存在すればnullや指定bucket欠落でも互換viewへ逃げない。
単一viewだけの場合も明示`limitId=codex`を要求する。業務read-onlyと、CLIが通常初期化・認証維持のため
ローカル状態を書き得ることは別。認証設定を人為的に変更する処理はない。

当該版の既知metadataは`limitName/normalModelSlug/planType/credits/individualLimit`と、
応答側`accountId/rateLimitResetCredits/rateLimitUpsell`。未知keyは停止する。
credit残高・display文字列は型だけを確認し、保存・使用率推定に使わない。
reset creditは形を検査するが利用しない。任意JSONのupsellが非nullなら意味未対応として保留する。
`ordinaryUsageAllowed=false`、`spendControlReached=true`、既知`rateLimitReachedType`の非null、
`individualLimit.remainingPercent=0`は低使用率でも拒否。
ordinary permission不明、spend control不明もfail-closedとし、過去値から復帰を推測しない。
当該JSON schemaの`usedPercent`はint32、Rustはcoreの値を丸めるためlive rawでは整数を要求する。
24.99/29.99の閾値は共有純粋予算判定で試験し、CLIが小数精度を提供すると主張しない。

[App Server説明](https://learn.chatgpt.com/docs/app-server)と
[使用量説明](https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex)
は本実装環境の直接取得が接続エラーとなり本文未確認。当該版の公式repository/schemaを根拠にした。
Windows利用者は現説明・導入済み版のschema・自分の条件も確認する。公式のnullable定義は全制限不存在の根拠ではない。

## 記録・承認・秘密情報

新CLIは`python -m scripts.seed_loop.live_usage --session ID COMMAND ...`。
`observe/gate/resume`は`--live-usage`必須。実入口の第一対象はWindows通常PowerShell、既存ChatGPTログイン。
毎操作で絶対`codex.cmd`の`--version`を再取得し`codex-cli 0.167.0`へ完全一致を要求する。
自動更新/降格、API key課金への切替、CODEX_HOME変更、認証fileコピーはしない。
管理LinuxにCODEX_HOME read-onlyで初期化不能だった履歴を保持し、Linux live入口は拒否する。
権限変更や再マウントを試みない。

| 操作 | 意味 |
| --- | --- |
| `contract` | 固定版source/schema hash、API契約hash、監視制限を表示。通信しない |
| `observe --live-usage --settings PATH` | 未承認でも有界read。`observation_only=true`、業務許可なし |
| `show --operation-id ID` | hash照合済みのsanitize監査・正規化・判定を表示。通信しない |
| `candidate --observation-id ID --settings PATH --grounds PATH --conditions PATH` | 保存観測・根拠から未承認候補を作成。期待集合は設定からだけ読み、自動生成しない |
| `approve --candidate-id ID --actor LOCAL_ALIAS` | ローカルTTYで候補全文を表示し`APPROVE 候補hash`の入力を要求。自動承認flag/importなし |
| `gate/resume --live-usage --settings PATH --approval-id ID --grounds PATH --conditions PATH` | 毎回新readし全条件を再判定。worker起動は常にfalse |
| `status` | 履歴・不完全保存・証拠失効を表示。通信しない |

記録先はGit管理外`.seed-loop/live-usage/SESSION/`。旧`.seed-loop/runs/`、L2b-0 task台帳には触れない。
各操作の`request/audit/read/result`と候補/承認は別kind/version・UUIDで原子的保存し、上書きしない。
承認済み判定は使用した候補/承認の実byte hashと承認元観測も結合し、statusでその欠落/変更を検出する。
監査保存→同一rawの正規化→read判定保存→証拠/入力/承認照合→完了時再判定→結果保存の順。
保存失敗は成功にせず、requestだけ残れば`incomplete_or_evidence_invalid`。再開は別操作・別証拠を追加する。
旧auditが消えても旧resultを修復/成功へ書き換えず、statusは実効的に無効と表示する。
新規readは旧証拠を再作成したふりをしない。承認元の観測が欠ければその承認も使えない。

承認IDを指定する操作では、readとrequest保存の**前**に
`approval-uses/APPROVAL_ID/OPERATION_ID/`と`intent.json`を作る。
kindは`seed-loop-live-diagnostic-approval-use / version:1`で、操作ID・承認ID・action・origin・作成時刻を結合する。
requestはintentのbyte hashを保持し、証拠検査で照合する。intent自体の保存失敗でもdirectoryが結果不明のguardとなり、
readは起動しない。read後のaudit/read/resultの保存失敗・欠落・hash不一致、request/intentの破損でも、
その承認に結び付く過去操作を「失効していない」とは扱わない。
正常な失効履歴は`approval_previously_invalidated`、結合した履歴の結果・失効有無を確認できない場合は
`approval_history_unknown`で同じ旧承認を拒否する。今回処理中の操作だけを履歴検査から除外する。
過去の失効や結果不明を、後の正常readで消したり、結果保存の再実行で埋めたりしない。

履歴表示ではrequestが壊れても、保持したresultのメタデータと承認別guardから帰属を復元して不正状態を表示する。
旧形式は有効なrequest/resultから承認IDを照合し、書き換えや暗黙移行をしない。
どちらも失われ、承認IDに帰属させられない旧操作が新たに見つかった場合も旧承認を安全側に拒否する。
新しい候補は既存の帰属不明IDを`acknowledged_unattributed_operations`へ明示し、本人の新しい対話承認のhashへ結合する。
これは旧操作の成功化ではない。未承認の新しいobserve、根拠確認、新しいcandidate/approve、明示resumeで復帰する。
既知の無関係な未承認診断のエラーや、別の承認に結び付く結果不明は、新承認を永久停止させない。
正常な予算停止は失効ではなく、同じ健全な承認を使う明示resumeのfresh readで再判定できる。

同sessionのOS lockで二重操作を拒否。共有network filesystem、電源断時directory永続化、
全fileを再hashして改ざんする攻撃への耐性は保証しない。保存領域ごとローカルに保全する。

承認は`seed-loop-live-approval / version:1 / origin:live`。
CI専用は`seed-loop-test-approval / origin:test`でありliveに使えない。生応答、token、メール、生ID、
環境変数一覧、認証fileはGit/CI artifactへ出さない。数値・key状態・型・版・時刻・hashだけを保存する。
`account/read`のChatGPT/planとusageのaccountIdを、session専用ランダムkeyのHMACへ変換する。
keyは認証情報ではなくローカル識別用であり、紛失時は復元/新規作成して旧承認を再利用しない。
前後account/readの一致とusageのID fingerprintを比較するが、APIは両者の暗号学的同一性を証明しない。
利用者は通常アプリの選択中ChatGPTアカウント/プラン/ワークスペースを画面で手動確認し、
承認する条件メモへ確認方法を記す。IDを表示/転載しない。accountIdが未提供なら自動同一性確認不能として保留する。
手動確認だけで欠落IDを捏造するoverrideはない。

結合対象はP/L、計画blob、本書のGit blobとcheckout byte hash、実装module byte hash、設定/予算hash、
CLI path/shim hash・版/API契約、OS/Python、bucket/両key状態/duration、HMACアカウント/プラン、
根拠/条件メモhash、承認元観測hash、承認者alias・日時・確認操作hash・scope。
同条件でも承認後24時間超/未来日時は拒否する。値`usedPercent/resetsAt`は承認bindingへ固定せず、毎readで取得する。
承認使用中に集合・期間・CLI/アカウント/設定条件の変更を観測した場合は、その承認の失効を記録する。
条件を戻しても旧承認は復帰しない。新観測と利用者の再承認が必要である。
候補hashは候補payloadだけ、承認hashは承認payloadだけ。自己hashをpayloadへ含めない。
JSON正規化は既存`digest`（UTF-8、sort_keys、ensure_ascii=false、allow_nan=false、Python既定separator）。
byte証拠hashは無変換SHA-256。working treeのCRLF hashとGit blob hashを区別する。

## Windowsでの後日確認手順

**Windows live未確認。実承認・日時・観測値はここに作らない。**
準備PR本文の最終HEAD欄を`$ExpectedHead`へ貼る。自己参照を避けるため本書へ自身のcommit SHAを埋めない。
PR本文には実際の最終HEADを指定した呼出例を置く。通常アプリ/checkpointを保全する専用の新規checkoutだけを使う。
以下は通常PowerShellのscript block。全native callは存在確認と終了値を確認し、古いLASTEXITCODEへ進まない。
同blockを段階ごとに使い、観測・根拠レビュー・承認の間は人が内容を確認する。

```powershell
& {
  param([Parameter(Mandatory)][string]$ExpectedHead,
        [Parameter(Mandatory)][string]$Checkout)
  $ErrorActionPreference = 'Stop'
  function Native([string]$Exe, [string[]]$Argv) {
    $Resolved = (Get-Command $Exe -CommandType Application -ErrorAction Stop).Source
    $Text = & $Resolved @Argv
    if ($LASTEXITCODE -ne 0) { throw "Native command failed: $Exe ($LASTEXITCODE)" }
    return $Text
  }
  if (Test-Path -LiteralPath $Checkout) { throw 'Choose a new dedicated checkout directory' }
  if ($ExpectedHead -notmatch '^[a-f0-9]{40}$') { throw 'Exact final SHA required' }
  $Repo = 'fujihara-masaki/shogi-learning-202606'
  $Pins = @(
    @(78,'codex/wikipedia-seed-loop-foundation','b438609f4bd7c04ff812d64e7de74718b935a39f','claude/clever-hopper-bphezm','49e45f45bd03bb958cfef1088f1fa44b67c15cdd'),
    @(79,'codex/opening-seed-loop-poc-plan','d9299b4d897849c218695f0cf1d5057e43e30af2','codex/wikipedia-seed-loop-foundation','b438609f4bd7c04ff812d64e7de74718b935a39f'),
    @(80,'codex/opening-seed-loop-l2b0','75718764a5794321a55b9b01f130a1c1eb4480f5','codex/opening-seed-loop-poc-plan','d9299b4d897849c218695f0cf1d5057e43e30af2')
  )
  foreach ($Pin in $Pins) {
    $P = (Native 'gh' @('api',"repos/$Repo/pulls/$($Pin[0])")) | ConvertFrom-Json
    if ($P.state -ne 'open' -or !$P.draft -or $P.merged -or $null -ne $P.auto_merge -or
        $P.head.ref -ne $Pin[1] -or $P.head.sha -ne $Pin[2] -or
        $P.base.ref -ne $Pin[3] -or $P.base.sha -ne $Pin[4]) { throw 'Fixed dependency changed' }
  }
  Native 'git' @('clone','--branch','codex/opening-seed-loop-live-usage',"https://github.com/$Repo.git",$Checkout)
  Push-Location -LiteralPath $Checkout
  try {
    if ((Native 'git' @('rev-parse','HEAD')).Trim() -ne $ExpectedHead) { throw 'HEAD changed' }
    Native 'git' @('merge-base','--is-ancestor','75718764a5794321a55b9b01f130a1c1eb4480f5','HEAD')
    Native 'python' @('-m','venv','work/usage-venv')
    $Python = (Resolve-Path 'work/usage-venv/Scripts/python.exe').Path
    Native $Python @('--version')
    Native 'node' @('--version')
    Native 'npm.cmd' @('--version')
    $Codex = (Get-Command 'codex.cmd' -CommandType Application -ErrorAction Stop).Source
    if ((Native $Codex @('--version')).Trim() -ne 'codex-cli 0.167.0') { throw 'CLI version differs; do not update automatically' }
    Native $Codex @('app-server','generate-json-schema','--out','work/schema-0.167.0')
    Native $Python @('-c',"import hashlib,subprocess; b=subprocess.check_output(['git','show','d9299b4d897849c218695f0cf1d5057e43e30af2:docs/opening-seed-loop-poc-plan.md']); assert hashlib.sha256(b).hexdigest()=='bfe9187863c66828c3f7edee175ee1b718a37651c6b213db9e031b748e076924'")
    # Existing login: manually verify account/plan/workspace in the usual app.
    # Verify the current CODEX_HOME's normal write prerequisites; never display/copy auth files.
    $Config = Get-Content -Raw -Encoding UTF8 'docs/opening-seed-loop-live-settings.example.json' | ConvertFrom-Json
    $Config.codex_binary = $Codex
    [IO.File]::WriteAllText((Join-Path $PWD 'work/live-settings.json'),($Config | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    $Cmd = @('-m','scripts.seed_loop.live_usage','--session','windows-usage')
    Native $Python ($Cmd + @('contract'))
    $Observed = (Native $Python ($Cmd + @('observe','--live-usage','--settings','work/live-settings.json'))) | ConvertFrom-Json
    Native $Python ($Cmd + @('show','--operation-id',$Observed.operation_id))
    # An observation is never a start permit, including when usedPercent is low.
    Write-Host "Observation ID: $($Observed.operation_id); worker remains disconnected."
  } finally { Pop-Location }
} -ExpectedHead $ExpectedHead -Checkout $Checkout
```

既知の利用者環境はPython 3.12.10 / Node 24.15.0 / npm 12.0.2 / CLI 0.167.0。
上記は現在値を表示し、版を勝手に変更しない。Pythonは`python`か利用者指定のPython絶対pathを使う。
`work/schema-0.167.0`の生成schemaを上記固定版公式契約と照合し、相違があれば承認しない。
`py` launcher、管理者権限、pip依存の追加は不要。通常ログインを維持できず初期化失敗なら原因を安全に分類して保留する。

専用checkoutへ移動し、`$Python`と`$Cmd`を再設定する。保存観測を`show`で再表示し、
現在の公式資料/導入版schemaと照合して`work/account-conditions.txt`を利用者が作る。
UTF-8で保存し、生ID/メール/tokenを書かない。`contract`表示のhashとscope、および
`python -c "from pathlib import Path; import hashlib; print(hashlib.sha256(Path('work/account-conditions.txt').read_bytes()).hexdigest())"`
のbyte hashを使い、次の`work/grounds.json`を**利用者が**編集する。`false`のままなら保留。

```json
{
  "kind": "seed-loop-live-grounds", "version": 1,
  "official_contract_hash": "COPY_FROM_CONTRACT_OUTPUT",
  "conditions_sha256": "COPY_ACTUAL_BYTE_HASH",
  "sufficient_for_conditional_scope": false,
  "scope": ["api-provided-codex-windows-only", "null-is-observation-not-permanent-absence",
            "other-buckets-hidden-billing-limits-unmonitored", "workers-always-disconnected"]
}
```

確認後、次のscript blockを実行する。候補を作るだけでは承認しない。
`approve`のTTYで表示候補/根拠/制限を読み、本人が要求された文字列を入力する。

```powershell
& {
  param([Parameter(Mandatory)][string]$ObservationId,
        [Parameter(Mandatory)][string]$ActorAlias)
  $ErrorActionPreference = 'Stop'
  $Python = (Resolve-Path 'work/usage-venv/Scripts/python.exe').Path
  $Cmd = @('-m','scripts.seed_loop.live_usage','--session','windows-usage')
  function UsageJson([string[]]$Argv, [int[]]$Allowed = @(0)) {
    if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python missing' }
    $Text = & $Python @Cmd @Argv
    $Code = $LASTEXITCODE
    if ($Allowed -notcontains $Code) { throw "usage operation failed ($Code)" }
    return ($Text | ConvertFrom-Json)
  }
  $Candidate = UsageJson @('candidate','--observation-id',$ObservationId,'--settings','work/live-settings.json','--grounds','work/grounds.json','--conditions','work/account-conditions.txt')
  # Interactive output includes prompts; do not pipe approve through JSON parsing.
  & $Python @Cmd approve --candidate-id $Candidate.candidate_id --actor $ActorAlias
  if ($LASTEXITCODE -ne 0) { throw 'Approval not completed' }
  $Gate = UsageJson @('gate','--live-usage','--settings','work/live-settings.json','--approval-id',$Candidate.candidate_id,'--grounds','work/grounds.json','--conditions','work/account-conditions.txt') @(0,3)
  $Gate | ConvertTo-Json -Depth 20
  if (!$Gate.monitoring_budget_permit) { Write-Host 'Read completed; new work prohibited. Inspect stop_reason.'; return }
  Write-Host 'Read-only gate passed for this observation; worker remains disconnected.'
} -ObservationId $ObservationId -ActorAlias 'local-owner'
```

上の診断後に停止したsessionでは`gate`を`resume`へ明示変更する。毎回fresh readする。
現在値がknownでも25/30%以上なら通信と新規作業禁止を分けて記録する。
結果の`real_usage / communication / diagnostic_complete / approval_state / monitoring_budget_permit / worker_connected`
を別々に確認する。過去の承認/観測の許可値を次回の開始許可として持ち越さない。

| 結果field | 意味 |
| --- | --- |
| `communication` | 既存adapterでID照合した応答を受信し、cleanup errorがない場合は`response_received`。完了境界で証拠が失われても受信済みの事実を成功/失敗へ書き換えない |
| `diagnostic_complete` | audit保存・終了管理に加え、read後とpublication lock取得後の両境界でrequest/audit/read等の必須証拠を照合できた場合だけtrue。証拠欠落・変更・読取不能ならfalse |
| `approval_state` | 実承認の検査結果。`policy_pending`や承認拒否は、正常に証拠付き観測を完了したこととは別 |
| `monitoring_budget_permit` | gate/resumeで現在の監視・予算・承認履歴が適合した場合だけtrue。observeは常にfalse |
| `worker_connected` / `worker_start_permitted` | 常にfalse。診断成功や監視/予算適合はworker開始許可ではない |

observeは、正常に証拠を保存・照合できれば未承認や25/30%以上でも**終了0**。
完了境界の証拠異常などを原因付きresultとして保存できた診断未完了は、`diagnostic_complete=false`と**終了3**。
gate/resumeの不許可も終了3。request/read/result保存不能等で操作結果を確定できない運用エラーは**終了2**で、
残ったintent/request/auditを保全する。`stop_reason != null`だけでobserveを失敗扱いにはしない。

## 試験・受入の区分

```text
python -m unittest discover -s scripts/tests -v
python -m scripts.seed_loop validate --profile full --run-id l2b1a-final
```

専用試験は固定CI stdio serverを同じ`read_audited`・raw監査・正規化・保存・境界へ接続する。
originはtest、実アカウント/token/ログインなし。Windowsでは日本語/空白絶対`.cmd`、UTF-8/CRLF、終了処理も実行する。
LinuxでのWindows専用skip、旧Linux専用試験のWindows skipを明記する。旧L2a/L2b-0と#80のA/B回帰は維持する。
最終HEAD、実コマンド、成功/失敗/skip、CI run/job/実checkout SHAは準備PR本文で確認する。

| 区分 | 受入条件 |
| --- | --- |
| 実装受入 | 採用記録・read-only入口・監査/境界・模擬試験・最新CI・Draft PR・最終HEAD付きWindows手順 |
| 実接続受入 | 利用者のWindowsで現応答→実承認→新read→保存→判定→終了を実測。高使用率停止でも通信を別記できる |
| 1件PoC開始 | 実worker等の後続機能/審査が揃い、開始時fresh gateが通る。今回未達成 |

実装環境にはWindows executorがなく、Windows実アカウント接続・実環境承認は未実施。
開発者の本準備PRへのcommit/push/PR作成は依頼で許可された開発操作であり、controllerの機能ではない。
