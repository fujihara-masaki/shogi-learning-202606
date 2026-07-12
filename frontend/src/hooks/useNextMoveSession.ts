// 「次の一手」1問分のセッション状態。
// 局面・着手・判定・ヒント段階を保持し、表示コンポーネントからロジックを分離する。
import { useCallback, useMemo, useState } from "react";
import { Square, type Move } from "tsshogi";
import type { LearningSample } from "../api/client";
import {
  hintsForTopCandidate,
  judgeNextMove,
  positionFromSfen,
  type NextMoveHint,
  type NextMoveVerdict,
} from "../shogi/nextMove";

export type NextMovePhase = "thinking" | "answered";

export interface NextMoveSession {
  phase: NextMovePhase;
  /** 表示用の局面(思考中は初期局面、解答後はユーザーの手を進めた局面) */
  position: ReturnType<typeof positionFromSfen>;
  /** SFEN が不正な場合 true */
  invalidPosition: boolean;
  verdict: NextMoveVerdict | null;
  userMoveUsi: string | null;
  lastMoveTo: Square | null;
  lastMoveFrom: Square | null;
  /** 公開済みのヒント(段階順) */
  revealedHints: NextMoveHint[];
  /** まだ出せるヒントが残っているか */
  hasMoreHints: boolean;
  playMove: (move: Move) => void;
  revealNextHint: () => void;
  retry: () => void;
}

export function useNextMoveSession(sample: LearningSample | null): NextMoveSession {
  const [userMoveUsi, setUserMoveUsi] = useState<string | null>(null);
  const [hintStage, setHintStage] = useState(0);

  const basePosition = useMemo(() => (sample ? positionFromSfen(sample.sfen) : null), [sample]);

  const applied = useMemo(() => {
    if (!basePosition || !userMoveUsi) return null;
    const position = basePosition.clone();
    const move = position.createMoveByUSI(userMoveUsi);
    if (!move || !position.isValidMove(move)) return null;
    position.doMove(move);
    return { position, move };
  }, [basePosition, userMoveUsi]);

  const verdict = useMemo(
    () => (sample && userMoveUsi ? judgeNextMove(userMoveUsi, sample.candidates) : null),
    [sample, userMoveUsi],
  );

  const hints = useMemo(
    () => (sample && basePosition ? hintsForTopCandidate(basePosition, sample.candidates) : []),
    [sample, basePosition],
  );

  const playMove = useCallback((move: Move) => {
    setUserMoveUsi(move.usi);
  }, []);

  const revealNextHint = useCallback(() => {
    setHintStage((stage) => Math.min(stage + 1, hints.length));
  }, [hints.length]);

  const retry = useCallback(() => {
    setUserMoveUsi(null);
    setHintStage(0);
  }, []);

  const lastMove = applied?.move ?? null;
  return {
    phase: userMoveUsi && applied ? "answered" : "thinking",
    position: applied?.position ?? basePosition,
    invalidPosition: Boolean(sample) && !basePosition,
    verdict: applied ? verdict : null,
    userMoveUsi: applied ? userMoveUsi : null,
    lastMoveTo: lastMove?.to ?? null,
    lastMoveFrom: lastMove && lastMove.from instanceof Square ? lastMove.from : null,
    revealedHints: hints.slice(0, hintStage),
    hasMoreHints: hintStage < hints.length,
    playMove,
    revealNextHint,
    retry,
  };
}
