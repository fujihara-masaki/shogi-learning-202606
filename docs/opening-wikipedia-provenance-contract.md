# Wikipedia 定跡 provenance / coverage 監査契約（v1.0.0）

## 1. 目的と適用範囲

本書は、Wikipedia/Wikibooks に由来すると主張する **catalog provenance** と **move-line provenance** の境界、および後者の監査交換形式を固定する。canonical 形式は [`opening-wikipedia-provenance-audit.json`](opening-wikipedia-provenance-audit.json)、その構文契約は [`opening-wikipedia-provenance-audit.schema.json`](opening-wikipedia-provenance-audit.schema.json)（JSON Schema draft-07）である。schema version `1.0.0` の破壊的変更は version を上げる。

これは監査契約であり、DB の `coverage_status`、migration、API、画面、または `SAMPLE_OPENING_LINES` を変更する契約ではない。現行の自由文 `coverage_status` は artifact の `legacy_coverage_status` に原文のまま写し、正規化 `coverage` と同一視しない。

## 2. provenance class

| code | enum | 契約 | move seed |
|---|---|---|---|
| A | `explicit_sequence` | Wikipedia 本文で着手を順番どおり連続して確認できる範囲。本文にない中間手は含めない。 | 全手を同一 revision で検証後に可 |
| B | `diagram_reconstruction` | Wikipedia の局面図とその周辺説明を根拠に再構成した範囲。A と表示・metadata を区別する。 | review 後、独立 line/segment として可 |
| C | `name_only` | 戦法名・変化名の存在だけを確認した catalog 根拠。 | **不可** |
| M | `mixed` | 一つの line に A と B が混在するもの。line 全体を「本文明示手順」と表示しない。 | A/B の各 segment を検証後に可 |

一般的な将棋知識、棋譜 DB、書籍、別サイト、または engine の候補手を用いて「Wikipedia 由来」の不足手を補ってはならない。別資料を併用する場合は Wikipedia provenance の外に独立した source/segment として記録し、A/B の根拠には数えない。

## 3. coverage enum

正規化列挙値と合法な組合せは次だけである。

| provenance | coverage | 意味 |
|---|---|---|
| A | `complete_for_cited_sequence` | cited section が明示する対象列の終端まで収録 |
| A | `partial_explicit_sequence` | cited section の明示列の途中まで収録 |
| B | `diagram_reconstruction` | 図と周辺説明から再構成 |
| C | `name_only` | 名称/catalog のみ（moves は空） |
| M | `mixed` | A/B segment が混在 |

「記事全体を網羅した」という意味ではなく、`complete_for_cited_sequence` も **引用した特定の連続列** に対する完了だけを表す。自由文の現行 DB `coverage_status` は説明用 legacy field であり、この enum の代用にしない。

## 4. catalog と move-line の分離

* **catalog provenance** は `opening_types` / `opening_categories` 等について「名称・分類・説明が資料に存在する」ことだけを表す。C を持てるが moves を持てない。
* **move-line provenance** は `SAMPLE_OPENING_LINES` / `opening_lines` の具体的な USI 列の各手がどの revision、section、本文列または図に基づくかを表す。
* catalog source が Wikipedia/Wikibooks であることを、move-line の A/B 判定へ継承してはならない。line ごと（M は segment ごと）に独立した evidence が必要である。

## 5. 必須 metadata

### 5.1 全監査 record

`record_id`, `subject_kind`, `line_name`, `seed_locator`, `provenance_class`, `coverage`, `verification`, `audit_issues` を必須とする。move-line はさらに `move_count`, `moves`, `coverage_boundary`, `evidence_note`, `segments`, `source` を必須とする。`evidence_note` は短い paraphrase とし、本文を長く転載しない。

### 5.2 source

| field | 条件と意味 |
|---|---|
| `source_type` | 必須。`wikipedia` または `wikibooks` |
| `source_title` | 必須。取得時の人間可読 title |
| `requested_url` | 必須。seed/調査者が要求した URL。redirect 後 URL で上書きしない |
| `canonical_url` | verified なら必須。redirect 解決後の canonical URL。取得不能時だけ `null` |
| `source_section` | move provenance が verified なら非空必須。取得不能/既存欠落の監査表現だけ `null` |
| `revision_id` | verified なら正整数必須。current revision を推測しない |
| `revision_timestamp` | verified なら revision の UTC timestamp 必須 |
| `retrieved_at` | 必須。取得を試みた UTC calendar date (`YYYY-MM-DD`) |
| `source_license` | 必須。取得時に確認した、または現行 seed が主張する license。後者は verification note で区別 |

`verification.status` は `verified`, `needs_review`, `unavailable`。`verified` のとき canonical URL、section、revision ID/timestamp が揃わなければ schema 違反である。取得不能なら値を捏造せず `null` とし、方法、時刻、理由を note に残す。

### 5.3 coverage boundary と M segment

move-line の `covered_through_ply` は収録済み終端の 1-origin ply、`covered_through_move` はその USI、`omitted_after` は判明している未収録の後続（なければ `null`）である。終端は `covered_through_ply == move_count == len(moves)` かつ `covered_through_move == moves[-1]` を満たす。

M は `segments` を2件以上持ち、各要素に `provenance_class`（A/B のみ）、包含的 `start_ply` / `end_ply`、`source_section`, `evidence_note` を持つ。範囲は 1 から `move_count` までを隙間・重複なく覆い、昇順で、少なくとも A と B を各1件含む。同じ section でも根拠種別が変わる境界で分割する。A/B の単一 provenance line は `segments: []` とする。

## 6. machine-readable artifact の読み方

監査 artifact は seed snapshot にある `backend/app/seed.py` の `SAMPLE_OPENING_LINES` 全件を機械抽出した、一行一 record の棚卸しである。`audit_issues` は既存データまたは外部確認の未完了を隠さず記録するための field であり、配列が空であることを schema 適合条件にはしない。つまり **schema valid は production metadata verified/compliant と同義ではない**。

2026-08-15 の監査では shell の HTTPS proxy が 403、別の web retrieval が 401 を返したため、全 source の current revision、redirect、canonical URL、section の存在を確認できなかった。したがって全34件を `unavailable`、revision/canonical を `null` とした。requested URL、legacy note/license/section は seed から機械抽出した値であり「current Wikipedia で確認済み」ではない。section が seed にない31件は `source_section_missing_in_seed`、升田式石田流には既知の終端主張不一致を記録した。

## 7. PR-D1 validator の規範要件

PR-D1 の production validator は最低限、次を失敗にする。

1. Wikipedia move-line の必須 metadata 欠落、または source section/revision/retrieved date/license の欠落。
2. provenance/coverage が列挙外、または第3節にない組合せ。
3. C/catalog record から move seed を生成、または catalog provenance を move-line evidence として継承。
4. M に segment がない、A/B 両方を含まない、範囲に隙間・重複・逆転・範囲外がある。
5. `move_count != len(moves)`、`covered_through_ply != len(moves)`、または終端 USI 不一致。
6. A の各 move が cited revision/section の連続本文列で確認できない、B を A と表示、または Wikipedia にない中間手を他の知識で補完。
7. `source_note` / `evidence_note` が `moves` にない後続を「手順化」「収録済み」と主張する。未収録なら `omitted_after` と明記する。
8. requested/canonical URL の混同、verified record の revision/timestamp 欠落、redirect/section 確認漏れ。
9. branch/main の根拠を別 branch/segment に暗黙継承すること。

特に升田式石田流の現行 moves は7手目 `5i4h` までだが、note は次の `7h7f` も「手順化」と主張する。D0 は seed を直さず artifact の issue と [`fixtures/opening-wikipedia-provenance-invalid-masuda.json`](fixtures/opening-wikipedia-provenance-invalid-masuda.json) に固定し、D1 validator が `note_claims_unrecorded_move` を返すことを要求する。

## 8. fixture の期待値

[`fixtures/opening-wikipedia-provenance-valid.json`](fixtures/opening-wikipedia-provenance-valid.json) は終端境界が一致する A の最小例である。invalid fixture は JSON としては正しく、意図的に semantic contract に違反する。fixture の `expected_errors` は将来の validator の安定した error code 契約であり、production audit schema の対象外とする。
