#!/usr/bin/env python3
"""本機快速測試：不經網頁，直接辨識一張照片。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.offline_ocr import OfflineHeaderOCR  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: py -3.12 scripts/test_header_ocr.py 照片路徑.jpg")
        return 1
    image = Path(sys.argv[1])
    if not image.exists():
        print(f"找不到檔案: {image}")
        return 1
    engine = OfflineHeaderOCR()
    print("status:", engine.status())
    fields, texts = engine.recognize(image)
    print("engine:", engine.engine_name)
    print(
        json.dumps(
            {
                "model_no": fields.model_no,
                "lot_no": fields.lot_no,
                "lot_normalized": fields.lot_normalized,
                "operator": fields.operator,
                "warnings": fields.warnings,
                "ocr_texts": texts,
                "last_error": engine.last_error,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
