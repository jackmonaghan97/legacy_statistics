"""Paths and names shared by every step. No credentials live anywhere in this project."""
from pathlib import Path

# the same local DuckDB file the IDOC projects use
DB_PATH = r"C:\Users\jackm\OneDrive\Documents\duckdb_cli-windows-amd64\my_database.duckdb"
TABLE = "aoic_legacy_probation"            # adult sheets
JUVENILE_TABLE = "aoic_legacy_juvenile"    # juvenile sheets (same workbooks + the Cook Juvenile workbook)

# everything this pipeline writes lands here
OUT_DIR = Path(r"C:\Users\jackm\OneDrive\Documents\git_projects\data_backups\legacy_statistics")
RAW_DIR = OUT_DIR / "raw"            # downloaded workbooks, one folder per year
MANIFEST = RAW_DIR / "manifest.csv"  # which Google Sheet each workbook came from

# AOIC "aggregate data" site: one page per year, one Google Sheet per circuit
SITE = "https://sites.google.com/probation.illinoiscourts.gov/aggregatedata/data-home"
FIRST_YEAR = 2011

# row-position keys for the two monthly report templates (see README)
MAP_FILE = Path(__file__).resolve().parent / "probation_map.csv"
JUVENILE_MAP_FILE = Path(__file__).resolve().parent / "juvenile_map.csv"

# circuit codes used for the two Cook workbooks (kept from the original pipeline)
COOK_CIRCUIT = 99
