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
        "name": "四間飛車",
        "opening_type": "振り飛車",
        "description": "飛車を4筋へ振り、美濃囲いなど堅い陣形から反撃を狙う基本形です。",
        "tag": "shikenbisha",
        "moves": ["7g7f", "3c3d", "6g6f", "8c8d", "2h6h", "8d8e", "7i7h", "6a5b"],
        "comments": ["角道を開けて駒組みを始めます。", "後手も角道を開けます。", "角道を止め、振り飛車らしい持久戦に備えます。", "後手は飛車先を伸ばします。", "飛車を4筋へ振って四間飛車に構えます。", "後手は飛車先を伸ばして圧力をかけます。", "左銀を上がり、美濃囲いと中央の厚みを準備します。", "後手は金を寄せて玉周りを整えます。"],
    },
    {
        "name": "矢倉",
        "opening_type": "相居飛車",
        "description": "左銀と金を連携させ、相居飛車の堅い玉形を目指す代表戦型です。",
        "tag": "yagura",
        "moves": ["7g7f", "8c8d", "6i7h", "3c3d", "6g6f", "7a6b", "7i6h", "5a4b", "5i6i"],
        "comments": ["角道を開けます。", "後手は飛車先を伸ばして相居飛車を示します。", "金を上がって矢倉の土台を作ります。", "後手も角道を開けます。", "角道を止めて矢倉の骨格を固めます。", "後手は銀を上がって受けの形を作ります。", "左銀を中央へ使い、矢倉囲いを目指します。", "後手は玉を囲う準備をします。", "玉を左へ寄せ、矢倉囲いへ進みます。"],
    },
    {
        "name": "角換わり",
        "opening_type": "相居飛車",
        "description": "角交換後に持ち角の打ち込みへ注意しながら駒組みする相居飛車です。",
        "tag": "kakugawari",
        "moves": ["7g7f", "8c8d", "2g2f", "3c3d", "8h2b+", "3a2b", "7i8h", "7a7b"],
        "comments": ["角道を開けます。", "後手は飛車先を伸ばします。", "先手も飛車先を伸ばします。", "後手も角道を開けます。", "角を交換して角換わりの入口に入ります。", "後手は銀で角を取り返します。", "銀を上がり、打ち込みに強い形を作ります。", "後手も銀を上がって角換わりの駒組みに進みます。"],
    },
    {
        "name": "相掛かり",
        "opening_type": "相居飛車",
        "description": "双方が飛車先を伸ばし、歩交換後の主導権を争うスピード感のある戦型です。",
        "tag": "aigakari",
        "moves": ["2g2f", "8c8d", "2f2e", "8d8e", "7g7f", "3c3d", "2h7h", "8b3b"],
        "comments": ["飛車先を伸ばして相掛かりを目指します。", "後手も飛車先を伸ばします。", "2筋の歩をさらに進めます。", "後手も8筋の歩を伸ばします。", "角道を開けて駒の働きを広げます。", "後手も角道を開けます。", "飛車を横に使い、ひねり飛車含みの含みを残します。", "後手も飛車を横に使ってバランスを取ります。"],
    },
    {
        "name": "横歩取り",
        "opening_type": "相居飛車",
        "description": "飛車先交換から横歩を取り、序盤から大駒が働く激しい戦型です。",
        "tag": "yokofudori",
        "moves": ["7g7f", "3c3d", "2g2f", "8c8d", "2f2e", "8d8e", "2e2d", "2c2d", "2h2d", "8e8f", "8g8f", "8b8f", "2d3d"],
        "comments": ["角道を開けます。", "後手も角道を開けます。", "飛車先を伸ばします。", "後手も飛車先を伸ばします。", "2筋の歩を伸ばして交換を狙います。", "後手も8筋で歩交換を狙います。", "先手から歩を突き捨てます。", "後手は同歩と取ります。", "飛車で歩を取り、飛車先交換に成功します。", "後手も8筋を突き捨てます。", "先手は同歩と応じます。", "後手も飛車で歩を取ります。", "3四の横歩を取り、横歩取りの基本局面に進みます。"],
    },
    {
        "name": "石田流",
        "opening_type": "振り飛車",
        "description": "三間飛車から7筋の位と浮き飛車を組み合わせて攻勢を取る構えです。",
        "tag": "ishida",
        "moves": ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e", "7h7f", "6a5b"],
        "comments": ["角道を開けます。", "後手も角道を開けます。", "7筋の歩を伸ばし、石田流の位を取ります。", "後手は飛車先を伸ばします。", "飛車を7筋へ振ります。", "後手は8筋を伸ばします。", "飛車を7六へ浮き、石田流の形を作ります。", "後手は金を寄せて受けに備えます。"],
    },
    {
        "name": "ゴキゲン中飛車",
        "opening_type": "振り飛車",
        "description": "角道を止めずに中央の歩を突き、主導権を取りに行く中飛車です。",
        "tag": "gokigen_nakabisha",
        "moves": ["7g7f", "3c3d", "2g2f", "5c5d", "2f2e", "5a5b", "2h5h", "8c8d"],
        "comments": ["角道を開けます。", "後手も角道を開けます。", "先手は飛車先を伸ばします。", "後手は角道を止めずに5筋の歩を突きます。", "先手は2筋の圧力を高めます。", "後手は玉を中央へ寄せて中飛車を支えます。", "先手も飛車を5筋へ振って中央で対抗します。", "後手は飛車先を伸ばしてバランスを取ります。"],
    },
    {
        "name": "角交換四間飛車",
        "opening_type": "振り飛車",
        "description": "角交換を済ませてから四間飛車へ振り、持ち角を活かす構想です。",
        "tag": "kakukokan_shikenbisha",
        "moves": ["7g7f", "3c3d", "8h2b+", "3a2b", "2g2f", "4c4d", "2h4h", "5a4b"],
        "comments": ["角道を開けます。", "後手も角道を開けます。", "角交換を行い、角交換振り飛車の含みを作ります。", "後手は銀で取り返します。", "飛車先を伸ばして居飛車の含みも見せます。", "後手は4筋を突いて四間飛車の形を目指します。", "飛車を4筋へ振り、角交換四間飛車に構えます。", "後手は玉を囲う準備をします。"],
    },
    {
        "name": "右四間飛車",
        "opening_type": "対抗型",
        "description": "飛車を右四間に寄せ、銀や角と連動して4筋突破を狙う急戦です。",
        "tag": "migi_shikenbisha",
        "moves": ["7g7f", "3c3d", "2g2f", "4c4d", "2f2e", "3a3b", "2h4h", "6a5b"],
        "comments": ["角道を開けます。", "後手も角道を開けます。", "飛車先を伸ばします。", "後手は4筋の歩を突いて争点を作ります。", "2筋を伸ばして居飛車の形を保ちます。", "後手は銀を上がって角頭を守ります。", "飛車を4筋へ寄せ、右四間飛車に構えます。", "後手は金を寄せて中央を厚くします。"],
    },
    {
        "name": "居飛車穴熊",
        "opening_type": "囲い・構想",
        "description": "対振り飛車で玉を端深く囲い、堅さを活かして戦う持久戦構想です。",
        "tag": "ibisha_anaguma",
        "moves": ["7g7f", "3c3d", "2g2f", "4c4d", "8h7g", "3a3b", "4i5h", "4a4b", "5i6h", "5a4a", "6h7h", "4a3a", "7h8h"],
        "comments": ["角道を開けます。", "後手も角道を開けます。", "居飛車らしく飛車先を伸ばします。", "後手は振り飛車を含みに4筋を突きます。", "角を上がって玉の通り道を作ります。", "後手は銀を上がって角頭を守ります。", "金を寄せて囲いの準備をします。", "後手も金を寄せます。", "玉を左へ移動します。", "後手玉も囲いへ向かいます。", "玉をさらに左へ寄せます。", "後手は玉を深く囲います。", "玉を8八へ潜り、居飛車穴熊の入口を作ります。"],
    },
    {
        "name": "対振り飛車急戦",
        "opening_type": "対抗型",
        "description": "居飛車側が銀を素早く繰り出し、振り飛車の囲いが完成する前に仕掛けを狙います。",
        "tag": "anti_furibisha_rapid",
        "moves": ["7g7f", "3c3d", "2g2f", "4c4d", "2f2e", "3a3b", "4i5h", "4a4b", "5g5f", "5a4a", "3i4h", "6a5b", "4h5g"],
        "comments": ["角道を開けます。", "後手も角道を開けます。", "飛車先を伸ばして居飛車を明示します。", "後手は4筋を突いて振り飛車模様にします。", "飛車先の圧力を高めます。", "後手は銀を上がって角頭を守ります。", "金を中央へ寄せて急戦に備えます。", "後手も金を寄せます。", "5筋の歩を突き、右銀の進出路を作ります。", "後手玉は囲いへ向かいます。", "右銀を上がって攻めに使います。", "後手は中央を厚くします。", "銀を5七へ進め、急戦の仕掛けを狙います。"],
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
    {"name_ja": "未分類", "sort_order": 999, "description": "import時に既知の戦型へ分類できなかった定跡です。", "source_url": "local seed", "license": "CC BY-SA"},
]

OPENING_TYPE_SEEDS = [
    ("相居飛車", None, "矢倉", "やぐら", "Yagura", ["矢倉戦法"], "相居飛車を代表する堅陣志向の戦型です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 10),
    ("相居飛車", "矢倉", "矢倉棒銀", "やぐらぼうぎん", "Yagura Climbing Silver", ["矢倉棒銀戦法"], "矢倉模様から銀を繰り出す急戦・攻撃型です。", "local seed", "local seed", "CC BY-SA", 11),
    ("相居飛車", None, "角換わり", "かくがわり", "Bishop Exchange", [], "角交換後の持ち角を活かして駒組みする相居飛車です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 20),
    ("相居飛車", "角換わり", "角換わり棒銀", "かくがわりぼうぎん", "Bishop Exchange Climbing Silver", ["角換り棒銀", "角換わり棒銀戦法"], "角換わりから棒銀で速攻を狙う戦型です。", "local seed", "local seed", "CC BY-SA", 21),
    ("相居飛車", "角換わり", "角換わり早繰り銀", "かくがわりはやくりぎん", "Bishop Exchange Rapid Silver", ["早繰り銀", "角換り早繰り銀"], "角換わりで銀を早く繰り出して主導権を争う戦型です。", "local seed", "local seed", "CC BY-SA", 22),
    ("相居飛車", "角換わり", "角換わり腰掛け銀", "かくがわりこしかけぎん", "Bishop Exchange Reclining Silver", ["腰掛け銀", "角換り腰掛け銀"], "角換わりで銀を5六/5四に据えて攻防を整える戦型です。", "local seed", "local seed", "CC BY-SA", 23),
    ("相居飛車", None, "相掛かり", "あいがかり", "Double Wing Attack", [], "双方が飛車先を伸ばして主導権を争う戦型です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 30),
    ("相居飛車", None, "横歩取り", "よこふどり", "Side Pawn Picker", [], "飛車先交換から横歩を取る激しい相居飛車です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 40),
    ("相居飛車", None, "雁木", "がんぎ", "Gangi", [], "金銀を盛り上げる相居飛車の構想です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 50),
    ("相居飛車", None, "棒銀", "ぼうぎん", "Climbing Silver", ["棒銀戦法"], "銀を飛車先から進出させて突破を狙う代表的な急戦です。", "local seed", "local seed", "CC BY-SA", 60),
    ("相居飛車", "棒銀", "原始棒銀", "げんしぼうぎん", "Primitive Climbing Silver", ["原始棒銀戦法"], "シンプルに飛車先と銀を連動させる棒銀の基本形です。", "local seed", "local seed", "CC BY-SA", 61),
    ("対抗型", None, "右四間飛車", "みぎしけんびしゃ", "Right Fourth File Rook", ["右四間", "右四間飛車戦法"], "右辺に飛車を寄せて4筋突破を狙う急戦構想です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 5),
    ("対抗型", None, "対振り飛車急戦", "たいふりびしゃきゅうせん", "Anti-Ranging Rook Quick Attack", ["対振り急戦", "急戦"], "居飛車側が振り飛車に対して早い仕掛けを目指す分類です。", "local seed", "local seed", "CC BY-SA", 6),
    ("囲い・構想", "穴熊", "居飛車穴熊", "いびしゃあなぐま", "Static Rook Anaguma", ["イビ穴"], "居飛車側が穴熊に囲う対振り飛車の持久戦構想です。", "local seed", "local seed", "CC BY-SA", 21),
    ("対抗型", None, "中飛車", "なかびしゃ", "Central Rook", [], "飛車を5筋に振って中央から戦う振り飛車です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 10),
    ("対抗型", "中飛車", "ゴキゲン中飛車", "ごきげんなかびしゃ", "Cheerful Central Rook", ["ゴキ中", "ゴキゲン中飛車戦法"], "角道を止めずに中飛車へ構える積極的な振り飛車です。", "local seed", "local seed", "CC BY-SA", 11),
    ("対抗型", None, "四間飛車", "しけんびしゃ", "Fourth File Rook", ["ノーマル四間飛車", "四間飛車戦法"], "飛車を4筋に振る代表的な振り飛車です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 20),
    ("対抗型", "四間飛車", "角交換四間飛車", "かくこうかんしけんびしゃ", "Bishop Exchange Fourth File Rook", ["角交換四間", "角交換四間飛車戦法"], "角交換を含みに四間飛車へ構える現代的な振り飛車です。", "local seed", "local seed", "CC BY-SA", 21),
    ("対抗型", None, "三間飛車", "さんけんびしゃ", "Third File Rook", [], "飛車を3筋に振り石田流などへ発展します。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 30),
    ("対抗型", "三間飛車", "石田流", "いしだりゅう", "Ishida Style", ["石田流三間飛車"], "三間飛車から攻撃的な石田流の形を目指す戦型です。", "local seed", "local seed", "CC BY-SA", 31),
    ("対抗型", None, "向かい飛車", "むかいびしゃ", "Opposing Rook", [], "相手飛車の向かい側に飛車を振る戦型です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 40),
    ("対抗型", None, "角交換振り飛車", "かくこうかんふりびしゃ", "Bishop Exchange Ranging Rook", [], "角交換を含みにする現代的な振り飛車構想です。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 50),
    ("相振り飛車", None, "相振り飛車", "あいふりびしゃ", "Double Ranging Rook", [], "双方が飛車を振って戦う大分類です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 10),
    ("奇襲・B級戦法", None, "嬉野流", "うれしのりゅう", "Ureshino Opening", [], "初手▲6八銀などから独自の構想で戦います。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 10),
    ("奇襲・B級戦法", None, "鬼殺し", "おにごろし", "Demon Killer", [], "桂跳ねを絡めて急戦を狙う奇襲戦法です。", "Wikibooks 将棋の戦法一覧", "https://ja.wikibooks.org/wiki/将棋の戦法一覧", "CC BY-SA", 20),
    ("奇襲・B級戦法", None, "早石田", "はやいしだ", "Quick Ishida", [], "早い段階で石田流を目指す三間飛車系の急戦です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 30),
    ("奇襲・B級戦法", None, "筋違い角", "すじちがいかく", "Wrong Diagonal Bishop", [], "序盤早々に角交換して筋違いに角を打つ戦法です。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 40),
    ("囲い・構想", None, "美濃囲い", "みのがこい", "Mino Castle", [], "振り飛車で多用される軽く堅い囲いです。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 10),
    ("囲い・構想", None, "穴熊", "あなぐま", "Anaguma", ["穴熊囲い"], "玉を端深く囲う堅陣です。", "Wikipedia 将棋の戦法", "https://ja.wikipedia.org/wiki/将棋の戦法", "CC BY-SA", 20),
    ("囲い・構想", None, "舟囲い", "ふながこい", "Boat Castle", [], "居飛車対振り飛車で急戦に用いられる囲いです。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 30),
    ("囲い・構想", None, "左美濃", "ひだりみの", "Left Mino", [], "居飛車側が左辺に美濃形を作る構想です。", "Wikipediaカテゴリ 将棋の戦法", "https://ja.wikipedia.org/wiki/Category:将棋の戦法", "CC BY-SA", 40),
    ("未分類", None, "未分類", "みぶんるい", "Unclassified", ["その他", "分類不能", "不明"], "既知の戦型へ分類できない定跡のフォールバックです。", "local seed", "local seed", "CC BY-SA", 999),
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
    for category in OPENING_CATEGORY_SEEDS:
        conn.execute(
            """
            INSERT INTO opening_categories(name_ja, sort_order, description, source_url, license)
            VALUES (:name_ja, :sort_order, :description, :source_url, :license)
            ON CONFLICT(name_ja) DO UPDATE SET
                sort_order = excluded.sort_order,
                description = excluded.description,
                source_url = excluded.source_url,
                license = excluded.license
            """,
            category,
        )
    category_rows = conn.execute("SELECT id, name_ja FROM opening_categories").fetchall()
    category_ids = {row["name_ja"]: row["id"] for row in category_rows}
    existing_by_name = {
        row["name_ja"]: row
        for row in conn.execute("SELECT id, category_id, name_ja FROM opening_types ORDER BY id").fetchall()
    }
    inserted: dict[str, int] = {}
    for category_name, parent_name, name_ja, name_kana, name_en, aliases, description, source_name, source_url, license_name, sort_order in OPENING_TYPE_SEEDS:
        category_id = category_ids[category_name]
        existing_row = existing_by_name.get(name_ja)
        if existing_row:
            conn.execute(
                """
                UPDATE opening_types
                SET category_id = ?, name_kana = ?, name_en = ?, aliases = ?,
                    description_short = ?, source_name = ?, source_url = ?, license = ?,
                    sort_order = ?, is_active = 1
                WHERE id = ?
                """,
                (
                    category_id,
                    name_kana,
                    name_en,
                    json.dumps(aliases, ensure_ascii=False),
                    description,
                    source_name,
                    source_url,
                    license_name,
                    sort_order,
                    existing_row["id"],
                ),
            )
            inserted[name_ja] = existing_row["id"]
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

    all_types = {
        row["name_ja"]: row["id"]
        for row in conn.execute("SELECT id, name_ja FROM opening_types").fetchall()
    }
    for _, parent_name, name_ja, *_ in OPENING_TYPE_SEEDS:
        if parent_name and parent_name in all_types and name_ja in all_types:
            conn.execute(
                "UPDATE opening_types SET parent_id = ? WHERE id = ? AND (parent_id IS NULL OR parent_id != ?)",
                (all_types[parent_name], all_types[name_ja], all_types[parent_name]),
            )

def seed_openings_if_empty(conn) -> None:
    import shogi

    row = conn.execute("SELECT COUNT(*) AS c FROM opening_lines").fetchone()
    if row["c"] > 0:
        return
    for opening in SAMPLE_OPENING_LINES:
        positions, move_rows = _opening_snapshots(shogi.STARTING_SFEN, opening["moves"])
        type_row = conn.execute(
            "SELECT id FROM opening_types WHERE name_ja = ?", (opening["name"],)
        ).fetchone()
        cur = conn.execute(
            """
            INSERT INTO opening_lines(opening_type_id, name, opening_type, initial_sfen, moves, comments, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                type_row["id"] if type_row else None,
                opening["name"],
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
        conn.commit()
    finally:
        conn.close()
