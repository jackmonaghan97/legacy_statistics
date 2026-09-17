"""
Tableau extracts (the old Tableau Pushes/): county-level rows with a month_year date.

    probation_population.csv  county rows for the five JC categories, joined to the
                              county's census population (illinois_demo in DuckDB)
    probation_intakes.csv     county intake rows (intakes + demographics of intakes)

Both go to <OUT_DIR>/tableau/.
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DB_PATH, OUT_DIR             # noqa: E402
from extract import read_table                  # noqa: E402

INCLUDE = ["discharge", "population", "new cases", "court actions", "reported violations"]


def county_population() -> pd.DataFrame:
    """
    Total residents per county and year from the ACS table. Race rows are mutually
    exclusive except HISPANIC_OR_LATINO (an ethnicity that overlaps them), so it is
    left out of the sum.
    """
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        pop = con.execute("""
            SELECT REPLACE(county_name, ' County, Illinois', '') AS county, year,
                   SUM(TRY_CAST(value AS DOUBLE)) AS gen_population
            FROM illinois_demo
            WHERE race <> 'HISPANIC_OR_LATINO' AND year IS NOT NULL
            GROUP BY 1, 2""").df()
    finally:
        con.close()
    return pop


def _month_year(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))


def _title(s: pd.Series) -> pd.Series:
    return s.str[:1].str.upper() + s.str[1:].str.lower()


def population_extract(df: pd.DataFrame) -> pd.DataFrame:
    d = df.loc[~df["is_total"] & df["breakdown_category"].isin(INCLUDE)].copy()
    d["state"] = "Illinois"
    pop = county_population()
    # probation years past the last ACS year use the nearest ACS year
    d["census_year"] = d["year"].clip(int(pop["year"].min()), int(pop["year"].max()))
    d = d.merge(pop, left_on=["county", "census_year"], right_on=["county", "year"], how="left",
                suffixes=("", "_acs")).drop(columns=["year_acs"])
    d["county_name"] = d["county"] + " County"
    d["month_year"] = _month_year(d)
    return d.drop(columns=["month", "year", "label"])


def intakes_extract(df: pd.DataFrame) -> pd.DataFrame:
    d = df.loc[~df["is_total"] & df["breakdown_category"].str.contains("intakes", na=False)].copy()
    d["metric"], d["breakdown"] = _title(d["metric"]), _title(d["breakdown"])
    d["state"], d["county_name"] = "Illinois", d["county"] + " County"
    d["month_year"] = _month_year(d)
    return d.drop(columns=["month", "year", "label"])


def export(df: pd.DataFrame | None = None) -> Path:
    df = read_table() if df is None else df
    out = OUT_DIR / "tableau"
    out.mkdir(parents=True, exist_ok=True)
    population_extract(df).to_csv(out / "probation_population.csv", index=False)
    intakes_extract(df).to_csv(out / "probation_intakes.csv", index=False)
    print(f"  tableau: probation_population.csv, probation_intakes.csv -> {out}")
    return out


if __name__ == "__main__":
    export()
