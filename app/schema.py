from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = ROOT / "config" / "defect_schema.json"


class HeaderField(BaseModel):
    key: str
    label: str
    type: str = "text"


class DefectItem(BaseModel):
    key: str
    label: str
    category: str = ""


class DefectCategory(BaseModel):
    key: str
    label: str
    codes: list[str] = Field(default_factory=list)


class ExcelMapping(BaseModel):
    summary_sheet: str = "檢驗日結"
    detail_sheet: str = "不良明細"
    header_row: int = 1
    # 舊版相容（可省略，改由程式自動配欄）
    sheet_name: str | None = None
    columns: dict[str, str] = Field(default_factory=dict)


class FormSchema(BaseModel):
    form_name: str
    form_id: str = ""
    form_version: str = ""
    notes: str = ""
    header_fields: list[HeaderField]
    defect_items: list[DefectItem]
    defect_categories: list[DefectCategory] = Field(default_factory=list)
    excel: ExcelMapping
    ocr_priority: list[str] = Field(default_factory=list)

    def defect_by_key(self) -> dict[str, DefectItem]:
        return {d.key: d for d in self.defect_items}


class DefectCount(BaseModel):
    key: str
    label: str
    category: str = ""
    count: int = 0
    raw_mark: str = ""
    confidence: float = 0.0
    note: str = ""


class FormReadResult(BaseModel):
    model_no: str = ""
    lot_no: str = ""
    operator: str = ""
    inspection_spec: str = ""
    date: str = ""
    aoi_result: str = ""
    aoi_count: str = ""
    total_qty: int | None = None
    total_defects_reported: int | None = None
    total_good: int | None = None
    hand_notes: str = ""
    # 舊欄位別名（相容舊 UI / demo 檔名解析）
    work_order: str = ""
    product_no: str = ""
    shift: str = ""
    defects: list[DefectCount] = Field(default_factory=list)
    total_defects: int = 0
    overall_confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    source_image: str = ""
    engine: str = ""
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    def nonzero_defects(self) -> list[DefectCount]:
        return [d for d in self.defects if d.count > 0]

    def recompute_total(self) -> None:
        self.total_defects = sum(d.count for d in self.defects)
        scored = [d for d in self.defects if d.count > 0 or d.confidence > 0]
        if scored:
            self.overall_confidence = sum(d.confidence for d in scored) / len(scored)
        if (
            self.total_defects_reported is not None
            and self.total_defects
            and self.total_defects != self.total_defects_reported
        ):
            msg = (
                f"各欄不良合計 {self.total_defects} 與表上總不良數 "
                f"{self.total_defects_reported} 不一致，請人工確認"
            )
            if msg not in self.warnings:
                self.warnings.append(msg)


def load_schema(path: Path | None = None) -> FormSchema:
    schema_path = path or DEFAULT_SCHEMA_PATH
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    return FormSchema.model_validate(data)


def empty_result(schema: FormSchema, source_image: str = "") -> FormReadResult:
    return FormReadResult(
        source_image=source_image,
        defects=[
            DefectCount(key=item.key, label=item.label, category=item.category)
            for item in schema.defect_items
        ],
    )
