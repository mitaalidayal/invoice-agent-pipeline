import pathlib
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from graph import build_graph
from main import _initial_state

SUPPORTED_SUFFIXES = (".txt", ".json", ".csv", ".xml", ".pdf")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB - generous for any real invoice, bounds cost/latency on abuse

app = FastAPI(title="Invoice Agent Pipeline API")

# Only needed if someone runs the Vite dev server separately (frontend
# development, hot-reload) rather than the built static files below - the
# dev server runs on a different port, so cross-origin requests need to be
# explicitly allowed. Not used when serving web/dist (same origin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INVOICES_DIR = pathlib.Path("data/invoices")
FRONTEND_DIST = pathlib.Path("web/dist")


@app.get("/api/invoices")
def list_invoices():
    files = sorted(f.name for f in INVOICES_DIR.iterdir() if f.suffix in SUPPORTED_SUFFIXES)
    return {"invoices": files}


@app.post("/api/invoices/{filename}/process")
def process_invoice(filename: str):
    path = INVOICES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Invoice not found")

    graph = build_graph()
    return graph.invoke(_initial_state(str(path)))


@app.post("/api/upload")
async def upload_invoice(file: UploadFile = File(...)):
    suffix = pathlib.Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or '(none)'}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        size_mb = len(content) / (1024 * 1024)
        limit_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=413, detail=f"File is {size_mb:.1f} MB, which exceeds the {limit_mb:.0f} MB limit"
        )

    # Processed from a temp file, then discarded - uploads aren't persisted
    # anywhere, same one-shot treatment as the sample invoices.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = pathlib.Path(tmp.name)

    try:
        graph = build_graph()
        result = graph.invoke(_initial_state(str(tmp_path)))
    finally:
        tmp_path.unlink(missing_ok=True)

    result["invoice_path"] = file.filename
    return result


# Registered last, and only if the frontend has actually been built - routes
# above are matched first, so /api/* is never shadowed by this catch-all.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
