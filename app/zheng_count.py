"""正字畫（正字計數）工具。

工廠常見畫法：
  一 = 1
  丅 / 丁形兩筆 = 2
  下形三筆 = 3
  未完成正字四筆 = 4
  正 = 5
  正正一 = 11
"""

from __future__ import annotations

import re


# 常見不完整正字筆畫近似寫法
_STROKE_CHARS = {
    "一": 1,
    "丨": 1,
    "/": 1,
    "\\": 1,
    "丁": 2,
    "丅": 2,
    "亠": 2,
    "下": 3,
    "止": 4,
    "正": 5,
}


def count_zheng_marks(text: str) -> tuple[int, float, str]:
    """從文字描述或 OCR 結果估算正字畫數量。

    Returns:
        (count, confidence, normalized_raw)
    """
    if not text:
        return 0, 0.9, ""

    cleaned = text.strip().replace(" ", "").replace("　", "")
    if not cleaned or cleaned in {"0", "無", "无", "-", "—", "×", "x", "X"}:
        return 0, 0.95, cleaned

    # 純數字直接採用
    if re.fullmatch(r"\d+", cleaned):
        return int(cleaned), 0.98, cleaned

    # 例如「正正一」「正x2 + 3」
    total = 0
    matched_any = False
    for ch in cleaned:
        if ch in _STROKE_CHARS:
            total += _STROKE_CHARS[ch]
            matched_any = True
        elif ch.isdigit():
            # 忽略混雜數字，留給下方正則
            pass

    # 「正x3」「3個正」「正*2」
    m = re.search(r"(?:正\s*[xX×*]\s*|(\d+)\s*個?\s*正|[xX×*]\s*)(\d+)?", cleaned)
    if "正" in cleaned:
        zheng_count = cleaned.count("正")
        remainder = cleaned.replace("正", "")
        rem_total = 0
        for ch in remainder:
            if ch in _STROKE_CHARS and ch != "正":
                rem_total += _STROKE_CHARS[ch]
        # 若 remainder 是純數字且沒有其他筆畫字，視為額外筆畫
        if re.fullmatch(r"\d+", remainder):
            rem_total = int(remainder)
        total = zheng_count * 5 + rem_total
        matched_any = True
        conf = 0.85 if rem_total or zheng_count else 0.7
        return total, conf, cleaned

    if matched_any:
        return total, 0.8, cleaned

    # 抓不到結構時回傳 0，並降低信心，交由人工審核
    return 0, 0.2, cleaned


def strokes_to_zheng_display(count: int) -> str:
    """把數量轉回正字畫顯示字串，方便審核畫面對照。"""
    if count <= 0:
        return ""
    full, rem = divmod(count, 5)
    parts = ["正"] * full
    rem_map = {1: "一", 2: "丁", 3: "下", 4: "止"}
    if rem:
        parts.append(rem_map[rem])
    return "".join(parts)
