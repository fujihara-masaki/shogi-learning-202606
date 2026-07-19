// 「次の一手」1問分のセッション状態。
// 局面・着手・判定・ヒント段階を保持し、表示コンポーネントからロジックを分離する。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Square, type Move } from "tsshogi";
import type { LearningSample } from "../api/client";
import { ApiError, postNextMoveResult } from "../api/client";
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
  saveMessage: string | null;
}

export function useNextMoveSession(sample: LearningSample | null): NextMoveSession {
  const [userMoveUsi, setUserMoveUsi] = useState<string | null>(null);
  const [hintStage, setHintStage] = useState(0);
  const [saveNotice, setSaveNotice] = useState<{key: string; text: string} | null>(null);
  const startedAt = useRef(0);
  const posting = useRef(false);
  const attemptGeneration = useRef(0);

  useEffect(() => {
    startedAt.current = performance.now();
    posting.current = false;
    attemptGeneration.current += 1;
    // A different sample row may represent the same problem_key; never carry its save status forward.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSaveNotice(null);
  }, [sample?.id, sample?.problem_key]);
  const saveMessage = saveNotice && saveNotice.key === sample?.problem_key ? saveNotice.text : null;

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
    if (!sample || posting.current) return;
    posting.current = true;
    const generation = attemptGeneration.current;
    setUserMoveUsi(move.usi);
    void postNextMoveResult({sample_id: sample.id, problem_key: sample.problem_key, move_usi: move.usi,
      hint_count: hintStage, elapsed_ms: Math.max(0, Math.round(performance.now() - startedAt.current))})
      .catch((error: unknown) => {
        if (generation !== attemptGeneration.current) return;
        setSaveNotice({key: sample.problem_key, text:
          error instanceof ApiError && error.code === "NEXT_MOVE_PROBLEM_CHANGED"
            ? "問題データが更新されました。再読み込みしてください。"
            : "解答記録が保存されたか確認できませんでした。学習はそのまま続けられます。"});
      });
  }, [hintStage, sample]);

  const revealNextHint = useCallback(() => {
    setHintStage((stage) => Math.min(stage + 1, hints.length));
  }, [hints.length]);

  const retry = useCallback(() => {
    setUserMoveUsi(null);
    setHintStage(0);
    startedAt.current = performance.now();
    posting.current = false;
    attemptGeneration.current += 1;
    setSaveNotice(null);
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
    saveMessage,
  };
}
