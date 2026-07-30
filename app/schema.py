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


class ExcelMapping(BaseModel):
    sheet_name: str = "不良統計"
    header_row: int = 1
    columns: dict[str, str]


class FormSchema(BaseModel):
    form_name: str
    header_fields: list[HeaderField]
    defect_items: list[DefectItem]
    excel: ExcelMapping


class DefectCount(BaseModel):
    key: str
    label: str
    count: int = 0
    raw_mark: str = ""
    confidence: float = 0.0
    note: str = ""


class FormReadResult(BaseModel):
    work_order: str = ""
    product_no: str = ""
    operator: str = ""
    date: str = ""
    shift: str = ""
    defects: list[DefectCount] = Field(default_factory=list)
    total_defects: int = 0
    overall_confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    source_image: str = ""
    engine: str = ""
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    def recompute_total(self) -> None:
        self.total_defects = sum(d.count for d in self.defects)
        if self.defects:
            self.overall_confidence = sum(d.confidence for d in self.defects) / len(
                self.defects
            )


def load_schema(path: Path | None = None) -> FormSchema:
    schema_path = path or DEFAULT_SCHEMA_PATH
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    return FormSchema.model_validate(data)


def empty_result(schema: FormSchema, source_image: str = "") -> FormReadResult:
    return FormReadResult(
        source_image=source_image,
        defects=[
            DefectCount(key=item.key, label=item.label) for item in schema.defect_items
        ],
    )
