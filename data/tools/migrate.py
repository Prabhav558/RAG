"""Migrate legacy spreadsheet scorecards (Cycle 2 · §8.3–8.4).

    python data/tools/migrate.py data/legacy/code-review-quality.xlsx            # preview only
    python data/tools/migrate.py data/legacy/vendor-assessment.csv data/legacy/vendor-assessment-ratings.csv --commit
    python data/tools/migrate.py --all --commit                                   # every dataset in data/legacy
    options: --rescale 0-10-rag  --subject-type team  --no-placeholders  --draft  --report-dir reports/migration
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import migration as mig  # noqa: E402
from app import services as svc  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402

# datasets: (files, options) — the rescale option is part of the documented run for the 7-point sheet
DATASETS = [
    (["code-review-quality.xlsx"], {}),
    (["training-session-quality.xlsx"], {}),
    (["vendor-assessment.csv", "vendor-assessment-ratings.csv"], {}),
    (["meeting-effectiveness-7pt.xlsx"], {}),
    (["meeting-effectiveness-7pt.xlsx"], {"rescale_to": "0-10-rag"}),
    (["broken-no-header.xlsx"], {}),
    (["corrupt.xlsx"], {}),
]


def render(report: dict) -> str:
    L = [f"# Migration report — {report['source']}", ""]
    L.append(f"**Status:** {report['status']} · **committed:** {report['committed']}"
             + (f" · scorecard id {report['scorecard_id']} / version {report['version_id']}" if report["scorecard_id"] else ""))
    if report["legacy_scale"]:
        L.append(f"**Legacy scale:** {report['legacy_scale'][0]}–{report['legacy_scale'][1]} → **{report['scale']}**")
    if report["fatal"]:
        L += ["", "## Fatal", *[f"- {f}" for f in report["fatal"]]]
    if report["notes"]:
        L += ["", "## Notes", *[f"- {n}" for n in report["notes"]]]
    if report["counts"]:
        L += ["", "## Row outcomes", "", "| Kind / status | Rows |", "|---|---|",
              *[f"| {k} | {v} |" for k, v in report["counts"].items()]]
    d = report["definition"]
    if d:
        L += ["", "## Migrated definition", f"`{d['code']}` · {d['name']} · subject `{d['subject_type']}` · "
              f"target {d['version']['target_score']} · tags {', '.join(d['tags'])}", ""]

        def tree(ps, depth=0):
            for p in ps:
                flags = [f for f, on in (("critical", p["is_critical"]), ("optional", p["is_optional"])) if on]
                L.append(f"{'  ' * depth}- `{p['code']}` {p['name']} (w {p['weight']:g}{', ' + ', '.join(flags) if flags else ''}"
                         f"{', ' + str(len(p['criteria'])) + ' matrix rows' if p['criteria'] else ''})")
                tree(p["children"], depth + 1)

        tree(d["version"]["parameters"])
    if report["validation_issues"]:
        L += ["", "## Validation of the migrated definition",
              *[f"- [{i['code']}] {i['severity']}: {i['path'] or ''} {i['message']}" for i in report["validation_issues"]]]
    problem_rows = [r for r in report["rows"] if r["status"] != "imported" or r["messages"]]
    if problem_rows:
        L += ["", "## Rows with warnings or rejections", "", "| Sheet | Row | Kind | Item | Status | Messages |",
              "|---|---|---|---|---|---|"]
        for r in problem_rows:
            L.append(f"| {r['sheet']} | {r['row']} | {r['kind']} | {r['label']} | {r['status']} | "
                     f"{'<br>'.join(m.replace('|', '/') for m in r['messages'])} |")
    rec = report["reconciliation"]
    if report["evaluations"]:
        L += ["", "## Reconciliation (legacy total vs recomputed)",
              f"{rec['rows_with_legacy_total']} rows with a legacy total · {rec['matched']} match (±0.01) · "
              f"{rec['mismatched']} differ ({rec['mismatched_unexplained']} unexplained) · max |diff| {rec['max_abs_diff']}", "",
              "| Row | Subject | Import as | Legacy total | Recomputed | Diff | Explanation |", "|---|---|---|---|---|---|---|"]
        for e in report["evaluations"]:
            if e["status"] == "rejected":
                continue
            L.append(f"| {e['row']} | {e['subject']} | {e['import_as']} | {e['legacy_total'] if e['legacy_total'] is not None else '—'} | "
                     f"{e['recomputed'] if e['recomputed'] is not None else '—'} | {e['diff'] if e['diff'] is not None else '—'} | "
                     f"{e['explanation'] or ''} |")
    return "\n".join(L) + "\n"


def run(db, files: list[Path], opts: dict, do_commit: bool) -> dict:
    options = mig.MigrationOptions(**opts)
    m = mig.plan(db, [(f.name, f.read_bytes()) for f in files], options)
    if do_commit and not m.fatal:
        try:
            mig.commit(db, m)
        except svc.DomainError as e:
            db.rollback()
            m.fatal.append(f"[{e.code}] {e.message}")
    return m.to_dict()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--all", action="store_true", help="run every dataset in data/legacy")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--rescale", dest="rescale_to")
    ap.add_argument("--subject-type")
    ap.add_argument("--no-placeholders", action="store_true")
    ap.add_argument("--draft", action="store_true", help="do not publish the migrated scorecard")
    ap.add_argument("--report-dir", type=Path, default=ROOT / "reports" / "migration")
    args = ap.parse_args(argv)

    init_db()
    jobs = []
    if args.all:
        jobs = [([ROOT / "data" / "legacy" / f for f in files], opts) for files, opts in DATASETS]
    elif args.files:
        opts = {k: v for k, v in {"rescale_to": args.rescale_to, "subject_type": args.subject_type}.items() if v}
        if args.no_placeholders:
            opts["fill_missing_guidelines"] = False
        if args.draft:
            opts["publish"] = False
        jobs = [(args.files, opts)]
    else:
        ap.error("give files or --all")

    args.report_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        svc.seed_reference_data(db)
        for files, opts in jobs:
            report = run(db, files, opts, args.commit)
            suffix = f"-rescaled-{opts['rescale_to']}" if opts.get("rescale_to") else ""
            out = args.report_dir / f"{files[0].stem}{suffix}.md"
            out.write_text(render(report))
            c = report["counts"]
            print(f"{report['status']:<17} {files[0].name}{suffix}: kpi ok/warn/rej "
                  f"{c.get('kpi_imported', 0)}/{c.get('kpi_warning', 0)}/{c.get('kpi_rejected', 0)} · ratings "
                  f"{c.get('rating_imported', 0)}/{c.get('rating_warning', 0)}/{c.get('rating_rejected', 0)} · "
                  f"reconciled {report['reconciliation']['matched']}/{report['reconciliation']['rows_with_legacy_total']}"
                  + (f" · FATAL {report['fatal'][0]}" if report["fatal"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
