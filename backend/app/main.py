from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import SessionLocal, init_db
from .routers import evaluations, scorecards
from .services import DomainError, seed_reference_data

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_reference_data(db)
    yield


app = FastAPI(title="Scorecard Studio", version="0.1.0", lifespan=lifespan)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status, content={"code": exc.code, "message": exc.message, "details": exc.details}
    )


app.include_router(scorecards.router)
app.include_router(evaluations.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
