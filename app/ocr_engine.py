"""QWF-ME061 外觀檢驗暨首件檢查表辨識引擎。

辨識優先順序：
1. 表頭（型號、批號、作業人員、檢驗規範、日期、AOI）
2. 底部「不良數」列的阿拉伯數字（對應各不良代碼欄）
3. 總數 / 總不良數 / 總良數交叉驗證
4. 底部空白時，才退回數格子內正字畫或劃記
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


SYSTEM_PROMPT = """你是工廠品管表單 OCR 助手，專門辨識 AMT「外觀檢驗暨首件檢查表」(QWF-ME061)。

表單特徵：
- 表頭：型號、批號、作業人員、檢驗規範、日期、AOI(OK/NG)
- 不良代碼分區：PET原材料(Pxx)、PET(PBxx)、GLASS(GBxx)、夾層(FAxx)
- 列區：AA區 / 非AA區 劃記
- 底部有「不良數」合計列，以及總數、總不良數、總良數

請只輸出 JSON（不要 markdown）：
{
  "model_no": "",
  "lot_no": "",
  "operator": "",
  "inspection_spec": "",
  "date": "",
  "aoi_result": "OK|NG|",
  "aoi_count": "",
  "total_qty": 0,
  "total_defects_reported": 0,
  "total_good": 0,
  "hand_notes": "跨欄大字手寫備註，如不平、水痕",
  "defects": [
    {"key": "PB01", "label": "PB01", "count": 2, "raw_mark": "2", "confidence": 0.9, "note": "來自底部不良數列"}
  ],
  "warnings": []
}

規則（很重要）：
1. defects 只輸出 count>0 的不良代碼，不要輸出全部代碼。
2. 優先讀底部「不良數」列的數字，對齊上方代碼（P03/PB../GB../FA..）。
3. 若某欄底部空白但格子有正字畫/劃記，再換算：正=5，未完成正字=1~4。
4. 垂直大字（不平、水痕等）放入 hand_notes，不要當成某代碼數量。
5. 字跡不清仍給最佳估計，confidence 調低並寫入 warnings。
6. confidence 介於 0~1；key 必須是不良代碼本身（如 PB07）。
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
                "設定 API Key 後即可辨識 QWF-ME061 表單。"
            )
        result.source_image = str(image_path)
        # 相容舊欄位
        if not result.product_no and result.model_no:
            result.product_no = result.model_no
        if not result.work_order and result.lot_no:
            result.work_order = result.lot_no
        result.recompute_total()
        return result

    def _recognize_with_vision(self, prepared: Path, original_name: str) -> FormReadResult:
        image_b64 = base64.b64encode(to_jpeg_bytes(prepared, max_side=2000)).decode(
            "ascii"
        )
        categories = [
            {"label": c.label, "codes": c.codes} for c in self.schema.defect_categories
        ]
        user_text = (
            f"請辨識這張 {self.schema.form_name}（{self.schema.form_id}）。\n"
            f"原始檔名: {original_name}\n"
            f"不良代碼分區: {json.dumps(categories, ensure_ascii=False)}\n"
            "請優先讀底部不良數列與總計，只回傳有數量的代碼。"
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
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return self._parse_model_json(data)

    def _parse_model_json(self, data: dict[str, Any]) -> FormReadResult:
        result = empty_result(self.schema)
        result.model_no = str(data.get("model_no", "") or "")
        result.lot_no = str(data.get("lot_no", "") or "")
        result.operator = str(data.get("operator", "") or "")
        result.inspection_spec = str(data.get("inspection_spec", "") or "")
        result.date = str(data.get("date", "") or "")
        result.aoi_result = str(data.get("aoi_result", "") or "")
        result.aoi_count = str(data.get("aoi_count", "") or "")
        result.hand_notes = str(data.get("hand_notes", "") or "")
        result.warnings = [str(w) for w in data.get("warnings", []) or []]
        result.raw_payload = data

        result.total_qty = _as_int(data.get("total_qty"))
        result.total_defects_reported = _as_int(data.get("total_defects_reported"))
        result.total_good = _as_int(data.get("total_good"))

        # 相容舊鍵名
        if not result.model_no:
            result.model_no = str(data.get("product_no", "") or "")
        if not result.lot_no:
            result.lot_no = str(data.get("work_order", "") or "")

        by_key = {
            str(d.get("key", "")).upper(): d for d in data.get("defects", []) or []
        }
        catalog = self.schema.defect_by_key()
        parsed: list[DefectCount] = []
        for item in self.schema.defect_items:
            raw = by_key.get(item.key.upper()) or {}
            count = raw.get("count")
            raw_mark = str(raw.get("raw_mark", "") or "")
            conf = float(raw.get("confidence", 0.0) or 0.0)
            note = str(raw.get("note", "") or "")
            if count is None and raw_mark:
                count, mark_conf, _ = count_zheng_marks(raw_mark)
                conf = min(conf or mark_conf, mark_conf)
            if count is None:
                count = 0
            if count and conf == 0:
                conf = 0.5
            parsed.append(
                DefectCount(
                    key=item.key,
                    label=item.label,
                    category=item.category,
                    count=int(count),
                    raw_mark=raw_mark,
                    confidence=conf,
                    note=note,
                )
            )

        # 模型回傳了 schema 以外的代碼時，附加進去以免遺失
        known = {p.key.upper() for p in parsed}
        for key, raw in by_key.items():
            if not key or key in known:
                continue
            count = _as_int(raw.get("count")) or 0
            if not count:
                continue
            parsed.append(
                DefectCount(
                    key=key,
                    label=str(raw.get("label") or key),
                    category="未登錄代碼",
                    count=count,
                    raw_mark=str(raw.get("raw_mark", "") or ""),
                    confidence=float(raw.get("confidence", 0.4) or 0.4),
                    note="不在預設代碼表，請確認",
                )
            )
            result.warnings.append(f"出現未登錄不良代碼 {key}")
            _ = catalog  # keep for future lookup

        result.defects = parsed
        return result

    def _recognize_demo(self, prepared: Path, original_name: str) -> FormReadResult:
        """無 API 時可跑通：可用檔名，或載入樣本期望值。"""
        result = empty_result(self.schema, source_image=str(prepared))
        stem = Path(original_name).stem.lower()

        # 針對使用者提供的樣張：AMT QWF-ME061 範例值
        if "qwf" in stem or "amt" in stem or "sample" in stem or "me061" in stem:
            result.model_no = "10819-B"
            result.lot_no = "26-06-209"
            result.operator = "17449 / 1229"
            result.inspection_spec = "A001-3"
            result.date = "16"
            result.aoi_result = "OK"
            result.aoi_count = "11"
            result.total_qty = 142
            result.total_defects_reported = 15
            result.total_good = 127
            result.hand_notes = "不平；水痕（樣張手寫大字）"
            # 樣張底部可見數值加總=15，代碼需人工對欄；示範先佔位
            demo_counts = [("PB01", 2), ("PB02", 1), ("PB03", 1), ("GB01", 6), ("GB02", 2), ("FA01", 1), ("FA02", 2)]
            by = {k: v for k, v in demo_counts}
            for defect in result.defects:
                if defect.key in by:
                    defect.count = by[defect.key]
                    defect.raw_mark = str(by[defect.key])
                    defect.confidence = 0.55
                    defect.note = "示範佔位：請依樣張底部不良數列對齊真實代碼"
            result.warnings.append(
                "示範模式使用樣張表頭與合計；各代碼欄位對應請人工核對後再登打。"
            )
            return result

        parts = re.split(r"[_\-]", Path(original_name).stem)
        if parts and re.search(r"\d{6,8}", parts[0]):
            result.date = parts[0]
        if len(parts) >= 2:
            result.lot_no = parts[1]
            result.work_order = parts[1]
        if len(parts) >= 3:
            result.model_no = parts[2]
            result.product_no = parts[2]
        if len(parts) >= 4:
            result.operator = parts[3]
        for defect in result.defects:
            defect.confidence = 0.0
            defect.note = "示範模式：請人工填入底部不良數"
        return result


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
