"""
Justice Counts upload files (the old aoic_clean_legacy.py), one CSV per metric in
<OUT_DIR>/justice_counts/.

Same categories as the BJA export but built from the circuit "Total" sheets, plus the
county sheet for circuits that have a single court and no total sheet, plus Cook.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import COOK_CIRCUIT, OUT_DIR        # noqa: E402
from extract import read_table                  # noqa: E402
from exports.bja import aggregate, categorize   # noqa: E402


def circuit_level(df: pd.DataFrame) -> pd.DataFrame:
    totals = df.loc[df["is_total"]]
    courts_per_circuit = df.loc[~df["is_total"]].groupby(["circuit", "year"])["court"].nunique()
    single = courts_per_circuit[courts_per_circuit == 1].index
    keyed = pd.MultiIndex.from_frame(df[["circuit", "year"]])
    add = df.loc[~df["is_total"] & (keyed.isin(single) | (df["circuit"] == COOK_CIRCUIT))]
    return pd.concat([totals, add], ignore_index=True)


def export(df: pd.DataFrame | None = None) -> Path:
    df = read_table() if df is None else df
    result = aggregate(categorize(circuit_level(df)))
    result = result.drop(columns=["system"]).assign(agency="PROBATION")
    out = OUT_DIR / "justice_counts"
    out.mkdir(parents=True, exist_ok=True)
    for m, part in result.groupby("metric"):
        part.to_csv(out / f"{m}.csv", index=False)
    print(f"  justice_counts: {', '.join(sorted(result['metric'].unique()))} -> {out}")
    return out


if __name__ == "__main__":
    export()
