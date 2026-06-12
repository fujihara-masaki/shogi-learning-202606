// 詰め将棋セッションの純粋ロジック(テスト対象)。
import { Move, Position, formatMove } from "tsshogi";

export interface AppliedMove {
  usi: string;
  text: string;
}

/** SFEN から局面を生成する。失敗時は null。 */
export function positionFromSfen(sfen: string): Position | null {
  return Position.newBySFEN(sfen);
}

/** 攻め方手順と玉方応手を 1 本の手順に交互に並べる。 */
export function interleaveLine(solution: string[], opponent: string[]): string[] {
  const line: string[] = [];
  for (let i = 0; i < solution.length; i += 1) {
    line.push(solution[i]);
    if (i < opponent.length) {
      line.push(opponent[i]);
    }
  }
  return line;
}

/** USI 手順を局面に適用し、適用後の局面と表示用テキストを返す。不正手なら null。 */
export function applyUsiMoves(
  position: Position,
  usiMoves: string[],
): { position: Position; applied: AppliedMove[] } | null {
  const pos = position.clone();
  const applied: AppliedMove[] = [];
  for (const usi of usiMoves) {
    const move = pos.createMoveByUSI(usi);
    if (!move || !pos.isValidMove(move)) {
      return null;
    }
    applied.push({ usi, text: formatMove(pos, move) });
    pos.doMove(move);
  }
  return { position: pos, applied };
}

/** 指し手が期待する正解手と一致するか。 */
export function isCorrectMove(move: Move, expectedUsi: string): boolean {
  return move.usi === expectedUsi;
}
