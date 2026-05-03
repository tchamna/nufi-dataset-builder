"""Small FastAPI app: drag-and-drop workbook → rebuild (same pipeline as CLI)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from nufi_dataset_builder.rebuild import (
    DEFAULT_CSV_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_SHEET,
    run_rebuild,
)

_MAX_BYTES = 120 * 1024 * 1024

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nufi dataset builder</title>
  <style>
    :root { font-family: system-ui, sans-serif; line-height: 1.4; }
    body { max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }
    #zone { border: 2px dashed #888; border-radius: 12px; padding: 2rem; text-align: center; background: #f6f6f6; }
    #zone.drag { border-color: #0a58ca; background: #eef5ff; }
    pre { background: #111; color: #eee; padding: 1rem; border-radius: 8px; overflow: auto; max-height: 24rem; font-size: 12px; }
    label { display: block; margin: 1rem 0 0.25rem; font-weight: 600; }
    input[type=text] { width: 100%; max-width: 24rem; padding: 0.4rem 0.5rem; }
    .err { color: #b00020; }
    .ok { color: #0a6620; }
  </style>
</head>
<body>
  <h1>Nufi dataset builder</h1>
  <p>Drop your <strong>.xlsx</strong> here (or pick a file). Outputs go to <code>reports/nufi-normalized-import/</code> and <code>data/local-dictionary.sqlite</code> relative to where you started the server.</p>
  <label for="sheet">Worksheet name</label>
  <input id="sheet" type="text" value="MainDictionary" />
  <div id="zone" style="margin-top:1rem;">
    <p>Drag workbook here</p>
    <input type="file" accept=".xlsx,.xlsm" id="file" />
  </div>
  <p id="status"></p>
  <pre id="out" hidden></pre>
  <script>
    const zone = document.getElementById('zone');
    const sheet = document.getElementById('sheet');
    const fileInput = document.getElementById('file');
    const status = document.getElementById('status');
    const out = document.getElementById('out');
    async function upload(file) {
      status.textContent = 'Rebuilding…';
      out.hidden = true;
      const fd = new FormData();
      fd.set('workbook', file);
      fd.set('sheet', sheet.value.trim() || 'MainDictionary');
      const res = await fetch('/api/rebuild', { method: 'POST', body: fd });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        status.innerHTML = '<span class="err">' + (json.error || res.statusText) + '</span>';
        if (json.detail) out.textContent = JSON.stringify(json.detail, null, 2);
        out.hidden = !json.detail;
        return;
      }
      status.innerHTML = '<span class="ok">Done.</span> CSV: <code>' + json.csv_dir + '</code> · DB: <code>' + json.db_path + '</code>';
      out.textContent = JSON.stringify(json, null, 2);
      out.hidden = false;
    }
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag');
      const f = e.dataTransfer.files[0];
      if (f) upload(f);
    });
    fileInput.addEventListener('change', () => {
      const f = fileInput.files[0];
      if (f) upload(f);
      fileInput.value = '';
    });
  </script>
</body>
</html>"""

app = FastAPI(title="Nufi dataset builder", version="0.1.0")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _INDEX_HTML


@app.post("/api/rebuild")
async def api_rebuild(
    workbook: UploadFile = File(...),
    sheet: str = Form(default=DEFAULT_SHEET),
) -> JSONResponse:
    raw_name = workbook.filename or "workbook.xlsx"
    suffix = Path(raw_name).suffix.lower() or ".xlsx"
    if suffix not in (".xlsx", ".xlsm"):
        return JSONResponse({"ok": False, "error": "Upload a .xlsx or .xlsm file."}, status_code=400)

    data = await workbook.read()
    if len(data) > _MAX_BYTES:
        return JSONResponse(
            {"ok": False, "error": f"File too large (max {_MAX_BYTES // (1024 * 1024)} MB)."},
            status_code=400,
        )

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        Path(tmp_path).write_bytes(data)

        wb, csv_dir, db_path = run_rebuild(
            xlsx_path=tmp_path,
            sheet=sheet.strip() or DEFAULT_SHEET,
            csv_dir=DEFAULT_CSV_DIR,
            db_path=DEFAULT_DB_PATH,
            app_port=None,
            allow_running_app=True,
        )
        return {
            "ok": True,
            "workbook": str(wb),
            "csv_dir": str(csv_dir),
            "db_path": str(db_path),
        }
    except (FileNotFoundError, RuntimeError) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def run_web() -> None:
    import uvicorn

    host = os.environ.get("NUFI_DATASET_HOST", "127.0.0.1")
    port = int(os.environ.get("NUFI_DATASET_PORT", "8765"))
    uvicorn.run("nufi_dataset_builder.web_app:app", host=host, port=port, reload=False)
