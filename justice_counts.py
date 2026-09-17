"""
Justice Counts / BJA exports: statewide monthly totals and breakdowns for the five JC
metrics, one CSV per metric. The same categorisation feeds two products that differ
only in which sheets they count and the agency columns they carry:

    <OUT_DIR>/bja/             county sheets (circuit "Total" sheets excluded so nothing
                               is counted twice); system + agency columns for the BJA form
    <OUT_DIR>/justice_counts/  circuit "Total" sheets, plus the county sheet for circuits
                               with a single court and no total sheet, plus Cook;
                               agency = PROBATION (the old aoic_clean_legacy.py upload files)

    python justice_counts.py   # write both from the table already in DuckDB
"""
import pandas as pd

from config import COOK_CIRCUIT, OUT_DIR
from extract import read_table

# template breakdown_category -> (JC metric, JC breakdown_category name)
METRICS = {
    "population":          ("population",  "supervision_type"),
    "discharge":           ("discharges",  "discharges_type"),
    "reported violations": ("violations",  "violation_type"),
    "court actions":       ("revocations", "revocations_type"),
    "new cases":           ("new_cases",   "case_type"),
}

# how the template's raw breakdowns roll up into JC categories. Keyed by
# breakdown_category because 'technical' / 'new offense' mean different things under
# revocations and under reported violations.
BREAKDOWNS = {
    "population": {
        "active":          "People on Active Supervision",
        "home confinment": "People on Active Supervision",
        "supervision":     "People on Active Supervision",
        "admin":           "People on Administrative Supervision",
    },
    "discharge": {
        "scheduled termination": "Successful Discharges from Supervision",
        "early termination":     "Successful Discharges from Supervision",
        "revoked-new":           "Unsuccessful Discharges from Supervision",
        "revoked-technical":     "Unsuccessful Discharges from Supervision",
        "absconder/warrant":     "Unsuccessful Discharges from Supervision",
        "alt doc commit":        "Unsuccessful Discharges from Supervision",
        "unsatisfactory":        "Unsuccessful Discharges from Supervision",
        "conditional disch":     "Neutral Discharges from Supervision",
        "transferred":           "Other Discharges from Supervision",
        "other":                 "Other Discharges from Supervision",
    },
    "court actions": {           # revocations: the template metric names the violation type
        "technical":   "Revocations for Technical Violations",
        "new offense": "Revocations for New Offenses",
    },
    "reported violations": {
        "technical":   "Technical Violations",
        "new offense": "New Offense Violations",
    },
}

COLS = ["month", "year", "metric", "value", "breakdown_category", "breakdown"]


# which sheets each product counts ------------------------------------------------

def county_level(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[~df["is_total"]]


def circuit_level(df: pd.DataFrame) -> pd.DataFrame:
    totals = df.loc[df["is_total"]]
    courts_per_circuit = df.loc[~df["is_total"]].groupby(["circuit", "year"])["court"].nunique()
    single = courts_per_circuit[courts_per_circuit == 1].index
    keyed = pd.MultiIndex.from_frame(df[["circuit", "year"]])
    add = df.loc[~df["is_total"] & (keyed.isin(single) | (df["circuit"] == COOK_CIRCUIT))]
    return pd.concat([totals, add], ignore_index=True)


# shared categorisation ----------------------------------------------------------

def categorize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep the five JC metrics and relabel each row with its JC metric / breakdown.
    Rows whose breakdown has no JC category (e.g. 'no revocation', 'inactive') are dropped.
    """
    df = df.loc[df["breakdown_category"].isin(METRICS)].copy()
    df = df.loc[df["metric"] != "inactive"]

    # court actions: metric holds the violation type; only the 'revocation' rows count
    ca = df["breakdown_category"] == "court actions"
    df = df.loc[~ca | (df["breakdown"] == "revocation")]
    df.loc[ca, "breakdown"] = df.loc[ca, "metric"]

    # reported violations: metric holds the violation type
    rv = df["breakdown_category"] == "reported violations"
    df.loc[rv, "breakdown"] = df.loc[rv, "metric"]

    df["jc_breakdown"] = [BREAKDOWNS.get(cat, {}).get(b) for cat, b in zip(df["breakdown_category"], df["breakdown"])]
    df["jc_metric"] = df["breakdown_category"].map(lambda c: METRICS[c][0])
    df["jc_category"] = df["breakdown_category"].map(lambda c: METRICS[c][1])

    # new cases are reported as a total only
    df.loc[df["jc_metric"] == "new_cases", "jc_breakdown"] = None
    # any other breakdown without a JC category is left out of the breakdown rows
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Statewide totals per metric-month, plus one row per JC breakdown."""
    totals = (df.groupby(["year", "month", "jc_metric"], as_index=False)["value"].sum()
                .rename(columns={"jc_metric": "metric"}))
    bd = df.loc[df["jc_breakdown"].notna()]
    breakdowns = (bd.groupby(["year", "month", "jc_metric", "jc_category", "jc_breakdown"], as_index=False)["value"].sum()
                    .rename(columns={"jc_metric": "metric", "jc_category": "breakdown_category",
                                     "jc_breakdown": "breakdown"}))
    out = pd.concat([totals, breakdowns], ignore_index=True)
    return out[COLS].sort_values(["metric", "breakdown_category", "breakdown", "year", "month"],
                                 na_position="first")


# the two products ---------------------------------------------------------------

def write(result: pd.DataFrame, folder: str) -> None:
    out = OUT_DIR / folder
    out.mkdir(parents=True, exist_ok=True)
    for m, part in result.groupby("metric"):
        part.to_csv(out / f"{m}.csv", index=False)
    print(f"  {folder}: {', '.join(sorted(result['metric'].unique()))} -> {out}")


def export(df: pd.DataFrame | None = None) -> None:
    df = read_table() if df is None else df
    write(aggregate(categorize(county_level(df)))
          .assign(system="PROBATION", agency="Illinois Department of Corrections"), "bja")
    write(aggregate(categorize(circuit_level(df)))
          .assign(agency="PROBATION"), "justice_counts")


if __name__ == "__main__":
    export()
