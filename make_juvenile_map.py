"""
Write juvenile_map.csv, the row-position key for the AOIC Juvenile Probation Monthly
Report template, from a reference sheet.

    python make_juvenile_map.py            # uses the 2024 1st Circuit workbook's Jackson Juvenile sheet

The map has the same shape as probation_map.csv: four key columns (metric, breakdown,
breakdown_category, subgroup) prepended to every template row from "I. JUVENILE COURT
ACTIVITY" down, so row n of any juvenile sheet gets row n's labels. Rows without a
metric (section headers, totals, subtotals, blank spacers) keep only their label.
"""
import pandas as pd

from config import JUVENILE_MAP_FILE, RAW_DIR

REFERENCE = RAW_DIR / "2024" / "2024_circuit_01.xlsx", "2024 Jackson Juvenile"

CASE_TYPES = ["probation", "supervision", "cus", "informal", "other"]        # IX a-e
PETITION_TYPES = ["delinquency", "addiction", "mrai", "truancy", "neglect/abuse", "dependent"]
RACES = ["american indian", "asian", "black", "hispanic", "white", "other"]
AGES = ["12-under", "13", "14", "15", "16", "17-over"]
LEVELS = ["max", "med", "min", "unclassified"]


def block(start: int, metrics: list[str], breakdown: str, category: str, subgroup: str = "all") -> dict:
    """Consecutive template rows starting at `start`, one per metric."""
    return {start + i: (m, breakdown, category, subgroup) for i, m in enumerate(metrics)}


# row offset (from the "I. JUVENILE COURT ACTIVITY" line = 0) -> keys
KEYS = {
    # I.A petitions filed
    **block(2, PETITION_TYPES, "filed", "petitions"),
    # I.B court action per month
    **block(11, PETITION_TYPES[:4], "dismissed", "court action"),
    **block(17, PETITION_TYPES[:4], "continued under supervision", "court action"),
    **block(23, PETITION_TYPES[:4], "adjudicated", "court action"),
    # IV demographics of intakes (formal / informal)
    33: ("male", "gender", "demographics of intakes", "formal"),
    34: ("male", "gender", "demographics of intakes", "informal"),
    35: ("female", "gender", "demographics of intakes", "formal"),
    36: ("female", "gender", "demographics of intakes", "informal"),
    **block(39, AGES, "age", "demographics of intakes", "formal"),
    **block(47, AGES, "age", "demographics of intakes", "informal"),
    **block(56, RACES, "race/ethnicity", "demographics of intakes", "formal"),
    **block(64, RACES, "race/ethnicity", "demographics of intakes", "informal"),
    73: ("enrolled in school", "education", "demographics of intakes", "formal"),
    74: ("enrolled in school", "education", "demographics of intakes", "informal"),
    # II criminal prosecutions (transfers to adult court)
    **block(76, ["automatic", "discretionary"], "transfer", "criminal prosecutions"),
    # III admissions during month to active caseload, by petition type
    **block(81, PETITION_TYPES, "case type", "admissions", "formal"),
    **block(89, PETITION_TYPES, "case type", "admissions", "informal"),
    # V intakes completed
    **block(98, ["full", "partial"], "intakes", "intakes"),
    # VI restitution and fees
    102: ("new cases ordered restit", "rest and fees", "rest and fees", "all"),
    103: ("amount restit ordered", "rest and fees", "rest and fees", "all"),
    104: ("new cases ordered to pay fees", "rest and fees", "rest and fees", "all"),
    # VII court ordered programs
    **block(106, ["alcohol", "drug", "alc and drug", "youth service agency", "mental health", "alternative ed",
                  "TASC", "UDIS", "JTPA", "other"], "programs ordered", "programs ordered"),
    # VIII placements
    **block(119, ["in state", "out of state"], "beginning", "placements"),
    **block(123, ["foster home", "group home", "residential treatment", "with relative"], "ordered", "placements", "in state"),
    128: ("removed", "removed", "placements", "in state"),
    **block(130, ["foster home", "group home", "residential treatment", "with relative"], "ordered", "placements", "out of state"),
    135: ("removed", "removed", "placements", "out of state"),
    **block(137, ["in state", "out of state"], "end of month", "placements"),
    # IX active caseload
    **block(142, CASE_TYPES, "first-of-month", "population FOM"),
    **block(149, CASE_TYPES, "new cases", "new cases"),
    **block(156, CASE_TYPES, "readmit admin", "readmit admin"),
    **block(163, CASE_TYPES, "transferred in", "transferred in"),
    **block(178, CASE_TYPES, "scheduled termination", "discharge"),
    **block(185, CASE_TYPES, "early termination", "discharge"),
    **block(192, CASE_TYPES, "absconder/warrant", "discharge"),
    **block(199, CASE_TYPES, "revoked-technical", "discharge"),
    **block(206, CASE_TYPES, "revoked-new", "discharge"),
    **block(213, CASE_TYPES, "alt djj commit", "discharge"),
    **block(220, CASE_TYPES, "unsatisfactory", "discharge"),
    **block(227, CASE_TYPES, "transferred", "discharge"),
    **block(234, CASE_TYPES, "other", "discharge"),
    **block(248, CASE_TYPES, "end-of-month", "population EOM"),
    # X commitments to DJJ
    **block(255, ["full", "evaluation", "habitual juvenile offender", "violent juvenile offender"],
            "djj commitments", "djj commitments"),
    # XI interstate cases
    261: ("interstate", "interstate", "interstate", "all"),
    # XII administrative caseload
    263: ("active", "admin", "population", "all"),
    264: ("inactive", "admin", "population", "all"),
    # XIII classification of active caseload: case type x supervision level (= the active caseload)
    **{267 + 6 * i + j: (f"{t} {lvl}", "active", "population", "all")
       for i, t in enumerate(CASE_TYPES) for j, lvl in enumerate(LEVELS)},
    # XIV investigations completed
    **block(305, ["social history", "adoption", "contested custody", "supplemental social history",
                  "intake screen", "other"], "investigations", "investigations"),
    # XV violations reported, XVI court action on violations
    **block(313, ["technical", "new offense"], "reported violations", "reported violations"),
    317: ("technical", "no revocation", "court actions", "all"),
    318: ("technical", "revocation", "court actions", "all"),
    320: ("new offense", "no revocation", "court actions", "all"),
    321: ("new offense", "revocation", "court actions", "all"),
    # XVII home detention / electronic monitoring
    **block(325, ["electronic", "non-electronic"], "ordered", "home detention", "pre-disposition"),
    **block(329, ["electronic", "non-electronic"], "end of month", "home detention", "pre-disposition"),
    **block(333, ["electronic", "non-electronic"], "ordered", "home detention", "post-disposition"),
    **block(337, ["electronic", "non-electronic"], "end of month", "home detention", "post-disposition"),
}

# a few label checks so a wrong offset fails loudly
EXPECT = {2: "1. Delinquency", 33: "1a. Male/Formal", 39: "12-under", 56: "1) American Indian",
          81: "A. Delinquency", 98: "FULL", 142: "a. Probation", 178: "a. Probation", 248: "a. Probation",
          255: "A. Full", 263: "Active", 267: "a. Maximum", 291: "a. Maximum", 305: "A. Social History",
          313: "Technical", 317: "No Vio. Tech.", 325: "a.1) Electronic Monitor Ordered",
          337: "a.2) Electronic Monitor Total EOM"}


def main():
    path, sheet = REFERENCE
    raw = pd.ExcelFile(path).parse(sheet, header=None)
    labels = raw.iloc[:, 0].map(lambda v: "" if pd.isna(v) else str(v)).tolist()
    start = next(i for i, l in enumerate(labels) if "JUVENILE COURT ACTIVITY" in l)
    labels = labels[start:]
    for off, text in EXPECT.items():
        assert labels[off].strip() == text, f"row {off}: expected {text!r}, sheet has {labels[off]!r}"
    rows = []
    for off, label in enumerate(labels):
        metric, breakdown, category, subgroup = KEYS.get(off, ("", "", "", ""))
        rows.append(dict(metric=metric, breakdown=breakdown, breakdown_category=category, subgroup=subgroup,
                         label=label))
    out = pd.DataFrame(rows)
    out.to_csv(JUVENILE_MAP_FILE, index=False)
    print(f"{JUVENILE_MAP_FILE}: {len(out)} rows, {(out['metric'] != '').sum()} with a metric")


if __name__ == "__main__":
    main()
