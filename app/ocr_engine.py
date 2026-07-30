"""表單辨識引擎。

優先使用多模態 Vision LLM（對潦草字與正字畫較穩），
若無 API Key 則走規則/示範模式，方便本機先串 Excel 流程。
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from .preprocess import preprocess, to_jpeg_bytes
from .schema import DefectCount, FormReadResult, FormSchema, empty_result
from .zheng_count import count_zheng_marks


SYSTEM_PROMPT = """你是工廠品管表單辨識助手。
使用者會上傳一張「不良記錄表」照片。表單通常包含：
- 製令、品號、作業人員、日期、班別
- 多個不良項目欄位，作業員用「正字畫」打勾計數（正=5，未完成正字為1~4筆）

請只輸出 JSON，不要 markdown。格式：
{
  "work_order": "...",
  "product_no": "...",
  "operator": "...",
  "date": "YYYY-MM-DD 或原樣文字",
  "shift": "...",
  "defects": [
    {"key": "scratch", "label": "刮傷", "count": 0, "raw_mark": "正一", "confidence": 0.0, "note": ""}
  ],
  "warnings": ["辨識不確定之處"]
}

規則：
1. defects 必須涵蓋提供的不良項目清單，沒畫就 count=0。
2. 正字畫要換算成數字：正=5，兩個正=10，正一=6，依此類推。
3. 字跡模糊時仍給最佳估計，但 confidence 調低，並在 warnings 說明。
4. confidence 介於 0~1。
"""


class FormOCREngine:
    def __init__(self, schema: FormSchema):
        self.schema = schema
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip(
            "/"
        )
        self.model = os.getenv("OCR_VISION_MODEL", "gpt-4o-mini")

    def recognize(self, image_path: str | Path) -> FormReadResult:
        image_path = Path(image_path)
        prepared = preprocess(image_path)
        if self.api_key:
            result = self._recognize_with_vision(prepared, image_path.name)
            result.engine = f"vision:{self.model}"
        else:
            result = self._recognize_demo(prepared, image_path.name)
            result.engine = "demo"
            result.warnings.append(
                "未設定 OPENAI_API_KEY，目前為示範模式（不會真的讀圖）。"
                "設定 API Key 後即可用 Vision 辨識潦草字與正字畫。"
            )
        result.source_image = str(image_path)
        result.recompute_total()
        return result

    def _recognize_with_vision(self, prepared: Path, original_name: str) -> FormReadResult:
        image_b64 = base64.b64encode(to_jpeg_bytes(prepared)).decode("ascii")
        defect_catalog = [
            {"key": d.key, "label": d.label} for d in self.schema.defect_items
        ]
        user_text = (
            "請辨識這張不良記錄表。"
            f"原始檔名: {original_name}\n"
            f"不良項目清單: {json.dumps(defect_catalog, ensure_ascii=False)}"
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
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
        return self._parse_model_json(data)

    def _parse_model_json(self, data: dict[str, Any]) -> FormReadResult:
        result = empty_result(self.schema)
        result.work_order = str(data.get("work_order", "") or "")
        result.product_no = str(data.get("product_no", "") or "")
        result.operator = str(data.get("operator", "") or "")
        result.date = str(data.get("date", "") or "")
        result.shift = str(data.get("shift", "") or "")
        result.warnings = [str(w) for w in data.get("warnings", []) or []]
        result.raw_payload = data

        by_key = {d.get("key"): d for d in data.get("defects", []) or []}
        by_label = {d.get("label"): d for d in data.get("defects", []) or []}
        parsed: list[DefectCount] = []
        for item in self.schema.defect_items:
            raw = by_key.get(item.key) or by_label.get(item.label) or {}
            count = raw.get("count")
            raw_mark = str(raw.get("raw_mark", "") or "")
            conf = float(raw.get("confidence", 0.5) or 0.5)
            note = str(raw.get("note", "") or "")
            if count is None and raw_mark:
                count, mark_conf, _ = count_zheng_marks(raw_mark)
                conf = min(conf, mark_conf)
            if count is None:
                count = 0
                conf = min(conf, 0.3)
                result.warnings.append(f"「{item.label}」數量不明，已暫記 0，請人工確認")
            parsed.append(
                DefectCount(
                    key=item.key,
                    label=item.label,
                    count=int(count),
                    raw_mark=raw_mark,
                    confidence=conf,
                    note=note,
                )
            )
        result.defects = parsed
        return result

    def _recognize_demo(self, prepared: Path, original_name: str) -> FormReadResult:
        """無 API 時的可跑通流程：從檔名推測欄位，不良數留空待審核。"""
        result = empty_result(self.schema, source_image=str(prepared))
        stem = Path(original_name).stem
        # 檔名慣例範例: 20260730_WO123_PN456_王小明.jpg
        parts = re.split(r"[_\-]", stem)
        if len(parts) >= 1 and re.search(r"\d{6,8}", parts[0]):
            result.date = parts[0]
        if len(parts) >= 2:
            result.work_order = parts[1]
        if len(parts) >= 3:
            result.product_no = parts[2]
        if len(parts) >= 4:
            result.operator = parts[3]
        for defect in result.defects:
            defect.confidence = 0.0
            defect.note = "示範模式：請人工填入正字畫數量"
        return result
