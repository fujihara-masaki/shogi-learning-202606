# 高度な定跡分岐可視化 follow-up 計画

- 対象: `fujihara-masaki/shogi-learning-202606`
- 検討時期: `docs/opening-branch-learning-wikipedia-import-plan.md` の PR-B / PR-C を含む完了条件を満たした後
- 位置づけ: discovery / prototype / performance planning。production実装を約束するものではない。

## 1. 本計画との境界

先行計画では、direct-parent tree、semantic mainと表示順の分離、通常は折りたたまれた補助一覧、current path、current/ancestor highlight、node jump、「この分岐点の本線へ切り替える」までを提供する。これらは盤面と通常の棋譜再生を中心にした学習UXを成立させるための基礎である。

本書の横レーン型visual branch tree、棋譜リストとの高度な同期、分岐比較、巨大tree最適化は、**先行計画のPR-Cにも全体完了条件にも追加しない**。PR-B/Cの実測と利用者feedbackを入力に、独立したRFCと小さなprototypeで採否を決める。先行計画を本書の実装待ちでblockしない。

## 2. 候補UXとベンチマーク方針

### 2.1 横レーン型 visual branch tree

ShogiHome等の棋譜再生ソフトで見られる、手数方向を一軸、分岐を横方向のlaneとして配置するvisual branch treeを候補にする。branchの発生、継続、合流候補、現在位置を線とnodeで俯瞰できることが利点である。

follow-up開始時には対象ソフトの現行version、OS、表示mode、操作手順を記録した比較表とscreen recordingを作る。「見た目を模倣する」のではなく、次のtaskが少ない操作で完了するかを比較する。

- 現在局面がどのbranch / 何手目かを見つける。
- 分岐元と二つの後続を見比べる。
- 遠いnodeへjumpし、元のcurrent pathへ戻る。
- mainとvariationを色だけに依存せず識別する。
- keyboard、screen reader、touchで同じnodeへ到達する。

### 2.2 棋譜リストとの手数同期

盤面、通常棋譜リスト、visual treeの三者で単一のselected node / path stateを共有する。

- 盤面の一手進む/戻る、棋譜行click、tree node clickのいずれも同じ手数・SFEN・source・historyへ更新する。
- current nodeを両viewでhighlightし、可能なら対応行/nodeを`scrollIntoView`する。ただし利用者が手動scroll中に毎手強制scrollしないmodeを検討する。
- 自動再生中の描画頻度、focus移動、`prefers-reduced-motion`を定義する。
- 手数表示（先後を一組とする番号かplyか）を内部node IDと混同しない。

### 2.3 分岐比較

二つのnodeまたはbranchを選び、共通祖先からの差分を比較する候補を検討する。

- 共通祖先、分岐手、各pathの手順、終端局面、coverage/provenanceを並べる。
- 盤面差分は駒配置だけでなく手番・持駒を含める。
- transposition候補は「同じ局面」と「同じ学習node」を区別し、自動mergeしない。
- 2 branch比較から始め、任意個数比較やengine評価値比較は別機能とする。
- Wikipedia由来解説を大量複製せず、source参照と短いmetadataを再利用する。

### 2.4 大規模tree対応

PR-Cの500-node fixtureに加え、深いtree、広いtree、branch-heavy Wikipedia相当の現実的fixtureを用意する。

検討候補:

- collapsed subtreeの遅延mount。
- viewport virtualization / canvas / SVG / HTMLの比較。
- lane割当のincremental計算とlayout worker化。
- zoom、pan、overview/minimap、現在pathだけへ絞るfilter。
- branch名、手数、USI、provenanceによる検索。
- layout安定性（node追加や表示順変更でlaneが不必要に飛ばないこと）。
- mobileでは全treeを縮小するのでなく、current path中心のwindowや補助一覧へ切り替えるresponsive戦略。

性能基準はprototype前に恣意的に固定しない。PR-C実測、対象端末、node/edge数、初期表示・jump・pan/zoomの各taskを分け、計測値と利用者が感じる遅延からbudgetを決める。

## 3. 前提となるデータ・状態契約

follow-upは先行PR-B/Cの次を再利用し、別tree表現を新たなsource of truthにしない。

- stable node key / direct `parent_move_id`。
- siblingごとのexplicit mainと独立した`sort_order`。
- rootからnodeへの一意なpathとcurrent/ancestor判定。
- transpositionを自動mergeしない学習tree。
- node / segment単位のbranch label、coverage、provenance。
- node jumpと「この分岐点の本線へ切り替える」の共通command/helper。

visual lane、座標、折りたたみ、zoomはderived UI stateとする。URLへ永続化する場合も配列indexでなくstable node keyを使い、古いlinkのmigration規則を定める。

## 4. discovery と prototype の段階

### Phase V0: 比較調査

- ShogiHomeを含む複数のメジャーな棋譜再生ソフトについて、version付きで分岐作成、分岐切替、main復帰、手数同期、大規模棋譜のtask analysisを行う。
- desktop / mobile、mouse / keyboardの差、accessible name/focusの観察結果を記録する。
- screenshotや名称の利用条件を確認し、成果物には必要な出典を付ける。

### Phase V1: read-only prototype

- production routeから隔離したfixtureベースprototypeで、横レーンlayoutとcurrent path同期だけを検証する。
- 既存PR-C一覧をfallbackとして残し、盤面・sourceの更新は既存node jump helperを使う。
- SVG、HTML/CSS、canvasの少なくとも二案を、accessibility、hit target、長い日本語label、印刷/zoom、性能で比較する。

### Phase V2: interaction prototype

- branch比較、keyboard navigation、pan/zoom、currentへ戻る操作を追加する。
- 360px、200% zoom、reduced motion、screen reader、touchを含むtask testを行う。
- 既存の盤面/card/listよりtask成功率が下がる場合、visual treeをadvanced modeのままにするか不採用とする。

### Phase V3: production提案

- prototypeの採用判断、component/API境界、性能budget、telemetry/privacy、段階rollout、rollbackをRFC化する。
- production PRはlayout engine、同期、比較、大規模最適化を必要に応じて分割し、一括導入しない。

## 5. 評価項目

| 観点 | 確認内容 |
|---|---|
| comprehension | branch数、分岐元、current path、mainを短時間で説明できるか |
| navigation | 目的nodeへのjump、元のcurrentへ復帰、誤click率 |
| comparison | 共通祖先と差分手順を正しく把握できるか |
| consistency | board / move list / tree / sourceが同一nodeを指すか |
| accessibility | keyboard順序、screen reader名、色非依存、200% zoom、reduced motion |
| responsive | 360pxで盤面学習を阻害せず、代替一覧へ戻れるか |
| performance | node規模別の初期表示、layout、jump、scroll/pan、memory、DOM数 |
| stability | seed追加、表示順変更、resizeで不要なlane移動が少ないか |
| provenance | branch/nodeごとのcoverage/sourceを取り違えないか |

## 6. 非目標

- 先行するopening branch / Wikipedia import計画の完了条件を拡張すること。
- 一般的な将棋GUI、棋譜編集、対局、engine analysis機能を丸ごと再現すること。
- transpositionをDAGとして自動mergeすること。
- engine評価値を根拠にWikipedia由来のmainや解説を自動変更すること。
- visual treeがないと定跡学習やbranch navigationを利用できない設計にすること。

## 7. 着手gateと成果物

着手gate:

1. PR-Bのdirect parent / explicit main / display order契約がproduction dataで安定している。
2. PR-Cのcollapsed list、current/ancestor、node jump、main切替が実装され、500-node測定がある。
3. branch-heavy seedの実規模、利用頻度、PR-Cで解決しないtaskが観測されている。

成果物はversion付き比較表、task flow、accessible prototype、性能report、採用/不採用理由を含むRFCとする。採用しない場合もPR-Cの補助一覧を恒久fallbackとして維持する。
