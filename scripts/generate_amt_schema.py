#!/usr/bin/env python3
"""產生 QWF-ME061（外觀檢驗暨首件檢查表）的 schema 設定。"""

from __future__ import annotations

import json
from pathlib import Path


def codes(prefix: str, start: int, end: int) -> list[dict]:
    return [
        {"key": f"{prefix}{i:02d}", "label": f"{prefix}{i:02d}", "category": prefix}
        for i in range(start, end + 1)
    ]


def main() -> None:
    pet_raw = [
        {"key": "P03", "label": "P03", "category": "PET原材料不良"},
        {"key": "P05", "label": "P05", "category": "PET原材料不良"},
        {"key": "P06", "label": "P06", "category": "PET原材料不良"},
        {"key": "P99", "label": "P99其他", "category": "PET原材料不良"},
    ]
    pet = [
        {**c, "category": "PET不良"}
        for c in codes("PB", 1, 23)
    ]
    glass = [
        {**c, "category": "GLASS不良"}
        for c in codes("GB", 1, 16)
    ]
    fa = [
        {**c, "category": "夾層不良"}
        for c in codes("FA", 1, 14)
    ] + [{"key": "FA99", "label": "FA99其他", "category": "夾層不良"}]

    defect_items = pet_raw + pet + glass + fa

    schema = {
        "form_name": "外觀檢驗暨首件檢查表",
        "form_id": "QWF-ME061",
        "form_version": "V2.04",
        "notes": (
            "對應 AMT 紙本表。辨識時優先讀底部「不良數」列與「總不良數/總良數/總數」；"
            "格子內正字畫或劃記僅作補強。不良代碼名稱可依工廠代碼表修改 label。"
        ),
        "header_fields": [
            {"key": "model_no", "label": "型號", "type": "text"},
            {"key": "lot_no", "label": "批號", "type": "text"},
            {"key": "operator", "label": "作業人員", "type": "text"},
            {"key": "inspection_spec", "label": "檢驗規範", "type": "text"},
            {"key": "date", "label": "日期", "type": "date"},
            {"key": "aoi_result", "label": "AOI", "type": "text"},
            {"key": "aoi_count", "label": "AOI數量", "type": "number"},
            {"key": "total_qty", "label": "總數", "type": "number"},
            {"key": "total_defects", "label": "總不良數", "type": "number"},
            {"key": "total_good", "label": "總良數", "type": "number"},
            {"key": "hand_notes", "label": "手寫備註", "type": "text"},
        ],
        "defect_categories": [
            {"key": "pet_raw", "label": "PET原材料不良", "codes": ["P03", "P05", "P06", "P99"]},
            {
                "key": "pet",
                "label": "PET不良",
                "codes": [f"PB{i:02d}" for i in range(1, 24)],
            },
            {
                "key": "glass",
                "label": "GLASS不良",
                "codes": [f"GB{i:02d}" for i in range(1, 17)],
            },
            {
                "key": "fa",
                "label": "夾層不良",
                "codes": [f"FA{i:02d}" for i in range(1, 15)] + ["FA99"],
            },
        ],
        "defect_items": defect_items,
        "excel": {
            "summary_sheet": "檢驗日結",
            "detail_sheet": "不良明細",
            "header_row": 1,
        },
        "ocr_priority": [
            "讀表頭：型號、批號、作業人員、檢驗規範、日期、AOI",
            "讀底部合計列：各不良代碼對應的「不良數」阿拉伯數字",
            "讀總數、總不良數、總良數並交叉驗證",
            "若底部空白，再數格子內正字畫/劃記",
            "記錄跨欄手寫註記（如不平、水痕）到 hand_notes",
        ],
    }

    out = Path(__file__).resolve().parents[1] / "config" / "defect_schema.json"
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} with {len(defect_items)} defect codes")


if __name__ == "__main__":
    main()
