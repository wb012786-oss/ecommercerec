"""
多平台电商账单自动对账 - 主入口
隐私优先：处理完即删。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import List
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, MAX_FILES, UPLOAD_DIR
from .processor import process_uploads, safe_cleanup

app = FastAPI(
    title="多平台电商账单对账",
    description="上传多平台账单 Excel/CSV，自动标准化并对账出差异。处理完即删。",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
if (BASE / "static").exists():
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


class Health(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=Health)
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "max_size_mb": MAX_FILE_SIZE // (1024 * 1024),
            "max_files": MAX_FILES,
        },
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.post("/api/process")
async def process(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "请至少上传一个文件")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"一次最多 {MAX_FILES} 个文件")

    temp_paths: list[Path] = []
    names: list[str] = []

    try:
        for f in files:
            if not f.filename:
                continue
            suffix = Path(f.filename).suffix.lower()
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(400, f"不支持: {f.filename}，仅 Excel/CSV")

            content = await f.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(400, f"{f.filename} 超过大小限制")
            if not content:
                raise HTTPException(400, f"{f.filename} 为空")

            path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
            path.write_bytes(content)
            temp_paths.append(path)
            names.append(Path(f.filename).name)

        if not temp_paths:
            raise HTTPException(400, "没有有效文件")

        excel_bytes, result = process_uploads(temp_paths, names)
        safe_cleanup(temp_paths)

        fn_cn = "电商账单对账报告.xlsx"
        fn_en = "ecommerce_reconcile_report.xlsx"
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{fn_en}"; filename*=UTF-8\'\'{quote(fn_cn)}'
                ),
                "X-Process-Ok": "1",
                "X-Matched": str(result.get("matched", 0)),
                "X-Mismatch": str(result.get("mismatch", 0)),
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )
    except HTTPException:
        safe_cleanup(temp_paths)
        raise
    except ValueError as e:
        safe_cleanup(temp_paths)
        raise HTTPException(400, str(e))
    except Exception as e:
        safe_cleanup(temp_paths)
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"处理失败: {type(e).__name__}")


@app.on_event("startup")
async def startup_cleanup():
    try:
        for p in UPLOAD_DIR.glob("*"):
            if p.is_file():
                p.unlink(missing_ok=True)
    except Exception:
        pass
