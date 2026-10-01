from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from sqlalchemy import select

from .. import auth
from .. import migration as mig
from .. import services as svc
from ..ai_import import (
    MAX_HINT_CHARS, AssistError, DraftContext, SheetDrafter, get_sheet_drafter, sheet_to_text, slugify, to_definition,
)
from ..db import get_session
from ..models import Scorecard, SubjectType
from ..validation import validate_version

router = APIRouter(prefix="/api/migrations")
require_importer = auth.require_role("importer")
require_designer = auth.require_role("designer")

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


@router.post("/ai-draft")
async def ai_draft(
    files: list[UploadFile] = File(...),
    rating_scale: str = Form("0-10-rag"),
    subject_type: str | None = Form(None),
    max_depth: int = Form(2),
    hint: str | None = Form(None),
    who: str = Depends(auth.actor_name),
    _: object = Depends(require_designer),
    db: Session = Depends(get_session),
    drafter: SheetDrafter = Depends(get_sheet_drafter),
):
    """Advisory only: reads any spreadsheet (messy or vague is fine) and drafts a scorecard definition from it.
    Writes nothing. The caller reviews the draft and creates it through POST /api/scorecards (as a draft version)."""
    if not 1 <= max_depth <= 4:
        raise svc.DomainError("M001", "Hierarchy depth must be between 1 and 4")
    if hint and len(hint) > MAX_HINT_CHARS:
        raise svc.DomainError("M001", f"The note is longer than {MAX_HINT_CHARS} characters")
    sources = await _read(files)
    sheets = [s for name, data in sources for s in mig.load_sheets(name, data)]
    text, truncated = sheet_to_text(sheets)
    if not any(r for sh in sheets for r in sh.rows):
        raise svc.DomainError("M002", "The spreadsheet is empty")
    scale = svc.scale_by_code(db, rating_scale)
    types = [t.code for t in db.scalars(select(SubjectType).order_by(SubjectType.name))]
    if subject_type:
        svc.subject_type_by_code(db, subject_type)
    ctx = DraftContext(
        filename=sources[0][0], sheet_text=text, scale_min=scale.min_value, scale_max=scale.max_value,
        band_lower_bounds=[b.lower_bound for b in scale.bands], max_depth=max_depth, subject_types=types,
        subject_type=subject_type or None, hint=hint or "",
    )
    try:
        draft = drafter.draft(ctx)
    except AssistError as e:
        raise svc.DomainError("J004", str(e), e.status) from e

    base, n = slugify(draft.name), 2
    code = base
    while db.scalar(select(Scorecard).where(Scorecard.code == code)):
        code, n = f"{base}-{n}", n + 1
    definition = to_definition(draft, code, rating_scale, max_depth, who)
    issues = validate_version(definition.version, svc.scale_info(scale))
    return {
        "model": draft.model, "summary": draft.summary, "assumptions": draft.assumptions,
        "truncated": truncated, "sheets": [{"name": sh.name, "rows": len(sh.rows)} for sh in sheets],
        "definition": definition.model_dump(), "issues": [i.model_dump() for i in issues],
    }
