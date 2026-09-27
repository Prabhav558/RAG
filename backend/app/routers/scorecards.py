from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services as svc
from ..db import get_session
from ..models import RatingScale, Scorecard, ScorecardVersion, SubjectType
from ..schemas import (
    CloneRequest,
    ScaleIn,
    ScorecardDefinition,
    ScorecardMetaUpdate,
    SubjectTypeIn,
    VersionIn,
)
from ..validation import validate_version

router = APIRouter(prefix="/api")


def _scorecard(db: Session, scorecard_id: int) -> Scorecard:
    sc = db.get(Scorecard, scorecard_id)
    if not sc:
        raise svc.DomainError("E404", f"Scorecard {scorecard_id} not found", 404)
    return sc


def _version(db: Session, version_id: int) -> ScorecardVersion:
    return svc.load_version(db, version_id)


# ---------------------------------------------------------------- reference data


@router.get("/meta/scales")
def list_scales(db: Session = Depends(get_session)):
    return [svc.scale_view(s) for s in db.scalars(select(RatingScale).order_by(RatingScale.id))]


@router.post("/meta/scales", status_code=201)
def create_scale(body: ScaleIn, db: Session = Depends(get_session)):
    return svc.scale_view(svc.create_scale(db, body))


@router.get("/meta/subject-types")
def list_subject_types(db: Session = Depends(get_session)):
    return [
        {"id": s.id, "code": s.code, "name": s.name, "description": s.description}
        for s in db.scalars(select(SubjectType).order_by(SubjectType.name))
    ]


@router.post("/meta/subject-types", status_code=201)
def create_subject_type(body: SubjectTypeIn, db: Session = Depends(get_session)):
    if db.scalar(select(SubjectType).where(SubjectType.code == body.code)):
        raise svc.DomainError("E011", f"Subject type '{body.code}' already exists", 409)
    st = SubjectType(**body.model_dump())
    db.add(st)
    db.commit()
    return {"id": st.id, "code": st.code, "name": st.name, "description": st.description}


# ---------------------------------------------------------------- scorecards


@router.get("/scorecards")
def list_scorecards(subject_type: str | None = None, db: Session = Depends(get_session)):
    q = select(Scorecard).where(Scorecard.archived_at.is_(None)).order_by(Scorecard.name)
    cards = [svc.scorecard_summary(db, sc) for sc in db.scalars(q)]
    if subject_type:
        cards = [c for c in cards if c["subject_type"] == subject_type]
    return cards


@router.post("/scorecards", status_code=201)
def create_scorecard(body: ScorecardDefinition, publish: bool = False, db: Session = Depends(get_session)):
    sc = svc.create_scorecard(db, body, publish=publish)
    return svc.scorecard_summary(db, sc)


@router.get("/scorecards/{scorecard_id}")
def get_scorecard(scorecard_id: int, db: Session = Depends(get_session)):
    return svc.scorecard_summary(db, _scorecard(db, scorecard_id))


@router.patch("/scorecards/{scorecard_id}")
def update_scorecard_meta(scorecard_id: int, body: ScorecardMetaUpdate, db: Session = Depends(get_session)):
    sc = _scorecard(db, scorecard_id)
    data = body.model_dump(exclude_unset=True)
    if "subject_type" in data:
        sc.subject_type = svc.subject_type_by_code(db, data.pop("subject_type"))
    for k, v in data.items():
        setattr(sc, k, v)
    db.commit()
    return svc.scorecard_summary(db, sc)


@router.delete("/scorecards/{scorecard_id}", status_code=204)
def archive_scorecard(scorecard_id: int, db: Session = Depends(get_session)):
    sc = _scorecard(db, scorecard_id)
    sc.archived_at = svc.now()
    db.commit()


@router.post("/scorecards/{scorecard_id}/clone", status_code=201)
def clone_scorecard(scorecard_id: int, body: CloneRequest, db: Session = Depends(get_session)):
    sc = _scorecard(db, scorecard_id)
    source = _version(db, body.version_id) if body.version_id else sc.versions[-1]
    if source.scorecard_id != sc.id:
        raise svc.DomainError("E008", "Version does not belong to this scorecard")
    return svc.scorecard_summary(db, svc.clone_scorecard(db, source, body.code, body.name))


# ---------------------------------------------------------------- versions


@router.get("/versions/{version_id}")
def get_version(version_id: int, db: Session = Depends(get_session)):
    return svc.version_view(_version(db, version_id))


@router.get("/versions/{version_id}/definition")
def get_definition(version_id: int, db: Session = Depends(get_session)):
    """Portable JSON (no ids): used by the builder and for export/import."""
    return svc.export_definition(_version(db, version_id))


@router.put("/versions/{version_id}")
def save_draft(version_id: int, body: VersionIn, db: Session = Depends(get_session)):
    version = svc.update_draft(db, _version(db, version_id), body)
    return {
        "version": svc.version_view(version),
        "issues": [i.model_dump() for i in svc.validate_stored_version(version)],
    }


@router.post("/versions/{version_id}/validate")
def validate(version_id: int, db: Session = Depends(get_session)):
    return [i.model_dump() for i in svc.validate_stored_version(_version(db, version_id))]


@router.post("/validate-definition")
def validate_definition(body: VersionIn, db: Session = Depends(get_session)):
    """Validate unsaved builder content."""
    scale = svc.scale_by_code(db, body.rating_scale)
    return [i.model_dump() for i in validate_version(body, svc.scale_info(scale))]


@router.post("/versions/{version_id}/publish")
def publish(version_id: int, x_actor: str | None = Header(default=None), db: Session = Depends(get_session)):
    version = svc.load_version(db, version_id, lock=True)
    issues = svc.publish_version(db, version, actor=(x_actor or "anonymous").strip()[:120] or "anonymous")
    return {"version": svc.version_view(version), "issues": [i.model_dump() for i in issues]}


@router.post("/versions/{version_id}/new-draft", status_code=201)
def new_draft(version_id: int, change_note: str | None = None, db: Session = Depends(get_session)):
    return svc.version_view(svc.new_draft_from(db, _version(db, version_id), change_note))


@router.delete("/versions/{version_id}", status_code=204)
def delete_draft(version_id: int, db: Session = Depends(get_session)):
    svc.delete_draft(db, _version(db, version_id))
