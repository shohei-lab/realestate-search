"""住所文字列の正規化ユーティリティ（純関数のみ）。

国土地理院ジオコーダ等の検索キーとして安定する形に整える:
- NFKC 正規化（全角英数字・記号 → 半角、ｶﾀｶﾅ → カタカナ）
- 漢数字（一〜九十九）→ アラビア数字
- 都道府県・「東京都」の補完（東京23区前提）
- 余分な空白の除去
- 「1丁目2番3号」「1-2-3」「1丁目2-3」などの軽微なゆれ吸収
"""

from __future__ import annotations

import re
import unicodedata

# ───────── 漢数字変換 ─────────

_KANJI_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                 "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_UNITS = {"十": 10, "百": 100, "千": 1000}


def _kanji_to_int(s: str) -> int | None:
    """簡易漢数字パーサ。九千九百九十九 まで対応。失敗時は None。"""
    if not s:
        return None
    total = 0
    current = 0
    for ch in s:
        if ch in _KANJI_DIGITS:
            current = _KANJI_DIGITS[ch]
        elif ch in _KANJI_UNITS:
            unit = _KANJI_UNITS[ch]
            total += (current or 1) * unit
            current = 0
        else:
            return None
    return total + current


_KANJI_NUM_PATTERN = re.compile(r"[〇零一二三四五六七八九十百千]+")


def kanji_numbers_to_arabic(s: str) -> str:
    """住所中の漢数字をアラビア数字に変換。

    丁目/番地以外の漢字（例: 大手町、千代田）は壊さないよう、
    マッチした塊が `_kanji_to_int` でパース可能な場合のみ変換する。
    """

    def _replace(m: re.Match[str]) -> str:
        token = m.group(0)
        # 単一の「千」「百」「十」だけでも文字列上は変換しないほうが安全
        # （地名: 千代田・百人町・十条 などを壊さない）
        if token in {"千", "百", "十", "〇", "零"}:
            return token
        # 純粋な単漢字（一〜九）は曖昧なので変換しない
        # （地名: 一橋・二子・三河島 等を壊さない）
        if len(token) == 1 and token in _KANJI_DIGITS:
            return token
        n = _kanji_to_int(token)
        if n is None:
            return token
        return str(n)

    return _KANJI_NUM_PATTERN.sub(_replace, s)


# ───────── 主処理 ─────────

_PREF_RE = re.compile(r"^(東京都|.{2,3}[都道府県])")
_WS_RE = re.compile(r"\s+")
_HYPHEN_FAMILY = "‐-‒–—―ー－"
_HYPHEN_TRANS = str.maketrans({c: "-" for c in _HYPHEN_FAMILY})


def normalize_address(raw: str, *, default_pref: str | None = "東京都") -> str:
    """住所文字列をジオコーダ向けに正規化する。

    Args:
        raw: 入力住所
        default_pref: 都道府県が含まれていないときに先頭に補う値。
            None を渡すと補完しない。

    Returns:
        正規化済み住所
    """
    if not raw:
        return ""

    s = unicodedata.normalize("NFKC", raw)
    s = s.translate(_HYPHEN_TRANS)
    s = _WS_RE.sub("", s)
    s = kanji_numbers_to_arabic(s)

    if default_pref and not _PREF_RE.match(s):
        s = default_pref + s

    return s


def parse_chome_banchi(addr: str) -> tuple[str, int | None, int | None, int | None]:
    """正規化済み住所から「町名」と「丁目・番・号」を抽出する。

    例:
        "東京都渋谷区代々木1-2-3" → ("東京都渋谷区代々木", 1, 2, 3)
        "東京都渋谷区代々木1丁目2-3" → ("東京都渋谷区代々木", 1, 2, 3)
        "東京都渋谷区代々木1丁目2番3号" → ("東京都渋谷区代々木", 1, 2, 3)

    抽出に失敗した部分は None を返す。
    """
    if not addr:
        return ("", None, None, None)

    s = addr

    # 1. 「N丁目M番L号」「N丁目M-L」を「N-M-L」に正規化
    m = re.search(r"(\d+)丁目(\d+)(?:番|-)?(\d+)?(?:号)?$", s)
    if m:
        chome = int(m.group(1))
        ban = int(m.group(2))
        gou = int(m.group(3)) if m.group(3) else None
        town = s[: m.start()]
        return (town, chome, ban, gou)

    # 2. 「N-M-L」「N-M」「N」末尾
    m = re.search(r"(\d+)(?:-(\d+))?(?:-(\d+))?$", s)
    if m:
        chome = int(m.group(1))
        ban = int(m.group(2)) if m.group(2) else None
        gou = int(m.group(3)) if m.group(3) else None
        town = s[: m.start()]
        return (town, chome, ban, gou)

    return (s, None, None, None)
