"""
BJA / Justice Counts submission: statewide monthly totals and breakdowns per metric.

Built from the county sheets (circuit "Total" sheets excluded so nothing is counted
twice). Writes one CSV per metric to <OUT_DIR>/bja/.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR                      # noqa: E402
from extract import read_table                  # noqa: E402
from exports.mappings import BREAKDOWNS, METRICS  # noqa: E402

SYSTEM, AGENCY = "PROBATION", "Illinois Department of Corrections"


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
    out["system"], out["agency"] = SYSTEM, AGENCY
    cols = ["month", "year", "metric", "value", "breakdown_category", "breakdown", "system", "agency"]
    return out[cols].sort_values(["metric", "breakdown_category", "breakdown", "year", "month"],
                                 na_position="first")


def export(df: pd.DataFrame | None = None) -> Path:
    df = read_table() if df is None else df
    result = aggregate(categorize(df.loc[~df["is_total"]]))
    out = OUT_DIR / "bja"
    out.mkdir(parents=True, exist_ok=True)
    for m, part in result.groupby("metric"):
        part.to_csv(out / f"{m}.csv", index=False)
    print(f"  bja: {', '.join(sorted(result['metric'].unique()))} -> {out}")
    return out


if __name__ == "__main__":
    export()
