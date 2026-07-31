from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .excel_writer import ExcelWriter
from .field_parsers import HeaderFields, normalize_lot
from .form_template import create_blank_form
from .header_excel import HeaderExcelWriter
from .ocr_engine import FormOCREngine
from .offline_ocr import OfflineHeaderOCR
from .schema import DefectCount, FormReadResult, load_schema

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
UPLOADS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)

schema = load_schema()
engine = FormOCREngine(schema)
offline_engine = OfflineHeaderOCR()
excel_path = OUTPUTS / "defect_stats.xlsx"
header_excel_path = OUTPUTS / "header_offline.xlsx"
blank_form_path = OUTPUTS / "blank_defect_form.xlsx"
writer = ExcelWriter(schema, excel_path)
header_writer = HeaderExcelWriter(header_excel_path)
writer.ensure_workbook()
header_writer.ensure()
create_blank_form(schema, blank_form_path)

app = FastAPI(title="QWF-ME061 不良表單 OCR 自動登打", version="0.3.0")
app.mount("/files", StaticFiles(directory=DATA), name="files")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def render(request: Request, name: str, context: dict | None = None):
    ctx = dict(context or {})
    return templates.TemplateResponse(request, name, ctx)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return render(
        request,
        "index.html",
        {
            "schema": schema,
            "excel_path": str(excel_path.relative_to(ROOT)),
            "has_api_key": bool(engine.api_key),
        },
    )


@app.get("/offline", response_class=HTMLResponse)
async def offline_home(request: Request):
    return render(request, "offline.html", {})


@app.post("/offline/recognize", response_class=HTMLResponse)
async def offline_recognize(request: Request, image: UploadFile = File(...)):
    suffix = Path(image.filename or "form.jpg").suffix or ".jpg"
    save_path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    fields, texts = offline_engine.recognize(save_path)
    return render(
        request,
        "offline_review.html",
        {
            "fields": fields,
            "engine": offline_engine.engine_name,
            "ocr_texts": texts,
            "image_url": f"/files/uploads/{save_path.name}",
            "source_image": str(save_path),
        },
    )


@app.post("/offline/commit")
async def offline_commit(request: Request):
    form = dict(await request.form())
    lot_raw = str(form.get("lot_no", "")).strip()
    lot_norm = str(form.get("lot_normalized", "")).strip()
    if lot_raw and not lot_norm:
        pretty, normalized = normalize_lot(lot_raw)
        lot_raw = pretty or lot_raw
        lot_norm = normalized

    fields = HeaderFields(
        model_no=str(form.get("model_no", "")).strip(),
        lot_no=lot_raw,
        lot_normalized=lot_norm,
        operators=[
            p.strip()
            for p in str(form.get("operator", "")).replace(",", "/").split("/")
            if p.strip()
        ],
        warnings=[],
    )
    row = header_writer.append(
        fields, source_image=str(form.get("source_image", ""))
    )
    return RedirectResponse(url=f"/offline/done?row={row}", status_code=303)


@app.get("/offline/done", response_class=HTMLResponse)
async def offline_done(request: Request, row: int = 0):
    return render(
        request,
        "offline_done.html",
        {
            "row": row,
            "excel_url": "/files/outputs/header_offline.xlsx",
        },
    )


@app.post("/recognize", response_class=HTMLResponse)
async def recognize(request: Request, image: UploadFile = File(...)):
    suffix = Path(image.filename or "form.jpg").suffix or ".jpg"
    save_path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    result = engine.recognize(save_path)
    return render(
        request,
        "review.html",
        {
            "result": result,
            "schema": schema,
            "image_url": f"/files/uploads/{save_path.name}",
            "nonzero": result.nonzero_defects(),
        },
    )


@app.post("/commit")
async def commit(request: Request):
    form = dict(await request.form())
    catalog = schema.defect_by_key()

    counts: dict[str, DefectCount] = {}
    for key, item in catalog.items():
        count_raw = str(form.get(f"defect_{key}", "") or "")
        if count_raw == "":
            continue
        try:
            count = int(count_raw)
        except ValueError:
            count = 0
        counts[key] = DefectCount(
            key=key,
            label=item.label,
            category=item.category,
            count=max(0, count),
            raw_mark=str(form.get(f"raw_{key}", "")),
            confidence=1.0,
        )

    extra_key = str(form.get("extra_key", "") or "").strip().upper()
    extra_count_raw = str(form.get("extra_count", "") or "").strip()
    if extra_key and extra_count_raw != "":
        try:
            extra_count = max(0, int(extra_count_raw))
        except ValueError:
            extra_count = 0
        if extra_key in catalog:
            item = catalog[extra_key]
            counts[extra_key] = DefectCount(
                key=extra_key,
                label=item.label,
                category=item.category,
                count=extra_count,
                confidence=1.0,
            )
        elif extra_count:
            counts[extra_key] = DefectCount(
                key=extra_key,
                label=extra_key,
                category="未登錄代碼",
                count=extra_count,
                confidence=1.0,
                note="人工補漏",
            )

    for key, item in catalog.items():
        if key not in counts:
            counts[key] = DefectCount(
                key=key,
                label=item.label,
                category=item.category,
                count=0,
                confidence=1.0,
            )

    order = {d.key: i for i, d in enumerate(schema.defect_items)}
    defects = sorted(counts.values(), key=lambda d: order.get(d.key, 9999))

    result = FormReadResult(
        model_no=str(form.get("model_no", "")),
        lot_no=str(form.get("lot_no", "")),
        operator=str(form.get("operator", "")),
        inspection_spec=str(form.get("inspection_spec", "")),
        date=str(form.get("date", "")),
        aoi_result=str(form.get("aoi_result", "")),
        aoi_count=str(form.get("aoi_count", "")),
        hand_notes=str(form.get("hand_notes", "")),
        total_qty=_to_int(form.get("total_qty")),
        total_defects_reported=_to_int(form.get("total_defects_reported")),
        total_good=_to_int(form.get("total_good")),
        product_no=str(form.get("model_no", "")),
        work_order=str(form.get("lot_no", "")),
        defects=defects,
        source_image=str(form.get("source_image", "")),
        engine="human-reviewed",
        overall_confidence=1.0,
    )
    result.recompute_total()
    row = writer.append_result(result, reviewed=True)
    return RedirectResponse(url=f"/done?row={row}", status_code=303)


def _to_int(value: object) -> int | None:
    text = str(value or "").strip()
    if text == "":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


@app.get("/done", response_class=HTMLResponse)
async def done(request: Request, row: int = 0):
    return render(
        request,
        "done.html",
        {
            "row": row,
            "excel_url": "/files/outputs/defect_stats.xlsx",
            "template_url": "/files/outputs/blank_defect_form.xlsx",
        },
    )


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "form_id": schema.form_id,
        "defect_codes": len(schema.defect_items),
        "vision_enabled": bool(engine.api_key),
        "offline_engine": offline_engine.engine_name,
        "model": engine.model if engine.api_key else None,
        "excel": str(excel_path),
        "header_excel": str(header_excel_path),
    }


@app.post("/api/recognize")
async def api_recognize(image: UploadFile = File(...)):
    suffix = Path(image.filename or "form.jpg").suffix or ".jpg"
    save_path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    result = engine.recognize(save_path)
    return JSONResponse(result.model_dump())


@app.post("/api/offline/recognize")
async def api_offline_recognize(image: UploadFile = File(...)):
    suffix = Path(image.filename or "form.jpg").suffix or ".jpg"
    save_path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    fields, texts = offline_engine.recognize(save_path)
    return JSONResponse(
        {
            "engine": offline_engine.engine_name,
            "model_no": fields.model_no,
            "lot_no": fields.lot_no,
            "lot_normalized": fields.lot_normalized,
            "operator": fields.operator,
            "warnings": fields.warnings,
            "ocr_texts": texts,
            "source_image": str(save_path),
        }
    )
