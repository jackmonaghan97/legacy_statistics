"""
Parse the downloaded workbooks into one long table and load it into DuckDB.

Every adult sheet follows the same 13-column monthly template (label, Jan..Dec, YTD),
~305 rows from the "I. INTAKES" line down. probation_map.csv is that template with
four label columns prepended (metric, breakdown, breakdown_category, felony), so row
n of a sheet gets row n's labels. Because that is positional, every sheet's labels are
compared with the template's and a sheet that drifts is skipped and reported instead
of being loaded with wrong labels.

Table: aoic_legacy_probation
    circuit, court, county, is_total, year, month, metric, breakdown,
    breakdown_category, felony, label, value
"""
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config import DB_PATH, MANIFEST, MAP_FILE, OUT_DIR, TABLE

KEY_COLS = ["metric", "breakdown", "breakdown_category", "felony"]
MONTHS = list(range(1, 13))
MAX_LABEL_MISMATCH = 15     # rows; more than this and the sheet is not the template


def load_map() -> pd.DataFrame:
    """Template rows from 'I. INTAKES' down: the four key columns plus the template label."""
    m = pd.read_csv(MAP_FILE, header=None, skiprows=1, usecols=range(5))
    m.columns = KEY_COLS + ["label"]
    for c in KEY_COLS:
        m[c] = m[c].str.strip()      # the map has e.g. 'felony ' with a trailing space
    start = m.index[m["label"].astype(str).str.contains("INTAKES", na=False)][0]
    return m.iloc[start:].reset_index(drop=True)


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9<>]", "", str(s).lower())


# department names that differ from the census county spelling
COUNTY_SPELLING = {"DeWitt": "De Witt", "JoDaviess": "Jo Daviess"}


def county_name(court: str) -> str:
    """'St. Clair Adult' -> 'St. Clair'; 'Cook Social' -> 'Cook'; census spellings applied."""
    name = re.sub(r"\s*(Adult|Social)$", "", court).strip()     # 'OgleAdult' exists too
    return COUNTY_SPELLING.get(name, name)


def adult_sheets(names: list[str]) -> list[str]:
    keep = [s for s in names if "Adult" in s or "Cook Social" in s]
    return [s for s in keep if not any(x in s for x in ("Pretrial", "IPS", "DUI"))]


def parse_sheet(xl: pd.ExcelFile, sheet: str, key: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """One sheet -> long rows for every template row that has a metric; also the mismatch count."""
    raw = xl.parse(sheet, header=None)
    first = raw.index[raw.iloc[:, 0].astype(str).str.contains("INTAKES", na=False)]
    if first.empty:
        raise ValueError("no INTAKES row")
    block = raw.iloc[first[0]:first[0] + len(key), :14].reset_index(drop=True)
    block = block.reindex(range(len(key)))                       # pad a short sheet with NaN rows
    block.columns = ["label"] + MONTHS + ["ytd"]

    mismatches = int((block["label"].map(_norm) != key["label"].map(_norm)).sum())

    df = pd.concat([key[KEY_COLS], block], axis=1)
    df = df.loc[df[KEY_COLS].notna().any(axis=1)]                # rows that carry a metric
    for c in MONTHS + ["ytd"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")           # '#REF!', blanks -> NaN
    long = df.melt(id_vars=KEY_COLS + ["label"], value_vars=MONTHS, var_name="month", value_name="value")
    return long, mismatches


def parse_workbook(entry: dict, key: pd.DataFrame, log: list) -> pd.DataFrame:
    xl = pd.ExcelFile(entry["file"])
    frames = []
    for sheet in adult_sheets(xl.sheet_names):
        # most sheets are "2024 Alexander Adult"; a few Cook / St. Clair / Rock Island
        # sheets carry no year prefix, so only strip the first token when it is a year
        first, _, rest = sheet.partition(" ")
        year, court = (int(first), rest) if re.fullmatch(r"\d{4}", first) else (int(entry["year"]), sheet)
        try:
            long, mism = parse_sheet(xl, sheet, key)
        except ValueError as e:
            log.append(dict(year=year, circuit=entry["circuit"], sheet=sheet, rows=0, label_mismatches=None,
                            status=f"skipped: {e}"))
            continue
        if mism > MAX_LABEL_MISMATCH:
            log.append(dict(year=year, circuit=entry["circuit"], sheet=sheet, rows=0, label_mismatches=mism,
                            status="skipped: labels do not match the template"))
            continue
        is_total = bool(re.search(r"total|compil", court, flags=re.I))
        long.insert(0, "circuit", entry["circuit"])
        long.insert(1, "court", court)
        long.insert(2, "county", None if is_total else county_name(court))
        long.insert(3, "is_total", is_total)
        long.insert(4, "year", year)
        frames.append(long)
        log.append(dict(year=year, circuit=entry["circuit"], sheet=sheet, rows=len(long), label_mismatches=mism,
                        status="ok"))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def extract(manifest: pd.DataFrame | None = None) -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST) if manifest is None else manifest
    key = load_map()
    frames, log = [], []
    for year, group in manifest.groupby("year"):
        for entry in group.to_dict("records"):
            if not Path(entry["file"]).exists():
                log.append(dict(year=year, circuit=entry["circuit"], sheet=entry["title"], rows=0,
                                label_mismatches=None, status="skipped: workbook not downloaded"))
                continue
            frames.append(parse_workbook(entry, key, log))
        n_ok = sum(1 for l in log if l["year"] == year and l["status"] == "ok")
        n_skip = sum(1 for l in log if l["year"] == year and l["status"] != "ok")
        print(f"  {year}: {n_ok} sheets loaded" + (f", {n_skip} skipped" if n_skip else ""), flush=True)
    df = pd.concat(frames, ignore_index=True)
    df = df.astype({"circuit": int, "year": int, "month": int, "value": float,
                    **{c: "string" for c in KEY_COLS + ["court", "county", "label"]}})
    df = df[["circuit", "court", "county", "is_total", "year", "month",
             "metric", "breakdown", "breakdown_category", "felony", "label", "value"]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(log).to_csv(OUT_DIR / "extract_log.csv", index=False)
    skipped = [l for l in log if l["status"] != "ok"]
    if skipped:
        print(f"  {len(skipped)} sheet(s) skipped - see {OUT_DIR / 'extract_log.csv'}")
    return df


def load(df: pd.DataFrame) -> None:
    con = duckdb.connect(DB_PATH)
    con.register("aoic_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {TABLE} AS SELECT * FROM aoic_df")
    n, y0, y1 = con.execute(f"SELECT COUNT(*), MIN(year), MAX(year) FROM {TABLE}").fetchone()
    con.close()
    df.to_csv(OUT_DIR / f"{TABLE}.csv", index=False)
    print(f"  {TABLE}: {n:,} rows, {y0}-{y1}  (DuckDB + {OUT_DIR / (TABLE + '.csv')})")


def read_table() -> pd.DataFrame:
    """The loaded table, for the export scripts."""
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(f"SELECT * FROM {TABLE}").df()
    finally:
        con.close()


if __name__ == "__main__":
    load(extract())
