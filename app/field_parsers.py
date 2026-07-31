"""表頭欄位解析與正規化。

型號：XX-XXXXX-XXX（例 91-28190-00C）
批號：YY-MM-NNN → 20YYMM + 序號補滿 5 碼（例 26-07-341 → 20260700341）
作業人員：固定 5 碼數字（可多位，以 / 分隔）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


MODEL_RE = re.compile(r"\b(\d{2}-\d{5}-[0-9A-Za-z]{3})\b", re.IGNORECASE)
# OCR 常把 0 認成 O
MODEL_FUZZY_RE = re.compile(r"\b([0-9O]{2}-[0-9O]{5}-[0-9A-ZO]{3})\b", re.IGNORECASE)
LOT_RE = re.compile(r"\b(\d{2})[-_/.．](\d{1,2})[-_/.．](\d{1,5})\b")

OPERATOR_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")


@dataclass
class HeaderFields:
    model_no: str = ""
    model_raw: str = ""
    lot_no: str = ""
    lot_raw: str = ""
    lot_normalized: str = ""
    operators: list[str] = field(default_factory=list)
    operator_raw: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def operator(self) -> str:
        return " / ".join(self.operators)


def normalize_lot(raw: str) -> tuple[str, str]:
    """回傳 (原始批號, 正規化批號)。失敗時正規化為空字串。"""
    text = (raw or "").strip().replace(" ", "")
    m = LOT_RE.search(text)
    if not m:
        return text, ""
    yy, mm, seq = m.group(1), m.group(2), m.group(3)
    month = int(mm)
    if month < 1 or month > 12:
        return f"{yy}-{mm}-{seq}", ""
    normalized = f"20{yy}{month:02d}{int(seq):05d}"
    pretty = f"{yy}-{month:02d}-{seq}"
    return pretty, normalized


def normalize_model(raw: str) -> str:
    text = (raw or "").strip().upper().replace(" ", "")
    text = text.replace("—", "-").replace("–", "-").replace("_", "-")
    m = MODEL_RE.search(text) or MODEL_FUZZY_RE.search(text)
    if not m:
        return ""
    fixed = _fix_model_ocr_confusions(m.group(1).upper())
    return fixed if fixed and MODEL_RE.fullmatch(fixed) else ""


def _fix_model_ocr_confusions(code: str) -> str:
    """修正型號常見 OCR 混淆（O↔0）。前兩段必為數字。"""
    parts = code.split("-")
    if len(parts) != 3:
        return code
    a = parts[0].replace("O", "0")
    b = parts[1].replace("O", "0")
    c = parts[2]
    # 第三段若混有數字，O 多半是 0（例 0OC → 00C）
    if any(ch.isdigit() for ch in c):
        c = "".join("0" if ch == "O" else ch for ch in c)
    fixed = f"{a}-{b}-{c}"
    return fixed if MODEL_RE.fullmatch(fixed) else ""


def normalize_operators(raw: str) -> list[str]:
    text = (raw or "").strip()
    found = OPERATOR_RE.findall(text)
    # 去重但保序
    seen: set[str] = set()
    out: list[str] = []
    for code in found:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def parse_header_from_texts(texts: list[str]) -> HeaderFields:
    """從 OCR 文字列中抓型號／批號／作業人員。"""
    result = HeaderFields()
    joined = "\n".join(texts)

    # 先依標籤附近取值
    labeled = _extract_by_labels(joined)
    model_src = labeled.get("model") or joined
    lot_src = labeled.get("lot") or joined
    op_src = labeled.get("operator") or joined

    result.model_raw = labeled.get("model", "")
    result.lot_raw = labeled.get("lot", "")
    result.operator_raw = labeled.get("operator", "")

    result.model_no = normalize_model(model_src)
    if not result.model_no:
        result.model_no = normalize_model(joined)
    if not result.model_no:
        result.warnings.append("找不到符合 XX-XXXXX-XXX 的型號")

    pretty, normalized = normalize_lot(lot_src)
    if not normalized:
        pretty, normalized = normalize_lot(joined)
    result.lot_normalized = normalized
    result.lot_no = pretty if normalized else ""
    if not normalized:
        result.warnings.append("找不到或無法正規化批號（期待 YY-MM-序號）")

    # 避免把型號中段五碼（如 28190）誤當工號
    scrubbed_joined = joined
    scrubbed_op = op_src
    if result.model_no:
        scrubbed_joined = scrubbed_joined.replace(result.model_no, " ")
        scrubbed_joined = re.sub(
            re.escape(result.model_no).replace(r"\-", r"[-‐−]"), " ", scrubbed_joined
        )
        scrubbed_op = scrubbed_op.replace(result.model_no, " ")
    # 也清掉未修正前的模糊型號
    scrubbed_joined = MODEL_FUZZY_RE.sub(" ", scrubbed_joined)
    scrubbed_op = MODEL_FUZZY_RE.sub(" ", scrubbed_op)

    if labeled.get("operator"):
        ops = normalize_operators(scrubbed_op)
    else:
        ops = normalize_operators(scrubbed_joined)
    if not ops and labeled.get("operator"):
        ops = normalize_operators(scrubbed_joined)
    result.operators = ops
    if not ops:
        result.warnings.append("找不到 5 碼作業人員工號")

    return result


def _extract_by_labels(text: str) -> dict[str, str]:
    """粗抓『型號／批號／作業人員』後方文字。"""
    out: dict[str, str] = {}
    patterns = {
        "model": r"(?:型號|型号|Model\s*No\.?|Model)[:：\s]*([^\n批作業確]{3,40})",
        "lot": r"(?:批號|批号|Lot\s*No\.?|Lot)[:：\s]*([^\n型作確]{3,30})",
        "operator": r"(?:作業人員|作业人员|作業员|Operator|人員)[:：\s]*([^\n型批確核]{3,40})",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            out[key] = m.group(1).strip(" ：:|-")
    return out
