"""雲端 Vision 表頭辨識：型號／批號／作業人員。"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx

from .field_parsers import HeaderFields, normalize_lot, normalize_model, normalize_operators
from .preprocess import to_jpeg_bytes


HEADER_PROMPT = """你是工廠表單辨識助手。請只讀這張「外觀檢驗暨首件檢查表」的表頭三欄。

請只輸出 JSON：
{
  "model_no": "型號，格式常為 XX-XXXXX-XXX，例如 91-28190-00C",
  "lot_no": "批號原文，格式常為 YY-MM-序號，例如 26-07-341",
  "operator": "作業人員工號，通常是 5 碼數字；若有兩個用 / 分隔",
  "warnings": []
}

規則：
1. 仔細辨識手寫藍/黑筆。
2. 作業人員只要 5 碼工號（例如 10672-10 取 10672）。
3. 看不清就給最佳估計，並在 warnings 說明。
4. 不要輸出 markdown。
"""


class VisionHeaderOCR:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip(
            "/"
        )
        self.model = os.getenv("OCR_VISION_MODEL", "gpt-4o-mini")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def status(self) -> dict[str, str]:
        return {
            "enabled": "yes" if self.enabled else "no",
            "model": self.model if self.enabled else "",
            "base_url": self.base_url if self.enabled else "",
        }

    def recognize(self, image_path: str | Path) -> tuple[HeaderFields, list[str]]:
        if not self.api_key:
            fields = HeaderFields(
                warnings=["未設定 OPENAI_API_KEY，無法使用 Vision。"]
            )
            return fields, []

        image_path = Path(image_path)
        image_b64 = base64.b64encode(to_jpeg_bytes(image_path, max_side=1800)).decode(
            "ascii"
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": HEADER_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "請辨識型號、批號、作業人員。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                    ],
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return _to_fields(data), [json.dumps(data, ensure_ascii=False)]


def _to_fields(data: dict) -> HeaderFields:
    model_raw = str(data.get("model_no", "") or "")
    lot_raw = str(data.get("lot_no", "") or "")
    op_raw = str(data.get("operator", "") or "")
    warnings = [str(w) for w in data.get("warnings", []) or []]

    model = normalize_model(model_raw) or model_raw.strip().upper()
    pretty, normalized = normalize_lot(lot_raw)
    ops = normalize_operators(op_raw)
    if not ops and op_raw.strip():
        # Vision 可能回傳 10672-10，再清一次
        ops = normalize_operators(op_raw.replace("-", " "))

    fields = HeaderFields(
        model_no=model,
        model_raw=model_raw,
        lot_no=pretty or lot_raw,
        lot_raw=lot_raw,
        lot_normalized=normalized,
        operators=ops,
        operator_raw=op_raw,
        warnings=warnings,
    )
    if not fields.model_no:
        fields.warnings.append("型號未辨識到")
    if not fields.lot_normalized:
        fields.warnings.append("批號未正規化成功")
    if not fields.operators:
        fields.warnings.append("作業人員未辨識到 5 碼")
    return fields
