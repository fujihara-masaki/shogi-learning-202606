"""サンプル問題が詰将棋として正しいことを python-shogi で検証する。"""
import shogi

from app.seed import SAMPLE_PROBLEMS
from app.shogi_utils import validate_problem


def test_all_samples_pass_validation():
    for p in SAMPLE_PROBLEMS:
        errors = validate_problem(
            p["initial_sfen"], p["solution_moves"], p["opponent_moves"], p["mate_length"]
        )
        assert errors == [], f"{p['title']}: {errors}"


def test_opponent_replies_are_forced():
    """玉方の応手が唯一の合法手であること(自動応手の前提)。"""
    for p in SAMPLE_PROBLEMS:
        board = shogi.Board(p["initial_sfen"])
        si = oi = 0
        for ply in range(p["mate_length"]):
            if ply % 2 == 0:
                usi = p["solution_moves"][si]
                si += 1
            else:
                usi = p["opponent_moves"][oi]
                oi += 1
                legal = list(board.legal_moves)
                assert len(legal) == 1, (
                    f"{p['title']}: {ply + 1}手目の応手が強制ではありません"
                )
            board.push(shogi.Move.from_usi(usi))
        assert board.is_checkmate(), p["title"]
