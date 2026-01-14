# SingKANA β 用 かな変換エンジン
# EN（英語）/ KR（韓国語）対応 + かなスペース区切り
# + 英語フェイク発音 + 日本語かな行もスペース区切り

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any, Dict, List

# ===== ログ設定 ======================================================

LOG_DIR = Path("Logs")
LOG_DIR.mkdir(exist_ok=True)

CONVERT_LOG = LOG_DIR / "convert.log"
FEEDBACK_LOG = LOG_DIR / "feedback.log"


def _safe_log(path: Path, message: str) -> None:
    """ログ周りで失敗してもサービス自体は落とさない用のユーティリティ。"""
    ts = dt.datetime.now().isoformat(timespec="seconds")
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        # ログ周りで例外が出ても握りつぶす
        pass


# ===== 例外クラス ====================================================


class SingKanaError(Exception):
    """シンカナ専用の業務エラー。app_web.py 側でハンドリングする想定。"""

    pass


# ===== 入力正規化 ====================================================

_ASCII_LINE = re.compile(r"^[A-Za-z0-9\s.,!?\"'()\-:/]+$")
_ASCII_CHARS = re.compile(r"[A-Za-z]")

def _normalize_input(*args: Any, **kwargs: Any) -> str:
    """
    convert_lyrics に渡された引数から歌詞テキストだけを取り出して整形する。
    - 第1引数を最優先
    - なければ kwargs["lyrics"]
    """
    if args:
        text = args[0]
    else:
        text = kwargs.get("lyrics", "")

    if not isinstance(text, str):
        text = str(text or "")

    # 改行系を統一
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _is_english_like(line: str) -> bool:
    """
    「ほぼ英語だけ」の行かどうかをざっくり判定。
    記号・数字・スペースは許容。
    """
    stripped = line.strip()
    if not stripped:
        return False
    return bool(_ASCII_LINE.fullmatch(stripped))


def _contains_korean(line: str) -> bool:
    """行の中にハングルが含まれているかどうか。"""
    return any("\uac00" <= ch <= "\ud7a3" for ch in line)


# ===== ローマ字 → ひらがな変換テーブル ===============================

ROMA_TABLE: Dict[str, str] = {
    # 3文字コンビ
    "kya": "きゃ", "kyu": "きゅ", "kyo": "きょ",
    "gya": "ぎゃ", "gyu": "ぎゅ", "gyo": "ぎょ",
    "sha": "しゃ", "shu": "しゅ", "sho": "しょ",
    "sya": "しゃ", "syu": "しゅ", "syo": "しょ",
    "ja": "じゃ", "ju": "じゅ", "jo": "じょ",
    "jya": "じゃ", "jyu": "じゅ", "jyo": "じょ",
    "cha": "ちゃ", "chu": "ちゅ", "cho": "ちょ",
    "tya": "ちゃ", "tyu": "ちゅ", "tyo": "ちょ",
    "nya": "にゃ", "nyu": "にゅ", "nyo": "にょ",
    "hya": "ひゃ", "hyu": "ひゅ", "hyo": "ひょ",
    "mya": "みゃ", "myu": "みゅ", "myo": "みょ",
    "rya": "りゃ", "ryu": "りゅ", "ryo": "りょ",
    "bya": "びゃ", "byu": "びゅ", "byo": "びょ",
    "pya": "ぴゃ", "pyu": "ぴゅ", "pyo": "ぴょ",
    "fya": "ふゃ", "fyu": "ふゅ", "fyo": "ふょ",

    # 2文字（子音 + 母音）
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "sa": "さ", "shi": "し", "si": "し", "su": "す", "se": "せ", "so": "そ",
    "za": "ざ", "ji": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "ta": "た", "chi": "ち", "ti": "ち", "tu": "つ", "tsu": "つ",
    "te": "て", "to": "と",
    "da": "だ", "di": "ぢ", "du": "づ", "de": "で", "do": "ど",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "hu": "ふ", "fu": "ふ", "he": "へ", "ho": "ほ",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "wa": "わ", "wo": "を",
    "la": "ら", "li": "り", "lu": "る", "le": "れ", "lo": "ろ",

    # 母音単体
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
}

# 子音単体は「子音 + う」っぽく扱う
SINGLE_CONSONANT: Dict[str, str] = {
    "b": "ぶ", "c": "く", "d": "ど", "f": "ふ", "g": "ぐ", "h": "は",
    "j": "じ", "k": "く", "l": "る", "m": "む", "n": "ん", "p": "ぷ",
    "q": "く", "r": "る", "s": "す", "t": "と", "v": "ゔ", "w": "う",
    "x": "くす", "y": "い", "z": "ず",
}

_WORD_OR_OTHER = re.compile(r"[A-Za-z]+|[^A-Za-z]+")

# 単語ごとの読み上書き（必要に応じて増やす）
# 歌いやすさを最優先にした「歌えるカタカナ」への変換
WORD_OVERRIDE: Dict[str, str] = {
    # 頻出語（母音を伸ばす）
    "me": "みー",
    "you": "ゆー",
    "we": "うぃー",
    "be": "びー",
    "see": "しー",
    "free": "ふりー",
    "feel": "ふぃーる",
    "real": "りーる",
    "deal": "でぃーる",
    "heal": "ひーる",
    "steal": "すてぃーる",
    "seal": "しーる",
    
    # 歌詞でよく伸ばされる語
    "ghost": "ごーすと",
    "alone": "あろーん",
    "throne": "すろーん",
    "believe": "びりーぶ",
    "leave": "りーぶ",
    "dream": "どりーむ",
    "scream": "すくりーむ",
    "stream": "すとりーむ",
    "team": "てぃーむ",
    "seem": "しーむ",
    "theme": "てぃーむ",
    
    # 感嘆詞・間投詞
    "hah": "はっ",
    "yeah": "いぇあ",
    "oh": "おー",
    "ah": "あー",
    "eh": "えー",
    "uh": "あー",
    "hey": "へい",
    "hi": "はい",
    
    # よく使われる動詞・名詞
    "love": "らぶ",
    "live": "りぶ",
    "life": "らいふ",
    "light": "らいと",
    "night": "ないと",
    "right": "らいと",
    "fight": "ふぁいと",
    "might": "まいと",
    "sight": "さいと",
    "bright": "ぶらいと",
    "flight": "ふらいと",
    
    # -tion 語尾（歌詞では -しょん が自然）
    "action": "あくしょん",
    "emotion": "いもーしょん",
    "motion": "もーしょん",
    "notion": "のーしょん",
    "passion": "ぱっしょん",
    "fashion": "ふぁっしょん",
    "nation": "ねーしょん",
    "station": "すてーしょん",
    "creation": "くりえーしょん",
    "relation": "りれーしょん",
    
    # -sion 語尾
    "vision": "びじょん",
    "mission": "みっしょん",
    "passion": "ぱっしょん",
    "session": "せっしょん",
    "version": "ばーじょん",
}


def _roman_to_hiragana(word: str) -> str:
    """
    英単語をなんちゃって日本語読みのひらがなに変換する。
    - 大文字小文字は無視
    - アルファベット以外はそのまま返す
    """
    core = re.sub(r"[^A-Za-z]", "", word)
    if not core:
        return word

    w = core.lower()
    result: List[str] = []
    i = 0

    while i < len(w):
        # 3文字コンビ優先
        chunk = None
        for size in (3, 2):
            if i + size <= len(w):
                cand = w[i : i + size]
                if cand in ROMA_TABLE:
                    chunk = ROMA_TABLE[cand]
                    i += size
                    break
        if chunk is not None:
            result.append(chunk)
            continue

        ch = w[i]

        # 促音っぽい重子音（例: happy の pp）
        if i + 1 < len(w) and w[i] == w[i + 1] and w[i] not in "aeiou":
            result.append("っ")
            i += 1
            continue

        # 母音単体
        if ch in "aeiou":
            result.append(ROMA_TABLE[ch])
        else:
            # 子音だけなら適当な母音をくっ付ける
            result.append(SINGLE_CONSONANT.get(ch, ch))

        i += 1

    return "".join(result)


# かなにスペースを挿入するレイヤー
def _kana_with_spaces(text: str) -> str:
    """
    かな文字を 1 文字ずつ区切ってスペースを入れる。
    記号やスペースはそのまま維持する。
    """
    result_chars: List[str] = []
    prev_kana = False

    for ch in text:
        # ひらがな or カタカナ or 長音記号なら「かな」
        is_kana = ("ぁ" <= ch <= "ゟ") or ("゠" <= ch <= "ヿ") or (ch == "ー")

        if is_kana:
            if prev_kana:
                result_chars.append(" ")
            result_chars.append(ch)
        else:
            # 記号・スペースなどはそのまま
            result_chars.append(ch)

        prev_kana = is_kana

    return "".join(result_chars)


# 英語の“フェイク発音”をローマ字的に反映するレイヤー
def _apply_english_phoneme_rules(line: str) -> str:
    """
    want you → wanchu, got you → gotchu など、
    よくある英語歌詞の発音崩しを事前にローマ字へ寄せる。
    """
    text = line

    rules = [
        # 頻出のフェイク発音パターン
        (r"\bwant you\b", "wanchu"),
        (r"\bwanna\b", "wana"),
        (r"\bgonna\b", "gona"),
        (r"\bgot you\b", "gotchu"),
        (r"\bget you\b", "getchu"),
        (r"\bdon't you\b", "donchu"),
        (r"\bdid you\b", "didju"),
        (r"\bwould you\b", "wudju"),
        (r"\bcould you\b", "cudju"),
        (r"\bshould you\b", "shudju"),
        (r"\bgotta\b", "gota"),
        (r"\bkinda\b", "kinda"),
        (r"\blemme\b", "lemmi"),
        (r"\bgimme\b", "gimmi"),
        (r"\boutta\b", "outa"),
        (r"\bain't\b", "aint"),
        (r"\bwhat you\b", "wachu"),
        (r"\bthat you\b", "thatchu"),
        (r"\bwhen you\b", "wenchu"),
        (r"\bwhere you\b", "wherechu"),
        (r"\bhow you\b", "howchu"),
        (r"\bwhy you\b", "whychu"),
        (r"\bwho you\b", "whochu"),
        (r"\bcan't you\b", "canchu"),
        (r"\bwon't you\b", "wonchu"),
        (r"\bmust you\b", "mustchu"),
        (r"\bmight you\b", "mightchu"),
        (r"\bmay you\b", "maychu"),
        (r"\bshall you\b", "shallchu"),
        (r"\blet me\b", "lemmi"),
        (r"\blet's\b", "lets"),
        (r"\b'cause\b", "cuz"),
        (r"\bcause\b", "cuz"),
        (r"\b'em\b", "em"),
        (r"\b'round\b", "round"),
        (r"\b'fore\b", "fore"),
        (r"\b'gainst\b", "gainst"),
        (r"\b'neath\b", "neath"),
        (r"\b'cross\b", "cross"),
        (r"\b'long\b", "long"),
        (r"\b'way\b", "way"),
        (r"\b'round\b", "round"),
        (r"\b'cause\b", "cuz"),
        (r"\b'em\b", "em"),
        (r"\b'cause\b", "cuz"),
        (r"\b'em\b", "em"),
    ]

    for pattern, repl in rules:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # 語尾 -ing → -in（singing → singin）
    text = re.sub(r"([A-Za-z]+)ing\b", r"\1in", text, flags=re.IGNORECASE)
    
    # 語尾 -tion → -shon（歌詞では -しょん が自然）
    text = re.sub(r"([A-Za-z]+)tion\b", r"\1shon", text, flags=re.IGNORECASE)
    
    # 語尾 -sion → -shon（歌詞では -しょん が自然）
    text = re.sub(r"([A-Za-z]+)sion\b", r"\1shon", text, flags=re.IGNORECASE)
    
    # 語尾 -ed → -d（過去形の -ed を簡略化）
    text = re.sub(r"([A-Za-z]+)ed\b", r"\1d", text, flags=re.IGNORECASE)
    
    # 語尾 -er → -a（比較級の -er を簡略化、歌詞では -a が自然）
    text = re.sub(r"([A-Za-z]+)er\b", r"\1a", text, flags=re.IGNORECASE)

    return text


def _english_to_kana_line(line: str) -> str:
    """
    1行分の英語テキストを、単語ごとにかな変換する。
    アルファベット連続部分だけを対象にし、それ以外はそのまま。
    最終的なかなは「1文字ごとにスペース区切り」に整形する。
    """
    # ① フェイク発音ルール適用
    line = _apply_english_phoneme_rules(line)

    pieces: List[str] = []
    for token in _WORD_OR_OTHER.findall(line):
        if re.fullmatch(r"[A-Za-z]+", token):
            lower = token.lower()
            if lower in WORD_OVERRIDE:
                pieces.append(WORD_OVERRIDE[lower])
            else:
                pieces.append(_roman_to_hiragana(token))
        else:
            pieces.append(token)

    joined = "".join(pieces)
    return _kana_with_spaces(joined)


def _english_to_kana_line_standard(line: str) -> str:
    """
    Standard変換（最適化なし）: 一般的なカタカナ寄せ。
    フェイク発音ルール、WORD_OVERRIDE、語尾ルールを一切使わない。
    単純にローマ字→ひらがな変換のみ。
    """
    # 最適化を一切通さない（フェイク発音ルールなし、WORD_OVERRIDEなし、語尾ルールなし）
    pieces: List[str] = []
    for token in _WORD_OR_OTHER.findall(line):
        if re.fullmatch(r"[A-Za-z]+", token):
            # WORD_OVERRIDEを使わず、直接_roman_to_hiraganaを呼ぶ
            pieces.append(_roman_to_hiragana(token))
        else:
            pieces.append(token)

    joined = "".join(pieces)
    return _kana_with_spaces(joined)


# ===== 韓国語 → かな =================================================

_CHO = [
    "g", "kk", "n", "d", "tt", "r", "m", "b", "pp",
    "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h",
]

_JUNG = [
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye",
    "o", "wa", "wae", "oe", "yo",
    "u", "weo", "we", "wi", "yu",
    "eu", "ui", "i",
]

_JONG = [
    "", "g", "kk", "gs", "n", "nj", "nh", "d",
    "l", "lg", "lm", "lb", "ls", "lt", "lp", "lh",
    "m", "b", "bs", "s", "ss", "ng", "j", "ch", "k", "t", "p", "h",
]


def _hangul_to_roman(ch: str) -> str:
    """1文字のハングル音節をローマ字（簡易）に変換する。"""
    code = ord(ch)
    if not ("\uac00" <= ch <= "\ud7a3"):
        return ch

    sindex = code - 0xAC00
    cho = sindex // 588
    jung = (sindex % 588) // 28
    jong = sindex % 28

    lead = _CHO[cho]
    vowel = _JUNG[jung]
    tail = _JONG[jong]

    return lead + vowel + tail


def _korean_to_kana_line(line: str) -> str:
    """
    ハングルを なんちゃって日本語かな に変換する。
    1文字ずつローマ字化 → _roman_to_hiragana → スペース区切り。
    """
    pieces: List[str] = []

    for ch in line:
        if "\uac00" <= ch <= "\ud7a3":
            roman = _hangul_to_roman(ch)
            kana = _roman_to_hiragana(roman)
            pieces.append(kana)
        else:
            pieces.append(ch)

    joined = "".join(pieces)
    return _kana_with_spaces(joined)


# ===== メイン変換ロジック ================================================

def convert_lyrics(*args: Any, **kwargs: Any) -> List[Dict[str, str]]:
    """
    歌詞テキストを EN / KA ペアの配列に変換して返す。

    戻り値の形:
        [{"en": "...", "kana": "..."}, ...]
    """

    # 1) 入力正規化（改行統一など）
    text = _normalize_input(*args, **kwargs)

    lines: List[Dict[str, str]] = []

    for raw in text.split("\n"):
        en_src = raw.rstrip("\r")
        # 完全な空行はスキップ
        if not en_src.strip():
            continue

        # 2) 行の中に英字が1文字でもあれば、
        #    その部分だけ _english_to_kana_line でかな変換する。
        #
        #    - 例: "어두워진, hah, 앞길 속에 (ah)"
        #      → ハングル部分はそのまま / "hah", "ah" だけかな変換
        #
        #    - 例: "サビ higher のところ"
        #      → "higher" だけかな変換、他はそのまま
        if _ASCII_CHARS.search(en_src):
            kana = _english_to_kana_line(en_src)
        else:
            # 英字が含まれない行（日本語だけ / ハングルだけなど）は
            # そのまま見せる
            kana = en_src

        lines.append({"en": en_src, "kana": kana})

    _safe_log(CONVERT_LOG, f"convert_lyrics ok: lines={len(lines)}")
    return lines


def convert_lyrics_with_comparison(*args: Any, **kwargs: Any) -> List[Dict[str, str]]:
    """
    歌詞テキストを EN / STANDARD / SINGKANA の3つを返す。
    上下比較UI用。

    戻り値の形:
        [{"en": "...", "standard": "...", "singkana": "..."}, ...]
    """

    # 1) 入力正規化（改行統一など）
    text = _normalize_input(*args, **kwargs)

    lines: List[Dict[str, str]] = []

    for raw in text.split("\n"):
        en_src = raw.rstrip("\r")
        # 完全な空行はスキップ
        if not en_src.strip():
            continue

        # 2) 行の中に英字が1文字でもあれば、両方の変換を実行
        if _ASCII_CHARS.search(en_src):
            standard = _english_to_kana_line_standard(en_src)
            singkana = _english_to_kana_line(en_src)
        else:
            # 英字が含まれない行（日本語だけ / ハングルだけなど）は
            # そのまま見せる
            standard = en_src
            singkana = en_src

        lines.append({"en": en_src, "standard": standard, "singkana": singkana})

    _safe_log(CONVERT_LOG, f"convert_lyrics_with_comparison ok: lines={len(lines)}")
    return lines


# ===== フィードバック保存 ============================================


def save_feedback(text: str) -> None:
    """フロントから送られてきたフィードバックをログに追記するだけ。"""
    text = (text or "").strip()
    if not text:
        return
    _safe_log(FEEDBACK_LOG, f"feedback: {text!r}")


# ===== 初期化フック ===================================================


def init_engine() -> None:
    """
    将来、本物のモデルや外部 API を初期化するためのフック。
    現状はログに一行書く だけの no-op。
    """
    _safe_log(CONVERT_LOG, "init_engine called (stub)")
