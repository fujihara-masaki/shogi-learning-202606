import { formatMove, Position, type Move } from "tsshogi";
import type { AppliedMove } from "./tsume";

export interface OpeningMoveNode {
  id: string;
  usi: string;
  notation: string;
  explanation: string;
  aim: string;
  hint: string;
  branchLabel?: string;
  isMain?: boolean;
  sortOrder?: number;
  sourceUrl?: string;
  sourceTitle?: string;
  license?: string;
  sourceNote?: string;
  coverageStatus?: string;
  sourceSection?: string;
  sourceLicense?: string;
  sourceRetrievedAt?: string;
  next?: OpeningMoveNode[];
}

export interface OpeningLine {
  id: string;
  name: string;
  category: string;
  description: string;
  initialSfen: string;
  moves: OpeningMoveNode[];
}

export interface OpeningStep {
  node: OpeningMoveNode;
  choices: OpeningMoveNode[];
}

const INITIAL_SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";

export const OPENING_LINES: OpeningLine[] = [
  {
    id: "static-rook-rapid-attack",
    name: "居飛車急戦の基本",
    category: "居飛車",
    description: "飛車先を伸ばしながら角道を開け、居飛車の自然な序盤感覚を学びます。",
    initialSfen: INITIAL_SFEN,
    moves: [
      {
        id: "static-1",
        usi: "7g7f",
        notation: "▲7六歩",
        explanation: "角道を開け、攻めと駒組みの自由度を高める初手です。",
        aim: "角を働かせ、相手の出方を見ながら飛車先の歩を伸ばす準備をします。",
        hint: "先手の角筋を通す歩を突きます。",
        next: [
          {
            id: "static-2",
            usi: "3c3d",
            notation: "△3四歩",
            explanation: "後手も角道を開け、角交換や急戦を含みにします。",
            aim: "互いに角道を開けた形で、飛車先交換を目指す基本形に進みます。",
            hint: "後手も角道を開ける歩を突きます。",
            next: [
              {
                id: "static-3",
                usi: "2g2f",
                notation: "▲2六歩",
                explanation: "飛車先を伸ばし、居飛車らしく2筋から主導権を取りに行きます。",
                aim: "次に▲2五歩と伸ばして、飛車先交換を狙います。",
                hint: "飛車の前の歩を一つ進めます。",
                next: [
                  {
                    id: "static-4",
                    usi: "8c8d",
                    notation: "△8四歩",
                    explanation: "後手も飛車先を伸ばして、相居飛車の主導権争いに備えます。",
                    aim: "お互いに飛車先を伸ばす相居飛車の基本形を作ります。",
                    hint: "後手飛車の前の歩を突きます。",
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
  {
    id: "yagura-foundation",
    name: "矢倉の出だし",
    category: "相居飛車",
    description: "角道を開けたあと銀を上がり、矢倉囲いへ向かう基本手順です。",
    initialSfen: INITIAL_SFEN,
    moves: [
      {
        id: "yagura-1",
        usi: "7g7f",
        notation: "▲7六歩",
        explanation: "角道を開けて、矢倉でも必要になる駒の活用を始めます。",
        aim: "角を働かせつつ、左銀を中央へ使える形にします。",
        hint: "角筋を開ける歩を突きます。",
        next: [
          {
            id: "yagura-2",
            usi: "8c8d",
            notation: "△8四歩",
            explanation: "後手は飛車先を伸ばし、相居飛車の進行を明示します。",
            aim: "先手に矢倉へ進むか、急戦にするかを問いかけます。",
            hint: "後手の飛車先の歩です。",
            next: [
              {
                id: "yagura-3",
                usi: "6i7h",
                notation: "▲7八銀",
                explanation: "左銀を上がり、矢倉囲いの骨格を作り始めます。",
                aim: "銀を7七へ進めて、玉を堅く囲う準備をします。",
                hint: "左銀を一つ上へ進めます。",
              },
            ],
          },
        ],
      },
    ],
  },
  {
    id: "fourth-file-rook",
    name: "四間飛車の基本",
    category: "振り飛車",
    description: "角道を開けて飛車を4筋へ振る、四間飛車の入口を学びます。",
    initialSfen: INITIAL_SFEN,
    moves: [
      {
        id: "shiken-1",
        usi: "7g7f",
        notation: "▲7六歩",
        explanation: "振り飛車でも角道を開けるのが自然な出だしです。",
        aim: "角の利きを通し、飛車を振る前に駒の働きを確保します。",
        hint: "角道を開ける初手です。",
        next: [
          {
            id: "shiken-2",
            usi: "3c3d",
            notation: "△3四歩",
            explanation: "後手も角道を開け、角交換の含みを持ちます。",
            aim: "角道を開け合った局面で、先手は飛車を振ります。",
            hint: "後手も角道を開けます。",
            next: [
              {
                id: "shiken-3",
                usi: "2h6h",
                notation: "▲6八飛",
                explanation: "飛車を4筋側へ振り、四間飛車の構えを作ります。",
                aim: "左辺に飛車を移して、美濃囲いと組み合わせる準備をします。",
                hint: "先手の飛車を左へ大きく移動します。",
              },
            ],
          },
        ],
      },
    ],
  },
];

export function findOpening(id: string): OpeningLine | undefined {
  return OPENING_LINES.find((opening) => opening.id === id);
}

export function countMainLineMoves(opening: OpeningLine): number {
  let count = 0;
  let choices = opening.moves;
  while (choices.length > 0) {
    count += 1;
    choices = mainOpeningChoice(choices)?.next ?? [];
  }
  return count;
}

export function flattenMainLine(opening: OpeningLine): OpeningMoveNode[] {
  const line: OpeningMoveNode[] = [];
  let choices = opening.moves;
  while (choices.length > 0) {
    const node = mainOpeningChoice(choices)!;
    line.push(node);
    choices = node.next ?? [];
  }
  return line;
}

export function positionFromOpening(opening: OpeningLine): Position {
  const position = Position.newBySFEN(opening.initialSfen);
  if (!position) {
    throw new Error(`定跡の初期局面SFENが不正です: ${opening.id}`);
  }
  return position;
}

export function applyOpeningPath(opening: OpeningLine, path: number[]): { position: Position; steps: OpeningStep[]; moves: AppliedMove[] } {
  const position = positionFromOpening(opening);
  const steps: OpeningStep[] = [];
  const moves: AppliedMove[] = [];
  let choices = opening.moves;
  for (const index of path) {
    const node = choices[index];
    if (!node) break;
    const move = position.createMoveByUSI(node.usi);
    if (!move || !position.isValidMove(move)) {
      throw new Error(`定跡手が合法手ではありません: ${node.usi}`);
    }
    steps.push({ node, choices });
    moves.push({ usi: node.usi, text: formatMove(position, move) });
    position.doMove(move);
    choices = node.next ?? [];
  }
  return { position, steps, moves };
}

export function expectedOpeningMove(opening: OpeningLine, path: number[]): OpeningMoveNode | null {
  let choices = opening.moves;
  for (const index of path) {
    const node = choices[index];
    if (!node) return null;
    choices = node.next ?? [];
  }
  return mainOpeningChoice(choices);
}

export function mainOpeningChoice(choices: OpeningMoveNode[]): OpeningMoveNode | null {
  return choices.find((choice) => choice.isMain === true) ?? choices[0] ?? null;
}

/** Return the array index of the semantic main choice, with the legacy first-choice fallback. */
export function mainOpeningChoiceIndex(choices: OpeningMoveNode[]): number {
  const main = mainOpeningChoice(choices);
  return main ? choices.indexOf(main) : -1;
}

export interface OpeningTreeEntry {
  node: OpeningMoveNode;
  path: number[];
  choices: OpeningMoveNode[];
  level: number;
}

/** Enumerate every tree node with its unique root-relative index path. */
export function enumerateOpeningTree(opening: OpeningLine): OpeningTreeEntry[] {
  const entries: OpeningTreeEntry[] = [];
  const visit = (choices: OpeningMoveNode[], parentPath: number[]) => {
    choices.forEach((node, index) => {
      const path = [...parentPath, index];
      entries.push({ node, path, choices, level: path.length });
      visit(node.next ?? [], path);
    });
  };
  visit(opening.moves, []);
  return entries;
}

export function countOpeningBranchPoints(opening: OpeningLine): number {
  let count = opening.moves.length > 1 ? 1 : 0;
  for (const { node } of enumerateOpeningTree(opening)) {
    if ((node.next?.length ?? 0) > 1) count += 1;
  }
  return count;
}

/** Classify a tree path relative to the currently applied path. */
export function openingPathState(nodePath: number[], currentPath: number[]): "current" | "ancestor" | "other" {
  if (nodePath.length > currentPath.length || nodePath.some((index, depth) => currentPath[depth] !== index)) return "other";
  return nodePath.length === currentPath.length ? "current" : "ancestor";
}

/** Discard everything after a branch point and select its semantic main choice. */
export function openingMainPathAt(opening: OpeningLine, branchPointPath: number[]): number[] {
  let choices = opening.moves;
  const validParentPath: number[] = [];
  for (const index of branchPointPath) {
    const node = choices[index];
    if (!node) return validParentPath;
    validParentPath.push(index);
    choices = node.next ?? [];
  }
  const mainIndex = mainOpeningChoiceIndex(choices);
  return mainIndex < 0 ? validParentPath : [...validParentPath, mainIndex];
}

/** Return the user-facing label for a choice at a branch point. */
export function openingBranchChoiceLabel(choices: OpeningMoveNode[], index: number): string {
  const choice = choices[index];
  if (!choice) return `分岐${index + 1}`;
  return choice.branchLabel ?? (choice === mainOpeningChoice(choices) ? "本線" : `分岐${index + 1}`);
}

/** Return the user-facing labels of the branch points traversed by an applied path. */
export function selectedOpeningBranchPath(steps: OpeningStep[]): string {
  const labels = steps
    .filter((step) => step.choices.length > 1)
    .map((step) => openingBranchChoiceLabel(step.choices, step.choices.indexOf(step.node)));
  return labels.join(" → ") || "本線";
}

export function findOpeningChoiceIndex(choices: OpeningMoveNode[], move: Pick<Move, "usi">): number {
  return choices.findIndex((choice) => choice.usi === move.usi);
}

/** Keep the selected path and append the first (main-line) choice until the end. */
export function continueOpeningMainLine(opening: OpeningLine, path: number[]): number[] {
  const nextPath: number[] = [];
  let choices = opening.moves;
  for (const index of path) {
    const node = choices[index];
    if (!node) break;
    nextPath.push(index);
    choices = node.next ?? [];
  }
  while (choices.length > 0) {
    const mainIndex = mainOpeningChoiceIndex(choices);
    const main = choices[mainIndex];
    nextPath.push(mainIndex);
    choices = main.next ?? [];
  }
  return nextPath;
}

/** Return the path immediately before the most recently traversed branch choice. */
export function pathBeforePreviousBranch(opening: OpeningLine, path: number[]): number[] {
  let choices = opening.moves;
  let latestBranchStep = -1;
  for (const [stepIndex, index] of path.entries()) {
    if (choices.length > 1) latestBranchStep = stepIndex;
    const node = choices[index];
    if (!node) break;
    choices = node.next ?? [];
  }
  return latestBranchStep < 0 ? path : path.slice(0, latestBranchStep);
}

export interface ImportedOpeningLike {
  id: number;
  name: string;
  opening_type: string;
  initial_sfen: string;
  moves: Array<{ id?: number; usi: string; comment?: string; from_sfen?: string; to_sfen?: string; variation_group?: string; parent_move_id?: number | null; sort_order?: number; move_key?: string; is_main?: boolean }>;
  tags?: Array<{ label?: string; tag: string }>;
  source?: {
    name: string;
    license_name: string;
    license_url: string;
    source_url?: string;
    source_title?: string;
    license?: string;
    source_note?: string;
    coverage_status?: string;
    source_type?: string;
    source_section?: string;
    source_license?: string;
    source_retrieved_at?: string;
  };
}

export function openingFromImportedLine(imported: ImportedOpeningLike): OpeningLine {
  const sourceLabel = imported.source?.source_title || imported.source?.name || "インポートデータ";
  const licenseLabel = imported.source?.license || imported.source?.license_name || "";
  const decorate = (move: ImportedOpeningLike["moves"][number], index: number, branchLabel?: string): OpeningMoveNode => ({
    id: `imported-${imported.id}-${move.move_key ?? move.id ?? `${index + 1}-${move.usi}`}`,
    usi: move.usi,
    notation: move.usi,
    branchLabel,
    isMain: move.is_main,
    sortOrder: move.sort_order,
    explanation: move.comment || "Wikipediaで確認できる範囲の定跡手です。",
    aim: licenseLabel ? `出典: ${sourceLabel} / ライセンス: ${licenseLabel}` : `出典: ${sourceLabel}`,
    hint: `USI ${move.usi} の手を指します。`,
    sourceUrl: imported.source?.source_url,
    sourceTitle: imported.source?.source_title || imported.source?.name,
    license: licenseLabel,
    sourceNote: imported.source?.source_note,
    coverageStatus: imported.source?.coverage_status,
    sourceSection: imported.source?.source_section,
    sourceLicense: imported.source?.source_license,
    sourceRetrievedAt: imported.source?.source_retrieved_at,
  });

  const hasDirectTree = imported.moves.every((move) => typeof move.id === "number" && "parent_move_id" in move);
  const byParent = new Map<number | null, Array<{ move: ImportedOpeningLike["moves"][number]; index: number }>>();
  for (const [index, move] of imported.moves.entries()) {
    if (!hasDirectTree) break;
    const bucket = byParent.get(move.parent_move_id ?? null) ?? [];
    bucket.push({ move, index });
    byParent.set(move.parent_move_id ?? null, bucket);
  }
  const buildFromParent = (parentId: number | null, ancestors: Set<number>): OpeningMoveNode[] =>
    (byParent.get(parentId) ?? [])
      .sort((a, b) => (a.move.sort_order ?? 0) - (b.move.sort_order ?? 0) || (a.move.move_key ?? "").localeCompare(b.move.move_key ?? "") || (a.move.id! - b.move.id!))
      .map(({ move, index }) => {
        if (ancestors.has(move.id!)) throw new Error(`定跡ツリーに循環があります: ${move.id}`);
        const choices = byParent.get(parentId) ?? [];
        const displayLabel = move.variation_group && move.variation_group !== "main"
          ? move.variation_group
          : undefined;
        const branchLabel = choices.length > 1
          ? (displayLabel ?? (move.is_main === true ? "本線" : undefined))
          : undefined;
        const node = decorate(move, index, branchLabel);
        node.next = buildFromParent(move.id!, new Set([...ancestors, move.id!]));
        return node;
      });

  const movesByFrom = new Map<string, Array<{ move: ImportedOpeningLike["moves"][number]; index: number }>>();
  for (const [index, move] of imported.moves.entries()) {
    const key = "from_sfen" in move && move.from_sfen ? move.from_sfen : `linear-${index}`;
    const bucket = movesByFrom.get(key) ?? [];
    bucket.push({ move, index });
    movesByFrom.set(key, bucket);
  }

  const buildFromSfen = (sfen: string, seen: Set<string>): OpeningMoveNode[] => {
    const choices = movesByFrom.get(sfen) ?? [];
    return choices
      .sort((a, b) => (a.move.sort_order ?? 0) - (b.move.sort_order ?? 0) || a.index - b.index)
      .map(({ move, index }) => {
        const branchLabel = choices.length > 1 ? (move.variation_group === "main" ? "本線" : move.variation_group) : undefined;
        const node = decorate(move, index, branchLabel);
        const nextSfen = "to_sfen" in move ? move.to_sfen : "";
        if (nextSfen && !seen.has(nextSfen)) {
          node.next = buildFromSfen(nextSfen, new Set([...seen, nextSfen]));
        }
        return node;
      });
  };

  const tree = hasDirectTree ? buildFromParent(null, new Set()) : imported.moves.some((move) => "from_sfen" in move && move.from_sfen)
    ? buildFromSfen(imported.initial_sfen, new Set([imported.initial_sfen]))
    : [];

  const buildLinear = (index: number): OpeningMoveNode[] => {
    const move = imported.moves[index];
    if (!move) return [];
    const node = decorate(move, index);
    node.next = buildLinear(index + 1);
    return [node];
  };

  return {
    id: String(imported.id),
    name: imported.name,
    category: imported.opening_type,
    description: imported.tags?.map((tag) => tag.label || tag.tag).join("、") || "インポートした定跡ライン",
    initialSfen: imported.initial_sfen,
    moves: tree.length > 0 ? tree : buildLinear(0),
  };
}


export interface LearningSampleLike {
  id: number;
  opening_name: string;
  sfen: string;
  sample_reason: string;
  candidates: Array<{ move_usi: string; score: number | null; depth: number | null }>;
  source?: { name: string; license_name: string };
}

export function openingFromLearningSample(sample: LearningSampleLike): OpeningLine {
  const move = sample.candidates[0];
  return {
    id: `sample-${sample.id}`,
    name: `${sample.opening_name} サンプル #${sample.id}`,
    category: sample.opening_name,
    description: sample.sample_reason || "定跡DBから抽出した学習サンプル",
    initialSfen: sample.sfen,
    moves: move
      ? [
          {
            id: `sample-${sample.id}-1`,
            usi: move.move_usi,
            notation: move.move_usi,
            explanation: "定跡DBの候補手を使った1手学習です。右側に同局面の候補一覧も表示します。",
            aim: sample.source?.license_name
              ? `出典: ${sample.source.name} / ライセンス: ${sample.source.license_name}`
              : `出典: ${sample.source?.name || "定跡DB"}`,
            hint: `USI ${move.move_usi} の候補手を指します。`,
          },
        ]
      : [],
  };
}
