from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from .. import auth
from .. import migration as mig
from .. import services as svc
from ..db import get_session

router = APIRouter(prefix="/api/migrations")
require_importer = auth.require_role("importer")

MAX_BYTES = 20 * 1024 * 1024


async def _read(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not 1 <= len(files) <= 2:
        raise svc.DomainError("M001", "Upload one workbook, or a definition CSV plus a ratings CSV")
    out = []
    for f in files:
        data = await f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise svc.DomainError("M001", f"'{f.filename}' is larger than 20 MB")
        out.append((f.filename or "upload", data))
    return out


def _options(rescale_to, subject_type, fill_missing_guidelines, publish, code) -> mig.MigrationOptions:
    return mig.MigrationOptions(subject_type=subject_type or None, rescale_to=rescale_to or None,
                                fill_missing_guidelines=fill_missing_guidelines, publish=publish, code=code or None)


@router.post("/preview")
async def preview(
    files: list[UploadFile] = File(...),
    rescale_to: str | None = Form(None),
    subject_type: str | None = Form(None),
    fill_missing_guidelines: bool = Form(True),
    publish: bool = Form(True),
    code: str | None = Form(None),
    db: Session = Depends(get_session),
):
    """Dry run: parse, map, validate and reconcile without writing anything."""
    m = mig.plan(db, await _read(files), _options(rescale_to, subject_type, fill_missing_guidelines, publish, code))
    return m.to_dict()


@router.post("/commit")
async def commit(
    files: list[UploadFile] = File(...),
    rescale_to: str | None = Form(None),
    subject_type: str | None = Form(None),
    fill_missing_guidelines: bool = Form(True),
    publish: bool = Form(True),
    code: str | None = Form(None),
    _: object = Depends(require_importer),
    db: Session = Depends(get_session),
):
    m = mig.plan(db, await _read(files), _options(rescale_to, subject_type, fill_missing_guidelines, publish, code))
    try:
        mig.commit(db, m)
    except svc.DomainError:
        db.rollback()
        raise
    return m.to_dict()
