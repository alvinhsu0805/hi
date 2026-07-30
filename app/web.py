from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .excel_writer import ExcelWriter
from .form_template import create_blank_form
from .ocr_engine import FormOCREngine
from .schema import DefectCount, FormReadResult, load_schema
from .zheng_count import strokes_to_zheng_display

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
UPLOADS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)

schema = load_schema()
engine = FormOCREngine(schema)
excel_path = OUTPUTS / "defect_stats.xlsx"
blank_form_path = OUTPUTS / "blank_defect_form.xlsx"
writer = ExcelWriter(schema, excel_path)
writer.ensure_workbook()
create_blank_form(schema, blank_form_path)

app = FastAPI(title="工廠不良表單 OCR 自動登打", version="0.1.0")
app.mount("/files", StaticFiles(directory=DATA), name="files")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "schema": schema,
            "excel_path": str(excel_path.relative_to(ROOT)),
            "has_api_key": bool(engine.api_key),
        },
    )


@app.post("/recognize", response_class=HTMLResponse)
async def recognize(request: Request, image: UploadFile = File(...)):
    suffix = Path(image.filename or "form.jpg").suffix or ".jpg"
    save_path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    result = engine.recognize(save_path)
    for defect in result.defects:
        if not defect.raw_mark and defect.count:
            defect.raw_mark = strokes_to_zheng_display(defect.count)

    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            "result": result,
            "schema": schema,
            "image_url": f"/files/uploads/{save_path.name}",
        },
    )


@app.post("/commit")
async def commit(request: Request):
    form = dict(await request.form())
    defects: list[DefectCount] = []
    for item in schema.defect_items:
        count_raw = str(form.get(f"defect_{item.key}", "0") or "0")
        try:
            count = int(count_raw)
        except ValueError:
            count = 0
        defects.append(
            DefectCount(
                key=item.key,
                label=item.label,
                count=max(0, count),
                raw_mark=str(form.get(f"raw_{item.key}", "")),
                confidence=1.0,
            )
        )
    result = FormReadResult(
        work_order=str(form.get("work_order", "")),
        product_no=str(form.get("product_no", "")),
        operator=str(form.get("operator", "")),
        date=str(form.get("date", "")),
        shift=str(form.get("shift", "")),
        defects=defects,
        source_image=str(form.get("source_image", "")),
        engine="human-reviewed",
        overall_confidence=1.0,
    )
    result.recompute_total()
    row = writer.append_result(result, reviewed=True)
    return RedirectResponse(url=f"/done?row={row}", status_code=303)


@app.get("/done", response_class=HTMLResponse)
async def done(request: Request, row: int = 0):
    return templates.TemplateResponse(
        "done.html",
        {
            "request": request,
            "row": row,
            "excel_url": "/files/outputs/defect_stats.xlsx",
            "template_url": "/files/outputs/blank_defect_form.xlsx",
        },
    )


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "vision_enabled": bool(engine.api_key),
        "model": engine.model if engine.api_key else None,
        "excel": str(excel_path),
    }


@app.post("/api/recognize")
async def api_recognize(image: UploadFile = File(...)):
    suffix = Path(image.filename or "form.jpg").suffix or ".jpg"
    save_path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    result = engine.recognize(save_path)
    return JSONResponse(result.model_dump())
