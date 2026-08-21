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
        "name": "三間飛車", "opening_type": "振り飛車", "description": "飛車を7筋へ振って左辺から主導権を狙う基本の振り飛車です。", "tag": "sangenbisha",
        "moves": ["7g7f", "3c3d", "6g6f", "8c8d", "2h7h", "8d8e", "7i6h", "6a5b"],
    },
    {
        "name": "角交換振り飛車", "opening_type": "振り飛車", "description": "角交換後に飛車を振り、持ち角を活かして戦う構想です。", "tag": "kakukokan_furibisha",
        "moves": ["7g7f", "3c3d", "8h2b+", "3a2b", "2h6h", "8c8d", "6g6f", "6a5b"],
    },
    {
        "name": "相振り飛車", "opening_type": "相振り飛車", "description": "双方が飛車を振り、玉の囲いと左辺の主導権を争う戦型です。", "tag": "ai_furibisha",
        "moves": ["7g7f", "3c3d", "6g6f", "5c5d", "2h7h", "8b5b", "7i6h", "5b3b"],
    },
    {
        "name": "嬉野流", "opening_type": "奇襲・B級戦法", "description": "左銀を早く中央へ繰り出し、力戦調の攻めを狙う構想です。", "tag": "ureshino",
        "moves": ["6i7h", "3c3d", "7i6h", "8c8d", "5g5f", "8d8e", "6h5g", "4a3b"],
    },
    {
        "name": "鬼殺し", "opening_type": "奇襲・B級戦法", "description": "左銀を早く5六へ進め、桂跳ねや角筋を絡めた奇襲を狙います。", "tag": "onigoroshi",
        "moves": ["7g7f", "3c3d", "7i7h", "8c8d", "6g6f", "8d8e", "7h6g", "6a5b", "6g5f"],
    },
    {
        "name": "原始鬼殺し（Wikipedia明示手順）",
        "opening_type": "奇襲・B級戦法",
        "description": "Wikipedia本文の原始鬼殺し節に明示された初手からの進行です。",
        "tag": "onigoroshi",
        "opening_type_name": "鬼殺し",
        "source_url": "https://ja.wikipedia.org/wiki/鬼殺し_(将棋)",
        "source_title": "Wikipedia 鬼殺し (将棋)",
        "source_section": "原始鬼殺し",
        "coverage_status": "Wikipedia本文明示の長手順・対策分岐",
        "source_note": "原始鬼殺し節の▲7六歩△3四歩▲7七桂から▲7三歩成までの本文記述と、△6二金/△6二銀の対応を短く手順化。",
        "moves": ["7g7f", "3c3d", "8i7g", "8c8d", "7g6e", "7a6b", "7f7e", "6c6d", "8h2b+", "3a2b", "B*5e", "2b3c", "5e6d", "6a5b", "7e7d", "6b6c", "2h7h", "6c6d", "7d7c+"],
        "comments": [
            "▲7六歩。原始鬼殺しの初手です。", "△3四歩。", "▲7七桂。Wikipedia図1-1の局面です。", "△8四歩。本文で示された応手です。",
            "▲6五桂。", "△6二銀。", "▲7五歩。Wikipedia図1-2の局面です。", "△6四歩。両取り筋への対応です。",
            "▲2二角成。", "△同銀。", "▲5五角。Wikipedia図1-3の局面です。", "△3三銀。",
            "▲6四角。", "△5二金右。", "▲7四歩。", "△6三金。", "▲7八飛。", "△6四金。", "▲7三歩成。Wikipedia図1-4までの本文手順です。"
        ],
        "branches": [
            {"from_ply": 3, "name": "△6二銀の対応", "moves": ["7a6b"], "note": "3手目▲7七桂に対する4手目△6二銀。"},
            {"from_ply": 3, "name": "△6二金の有効な受け", "moves": ["6a6b", "7g6e", "6c6d"], "note": "△6二金、▲6五桂に△6四歩と受ける入口。"}
        ],
    },
    {
        "name": "新・早石田（鈴木流急戦・Wikipedia明示手順）",
        "opening_type": "振り飛車",
        "description": "Wikipedia本文の新・早石田節に明示された初手からの進行です。",
        "tag": "haya_ishida",
        "opening_type_name": "早石田",
        "source_url": "https://ja.wikipedia.org/wiki/石田流",
        "source_title": "Wikipedia 石田流",
        "source_section": "新・早石田",
        "coverage_status": "Wikipedia本文明示の初手からの手順",
        "source_note": "新・早石田節の第7手▲7四歩までの本文・図示手順を対象化。以降は本文にある範囲のみ。",
        "moves": ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e", "7e7d"],
    },
    {
        "name": "升田式石田流（Wikipedia明示手順）",
        "opening_type": "振り飛車",
        "description": "Wikipedia本文の升田式石田流節に明示された初手からの進行です。",
        "tag": "ishida",
        "opening_type_name": "石田流",
        "source_url": "https://ja.wikipedia.org/wiki/石田流",
        "source_title": "Wikipedia 石田流",
        "source_section": "升田式石田流",
        "coverage_status": "Wikipedia本文明示の初手から▲4八玉まで（続く▲7六飛は未収録）",
        "source_note": "升田式石田流節の初手▲7六歩から7手目▲4八玉までを収録。本文に記載された続く▲7六飛は未収録。",
        "moves": ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e", "5i4h"],
    },
    {
        "name": "早石田", "opening_type": "振り飛車", "description": "早く7筋の位を取り、三間飛車から攻勢を目指す急戦調の石田流です。", "tag": "haya_ishida",
        "moves": ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e", "7h7f"],
    },
    {
        "name": "筋違い角", "opening_type": "奇襲・B級戦法", "description": "角交換後に4五角と打ち、相手陣の隙を狙う力戦戦法です。", "tag": "sujichigai_kaku",
        "moves": ["7g7f", "3c3d", "8h2b+", "3a2b", "B*4e", "6a5b"],
    },
    {
        "name": "雁木", "opening_type": "相居飛車", "description": "金銀を中央へ盛り上げ、厚みで受け止める相居飛車の構想です。", "tag": "gangi",
        "moves": ["7g7f", "8c8d", "6g6f", "3c3d", "7i6h", "7a6b", "6h6g", "5c5d", "5g5f"],
    },
    {
        "name": "矢倉棒銀", "opening_type": "相居飛車", "description": "矢倉模様から右銀を繰り出し、2筋突破を狙う急戦です。", "tag": "yagura_bougin",
        "moves": ["7g7f", "8c8d", "6i7h", "3c3d", "6g6f", "7a6b", "2g2f", "5c5d", "3i3h", "5a4b", "3h2g"],
    },
    {
        "name": "角換わり棒銀", "opening_type": "相居飛車", "description": "角交換後に右銀を2筋へ繰り出し、飛車先突破を目指します。", "tag": "kakugawari_bougin",
        "moves": ["7g7f", "8c8d", "2g2f", "3c3d", "8h2b+", "3a2b", "3i3h", "7a7b", "3h2g"],
    },
    {
        "name": "角換わり早繰り銀", "opening_type": "相居飛車", "description": "角交換後に銀を4六へ急ぎ、主導権を取りに行く戦型です。", "tag": "kakugawari_hayakuri_gin",
        "moves": ["7g7f", "8c8d", "2g2f", "3c3d", "8h2b+", "3a2b", "3i4h", "7a7b", "3g3f", "6a5b", "4h3g"],
    },
    {
        "name": "角換わり腰掛け銀", "opening_type": "相居飛車", "description": "角交換後に銀を5六へ据え、厚みを作って仕掛けを待つ戦型です。", "tag": "kakugawari_koshikake_gin",
        "moves": ["7g7f", "8c8d", "2g2f", "3c3d", "8h2b+", "3a2b", "7i8h", "7a7b", "5g5f", "6a5b", "3i4h", "5c5d", "4h5g"],
    },
    {
        "name": "原始棒銀", "opening_type": "相居飛車", "description": "飛車先と右銀を一直線に進める、棒銀の最も基本的な形です。", "tag": "primitive_bougin",
        "moves": ["2g2f", "8c8d", "2f2e", "8d8e", "3i3h", "7a6b", "3h2g", "4a3b", "2g2f"],
    },
    {
        "name": "美濃囲い", "opening_type": "囲い・構想", "description": "振り飛車側の玉を右辺へ囲い、金銀で横からの攻めに強い形を作ります。", "tag": "mino_gakoi",
        "moves": ["7g7f", "3c3d", "6g6f", "8c8d", "2h6h", "8d8e", "5i4h", "6a5b", "4h3h", "5b4b", "3h2h", "7a6b", "3i3h"],
    },
    {
        "name": "穴熊", "opening_type": "囲い・構想", "description": "玉を端深く潜らせ、香の下で堅く囲う代表的な持久戦の囲いです。", "tag": "anaguma",
        "moves": ["7g7f", "3c3d", "2g2f", "4c4d", "8h7g", "3a3b", "5i6h", "5a4b", "6h7h", "6a5b", "7h8h"],
    },
    {
        "name": "舟囲い", "opening_type": "囲い・構想", "description": "居飛車対振り飛車で素早く玉を左へ寄せる急戦向けの基本囲いです。", "tag": "funagakoi",
        "moves": ["7g7f", "3c3d", "2g2f", "4c4d", "4i5h", "3a3b", "5i6h", "4a4b", "6h7h"],
    },
    {
        "name": "左美濃", "opening_type": "囲い・構想", "description": "居飛車側が左辺で美濃囲いに組み、対振り飛車で堅さを確保します。", "tag": "hidari_mino",
        "moves": ["7g7f", "3c3d", "2g2f", "8c8d", "7i6h", "7a6b", "6h7g", "4a3b", "5i6h", "6a5b", "4i5h"],
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

WIKIPEDIA_OPENING_SOURCE_DEFAULTS = {
    "source_url": "https://ja.wikipedia.org/wiki/将棋の戦法",
    "source_title": "Wikipedia 将棋の戦法",
    "license": "CC BY-SA 4.0",
    "source_type": "wikipedia",
    "source_section": "",
    "source_license": "CC BY-SA 4.0",
    "source_retrieved_at": "2026-07-03",
    "source_note": "Wikipediaの戦法説明・局面図を参考に、既存seedのUSI手順として再構成。明示情報が短い戦型は短い手順に留めています。",
    "coverage_status": "短い手順のみ",
}

WIKIPEDIA_OPENING_SOURCE_BY_NAME = {
    "棒銀": {"source_url": "https://ja.wikipedia.org/wiki/棒銀", "source_title": "Wikipedia 棒銀", "coverage_status": "局面図参考の短い手順"},
    "原始棒銀": {"source_url": "https://ja.wikipedia.org/wiki/棒銀", "source_title": "Wikipedia 棒銀", "coverage_status": "局面図参考の短い手順"},
    "角換わり": {"source_url": "https://ja.wikipedia.org/wiki/角換わり", "source_title": "Wikipedia 角換わり", "coverage_status": "短い手順のみ"},
    "角換わり棒銀": {"source_url": "https://ja.wikipedia.org/wiki/角換わり", "source_title": "Wikipedia 角換わり", "coverage_status": "短い手順のみ"},
    "角換わり早繰り銀": {"source_url": "https://ja.wikipedia.org/wiki/角換わり", "source_title": "Wikipedia 角換わり", "coverage_status": "短い手順のみ"},
    "角換わり腰掛け銀": {"source_url": "https://ja.wikipedia.org/wiki/腰掛け銀", "source_title": "Wikipedia 腰掛け銀", "coverage_status": "短い手順のみ"},
    "横歩取り": {"source_url": "https://ja.wikipedia.org/wiki/横歩取り", "source_title": "Wikipedia 横歩取り", "coverage_status": "基本局面まで"},
    "石田流": {"source_url": "https://ja.wikipedia.org/wiki/石田流", "source_title": "Wikipedia 石田流", "coverage_status": "短い手順のみ"},
    "ゴキゲン中飛車": {"source_url": "https://ja.wikipedia.org/wiki/ゴキゲン中飛車", "source_title": "Wikipedia ゴキゲン中飛車", "coverage_status": "短い手順のみ"},
    "居飛車穴熊": {"source_url": "https://ja.wikipedia.org/wiki/穴熊囲い", "source_title": "Wikipedia 穴熊囲い", "coverage_status": "短い手順のみ"},
}

def _opening_source_metadata(opening: dict) -> dict:
    metadata = dict(WIKIPEDIA_OPENING_SOURCE_DEFAULTS)
    metadata.update(WIKIPEDIA_OPENING_SOURCE_BY_NAME.get(opening["name"], {}))
    metadata.update({key: opening[key] for key in ("source_url", "source_title", "license", "source_type", "source_section", "source_license", "source_retrieved_at", "source_note", "coverage_status") if key in opening})
    return metadata

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


def find_duplicate_opening_sibling_moves(conn, line_ids=None) -> list[dict]:
    """Return duplicate USI moves that compete from the same seeded position.

    Siblings are nodes with the same direct parent (roots share NULL).  SFEN is
    deliberately not identity: transposed paths remain separate tree nodes.
    """
    params = []
    line_filter = ""
    if line_ids is not None:
        ids = sorted({int(line_id) for line_id in line_ids})
        if not ids:
            return []
        line_filter = f"WHERE olm.line_id IN ({','.join('?' for _ in ids)})"
        params.extend(ids)

    rows = conn.execute(
        f"""
        SELECT olm.line_id, ol.name AS line_name, olm.parent_move_id, olm.usi,
               COUNT(*) AS duplicate_count
        FROM opening_line_moves AS olm
        JOIN opening_lines AS ol ON ol.id = olm.line_id
        {line_filter}
        GROUP BY olm.line_id, ol.name, olm.parent_move_id, olm.usi
        HAVING COUNT(*) > 1
        ORDER BY olm.line_id, olm.parent_move_id, olm.usi
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def validate_opening_move_tree(conn, line_ids=None) -> None:
    """Validate the persisted direct-parent tree and explicit-main contract."""
    import shogi

    params = []
    where = ""
    if line_ids is not None:
        ids = sorted({int(value) for value in line_ids})
        if not ids:
            return
        where = f"WHERE line_id IN ({','.join('?' for _ in ids)})"
        params = ids
    rows = conn.execute(f"SELECT * FROM opening_line_moves {where} ORDER BY line_id, id", params).fetchall()
    line_rows = conn.execute(
        f"SELECT id, initial_sfen FROM opening_lines "
        + (f"WHERE id IN ({','.join('?' for _ in params)})" if line_ids is not None else ""),
        params,
    ).fetchall()
    initial_positions = {}
    for line in line_rows:
        initial_sfen = shogi.STARTING_SFEN if line["initial_sfen"].strip() == "startpos" else line["initial_sfen"]
        initial_positions[line["id"]] = " ".join(shogi.Board(initial_sfen).sfen().split()[:3])
    by_id = {row["id"]: row for row in rows}
    keys = set()
    siblings = {}
    for row in rows:
        key = (row["line_id"], row["move_key"])
        if not row["move_key"] or key in keys:
            raise ValueError("opening move_key must be non-empty and unique within a line")
        keys.add(key)
        seen = set()
        cursor = row
        while cursor["parent_move_id"] is not None:
            if cursor["id"] in seen:
                raise ValueError(f"opening cycle: {row['move_key']}")
            seen.add(cursor["id"])
            cursor = by_id.get(cursor["parent_move_id"])
            if cursor is None:
                break
        parent = by_id.get(row["parent_move_id"]) if row["parent_move_id"] is not None else None
        if row["parent_move_id"] is not None and parent is None:
            raise ValueError(f"invalid opening parent: {row['move_key']}")
        if parent is not None:
            if parent["line_id"] != row["line_id"]:
                raise ValueError(f"opening parent belongs to another line: {row['move_key']}")
            if row["ply"] != parent["ply"] + 1:
                raise ValueError(f"opening ply mismatch: {row['move_key']}")
            if parent["to_sfen"] != row["from_sfen"]:
                raise ValueError(f"opening parent/child SFEN mismatch: {row['move_key']}")
        else:
            if row["ply"] != 1:
                raise ValueError(f"only ply-one opening moves may be roots: {row['move_key']}")
            root_sfen = shogi.STARTING_SFEN if row["from_sfen"].strip() == "startpos" else row["from_sfen"]
            root_position = " ".join(shogi.Board(root_sfen).sfen().split()[:3])
            if root_position != initial_positions[row["line_id"]]:
                raise ValueError(f"opening root/initial SFEN mismatch: {row['move_key']}")
        from_sfen = shogi.STARTING_SFEN if row["from_sfen"].strip() == "startpos" else row["from_sfen"]
        board = shogi.Board(from_sfen)
        move = shogi.Move.from_usi(row["usi"])
        if move not in board.legal_moves:
            raise ValueError(f"illegal opening move: {row['move_key']} {row['usi']}")
        board.push(move)
        if board.sfen() != row["to_sfen"]:
            raise ValueError(f"opening generated SFEN mismatch: {row['move_key']}")
        siblings.setdefault((row["line_id"], row["parent_move_id"]), []).append(row)
    for group in siblings.values():
        if sum(int(row["is_main"]) for row in group) != 1:
            raise ValueError("each opening sibling set must contain exactly one main move")
        if len({row["sort_order"] for row in group}) != len(group):
            raise ValueError("opening sibling sort_order must be unique")
        if len({row["usi"] for row in group}) != len(group):
            raise ValueError("opening sibling USI must be unique")


def _opening_move_nodes(opening: dict) -> list[dict]:
    """Return the canonical stable-key tree for either supported seed syntax."""
    if "move_nodes" in opening:
        return [dict(node) for node in opening["move_nodes"]]

    nodes = []
    comments = opening.get("comments", [])
    for index, usi in enumerate(opening.get("moves", [])):
        nodes.append({
            "key": f"main-{index + 1}",
            "parent_key": f"main-{index}" if index else None,
            "usi": usi,
            "sort_order": 0,
            "is_main": True,
            "variation_group": "main",
            "comment": comments[index] if index < len(comments) else "",
        })
    for branch_index, branch in enumerate(opening.get("branches", []), start=1):
        from_ply = int(branch["from_ply"])
        # The pre-PR-B adapter represented a branch from the initial position
        # as a root sibling (parent_move_id=NULL), not as a child of a
        # nonexistent main-0 node.
        parent_key = None if from_ply == 0 else f"main-{from_ply}"
        for offset, usi in enumerate(branch["moves"], start=1):
            key = f"branch-{branch_index}-{offset}"
            nodes.append({
                "key": key,
                "parent_key": parent_key,
                "usi": usi,
                "sort_order": branch_index if offset == 1 else 0,
                "is_main": offset != 1,
                "variation_group": branch["name"],
                "comment": (
                    branch.get("note", f"{branch['name']} {offset}手目です。")
                    if offset == 1 else f"{branch['name']} {offset}手目です。"
                ),
            })
            parent_key = key

    # The legacy syntax did not explicitly identify a semantic continuation.
    # A following main-line move wins when present; otherwise the first
    # displayed terminal branch becomes the continuation.  Single-child
    # branch chains are handled by the same sibling-set rule.
    siblings = {}
    for node in nodes:
        siblings.setdefault(node["parent_key"], []).append(node)
    for children in siblings.values():
        if not any(child["is_main"] for child in children):
            min(children, key=lambda child: (child["sort_order"], child["key"]))["is_main"] = True
    return nodes


def _prepare_opening_move_nodes(opening: dict, initial_sfen: str) -> list[dict]:
    """Validate a seed tree and derive its DB parent, ply, and SFEN fields."""
    import shogi

    nodes = _opening_move_nodes(opening)
    by_key = {}
    for node in nodes:
        key = node.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("opening move node key must be a non-empty string")
        if key in by_key:
            raise ValueError(f"duplicate opening move node key: {key}")
        by_key[key] = node
    for node in nodes:
        parent_key = node.get("parent_key")
        if parent_key is not None and parent_key not in by_key:
            raise ValueError(f"missing opening move node parent_key: {parent_key}")

    visiting = set()
    prepared = {}

    def prepare(key):
        if key in prepared:
            return prepared[key]
        if key in visiting:
            raise ValueError(f"opening move node cycle: {key}")
        visiting.add(key)
        source = by_key[key]
        parent_key = source.get("parent_key")
        parent = prepare(parent_key) if parent_key is not None else None
        from_sfen = parent["to_sfen"] if parent else initial_sfen
        board = shogi.Board(shogi.STARTING_SFEN if from_sfen.strip() == "startpos" else from_sfen)
        try:
            move = shogi.Move.from_usi(source["usi"])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"illegal opening move node USI: {key} {source.get('usi')}") from exc
        if move not in board.legal_moves:
            raise ValueError(f"illegal opening move node USI: {key} {source['usi']}")
        board.push(move)
        result = {
            **source,
            "parent_key": parent_key,
            "ply": parent["ply"] + 1 if parent else 1,
            "from_sfen": shogi.STARTING_SFEN if from_sfen.strip() == "startpos" else from_sfen,
            "to_sfen": board.sfen(),
            "sort_order": int(source.get("sort_order", 0)),
            # Keep omission distinct from an explicit false until sibling
            # cardinality is known.  Display order must never imply semantic
            # main status for a branching stable-key seed.
            "is_main": bool(source["is_main"]) if "is_main" in source else None,
            # variation_group is the existing persisted display-label field.
            # Stable branch keys identify nodes; they must not leak into the UI
            # when the seed provides a separate human-readable label.
            "variation_group": source.get(
                "variation_group", source.get("branch_label", source.get("branch_key", "main"))
            ),
            "comment": source.get("comment", ""),
        }
        visiting.remove(key)
        prepared[key] = result
        return result

    for key in by_key:
        prepare(key)

    siblings = {}
    for node in prepared.values():
        siblings.setdefault(node["parent_key"], []).append(node)
    for children in siblings.values():
        if len({child["sort_order"] for child in children}) != len(children):
            raise ValueError("opening move node sibling sort_order must be unique")
        if len(children) == 1 and children[0]["is_main"] is None:
            children[0]["is_main"] = True
        elif len(children) > 1 and all(child["is_main"] is None for child in children):
            raise ValueError(
                "opening move node siblings are ambiguous; multiple siblings "
                "require exactly one explicit is_main=true"
            )
        if sum(child["is_main"] is True for child in children) != 1:
            raise ValueError("opening move node siblings must have exactly one is_main")
        for child in children:
            if child["is_main"] is None:
                child["is_main"] = False
        if len({child["usi"] for child in children}) != len(children):
            raise ValueError("opening move node sibling USI must be unique")

    # Parents always precede children, independent of input order.
    return sorted(prepared.values(), key=lambda node: (node["ply"], node["sort_order"], node["key"]))


def _semantic_main_nodes(nodes: list[dict]) -> list[dict]:
    children = {}
    for node in nodes:
        children.setdefault(node["parent_key"], []).append(node)
    result = []
    parent_key = None
    while parent_key in children:
        main = next(node for node in children[parent_key] if node["is_main"])
        result.append(main)
        parent_key = main["key"]
    return result


def upsert_opening_move_nodes(conn, line_id: int, move_nodes: list[dict]) -> dict[str, int]:
    """Replace one line's tree by stable key while retaining claimed row IDs.

    Callers must supply parent-before-child nodes.  Moving every existing row's
    order out of range avoids transient sibling uniqueness failures.  Obsolete
    parents are deleted only after retained children have been reparented.
    """
    existing_rows = {
        node["key"]: row
        for node in move_nodes
        if (row := conn.execute(
            "SELECT id, comment FROM opening_line_moves WHERE line_id=? AND move_key=?",
            (line_id, node["key"]),
        ).fetchone()) is not None
    }
    existing_ids = {key: int(row["id"]) for key, row in existing_rows.items()}
    claimed_ids = set(existing_ids.values())
    for node in move_nodes:
        if node["key"] in existing_ids:
            continue
        parent_id = existing_ids.get(node["parent_key"])
        if node["parent_key"] is not None and parent_id is None:
            continue
        parent_clause = "parent_move_id IS NULL" if parent_id is None else "parent_move_id=?"
        params = [line_id, node["ply"], node["variation_group"], node["sort_order"], node["usi"]]
        if parent_id is not None:
            params.append(parent_id)
        candidates = conn.execute(
            f"""SELECT id, comment FROM opening_line_moves
                WHERE line_id=? AND ply=? AND variation_group=? AND sort_order=? AND usi=?
                  AND {parent_clause} AND move_key = 'legacy-' || id ORDER BY id""",
            params,
        ).fetchall()
        candidate = next((row for row in candidates if int(row["id"]) not in claimed_ids), None)
        if candidate is not None:
            existing_ids[node["key"]] = int(candidate["id"])
            existing_rows[node["key"]] = candidate
            claimed_ids.add(int(candidate["id"]))

    conn.execute(
        "UPDATE opening_line_moves SET sort_order = -1000000000 - id WHERE line_id=?",
        (line_id,),
    )
    id_by_key = {}
    for node in move_nodes:
        parent_id = id_by_key.get(node["parent_key"])
        values = (
            node["ply"], node["usi"], node["from_sfen"], node["to_sfen"],
            (node["comment"] if "comment" in node else
             existing_rows[node["key"]]["comment"] if node["key"] in existing_rows else ""),
            node["variation_group"], parent_id,
            node["sort_order"], node["key"], int(node["is_main"]),
        )
        current_id = existing_ids.get(node["key"])
        if current_id is None:
            current_id = int(conn.execute(
                """INSERT INTO opening_line_moves
                   (line_id, ply, usi, from_sfen, to_sfen, comment, variation_group,
                    parent_move_id, sort_order, move_key, is_main)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (line_id, *values),
            ).lastrowid)
        else:
            conn.execute(
                """UPDATE opening_line_moves SET ply=?, usi=?, from_sfen=?, to_sfen=?,
                   comment=?, variation_group=?, parent_move_id=?, sort_order=?, move_key=?,
                   is_main=? WHERE id=?""",
                (*values, current_id),
            )
        id_by_key[node["key"]] = current_id

    retained = tuple(id_by_key.values())
    if retained:
        marks = ", ".join("?" for _ in retained)
        conn.execute(
            f"DELETE FROM opening_line_moves WHERE line_id=? AND id NOT IN ({marks})",
            (line_id, *retained),
        )
    else:
        conn.execute("DELETE FROM opening_line_moves WHERE line_id=?", (line_id,))
    return id_by_key


def _static_opening_seed_key(opening: dict) -> str:
    """Stable ownership identity for a bundled SAMPLE_OPENING_LINES entry."""
    return f"sample:{opening['name']}"


def static_opening_seed_key_for_name(name: str) -> str:
    """Return a seed owner only when the bundled name identifies one entry."""
    matches = [_static_opening_seed_key(item) for item in SAMPLE_OPENING_LINES if item["name"] == name]
    return matches[0] if len(matches) == 1 else ""


def seed_openings_if_empty(conn) -> None:
    import shogi

    seeded_line_ids = []
    for opening in SAMPLE_OPENING_LINES:
        seed_key = _static_opening_seed_key(opening)
        opening.setdefault("comments", [f"{opening['name']}の代表手順 {i}手目です。" for i in range(1, len(opening.get("moves", [])) + 1)])
        metadata = _opening_source_metadata(opening)
        initial_sfen = opening.get("initial_sfen", shogi.STARTING_SFEN)
        initial_sfen = shogi.STARTING_SFEN if initial_sfen.strip() == "startpos" else initial_sfen
        move_nodes = _prepare_opening_move_nodes(opening, initial_sfen)
        main_nodes = _semantic_main_nodes(move_nodes)
        main_moves = [node["usi"] for node in main_nodes]
        main_comments = [node["comment"] for node in main_nodes]
        positions, _ = _opening_snapshots(initial_sfen, main_moves)
        type_row = conn.execute(
            "SELECT id FROM opening_types WHERE name_ja = ?", (opening.get("opening_type_name", opening["name"]),)
        ).fetchone()
        type_id = type_row["id"] if type_row else None
        line_row = conn.execute(
            """
            SELECT id, line_key
            FROM opening_lines
            WHERE seed_key = ?
            ORDER BY id
            LIMIT 1
            """,
            (seed_key,),
        ).fetchone()
        if line_row is None:
            # Backfill ownership for databases created before seed_key.  A
            # unique canonical row with the old bundled name receives the
            # static alias too, making the decision persistent rather than
            # relying on name matching on every startup.
            candidates = conn.execute(
                """SELECT id, line_key FROM opening_lines
                   WHERE seed_key='' AND source_id IS NULL AND name=?
                   ORDER BY id""",
                (opening["name"],),
            ).fetchall()
            if len(candidates) == 1:
                line_row = candidates[0]
                conn.execute(
                    "UPDATE opening_lines SET seed_key=? WHERE id=?",
                    (seed_key, line_row["id"]),
                )
        # A canonical claim keeps seed_key solely as the old static ownership
        # alias.  Static seeding must neither overwrite it nor create a second
        # line under the pre-rename SAMPLE name.
        if line_row is not None and line_row["line_key"]:
            continue
        if line_row:
            line_id = int(line_row["id"])
            conn.execute(
                """
                UPDATE opening_lines
                SET opening_type_id = ?, opening_type = ?, initial_sfen = ?, moves = ?, comments = ?, tags = ?,
                    source_url = ?, source_title = ?, license = ?, source_note = ?, coverage_status = ?,
                    source_type = ?, source_section = ?, source_license = ?, source_retrieved_at = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    type_id,
                    opening["opening_type"],
                    initial_sfen,
                    json.dumps(main_moves, ensure_ascii=False),
                    json.dumps(main_comments, ensure_ascii=False),
                    json.dumps([opening["tag"]], ensure_ascii=False),
                    metadata["source_url"],
                    metadata["source_title"],
                    metadata["license"],
                    metadata["source_note"],
                    metadata["coverage_status"],
                    metadata["source_type"],
                    metadata["source_section"],
                    metadata["source_license"],
                    metadata["source_retrieved_at"],
                    line_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO opening_lines(seed_key, opening_type_id, name, opening_type, initial_sfen, moves, comments, tags,
                                          source_url, source_title, license, source_note, coverage_status,
                                          source_type, source_section, source_license, source_retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seed_key,
                    type_id,
                    opening["name"],
                    opening["opening_type"],
                    initial_sfen,
                    json.dumps(main_moves, ensure_ascii=False),
                    json.dumps(main_comments, ensure_ascii=False),
                    json.dumps([opening["tag"]], ensure_ascii=False),
                    metadata["source_url"],
                    metadata["source_title"],
                    metadata["license"],
                    metadata["source_note"],
                    metadata["coverage_status"],
                    metadata["source_type"],
                    metadata["source_section"],
                    metadata["source_license"],
                    metadata["source_retrieved_at"],
                ),
            )
            line_id = int(cur.lastrowid)
        seeded_line_ids.append(line_id)
        for ply, sfen in enumerate(positions):
            position_row = conn.execute(
                "SELECT id FROM opening_positions WHERE line_id = ? AND ply = ?",
                (line_id, ply),
            ).fetchone()
            if position_row:
                conn.execute(
                    "UPDATE opening_positions SET sfen = ? WHERE id = ?",
                    (sfen, position_row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO opening_positions(line_id, ply, sfen) VALUES (?, ?, ?)",
                    (line_id, ply, sfen),
                )
        conn.execute(
            "DELETE FROM opening_positions WHERE line_id = ? AND ply >= ?",
            (line_id, len(positions)),
        )

        upsert_opening_move_nodes(conn, line_id, move_nodes)

        tag_row = conn.execute(
            "SELECT id FROM opening_tags WHERE line_id = ? AND tag = ?",
            (line_id, opening["tag"]),
        ).fetchone()
        if tag_row:
            conn.execute(
                "UPDATE opening_tags SET score = ?, reason = ? WHERE id = ?",
                (1.0, opening["description"], tag_row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO opening_tags(line_id, tag, score, reason) VALUES (?, ?, ?, ?)",
                (line_id, opening["tag"], 1.0, opening["description"]),
            )

    duplicates = find_duplicate_opening_sibling_moves(conn, seeded_line_ids)
    if duplicates:
        details = ", ".join(
            f"{row['line_name']}: {row['usi']} ({row['duplicate_count']} nodes)"
            for row in duplicates
        )
        raise ValueError(f"サンプル定跡に同一 sibling USI の重複があります: {details}")
    validate_opening_move_tree(conn, seeded_line_ids)


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
