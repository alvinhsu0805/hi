#!/usr/bin/env python3
"""命令列：辨識單張表單照片並寫入 Excel。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.excel_writer import ExcelWriter
from app.form_template import create_blank_form
from app.ocr_engine import FormOCREngine
from app.schema import load_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="不良表單 OCR 登打")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="建立空白表單與統計 Excel")
    p_init.add_argument("--out", default="data/outputs")

    p_ocr = sub.add_parser("recognize", help="辨識照片")
    p_ocr.add_argument("image")
    p_ocr.add_argument("--json-out", default="")
    p_ocr.add_argument("--write-excel", action="store_true")
    p_ocr.add_argument("--excel", default="data/outputs/defect_stats.xlsx")
    p_ocr.add_argument("--reviewed", action="store_true")

    p_serve = sub.add_parser("serve", help="啟動審核網站")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    schema = load_schema()

    if args.cmd == "init":
        out = Path(args.out)
        create_blank_form(schema, out / "blank_defect_form.xlsx")
        writer = ExcelWriter(schema, out / "defect_stats.xlsx")
        writer.ensure_workbook()
        print(f"已建立: {out / 'blank_defect_form.xlsx'}")
        print(f"已建立: {out / 'defect_stats.xlsx'}")
        return

    if args.cmd == "recognize":
        engine = FormOCREngine(schema)
        result = engine.recognize(args.image)
        payload = result.model_dump()
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.json_out:
            Path(args.json_out).write_text(text, encoding="utf-8")
            print(f"JSON 已寫入 {args.json_out}")
        else:
            print(text)
        if args.write_excel:
            writer = ExcelWriter(schema, args.excel)
            row = writer.append_result(result, reviewed=args.reviewed)
            print(f"已寫入 Excel 第 {row} 列 -> {args.excel}")
        return

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("app.web:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
