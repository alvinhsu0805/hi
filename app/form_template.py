"""產生可列印的空白不良記錄表（PDF/影像前可用 Excel 或 HTML 列印）。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

from .schema import FormSchema


def create_blank_form(schema: FormSchema, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "不良記錄表"

    thin = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    title_font = Font(size=18, bold=True)
    label_font = Font(size=12, bold=True)

    ws.merge_cells("A1:F1")
    ws["A1"] = schema.form_name
    ws["A1"].font = title_font
    ws["A1"].alignment = Alignment(horizontal="center")

    headers = [(f.label, f.key) for f in schema.header_fields]
    row = 3
    col = 1
    for label, _ in headers:
        cell_label = ws.cell(row=row, column=col, value=label)
        cell_value = ws.cell(row=row, column=col + 1, value="")
        cell_label.font = label_font
        for c in (cell_label, cell_value):
            c.border = thin
            c.alignment = Alignment(horizontal="center", vertical="center")
        col += 2
        if col > 5:
            col = 1
            row += 1

    row += 2
    ws.cell(row=row, column=1, value="不良項目").font = label_font
    ws.cell(row=row, column=2, value="正字畫（正=5）").font = label_font
    ws.cell(row=row, column=3, value="備註").font = label_font
    for c in range(1, 4):
        ws.cell(row=row, column=c).border = thin

    for item in schema.defect_items:
        row += 1
        ws.cell(row=row, column=1, value=item.label).border = thin
        ws.cell(row=row, column=2, value="").border = thin
        ws.cell(row=row, column=3, value="").border = thin
        ws.row_dimensions[row].height = 28

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 16

    tip_row = row + 2
    ws.merge_cells(start_row=tip_row, start_column=1, end_row=tip_row, end_column=3)
    ws.cell(
        row=tip_row,
        column=1,
        value="填寫提示：請用正字畫計數（正=5）。拍照時請整張入鏡、光線充足、避免反光。",
    )

    wb.save(output_path)
    return output_path
