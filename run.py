"""
AOIC legacy adult-probation statistics: site -> DuckDB -> export CSVs.

    python run.py                  download new workbooks, rebuild the table, write exports
    python run.py --offline        skip the site, rebuild from the workbooks already on disk
    python run.py --years 2023 2024   only those years (download + load); exports still use all
    python run.py --refresh        re-download workbooks even if already on disk
    python run.py --program juvenile   only the juvenile sheets (default: both programs)
"""
import argparse

import pandas as pd

import extract
import justice_counts
import retrieve
import tableau
from config import MANIFEST, OUT_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use the workbooks already in the raw folder")
    ap.add_argument("--refresh", action="store_true", help="re-download workbooks that are already on disk")
    ap.add_argument("--years", nargs="*", type=int, help="restrict the download to these years")
    ap.add_argument("--program", choices=["adult", "juvenile", "both"], default="both",
                    help="which monthly-report sheets to extract")
    args = ap.parse_args()
    programs = [extract.ADULT, extract.JUVENILE] if args.program == "both" else [extract.PROGRAMS[args.program]]

    if args.offline:
        manifest = pd.read_csv(MANIFEST)
        print(f"Offline: {len(manifest)} workbooks in {MANIFEST.parent}")
    else:
        print("Retrieving workbooks from the AOIC site...")
        manifest = retrieve.retrieve(args.years, refresh=args.refresh)   # merged with years already on disk

    for program in programs:
        print(f"Extracting {program.name} sheets...")
        df = extract.extract(manifest, program)
        extract.load(df, program)
        if program is extract.ADULT:          # the BJA / Justice Counts / Tableau exports are adult-only
            print("Exporting...")
            justice_counts.export(df)
            tableau.export(df)
    print(f"Done -> {OUT_DIR}")


if __name__ == "__main__":
    main()
