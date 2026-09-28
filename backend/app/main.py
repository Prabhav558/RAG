import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from . import auth
from .db import SessionLocal, init_db
from .routers import auth as auth_router
from .routers import evaluations, flow, migrations, scorecards
from .services import DomainError, seed_reference_data

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Development: create tables directly. Production: set SCORECARD_AUTO_CREATE=0 and run `alembic upgrade head`.
    if os.environ.get("SCORECARD_AUTO_CREATE", "1") != "0":
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


@app.exception_handler(RequestValidationError)
async def contract_error_handler(_: Request, exc: RequestValidationError):
    # Never echo the raw input back: it may be NaN/Infinity (unserialisable) or megabytes of text.
    detail = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail[:50]})


@app.exception_handler(StaleDataError)
async def stale_data_handler(_: Request, exc: StaleDataError):
    # optimistic concurrency: someone else changed this record between our read and our write
    return JSONResponse(status_code=409, content={
        "code": "S012", "message": "This was changed by someone else at the same time. Reload and try again.",
        "details": None})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    # Safety net: validation should catch these first. A hit here is a validation gap to fix.
    return JSONResponse(
        status_code=409,
        content={"code": "E017", "message": "The data violates a database integrity rule", "details": None},
    )


app.include_router(auth_router.router)  # register/login are the only unauthenticated endpoints
app.include_router(scorecards.router, dependencies=[Depends(auth.get_current_user)])
app.include_router(evaluations.router, dependencies=[Depends(auth.get_current_user)])
app.include_router(migrations.router, dependencies=[Depends(auth.get_current_user)])
app.include_router(flow.router, dependencies=[Depends(auth.get_current_user)])


@app.get("/api/health")
def health():
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
