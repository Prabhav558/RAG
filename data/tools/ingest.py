"""Load scorecard definitions (data/scorecards/*.json) through the same validation as the API.

    python data/tools/ingest.py                 # ingest + publish all definitions
    python data/tools/ingest.py --reset         # drop and recreate the database first
    python data/tools/ingest.py path/to/x.json  # specific files
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import ValidationError  # noqa: E402

from app import services as svc  # noqa: E402
from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.schemas import ScorecardDefinition  # noqa: E402

SCORECARD_DIR = ROOT / "data" / "scorecards"


def ingest_file(db, path: Path, publish: bool = True) -> tuple[bool, str]:
    try:
        definition = ScorecardDefinition.model_validate(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as e:
        return False, f"{path.name}: contract violation\n{e}"
    try:
        sc = svc.create_scorecard(db, definition, publish=publish)
    except svc.DomainError as e:
        db.rollback()
        details = "".join(f"\n    - [{d['code']}] {d['path'] or ''} {d['message']}" for d in (e.details or [])
                          if isinstance(d, dict))
        return False, f"{path.name}: [{e.code}] {e.message}{details}"
    n, leaves, depth = svc.tree_stats(sc.versions[-1])
    return True, f"{path.name}: '{sc.name}' v1 {sc.versions[-1].status} ({n} parameters, {leaves} leaves, depth {depth})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--reset", action="store_true", help="drop all tables first")
    ap.add_argument("--draft", action="store_true", help="ingest as drafts (do not publish)")
    args = ap.parse_args(argv)

    if args.reset:
        Base.metadata.drop_all(engine)
    init_db()
    files = args.files or sorted(SCORECARD_DIR.glob("*.json"))
    ok = True
    with SessionLocal() as db:
        svc.seed_reference_data(db)
        for f in files:
            success, msg = ingest_file(db, f, publish=not args.draft)
            ok &= success
            print(("OK   " if success else "FAIL ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
