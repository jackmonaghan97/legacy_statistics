# aoic_legacy

Pipeline for the AOIC (Administrative Office of the Illinois Courts) **legacy adult and
juvenile probation monthly statistics**: the annual Google Sheets workbooks published per
judicial circuit at
<https://sites.google.com/probation.illinoiscourts.gov/aggregatedata/data-home>,
2011 to the current year. Each circuit workbook holds one adult, one juvenile and one
pretrial sheet per county; Cook files separate Adult, Social Service and Juvenile workbooks.

```
site (one Google Sheet per circuit per year)
   │  retrieve.py    scrape each year page, export every circuit workbook as .xlsx
   ▼
data_backups/legacy_statistics/raw/<year>/*.xlsx   (+ manifest.csv)
   │  extract.py     parse the adult sheets with probation_map.csv and the juvenile
   │                 sheets with juvenile_map.csv -> one long table each
   ▼
DuckDB  aoic_legacy_probation, aoic_legacy_juvenile   (+ CSV copies in data_backups/legacy_statistics)
   │  justice_counts.py  statewide totals + breakdowns per JC metric, written twice:
   │                     bja/ from the county sheets, justice_counts/ from the circuit totals
   │  tableau.py         county-level extracts with census population
   ▼
data_backups/legacy_statistics/{bja,justice_counts,tableau}/*.csv
```

No database credentials are needed: the DuckDB file is local
(`config.DB_PATH`, the same one the IDOC projects use).

## Run

```
python run.py                     # download anything new, rebuild the table, write exports
python run.py --offline           # rebuild from the workbooks already downloaded
python run.py --years 2025 2026   # only (re)fetch those years; the load still uses all years
python run.py --refresh           # re-download workbooks already on disk
python run.py --program juvenile  # only the juvenile sheets (default: both)
```

If another program (DBeaver, the DuckDB CLI) holds the database file, the load is skipped
with a note and only the CSV copies are written; rerun once the file is free.

Requires `pandas duckdb requests beautifulsoup4 openpyxl` (all in `git_projects/.venv`).

## Files

| file | role |
|---|---|
| `config.py` | paths, table name, first year |
| `retrieve.py` | year pages -> circuit workbooks (`1st Circuit` ... `24th Circuit`, `Cook Adult`, `Cook Social Service`, `Cook Juvenile`); retries Google's flaky export endpoint; cached on disk |
| `extract.py` | sheet parsing, label check, DuckDB load (`CREATE OR REPLACE`); `Program` describes each template (ADULT, JUVENILE) |
| `probation_map.csv` | the adult monthly report template with `metric, breakdown, breakdown_category, felony` prepended to every row - row *n* of a sheet gets row *n*'s labels |
| `juvenile_map.csv` | the same for the juvenile template (`subgroup` = formal / informal / in state / ... in place of `felony`); regenerated from a reference sheet by `make_juvenile_map.py` |
| `justice_counts.py` | raw breakdowns -> Justice Counts categories (`METRICS`, `BREAKDOWNS`), and the `bja/` and `justice_counts/` CSVs built from them |
| `tableau.py` | the Tableau extracts, joined to `illinois_demo` for county population |
| `BJA Submission/data/` | outputs of the previous (Postgres) version, kept for comparison |

## The tables: `aoic_legacy_probation`, `aoic_legacy_juvenile`

| column | meaning |
|---|---|
| `circuit` | 1-24; Cook workbooks are 99 |
| `court` | sheet name minus the year, e.g. `Alexander Adult`, `Adult Total 1st`, `Cook Social` |
| `county` | county for a county sheet, null for a circuit total |
| `is_total` | true for the circuit "Total" sheets - exclude them when summing counties |
| `year`, `month` | calendar year and month (1-12) |
| `metric`, `breakdown`, `breakdown_category`, `felony` \| `subgroup` | labels from `probation_map.csv` / `juvenile_map.csv` |
| `label` | the row's text as printed in the sheet |
| `value` | the reported count; blank / `#REF!` cells are null (not -1) |

Sheets kept: names containing `Adult` or `Cook Social` (adult), `Juvenile` (juvenile),
minus `Pretrial`, `IPS` and `DUI`. The statewide compilation workbooks are not loaded.

Juvenile `breakdown_category` values: `petitions` (I.A), `court action` (I.B),
`demographics of intakes` (IV, subgroup formal / informal), `criminal prosecutions` (II),
`admissions` (III, by petition type), `intakes` (V), `rest and fees` (VI), `programs
ordered` (VII), `placements` (VIII), `population FOM` / `new cases` / `readmit admin` /
`transferred in` / `discharge` / `population EOM` (IX, metric = case type), `djj
commitments` (X), `interstate` (XI), `population` (XII admin + XIII classification, metric
= `<case type> <level>`), `investigations` (XIV), `reported violations` (XV), `court
actions` (XVI), `home detention` (XVII).

## Checks

- Because labelling is by row position, every sheet's labels are compared with the
  template. A sheet with more differing rows than the program allows (15 adult, 20
  juvenile - the juvenile circuit-total sheets reword 17 labels without moving a row) is
  skipped, not loaded wrong. Every sheet's outcome is in
  `data_backups/legacy_statistics/extract_log.csv` / `extract_log_juvenile.csv`.
- Three workbooks return HTTP 401 from Google's export endpoint (16th Circuit 2024, 9th
  Circuit 2025 and 2026): they are not publicly shared, so both programs lack those
  counties for those years until AOIC fixes the sharing.
- Workbooks that fail to download after four tries are listed in `manifest.csv`
  (`downloaded = False`) and skipped; run again to pick them up.

## Security

The previous version of these scripts embedded a Postgres password and the repo root
still holds an SSH key pair (`a`, `a.pub`). Both are in the git history on the remote.
They are now git-ignored, but the password and key should be rotated and the history
purged (`git filter-repo`).
