"""將 QWF-ME061 辨識結果寫入 Excel。

- 檢驗日結：一張表單一列（表頭 + 總計 + 各不良代碼欄）
- 不良明細：只寫 count>0 的代碼，方便樞紐分析
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .schema import FormReadResult, FormSchema


HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)
WARNING_FILL = PatternFill("solid", fgColor="FFF2CC")


SUMMARY_FIXED = [
    ("date", "日期"),
    ("model_no", "型號"),
    ("lot_no", "批號"),
    ("operator", "作業人員"),
    ("inspection_spec", "檢驗規範"),
    ("aoi_result", "AOI"),
    ("aoi_count", "AOI數量"),
    ("total_qty", "總數"),
    ("total_defects", "不良合計(系統)"),
    ("total_defects_reported", "總不良數(表上)"),
    ("total_good", "總良數"),
    ("hand_notes", "手寫備註"),
    ("confidence", "信心分數"),
    ("reviewed", "已審核"),
    ("source_image", "來源影像"),
]


DETAIL_HEADERS = [
    "日期",
    "型號",
    "批號",
    "作業人員",
    "不良分類",
    "不良代碼",
    "不良名稱",
    "數量",
    "原始劃記",
    "信心",
    "備註",
    "已審核",
    "來源影像",
]


class ExcelWriter:
    def __init__(self, schema: FormSchema, workbook_path: str | Path):
        self.schema = schema
        self.path = Path(workbook_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_keys = [k for k, _ in SUMMARY_FIXED] + [
            d.key for d in schema.defect_items
        ]
        self.summary_labels = {k: v for k, v in SUMMARY_FIXED}
        for d in schema.defect_items:
            self.summary_labels[d.key] = d.label

    def ensure_workbook(self) -> None:
        if self.path.exists():
            return
        wb = Workbook()
        ws = wb.active
        ws.title = self.schema.excel.summary_sheet
        for idx, key in enumerate(self.summary_keys, start=1):
            cell = ws.cell(row=self.schema.excel.header_row, column=idx)
            cell.value = self.summary_labels.get(key, key)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.freeze_panes = "A2"

        detail = wb.create_sheet(self.schema.excel.detail_sheet)
        for idx, label in enumerate(DETAIL_HEADERS, start=1):
            cell = detail.cell(row=1, column=idx, value=label)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center")
        detail.freeze_panes = "A2"
        wb.save(self.path)

    def append_result(self, result: FormReadResult, reviewed: bool = False) -> int:
        self.ensure_workbook()
        wb = load_workbook(self.path)
        summary_name = self.schema.excel.summary_sheet
        if summary_name not in wb.sheetnames:
            # 相容舊檔：取第一個工作表
            summary_name = wb.sheetnames[0]
        ws = wb[summary_name]
        row = ws.max_row + 1

        values: dict[str, object] = {
            "date": result.date,
            "model_no": result.model_no or result.product_no,
            "lot_no": result.lot_no or result.work_order,
            "operator": result.operator,
            "inspection_spec": result.inspection_spec,
            "aoi_result": result.aoi_result,
            "aoi_count": result.aoi_count,
            "total_qty": result.total_qty,
            "total_defects": result.total_defects,
            "total_defects_reported": result.total_defects_reported,
            "total_good": result.total_good,
            "hand_notes": result.hand_notes,
            "confidence": round(result.overall_confidence, 3),
            "reviewed": "Y" if reviewed else "N",
            "source_image": result.source_image,
        }
        for defect in result.defects:
            values[defect.key] = defect.count if defect.count else ""

        low_conf = (not reviewed) and (
            result.overall_confidence < 0.7
            or any(d.count > 0 and d.confidence < 0.6 for d in result.defects)
        )
        for idx, key in enumerate(self.summary_keys, start=1):
            cell = ws.cell(row=row, column=idx, value=values.get(key, ""))
            if low_conf:
                cell.fill = WARNING_FILL

        detail_name = self.schema.excel.detail_sheet
        if detail_name not in wb.sheetnames:
            detail = wb.create_sheet(detail_name)
            for idx, label in enumerate(DETAIL_HEADERS, start=1):
                cell = detail.cell(row=1, column=idx, value=label)
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
        else:
            detail = wb[detail_name]

        for defect in result.nonzero_defects():
            drow = detail.max_row + 1
            detail.cell(row=drow, column=1, value=result.date)
            detail.cell(row=drow, column=2, value=result.model_no or result.product_no)
            detail.cell(row=drow, column=3, value=result.lot_no or result.work_order)
            detail.cell(row=drow, column=4, value=result.operator)
            detail.cell(row=drow, column=5, value=defect.category)
            detail.cell(row=drow, column=6, value=defect.key)
            detail.cell(row=drow, column=7, value=defect.label)
            detail.cell(row=drow, column=8, value=defect.count)
            detail.cell(row=drow, column=9, value=defect.raw_mark)
            detail.cell(row=drow, column=10, value=round(defect.confidence, 3))
            detail.cell(row=drow, column=11, value=defect.note)
            detail.cell(row=drow, column=12, value="Y" if reviewed else "N")
            detail.cell(row=drow, column=13, value=result.source_image)

        # 稍微加寬前幾欄
        for col in range(1, min(16, len(self.summary_keys) + 1)):
            ws.column_dimensions[get_column_letter(col)].width = 14

        wb.save(self.path)
        return row
