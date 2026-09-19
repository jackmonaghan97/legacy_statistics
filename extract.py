"""
Parse the downloaded workbooks into one long table per program and load it into DuckDB.

Every sheet follows a 13-column monthly template (label, Jan..Dec, YTD): ~305 rows from
the "I. INTAKES" line down for adult sheets, ~340 rows from "I. JUVENILE COURT ACTIVITY"
down for juvenile sheets. probation_map.csv / juvenile_map.csv are those templates with
four label columns prepended (metric, breakdown, breakdown_category, felony | subgroup),
so row n of a sheet gets row n's labels. Because that is positional, every sheet's labels
are compared with the template's and a sheet that drifts is skipped and reported instead
of being loaded with wrong labels.

Tables
    aoic_legacy_probation   circuit, court, county, is_total, year, month, metric, breakdown,
                            breakdown_category, felony, label, value
    aoic_legacy_juvenile    same, with `subgroup` (formal / informal / in state / ...) in place of felony
"""
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config import DB_PATH, JUVENILE_MAP_FILE, JUVENILE_TABLE, MANIFEST, MAP_FILE, OUT_DIR, TABLE

MONTHS = list(range(1, 13))


@dataclass(frozen=True)
class Program:
    name: str
    table: str
    map_file: Path
    key_cols: tuple[str, ...]      # the four key columns, in map-file order
    anchor: str                    # text of the template's first row (also found in every sheet)
    sheet_word: str                # sheet names that carry this program's reports
    max_mismatch: int              # label rows allowed to differ; more and the sheet is not the template


ADULT = Program("adult", TABLE, MAP_FILE, ("metric", "breakdown", "breakdown_category", "felony"),
                "INTAKES", "Adult", max_mismatch=15)
# the juvenile circuit-total sheets reword 17 labels ("Total:" for "Subtotal:", ...) without moving a row
JUVENILE = Program("juvenile", JUVENILE_TABLE, JUVENILE_MAP_FILE,
                   ("metric", "breakdown", "breakdown_category", "subgroup"), "JUVENILE COURT ACTIVITY", "Juvenile",
                   max_mismatch=20)
PROGRAMS = {"adult": ADULT, "juvenile": JUVENILE}


def load_map(program: Program = ADULT) -> pd.DataFrame:
    """Template rows from the anchor line down: the four key columns plus the template label."""
    m = pd.read_csv(program.map_file, header=None, skiprows=1, usecols=range(5))
    m.columns = list(program.key_cols) + ["label"]
    for c in program.key_cols:
        m[c] = m[c].str.strip()      # the adult map has e.g. 'felony ' with a trailing space
    start = m.index[m["label"].astype(str).str.contains(program.anchor, na=False)][0]
    return m.iloc[start:].reset_index(drop=True)


def _norm(s) -> str:
    """Label text reduced to letters / digits; a blank cell and a blank template row compare equal."""
    return "" if pd.isna(s) else re.sub(r"[^a-z0-9<>]", "", str(s).lower())


# department names that differ from the census county spelling
COUNTY_SPELLING = {"DeWitt": "De Witt", "JoDaviess": "Jo Daviess"}


def county_name(court: str) -> str:
    """'St. Clair Adult' -> 'St. Clair'; 'Cook Social' -> 'Cook'; census spellings applied."""
    name = re.sub(r"\s*(Adult|Social|Juvenile)$", "", court).strip()     # 'OgleAdult' exists too
    return COUNTY_SPELLING.get(name, name)


def program_sheets(names: list[str], program: Program) -> list[str]:
    """Sheets carrying this program's monthly reports (Cook Social Service files an adult form)."""
    keep = [s for s in names if program.sheet_word in s or (program is ADULT and "Cook Social" in s)]
    return [s for s in keep if not any(x in s for x in ("Pretrial", "IPS", "DUI"))]


def parse_sheet(xl: pd.ExcelFile, sheet: str, key: pd.DataFrame, program: Program) -> tuple[pd.DataFrame, int]:
    """One sheet -> long rows for every template row that has a metric; also the mismatch count."""
    key_cols = list(program.key_cols)
    raw = xl.parse(sheet, header=None)
    first = raw.index[raw.iloc[:, 0].astype(str).str.contains(program.anchor, na=False)]
    if first.empty:
        raise ValueError(f"no {program.anchor} row")
    block = raw.iloc[first[0]:first[0] + len(key), :14].reset_index(drop=True)
    block = block.reindex(range(len(key)))                       # pad a short sheet with NaN rows
    block.columns = ["label"] + MONTHS + ["ytd"]

    mismatches = int((block["label"].map(_norm) != key["label"].map(_norm)).sum())

    df = pd.concat([key[key_cols], block], axis=1)
    df = df.loc[df[key_cols].notna().any(axis=1)]                # rows that carry a metric
    for c in MONTHS + ["ytd"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")           # '#REF!', blanks -> NaN
    long = df.melt(id_vars=key_cols + ["label"], value_vars=MONTHS, var_name="month", value_name="value")
    return long, mismatches


def parse_workbook(entry: dict, key: pd.DataFrame, log: list, program: Program) -> pd.DataFrame:
    xl = pd.ExcelFile(entry["file"])
    frames = []
    for sheet in program_sheets(xl.sheet_names, program):
        # most sheets are "2024 Alexander Adult"; a few Cook / St. Clair / Rock Island
        # sheets carry no year prefix, so only strip the first token when it is a year
        first, _, rest = sheet.partition(" ")
        year, court = (int(first), rest) if re.fullmatch(r"\d{4}", first) else (int(entry["year"]), sheet)
        try:
            long, mism = parse_sheet(xl, sheet, key, program)
        except ValueError as e:
            log.append(dict(year=year, circuit=entry["circuit"], sheet=sheet, rows=0, label_mismatches=None,
                            status=f"skipped: {e}"))
            continue
        if mism > program.max_mismatch:
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


def extract(manifest: pd.DataFrame | None = None, program: Program = ADULT) -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST) if manifest is None else manifest
    key = load_map(program)
    key_cols = list(program.key_cols)
    frames, log = [], []
    for year, group in manifest.groupby("year"):
        for entry in group.to_dict("records"):
            if not Path(entry["file"]).exists():
                log.append(dict(year=year, circuit=entry["circuit"], sheet=entry["title"], rows=0,
                                label_mismatches=None, status="skipped: workbook not downloaded"))
                continue
            frames.append(parse_workbook(entry, key, log, program))
        n_ok = sum(1 for l in log if l["year"] == year and l["status"] == "ok")
        n_skip = sum(1 for l in log if l["year"] == year and l["status"] != "ok")
        print(f"  {year}: {n_ok} {program.name} sheets loaded" + (f", {n_skip} skipped" if n_skip else ""), flush=True)
    df = pd.concat(frames, ignore_index=True)
    df = df.astype({"circuit": int, "year": int, "month": int, "value": float,
                    **{c: "string" for c in key_cols + ["court", "county", "label"]}})
    df = df[["circuit", "court", "county", "is_total", "year", "month", *key_cols, "label", "value"]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = OUT_DIR / ("extract_log.csv" if program is ADULT else f"extract_log_{program.name}.csv")
    pd.DataFrame(log).to_csv(log_file, index=False)
    skipped = [l for l in log if l["status"] != "ok"]
    if skipped:
        print(f"  {len(skipped)} sheet(s) skipped - see {log_file}")
    return df


def load(df: pd.DataFrame, program: Program = ADULT) -> None:
    """Write the CSV copy, then replace the DuckDB table (skipped, with a note, if the file is locked)."""
    csv = OUT_DIR / f"{program.table}.csv"
    df.to_csv(csv, index=False)
    try:
        con = duckdb.connect(DB_PATH)
    except duckdb.IOException as e:
        print(f"  !! DuckDB not updated ({str(e).splitlines()[0]}); CSV written to {csv} - rerun once the file is free")
        return
    con.register("aoic_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {program.table} AS SELECT * FROM aoic_df")
    n, y0, y1 = con.execute(f"SELECT COUNT(*), MIN(year), MAX(year) FROM {program.table}").fetchone()
    con.close()
    print(f"  {program.table}: {n:,} rows, {y0}-{y1}  (DuckDB + {csv})")


def read_table(program: Program = ADULT) -> pd.DataFrame:
    """The loaded table, for the export scripts."""
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(f"SELECT * FROM {program.table}").df()
    finally:
        con.close()


if __name__ == "__main__":
    for p in PROGRAMS.values():
        load(extract(program=p), p)
