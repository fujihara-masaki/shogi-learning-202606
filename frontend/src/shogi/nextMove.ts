// 「次の一手」学習モードの判定ロジック。
// 候補手の順序・rank・score は定跡DB由来の値をそのまま使い、
// データから確定できない意味(評価値の向き・単位、候補外の手の優劣)は判定に持ち込まない。
import { Position, Square, formatMove } from "tsshogi";

const PIECE_TYPE_JA: Record<string, string> = {
  pawn: "歩",
  lance: "香",
  knight: "桂",
  silver: "銀",
  gold: "金",
  bishop: "角",
  rook: "飛",
  king: "玉",
  promPawn: "と金",
  promLance: "成香",
  promKnight: "成桂",
  promSilver: "成銀",
  horse: "馬",
  dragon: "龍",
};

const RANK_KANJI = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];

/** 候補手のうち UI 判定に使う最小構造(API の BookCandidate と互換)。 */
export interface NextMoveCandidateLike {
  move_usi: string;
  rank: number | null;
  score: number | null;
  depth: number | null;
  pv: string | null;
}

export type NextMoveVerdictKind = "top" | "strong" | "listed" | "unlisted";

export interface NextMoveVerdict {
  kind: NextMoveVerdictKind;
  /** 短いラベル(例: 最有力候補) */
  label: string;
  /** 断定を避けた説明文 */
  description: string;
  moveUsi: string;
  /** 指した手が候補手に含まれる場合、その候補 */
  candidate: NextMoveCandidateLike | null;
  /** 表示用の候補順位(DB の rank、無ければ並び順から補完) */
  candidateRank: number | null;
  /** 最上位候補(候補が1つも無い場合は null) */
  best: NextMoveCandidateLike | null;
  /**
   * 最上位候補との評価値の絶対差。どちらかの score が欠けていれば null。
   * 評価値の向き・単位はデータから確定できないため、符号付きの差は扱わない。
   */
  scoreDiffFromBest: number | null;
}

export const UNLISTED_MOVE_DESCRIPTION =
  "この手は、現在取り込まれている定跡DBには候補手として登録されていません。局面上の評価を完全に否定するものではありません。";

/** 候補の並び順(API が sort_order 優先で返す)から表示用順位を補完する。 */
export function displayRank(candidate: NextMoveCandidateLike, index: number): number {
  return candidate.rank ?? index + 1;
}

export function normalizeNextMoveCandidates<T extends NextMoveCandidateLike>(candidates: T[]): T[] {
  return candidates.map((candidate, index) => ({candidate, index})).sort((a, b) => {
    const rank = displayRank(a.candidate, a.index) - displayRank(b.candidate, b.index);
    if (rank) return rank;
    if (a.candidate.score !== b.candidate.score) {
      if (a.candidate.score === null) return 1;
      if (b.candidate.score === null) return -1;
      return b.candidate.score - a.candidate.score;
    }
    if (a.candidate.depth !== b.candidate.depth) {
      if (a.candidate.depth === null) return 1;
      if (b.candidate.depth === null) return -1;
      return b.candidate.depth - a.candidate.depth;
    }
    return a.candidate.move_usi.localeCompare(b.candidate.move_usi);
  }).map(({candidate}) => candidate);
}

/**
 * ユーザーの指した手(合法手)を候補手リストと突き合わせる。
 * candidates は API の返却順(定跡DBの候補順)をそのまま渡すこと。
 */
export function judgeNextMove(moveUsi: string, candidates: NextMoveCandidateLike[]): NextMoveVerdict {
  candidates = normalizeNextMoveCandidates(candidates);
  const best = candidates[0] ?? null;
  const index = candidates.findIndex((c) => c.move_usi === moveUsi);
  if (index < 0) {
    return {
      kind: "unlisted",
      label: "定跡DB未登録の手",
      description: UNLISTED_MOVE_DESCRIPTION,
      moveUsi,
      candidate: null,
      candidateRank: null,
      best,
      scoreDiffFromBest: null,
    };
  }
  const candidate = candidates[index];
  const rank = displayRank(candidate, index);
  const scoreDiffFromBest =
    best && best.score !== null && candidate.score !== null ? Math.abs(best.score - candidate.score) : null;
  if (index === 0) {
    return {
      kind: "top",
      label: "最有力候補",
      description: "定跡DBで最上位に登録されている候補手です。",
      moveUsi,
      candidate,
      candidateRank: rank,
      best,
      scoreDiffFromBest,
    };
  }
  if (rank <= 3) {
    return {
      kind: "strong",
      label: "有力候補",
      description: "定跡DBに上位の候補手として登録されている手です。",
      moveUsi,
      candidate,
      candidateRank: rank,
      best,
      scoreDiffFromBest,
    };
  }
  return {
    kind: "listed",
    label: "その他の登録候補",
    description: "定跡DBに候補手として登録されている手です。",
    moveUsi,
    candidate,
    candidateRank: rank,
    best,
    scoreDiffFromBest,
  };
}

/** SFEN から局面を作る(不正なら null)。 */
export function positionFromSfen(sfen: string): Position | null {
  return Position.newBySFEN(sfen);
}

/** USI の指し手を日本語表記にする(局面上で解釈できなければ USI のまま)。 */
export function notationForUsi(position: Position, usi: string): string {
  const move = position.createMoveByUSI(usi);
  if (!move || !position.isValidMove(move)) return usi;
  return formatMove(position, move);
}

export interface NextMoveHint {
  stage: 1 | 2;
  text: string;
}

/**
 * 最上位候補から段階的ヒントを導出する。
 * stage 1: 動かす(打つ)駒の種類 / stage 2: 移動先のマス。
 */
export function hintsForTopCandidate(position: Position, candidates: NextMoveCandidateLike[]): NextMoveHint[] {
  const best = candidates[0];
  if (!best) return [];
  const move = position.createMoveByUSI(best.move_usi);
  if (!move || !position.isValidMove(move)) return [];
  const pieceName = PIECE_TYPE_JA[move.pieceType] ?? move.pieceType;
  const isDrop = !(move.from instanceof Square);
  const toLabel = `${move.to.file}${RANK_KANJI[move.to.rank - 1]}`;
  return [
    { stage: 1, text: isDrop ? `持ち駒の${pieceName}を使う手です。` : `${pieceName}を動かす手です。` },
    { stage: 2, text: `移動先は${toLabel}のマスです。` },
  ];
}
