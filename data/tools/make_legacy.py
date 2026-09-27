"""Build the legacy-spreadsheet datasets used to exercise the Cycle 2 migration (data/legacy/).

Each file mimics how teams actually keep scorecards in Excel/CSV today, with deliberately injected problems.
The expected outcome of every injected problem is listed in docs/cycle2/MIGRATION_RULES.md.

    python data/tools/make_legacy.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

OUT = Path(__file__).resolve().parents[2] / "data" / "legacy"
rng = random.Random(7)


def weighted(scores: dict, weights: dict) -> float:
    return round(sum(scores[k] * weights[k] for k in scores) / sum(weights[k] for k in scores), 2)


# ---------------------------------------------------------------- L1: clean, flat, 1-5
def code_review():
    wb = Workbook()
    ws = wb.active
    ws.title = "Scorecard"
    for row in [["Scorecard: Code Review Quality"], ["Purpose", "Catch defects and design problems before merge"],
                ["Objective", "Every reviewed PR scores 4 or above"], ["Scale", "1-5"], ["Target", 4],
                ["Subject", "Task"], []]:
        ws.append(row)
    ws.append(["No", "KPI", "Weight %", "Description", "5", "4", "3", "2", "1"])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    kpis = [
        ("1", "Defects found", 30, "Real defects caught", "All real defects caught with repro", "Most defects caught",
         "Obvious defects only", "Missed a defect", "Rubber stamp"),
        ("2", "Design feedback", 25, "Architecture and design", "Improves design materially", "Useful design notes",
         "Some design comments", "Style only", "None"),
        ("3", "Clarity of comments", 20, "Actionable wording", "Every comment actionable", "Mostly actionable",
         "Some vague comments", "Mostly vague", "Unclear"),
        ("4", "Turnaround", 15, "Time to first review", "< 4 hours", "< 1 day", "< 2 days", "< 4 days", ">= 4 days"),
        ("5", "Tone", 10, "Respectful, constructive", "Exemplary", "Constructive", "Neutral", "Curt", "Hostile"),
    ]
    for k in kpis:
        ws.append(list(k))
    w = {k[0]: k[2] for k in kpis}
    rs = wb.create_sheet("Ratings")
    rs.append(["PR", "Reviewer", "Date", "Defects found", "Design feedback", "Clarity of comments", "Turnaround",
               "Tone", "Total", "Comments"])
    d0 = date(2026, 3, 2)
    for i in range(15):
        s = {k: rng.randint(2, 5) for k in w}
        rs.append([f"PR-{1200 + i}", rng.choice(["Asha", "Ben", "Chen"]), d0 + timedelta(days=3 * i),
                   *s.values(), weighted(s, w), rng.choice(["", "Good catch on the race condition", "Needs follow-up"])])
    wb.save(OUT / "code-review-quality.xlsx")


# ---------------------------------------------------------------- L2: messy, hierarchical, 0-10, M01-M05
def training_feedback():
    wb = Workbook()
    ws = wb.active
    ws.title = "KPIs"
    for row in [["TRAINING SESSION FEEDBACK SCORECARD"], ["Scorecard: Training Session Quality"],
                ["Owner: L&D team"], ["Target: good"], ["Last updated", "Q4 2025"], []]:
        ws.append(row)
    ws.append(["S.No", "Parameter", "Weightage", "Score 10", "Score 9", "Score 8", "Score 6-7", "Score 4-5", "Score 0-3",
               "Owner notes"])
    rows = [
        ("1", "Content", 40, None, None, None, None, None, None, ""),
        ("1.1", "Relevance to role", 60, "Directly applicable", "Directly applicable", "Mostly applicable",
         "Partly applicable", "Rarely applicable", "Irrelevant", ""),
        ("1.2", "Accuracy", "high", "No errors", "No errors", "One minor slip", "Several slips", "Errors", "Wrong", ""),
        ("2", "Delivery", 50, None, None, None, None, None, None, ""),
        ("2.1", "Clarity", 40, "Crystal clear", "Very clear", "Clear", "Some confusion", None, "Confusing", "check 4-5"),
        ("2.2", "Engagement", None, "Everyone engaged", "Most engaged", "Engaged", "Mixed", "Low", "None", ""),
        ("2.3", "Pace", 20, "Perfect", "Good", "Good", "Uneven", "Too fast/slow", "Unusable", ""),
        ("3", "Logistics", 20, None, None, None, None, None, None, ""),
        ("3.1", "Venue & equipment", 100, "Flawless", "Minor issue", "Minor issue", "Issues", "Major issues", "Failed", ""),
        ("", "", None, None, None, None, None, None, None, ""),
        ("", "Total", 110, None, None, None, None, None, None, ""),
    ]
    for r in rows:
        ws.append(list(r))
    # legacy formula: sum(weight * score) / 100 over the leaves, using the sheet's own (unnormalised) weights
    leaf_w = {"Relevance to role": 60 * 0.4, "Accuracy": 3 * 0.4, "Clarity": 40 * 0.5, "Engagement": 1 * 0.5,
              "Pace": 20 * 0.5, "Venue & equipment": 100 * 0.2}
    rs = wb.create_sheet("Feedback log")
    rs.append(["Session", "Assessor", "Date", *leaf_w.keys(), "Overall", "Remarks"])

    def add(subject, assessor, when, scores, overall=None, remarks=""):
        num = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
        if overall is None and len(num) == len(scores):
            overall = round(sum(v * leaf_w[k] for k, v in num.items()) / 100, 2)
        rs.append([subject, assessor, when, *scores.values(), overall, remarks])

    d0 = date(2025, 10, 6)
    for i in range(14):
        add(f"Onboarding batch {i + 1}", rng.choice(["R. Iyer", "M. Das"]), d0 + timedelta(days=7 * i),
            {k: rng.randint(5, 10) for k in leaf_w})
    full = {k: 8 for k in leaf_w}
    add("Workshop: Git", "R. Iyer", "2025-12-01", {**full, "Venue & equipment": "N/A"}, remarks="Remote session")
    add("Workshop: SQL", "R. Iyer", "2025-12-02", {**full, "Pace": 7.5})
    add("Workshop: Cloud", "M. Das", "2025-12-03", {**full, "Clarity": 12})
    add("Workshop: Testing", "M. Das", "2025-12-04", {**full, "Engagement": "good"})
    add("Workshop: Docker", "M. Das", "2025-12-05", {**full, "Accuracy": None})
    add("Workshop: APIs", None, "2025-12-06", full)
    add("Workshop: Security", "R. Iyer", "31/02/2025", full)
    add("Workshop: Python", "R. Iyer", "2025-12-08", full)
    add("Workshop: Python", "R. Iyer", "2025-12-08", full)  # exact duplicate
    add("Workshop: Agile", "M. Das", "2025-12-09", full)
    add("Workshop: Agile", "M. Das", "2025-12-09", {**full, "Clarity": 5})  # conflicting duplicate
    add("Workshop: Kafka", "M. Das", "2025-12-10", {**full, "Clarity": 5})
    add("Workshop: Kafka", "M. Das", "2026-01-12", full)  # re-run: second attempt
    add("", "M. Das", "2025-12-11", full)  # no subject
    add("Workshop: Linux", "R. Iyer", "2025-12-12", {k: None for k in leaf_w})  # no scores
    rs.append([])
    rs.append(["Average", None, None, *[7.9] * len(leaf_w), 7.9, ""])
    wb.save(OUT / "training-session-quality.xlsx")


# ---------------------------------------------------------------- L3: CSV, indentation, %, no guidelines
def vendor_csv():
    with open(OUT / "vendor-assessment.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Scorecard: Vendor Assessment"])
        w.writerow(["Scale: %"])
        w.writerow(["Target: 75"])
        w.writerow(["Applies to: Vendor"])
        w.writerow([])
        w.writerow(["Criteria", "Weight", "Critical"])
        for name, wt, crit in [("Commercials", 30, ""), ("  Pricing competitiveness", 60, ""),
                               ("  Payment terms", 40, ""), ("Delivery", 40, ""), ("  On-time delivery", 70, "Y"),
                               ("  Quality of goods", 30, "Y"), ("Compliance", 30, ""), ("  ISO certification", 50, ""),
                               ("  Data protection", 50, "yes")]:
            w.writerow([name, wt, crit])
    with open(OUT / "vendor-assessment-ratings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Vendor", "Rated by", "Date", "Pricing competitiveness", "Payment terms", "On-time delivery",
                    "Quality of goods", "ISO certification", "Data protection", "Score"])
        for i, v in enumerate(["Acme Supplies", "Globex", "Initech", "Umbrella Corp", "Hooli", "Stark Industries"]):
            s = [rng.randint(45, 100) for _ in range(6)]
            w.writerow([v, "Procurement", f"0{i + 1}.02.2026", *s, ""])


# ---------------------------------------------------------------- L4: garbage
def broken():
    wb = Workbook()
    ws = wb.active
    ws.append(["Quarterly numbers"])
    ws.append(["Region", "Revenue", "Growth"])
    ws.append(["North", 120, 0.05])
    wb.save(OUT / "broken-no-header.xlsx")
    (OUT / "corrupt.xlsx").write_bytes(b"PK\x03\x04 this is not really a zip")


# ---------------------------------------------------------------- L5: unsupported scale (needs rescale)
def seven_point():
    wb = Workbook()
    ws = wb.active
    ws.title = "Scorecard"
    for row in [["Scorecard: Meeting Effectiveness"], ["Scale: 1 to 7"], ["Target: 5"], ["Subject: Meeting"], []]:
        ws.append(row)
    ws.append(["KPI", "Weight", "7", "6", "5", "4", "3", "2", "1"])
    for name, wt in [("Agenda shared in advance", 1), ("Decisions recorded", 2), ("Actions with owners", 2),
                     ("Timekeeping", 1)]:
        ws.append([name, wt, "Always", "Almost always", "Usually", "Sometimes", "Rarely", "Almost never", "Never"])
    ws.cell(row=7, column=1).alignment = Alignment(indent=0)
    rs = wb.create_sheet("Ratings")
    rs.append(["Meeting", "Rated by", "Date", "Agenda shared in advance", "Decisions recorded", "Actions with owners",
               "Timekeeping"])
    for i in range(8):
        rs.append([f"Weekly sync {i + 1}", "PMO", date(2026, 1, 5) + timedelta(days=7 * i),
                   *[rng.randint(3, 7) for _ in range(4)]])
    wb.save(OUT / "meeting-effectiveness-7pt.xlsx")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    code_review()
    training_feedback()
    vendor_csv()
    broken()
    seven_point()
    for p in sorted(OUT.iterdir()):
        print(p.relative_to(OUT.parent.parent), p.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
