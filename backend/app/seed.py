"""初回起動時のサンプル詰将棋問題。

全問題は python-shogi で次を機械検証済み:
- 手順がすべて合法手
- 玉方の応手はその局面での唯一の合法手(強制)
- 最終局面が詰み
- より短い詰みが存在しない
- 初手の正解が一意(別解なし)

ただし芸術性は考慮していない練習用サンプルのため、タイトルに [sample] を付与。
"""
import json

from .database import get_connection
from .shogi_utils import validate_problem

SAMPLE_PROBLEMS = [
    {
        "title": "[sample] 頭金の基本",
        "initial_sfen": "4k4/9/5+B3/9/9/9/9/9/9 b G 1",
        "mate_length": 1,
        "solution_moves": ["G*5b"],
        "opponent_moves": [],
        "difficulty": 1,
        "tags": ["1手詰", "頭金"],
        "explanation": "馬が5二に利いているので、玉頭に金を打てば取られません。"
        "金は玉の逃げ道(4一・6一・4二・6二)をすべて押さえています。",
    },
    {
        "title": "[sample] 退路封鎖の金",
        "initial_sfen": "8k/9/7P1/9/9/9/9/9/9 b G 1",
        "mate_length": 1,
        "solution_moves": ["G*2b"],
        "opponent_moves": [],
        "difficulty": 1,
        "tags": ["1手詰", "頭金", "逃げ道封鎖"],
        "explanation": "2三の歩が支えになるので2二の金は取られません。"
        "金一枚で1二・2一の逃げ道を同時に塞ぐ形です。",
    },
    {
        "title": "[sample] 開き王手",
        "initial_sfen": "8k/9/8B/8R/9/9/9/9/9 b - 1",
        "mate_length": 1,
        "solution_moves": ["1c3a+"],
        "opponent_moves": [],
        "difficulty": 2,
        "tags": ["1手詰", "実戦型"],
        "explanation": "角を3一に成ると飛車の利きが通って開き王手になります。"
        "馬が2一・2二を押さえているため玉は逃げられません。",
    },
    {
        "title": "[sample] 一間龍から頭金",
        "initial_sfen": "8k/9/5+R3/9/9/9/9/9/9 b G 1",
        "mate_length": 3,
        "solution_moves": ["4c1c", "G*2b"],
        "opponent_moves": ["1a2a"],
        "difficulty": 1,
        "tags": ["3手詰", "頭金"],
        "explanation": "龍を1三に寄せて王手。玉は2一への一手しかありません。"
        "そこで龍の利きを支えに2二へ金を打てば頭金の詰みです。",
    },
    {
        "title": "[sample] 銀打ちから龍の寄せ",
        "initial_sfen": "8k/9/9/7+R1/9/9/9/9/9 b S 1",
        "mate_length": 3,
        "solution_moves": ["S*2b", "2d1c"],
        "opponent_moves": ["1a1b"],
        "difficulty": 2,
        "tags": ["3手詰", "逃げ道封鎖"],
        "explanation": "2二銀は龍が支えているので取れず、玉は1二へ逃げる一手。"
        "そこで龍を1三へ引き付ければ上下を押さえて詰みです。",
    },
    {
        "title": "[sample] 馬の利きを使う金打ち",
        "initial_sfen": "6+B2/8k/9/9/9/9/9/9/9 b G 1",
        "mate_length": 3,
        "solution_moves": ["G*1c", "1c2b"],
        "opponent_moves": ["1b1a"],
        "difficulty": 2,
        "tags": ["3手詰", "逃げ道封鎖"],
        "explanation": "馬の斜めの利きを支えに1三へ金打ち。玉は1一へ逃げる一手です。"
        "金を2二に寄せれば馬が支えとなり、ぴったりの詰みになります。",
    },
    {
        "title": "[sample] 銀の成り捨てならぬ成り寄せ",
        "initial_sfen": "6+B1k/9/9/9/9/9/9/9/9 b S 1",
        "mate_length": 5,
        "solution_moves": ["S*2b", "2b1c+", "1c2b"],
        "opponent_moves": ["1a1b", "1b1a"],
        "difficulty": 3,
        "tags": ["5手詰", "逃げ道封鎖"],
        "explanation": "馬の利きを支えに2二銀と打ち、玉を1二へ追います。"
        "銀を1三に成って王手すると玉は1一へ戻る一手。"
        "最後は成銀を2二へ寄せて詰み。銀が金に変わる成りの活用がテーマです。",
    },
]


def seed_if_empty() -> None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM tsume_problems").fetchone()
        if row["c"] > 0:
            return
        for p in SAMPLE_PROBLEMS:
            errors = validate_problem(
                p["initial_sfen"], p["solution_moves"], p["opponent_moves"], p["mate_length"]
            )
            if errors:
                raise ValueError(f"サンプル問題 '{p['title']}' が不正です: {errors}")
            conn.execute(
                """
                INSERT INTO tsume_problems
                  (title, initial_sfen, mate_length, solution_moves, opponent_moves,
                   difficulty, tags, explanation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["title"],
                    p["initial_sfen"],
                    p["mate_length"],
                    json.dumps(p["solution_moves"]),
                    json.dumps(p["opponent_moves"]),
                    p["difficulty"],
                    json.dumps(p["tags"], ensure_ascii=False),
                    p["explanation"],
                ),
            )
        conn.commit()
    finally:
        conn.close()
