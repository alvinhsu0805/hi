#!/usr/bin/env python3
"""離線初版：辨識型號／批號／作業人員，可寫入 Excel。

用法：
  python offline_tool.py recognize photo.jpg
  python offline_tool.py recognize photo.jpg --write-excel
  python offline_tool.py gui
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.field_parsers import HeaderFields, parse_header_from_texts
from app.header_excel import HeaderExcelWriter
from app.offline_ocr import OfflineHeaderOCR


def recognize_image(image: Path) -> tuple[HeaderFields, list[str], str]:
    engine = OfflineHeaderOCR()
    fields, texts = engine.recognize(image)
    return fields, texts, engine.engine_name


def cmd_recognize(args: argparse.Namespace) -> int:
    image = Path(args.image)
    if not image.exists():
        print(f"找不到影像: {image}", file=sys.stderr)
        return 1
    fields, texts, engine = recognize_image(image)
    payload = {
        "engine": engine,
        "model_no": fields.model_no,
        "lot_no": fields.lot_no,
        "lot_normalized": fields.lot_normalized,
        "operator": fields.operator,
        "operators": fields.operators,
        "warnings": fields.warnings,
        "ocr_texts": texts,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.write_excel:
        xlsx = Path(args.excel)
        row = HeaderExcelWriter(xlsx).append(fields, source_image=str(image))
        print(f"已寫入 Excel 第 {row} 列 -> {xlsx}")
    return 0


def cmd_parse_demo(_: argparse.Namespace) -> int:
    """不靠影像，驗證解析規則。"""
    sample = [
        "型號 91-28190-00C",
        "批號 26-07-341",
        "作業人員 10672",
    ]
    fields = parse_header_from_texts(sample)
    print(
        json.dumps(
            {
                "model_no": fields.model_no,
                "lot_no": fields.lot_no,
                "lot_normalized": fields.lot_normalized,
                "operator": fields.operator,
                "warnings": fields.warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_gui(_: argparse.Namespace) -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:  # noqa: BLE001
        print(f"Tkinter 不可用: {exc}", file=sys.stderr)
        return 1

    root = tk.Tk()
    root.title("離線表頭辨識初版（型號／批號／作業人員）")
    root.geometry("720x520")

    status = tk.StringVar(value="選擇表頭照片開始辨識（可離線）")
    model_var = tk.StringVar()
    lot_var = tk.StringVar()
    lot_norm_var = tk.StringVar()
    op_var = tk.StringVar()
    warn_var = tk.StringVar()
    current_image: dict[str, Path | None] = {"path": None}
    last_fields: dict[str, HeaderFields | None] = {"fields": None}

    frm = tk.Frame(root, padx=16, pady=16)
    frm.pack(fill="both", expand=True)

    tk.Label(frm, textvariable=status, wraplength=680, justify="left").pack(anchor="w")

    grid = tk.Frame(frm)
    grid.pack(fill="x", pady=12)
    labels = [
        ("型號 (XX-XXXXX-XXX)", model_var),
        ("批號原文", lot_var),
        ("批號正規化", lot_norm_var),
        ("作業人員（5碼）", op_var),
    ]
    for i, (label, var) in enumerate(labels):
        tk.Label(grid, text=label).grid(row=i, column=0, sticky="w", pady=4)
        tk.Entry(grid, textvariable=var, width=48).grid(row=i, column=1, sticky="we", pady=4)
    grid.columnconfigure(1, weight=1)

    tk.Label(frm, text="提醒").pack(anchor="w")
    tk.Label(frm, textvariable=warn_var, fg="#a15c00", wraplength=680, justify="left").pack(
        anchor="w"
    )

    def do_open() -> None:
        path = filedialog.askopenfilename(
            title="選擇表單照片",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All", "*.*")],
        )
        if not path:
            return
        current_image["path"] = Path(path)
        status.set(f"辨識中：{path}")
        root.update_idletasks()
        try:
            fields, texts, engine = recognize_image(Path(path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("辨識失敗", str(exc))
            status.set("辨識失敗")
            return
        last_fields["fields"] = fields
        model_var.set(fields.model_no)
        lot_var.set(fields.lot_no)
        lot_norm_var.set(fields.lot_normalized)
        op_var.set(fields.operator)
        warn_var.set("；".join(fields.warnings) or "（無）")
        status.set(f"完成（引擎：{engine}，OCR行數：{len(texts)}）。可人工修改後寫入 Excel。")

    def do_save() -> None:
        fields = HeaderFields(
            model_no=model_var.get().strip(),
            lot_no=lot_var.get().strip(),
            lot_normalized=lot_norm_var.get().strip(),
            operators=[p.strip() for p in op_var.get().split("/") if p.strip()],
            warnings=[w for w in warn_var.get().split("；") if w and w != "（無）"],
        )
        # 若使用者只改批號原文，自動重算正規化
        if fields.lot_no and not fields.lot_normalized:
            from app.field_parsers import normalize_lot

            pretty, normalized = normalize_lot(fields.lot_no)
            fields.lot_no = pretty or fields.lot_no
            fields.lot_normalized = normalized
            lot_norm_var.set(fields.lot_normalized)

        out = Path("data/outputs/header_offline.xlsx")
        row = HeaderExcelWriter(out).append(
            fields, source_image=str(current_image["path"] or "")
        )
        messagebox.showinfo("已寫入", f"已寫入 {out} 第 {row} 列")

    btns = tk.Frame(frm)
    btns.pack(fill="x", pady=16)
    tk.Button(btns, text="選擇照片並辨識", command=do_open, width=18).pack(side="left")
    tk.Button(btns, text="寫入 Excel", command=do_save, width=14).pack(side="left", padx=8)
    tk.Button(btns, text="離開", command=root.destroy, width=10).pack(side="right")

    tip = (
        "規則：型號 XX-XXXXX-XXX；批號 26-07-341 → 20260700341；"
        "作業人員固定 5 碼。建議拍表頭特寫、數字分開寫。"
    )
    tk.Label(frm, text=tip, fg="#445566", wraplength=680, justify="left").pack(
        anchor="w", pady=8
    )
    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="離線表頭辨識初版")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("recognize", help="辨識單張照片")
    p_rec.add_argument("image")
    p_rec.add_argument("--write-excel", action="store_true")
    p_rec.add_argument("--excel", default="data/outputs/header_offline.xlsx")
    p_rec.set_defaults(func=cmd_recognize)

    p_demo = sub.add_parser("demo-parse", help="驗證解析規則（不需影像）")
    p_demo.set_defaults(func=cmd_parse_demo)

    p_gui = sub.add_parser("gui", help="開啟簡易 GUI")
    p_gui.set_defaults(func=cmd_gui)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
