// 詰め将棋 1 問のプレイ進行を管理するフック。
// - ユーザーの手を正解手順 (USI) と照合
// - 3手詰・5手詰では玉方の応手を自動実行
// - 不正解時は「もう一度」「答えを見る」を選択可能
import { useCallback, useEffect, useRef, useState } from "react";
import type { Move, Position, Square } from "tsshogi";
import { formatMove } from "tsshogi";
import type { TsumeProblem } from "../api/client";
import { moveFromSquare, positionFromSfen, type AppliedMove } from "../shogi/tsume";

export type SessionStatus =
  | "loading"
  | "playing" // ユーザーの手番
  | "opponent" // 玉方応手の自動実行待ち
  | "wrong" // 不正解(もう一度 / 答えを見る)
  | "cleared" // 正解クリア
  | "showing" // 答えの自動再生中
  | "shown"; // 答え表示済み

export interface SessionOutcome {
  cleared: boolean;
  elapsedMs: number;
  mistakeCount: number;
}

export interface TsumeSession {
  status: SessionStatus;
  position: Position | null;
  moves: AppliedMove[];
  lastMoveTo: Square | null;
  lastMoveFrom: Square | null;
  mistakeCount: number;
  wrongMoveText: string | null;
  handleUserMove: (move: Move) => void;
  retry: () => void;
  showAnswer: () => void;
  reset: () => void;
  undo: () => void;
  canUndo: boolean;
}

interface Options {
  /** 不正解時に即終了する(タイムアタック用)。 */
  failFast?: boolean;
  /** クリア・答え表示・即時失敗の確定時に一度だけ呼ばれる。 */
  onTerminal?: (outcome: SessionOutcome) => void;
  /** 自動応手・自動再生の間隔 (ms) */
  stepDelayMs?: number;
}

export function useTsumeSession(problem: TsumeProblem | null, options: Options = {}): TsumeSession {
  const { failFast = false, onTerminal, stepDelayMs = 600 } = options;
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [position, setPosition] = useState<Position | null>(null);
  const [moves, setMoves] = useState<AppliedMove[]>([]);
  const [lastMoveTo, setLastMoveTo] = useState<Square | null>(null);
  const [lastMoveFrom, setLastMoveFrom] = useState<Square | null>(null);
  const [mistakeCount, setMistakeCount] = useState(0);
  const [wrongMoveText, setWrongMoveText] = useState<string | null>(null);

  const timersRef = useRef<number[]>([]);
  const startedAtRef = useRef(0);
  const terminalSentRef = useRef(false);
  const onTerminalRef = useRef(onTerminal);
  useEffect(() => {
    onTerminalRef.current = onTerminal;
  });

  const clearTimers = () => {
    timersRef.current.forEach((t) => window.clearTimeout(t));
    timersRef.current = [];
  };

  const sendTerminal = useCallback((cleared: boolean, mistakes: number) => {
    if (terminalSentRef.current) return;
    terminalSentRef.current = true;
    onTerminalRef.current?.({
      cleared,
      elapsedMs: Date.now() - startedAtRef.current,
      mistakeCount: mistakes,
    });
  }, []);

  const setupProblem = useCallback(() => {
    clearTimers();
    terminalSentRef.current = false;
    startedAtRef.current = Date.now();
    setMoves([]);
    setLastMoveTo(null);
    setLastMoveFrom(null);
    setMistakeCount(0);
    setWrongMoveText(null);
    if (!problem) {
      setStatus("loading");
      setPosition(null);
      return;
    }
    const pos = positionFromSfen(problem.initial_sfen);
    if (!pos) {
      setStatus("loading");
      setPosition(null);
      return;
    }
    setPosition(pos);
    setStatus("playing");
  }, [problem]);

  useEffect(() => {
    // 問題が切り替わったタイミングで盤面・進行状態を初期化する。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setupProblem();
    return clearTimers;
  }, [setupProblem]);

  /** moves の長さからユーザーが次に指すべき solution のインデックスを得る */
  const solutionIndex = Math.ceil(moves.length / 2);

  const applyMove = useCallback(
    (pos: Position, move: Move): Position => {
      const text = formatMove(pos, move);
      const next = pos.clone();
      next.doMove(move);
      setMoves((prev) => [...prev, { usi: move.usi, text }]);
      setLastMoveTo(move.to);
      setLastMoveFrom(moveFromSquare(move));
      setPosition(next);
      return next;
    },
    [],
  );

  const handleUserMove = useCallback(
    (move: Move) => {
      if (!problem || !position || status !== "playing") return;
      const expected = problem.solution_moves[solutionIndex];
      if (move.usi !== expected) {
        const newMistakes = mistakeCount + 1;
        setMistakeCount(newMistakes);
        setWrongMoveText(formatMove(position, move));
        setStatus("wrong");
        if (failFast) {
          sendTerminal(false, newMistakes);
        }
        return;
      }
      const next = applyMove(position, move);
      const isLast = solutionIndex === problem.solution_moves.length - 1;
      if (isLast) {
        setStatus("cleared");
        sendTerminal(true, mistakeCount);
        return;
      }
      // 玉方の応手を自動実行
      setStatus("opponent");
      const replyUsi = problem.opponent_moves[solutionIndex];
      const timer = window.setTimeout(() => {
        const reply = next.createMoveByUSI(replyUsi);
        if (reply && next.isValidMove(reply)) {
          applyMove(next, reply);
        }
        setStatus("playing");
      }, stepDelayMs);
      timersRef.current.push(timer);
    },
    [problem, position, status, solutionIndex, mistakeCount, failFast, applyMove, sendTerminal, stepDelayMs],
  );

  const retry = useCallback(() => {
    if (status !== "wrong") return;
    setWrongMoveText(null);
    setStatus("playing");
  }, [status]);

  const showAnswer = useCallback(() => {
    if (!problem) return;
    clearTimers();
    const pos = positionFromSfen(problem.initial_sfen);
    if (!pos) return;
    sendTerminal(false, mistakeCount);
    setMoves([]);
    setLastMoveTo(null);
    setLastMoveFrom(null);
    setWrongMoveText(null);
    setPosition(pos);
    setStatus("showing");
    const line: string[] = [];
    for (let i = 0; i < problem.solution_moves.length; i += 1) {
      line.push(problem.solution_moves[i]);
      if (i < problem.opponent_moves.length) line.push(problem.opponent_moves[i]);
    }
    let current = pos;
    line.forEach((usi, i) => {
      const timer = window.setTimeout(() => {
        const move = current.createMoveByUSI(usi);
        if (move && current.isValidMove(move)) {
          current = applyMove(current, move);
        }
        if (i === line.length - 1) {
          setStatus("shown");
        }
      }, stepDelayMs * (i + 1));
      timersRef.current.push(timer);
    });
  }, [problem, mistakeCount, applyMove, sendTerminal, stepDelayMs]);

  // 1手戻る: 直近のユーザーの手(と応手)を取り消して指し直す
  const undo = useCallback(() => {
    if (!problem || (status !== "playing" && status !== "wrong")) return;
    if (moves.length === 0) return;
    const keep = moves.length % 2 === 0 ? moves.length - 2 : moves.length - 1;
    const pos = positionFromSfen(problem.initial_sfen);
    if (!pos) return;
    let current = pos;
    const kept = moves.slice(0, Math.max(0, keep));
    for (const m of kept) {
      const move = current.createMoveByUSI(m.usi);
      if (!move) return;
      const next = current.clone();
      next.doMove(move);
      current = next;
    }
    setMoves(kept);
    setPosition(current);
    setLastMoveTo(null);
    setLastMoveFrom(null);
    setWrongMoveText(null);
    setStatus("playing");
  }, [problem, status, moves]);

  const canUndo =
    moves.length > 0 && (status === "playing" || status === "wrong");

  return {
    status,
    position,
    moves,
    lastMoveTo,
    lastMoveFrom,
    mistakeCount,
    wrongMoveText,
    handleUserMove,
    retry,
    showAnswer,
    reset: setupProblem,
    undo,
    canUndo,
  };
}
