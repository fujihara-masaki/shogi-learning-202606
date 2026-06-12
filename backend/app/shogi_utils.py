"""python-shogi を使った詰将棋データの検証ユーティリティ。"""
from __future__ import annotations

import shogi


def validate_problem(
    initial_sfen: str,
    solution_moves: list[str],
    opponent_moves: list[str],
    mate_length: int,
) -> list[str]:
    """問題データを検証し、問題点のリストを返す(空なら OK)。

    検証内容:
    - SFEN が解釈できる
    - 手数と手順の個数が整合する
    - 手順がすべて合法手である
    - 最終局面が詰みである
    """
    errors: list[str] = []
    try:
        board = shogi.Board(initial_sfen)
    except Exception as exc:  # python-shogi は ValueError 以外も投げ得る
        return [f"SFENを解釈できません: {exc}"]

    if mate_length % 2 == 0 or mate_length < 1:
        errors.append("mate_length は正の奇数にしてください")
        return errors
    if len(solution_moves) != (mate_length + 1) // 2:
        errors.append(
            f"solution_moves の数が不正です (期待 {(mate_length + 1) // 2}, 実際 {len(solution_moves)})"
        )
    if len(opponent_moves) != mate_length // 2:
        errors.append(
            f"opponent_moves の数が不正です (期待 {mate_length // 2}, 実際 {len(opponent_moves)})"
        )
    if errors:
        return errors

    king_sq = board.king_squares[shogi.WHITE]
    if king_sq is None:
        return ["玉方の玉が盤上にありません"]
    if board.is_attacked_by(shogi.BLACK, king_sq):
        errors.append("初期局面で玉に王手が掛かっています")

    si = oi = 0
    for ply in range(mate_length):
        if ply % 2 == 0:
            usi = solution_moves[si]
            si += 1
        else:
            usi = opponent_moves[oi]
            oi += 1
        try:
            move = shogi.Move.from_usi(usi)
        except Exception:
            errors.append(f"{ply + 1}手目 '{usi}' をUSIとして解釈できません")
            return errors
        if move not in board.legal_moves:
            errors.append(f"{ply + 1}手目 '{usi}' は合法手ではありません")
            return errors
        board.push(move)

    if not board.is_checkmate():
        errors.append("最終局面が詰みになっていません")
    return errors
