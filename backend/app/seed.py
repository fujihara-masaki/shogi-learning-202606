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


SAMPLE_OPENING_LINES = [
    {
        "name": "棒銀",
        "opening_type": "居飛車",
        "description": "右銀を2筋へ繰り出し、飛車先突破を狙う基本の攻め筋です。",
        "tag": "bougin",
        "moves": ["7g7f", "3c3d", "2g2f", "8c8d", "2f2e", "8d8e", "3i3h", "7a6b", "3h2g", "4a3b", "2g2f"],
        "comments": [
            "角道を開けて攻めの準備をします。",
            "後手も角道を開けます。",
            "飛車先の歩を伸ばします。",
            "後手も飛車先を伸ばします。",
            "2筋の圧力を高めます。",
            "後手も8筋を伸ばして対抗します。",
            "右銀を攻めに使う第一歩です。",
            "後手は銀を上がって受けの形を整えます。",
            "銀を2筋へ進め、棒銀の形を明確にします。",
            "後手は玉側の金を締めます。",
            "銀をさらに前へ出て飛車先突破を狙います。",
        ],
    },
    {
        "name": "中飛車",
        "opening_type": "振り飛車",
        "description": "飛車を5筋へ振り、中央から主導権を取る構えです。",
        "tag": "nakabisha",
        "moves": ["7g7f", "3c3d", "2h5h", "8c8d", "5g5f", "8d8e", "5h5g", "6a5b"],
        "comments": [
            "角道を開けます。",
            "後手も角道を開けます。",
            "飛車を中央の5筋へ振ります。",
            "後手は飛車先を伸ばします。",
            "5筋の歩を突き、中央の争点を作ります。",
            "後手は8筋の圧力を高めます。",
            "飛車を5七へ浮き、中央を支えます。",
            "後手は金を寄せて中央を厚くします。",
        ],
    },
    {
        "name": "向かい飛車",
        "opening_type": "振り飛車",
        "description": "飛車を相手飛車の向かい側へ振り、8筋で対抗する構えです。",
        "tag": "mukaibisha",
        "moves": ["7g7f", "3c3d", "8h7g", "8c8d", "2h8h", "8d8e", "4i5h", "4a3b"],
        "comments": [
            "角道を開けます。",
            "後手も角道を開けます。",
            "角を上がって飛車の横移動路を作ります。",
            "後手は飛車先を伸ばします。",
            "飛車を8筋へ振って向かい飛車に構えます。",
            "後手は8筋を伸ばして接点を作ります。",
            "金を中央へ寄せて陣形を整えます。",
            "後手も金を締めます。",
        ],
    },
]

OPENING_CATEGORY_SEEDS = [
    {"name_ja": "相居飛車", "sort_order": 10, "description": "双方が居飛車で戦う代表的な序盤分類です。", "source_url": "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "license": "CC BY-SA"},
    {"name_ja": "対抗型", "sort_order": 20, "description": "居飛車対振り飛車の対抗形です。", "source_url": "https://ja.wikipedia.org/wiki/将棋の戦法", "license": "CC BY-SA"},
    {"name_ja": "相振り飛車", "sort_order": 30, "description": "双方が振り飛車に構える戦型です。", "source_url": "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "license": "CC BY-SA"},
    {"name_ja": "奇襲・B級戦法", "sort_order": 40, "description": "意表を突く構想や力戦志向の戦法です。", "source_url": "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "license": "CC BY-SA"},
    {"name_ja": "囲い・構想", "sort_order": 50, "description": "序盤構想や玉の囲いに関する項目です。", "source_url": "https://ja.wikipedia.org/wiki/将棋の戦法", "license": "CC BY-SA"},
]

OPENING_TYPE_SEEDS = [
    ("相居飛車", None, "矢倉", "やぐら", "Yagura", ["矢倉戦法"], "相居飛車を代表する堅陣志向の戦型です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 10),
    ("相居飛車", None, "角換わり", "かくがわり", "Bishop Exchange", [], "角交換後の持ち角を活かして駒組みする相居飛車です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 20),
    ("相居飛車", None, "相掛かり", "あいがかり", "Double Wing Attack", [], "双方が飛車先を伸ばして主導権を争う戦型です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 30),
    ("相居飛車", None, "横歩取り", "よこふどり", "Side Pawn Picker", [], "飛車先交換から横歩を取る激しい相居飛車です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 40),
    ("対抗型", None, "中飛車", "なかびしゃ", "Central Rook", [], "飛車を5筋に振って中央から戦う振り飛車です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 10),
    ("対抗型", None, "四間飛車", "しけんびしゃ", "Fourth File Rook", [], "飛車を4筋に振る代表的な振り飛車です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 20),
    ("対抗型", None, "三間飛車", "さんけんびしゃ", "Third File Rook", [], "飛車を3筋に振り石田流などへ発展します。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 30),
    ("対抗型", None, "向かい飛車", "むかいびしゃ", "Opposing Rook", [], "相手飛車の向かい側に飛車を振る戦型です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 40),
    ("対抗型", None, "角交換振り飛車", "かくこうかんふりびしゃ", "Bishop Exchange Ranging Rook", [], "角交換を含みにする現代的な振り飛車構想です。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 50),
    ("相振り飛車", None, "相振り飛車", "あいふりびしゃ", "Double Ranging Rook", [], "双方が飛車を振って戦う大分類です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 10),
    ("奇襲・B級戦法", None, "嬉野流", "うれしのりゅう", "Ureshino Opening", [], "初手▲6八銀などから独自の構想で戦います。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 10),
    ("奇襲・B級戦法", None, "鬼殺し", "おにごろし", "Demon Killer", [], "桂跳ねを絡めて急戦を狙う奇襲戦法です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 20),
    ("奇襲・B級戦法", None, "早石田", "はやいしだ", "Quick Ishida", [], "早い段階で石田流を目指す三間飛車系の急戦です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 30),
    ("奇襲・B級戦法", None, "筋違い角", "すじちがいかく", "Wrong Diagonal Bishop", [], "序盤早々に角交換して筋違いに角を打つ戦法です。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 40),
    ("奇襲・B級戦法", None, "右四間飛車", "みぎしけんびしゃ", "Right Fourth File Rook", [], "右辺に飛車を寄せて4筋突破を狙う急戦構想です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 50),
    ("囲い・構想", None, "美濃囲い", "みのがこい", "Mino Castle", [], "振り飛車で多用される軽く堅い囲いです。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 10),
    ("囲い・構想", None, "穴熊", "あなぐま", "Anaguma", ["穴熊囲い"], "玉を端深く囲う堅陣です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 20),
    ("囲い・構想", None, "舟囲い", "ふながこい", "Boat Castle", [], "居飛車対振り飛車で急戦に用いられる囲いです。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 30),
    ("囲い・構想", None, "左美濃", "ひだりみの", "Left Mino", [], "居飛車側が左辺に美濃形を作る構想です。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 40),
    ("囲い・構想", None, "雁木", "がんぎ", "Gangi", [], "金銀を盛り上げる相居飛車の構想です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 50),
]


def _opening_snapshots(initial_sfen: str, moves: list[str]) -> tuple[list[str], list[tuple[int, str, str, str]]]:
    import shogi

    board = shogi.Board(initial_sfen)
    positions = [board.sfen()]
    move_rows = []
    for ply, usi in enumerate(moves, start=1):
        before = board.sfen()
        move = shogi.Move.from_usi(usi)
        if move not in board.legal_moves:
            raise ValueError(f"サンプル定跡手が不正です: {usi}")
        board.push(move)
        after = board.sfen()
        positions.append(after)
        move_rows.append((ply, usi, before, after))
    return positions, move_rows



def seed_opening_catalog_if_empty(conn) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO opening_categories(name_ja, sort_order, description, source_url, license)
        VALUES (:name_ja, :sort_order, :description, :source_url, :license)
        """,
        OPENING_CATEGORY_SEEDS,
    )
    category_rows = conn.execute("SELECT id, name_ja FROM opening_categories").fetchall()
    category_ids = {row["name_ja"]: row["id"] for row in category_rows}
    existing = {
        (row["category_id"], row["name_ja"])
        for row in conn.execute("SELECT category_id, name_ja FROM opening_types").fetchall()
    }
    inserted: dict[str, int] = {}
    for category_name, parent_name, name_ja, name_kana, name_en, aliases, description, source_name, source_url, license_name, sort_order in OPENING_TYPE_SEEDS:
        category_id = category_ids[category_name]
        if (category_id, name_ja) in existing:
            row = conn.execute("SELECT id FROM opening_types WHERE category_id = ? AND name_ja = ?", (category_id, name_ja)).fetchone()
            inserted[name_ja] = row["id"]
            continue
        parent_id = inserted.get(parent_name) if parent_name else None
        cur = conn.execute(
            """
            INSERT INTO opening_types(category_id, parent_id, name_ja, name_kana, name_en, aliases,
                                      description_short, source_name, source_url, license, sort_order, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (category_id, parent_id, name_ja, name_kana, name_en, json.dumps(aliases, ensure_ascii=False),
             description, source_name, source_url, license_name, sort_order),
        )
        inserted[name_ja] = int(cur.lastrowid)


def find_opening_type_id(conn, name: str | None) -> int | None:
    if not name:
        return None
    row = conn.execute("SELECT id FROM opening_types WHERE name_ja = ? AND is_active = 1 ORDER BY id LIMIT 1", (name,)).fetchone()
    if row:
        return int(row["id"])
    rows = conn.execute("SELECT id, aliases FROM opening_types WHERE is_active = 1").fetchall()
    for row in rows:
        try:
            aliases = json.loads(row["aliases"] or "[]")
        except json.JSONDecodeError:
            aliases = []
        if name in aliases:
            return int(row["id"])
    return None


def backfill_opening_line_type_ids(conn) -> None:
    rows = conn.execute("SELECT id, name, opening_type FROM opening_lines WHERE opening_type_id IS NULL").fetchall()
    for row in rows:
        opening_type_id = find_opening_type_id(conn, row["name"]) or find_opening_type_id(conn, row["opening_type"])
        if opening_type_id is not None:
            conn.execute("UPDATE opening_lines SET opening_type_id = ? WHERE id = ?", (opening_type_id, row["id"]))

def seed_openings_if_empty(conn) -> None:
    import shogi

    row = conn.execute("SELECT COUNT(*) AS c FROM opening_lines").fetchone()
    if row["c"] > 0:
        return
    for opening in SAMPLE_OPENING_LINES:
        positions, move_rows = _opening_snapshots(shogi.STARTING_SFEN, opening["moves"])
        opening_type_id = find_opening_type_id(conn, opening["name"]) or find_opening_type_id(conn, opening["opening_type"])
        cur = conn.execute(
            """
            INSERT INTO opening_lines(name, opening_type_id, opening_type, initial_sfen, moves, comments, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opening["name"],
                opening_type_id,
                opening["opening_type"],
                shogi.STARTING_SFEN,
                json.dumps(opening["moves"], ensure_ascii=False),
                json.dumps(opening["comments"], ensure_ascii=False),
                json.dumps([opening["tag"]], ensure_ascii=False),
            ),
        )
        line_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO opening_positions(line_id, ply, sfen) VALUES (?, ?, ?)",
            [(line_id, ply, sfen) for ply, sfen in enumerate(positions)],
        )
        conn.executemany(
            "INSERT INTO opening_line_moves(line_id, ply, usi, from_sfen, to_sfen, comment) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (line_id, ply, usi, before, after, opening["comments"][ply - 1])
                for ply, usi, before, after in move_rows
            ],
        )
        conn.execute(
            "INSERT INTO opening_tags(line_id, tag, score, reason) VALUES (?, ?, ?, ?)",
            (line_id, opening["tag"], 1.0, opening["description"]),
        )


def seed_if_empty() -> None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM tsume_problems").fetchone()
        if row["c"] == 0:
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
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        backfill_opening_line_type_ids(conn)
        conn.commit()
    finally:
        conn.close()
