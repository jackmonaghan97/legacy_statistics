"""
Download the adult-probation workbooks from the AOIC aggregate-data site.

Each year page lists one Google Sheet per circuit ("1st Circuit" ... "24th Circuit",
"Cook Adult", "Cook Social Service", "Cook Juvenile"). The circuit workbooks hold the
adult, juvenile and pretrial sheets of every county. The sheet is fetched with the public export
endpoint, so no Google API or gdown is needed. Files already on disk are not fetched
again; delete a year's folder (or pass refresh=True) to re-download it.
"""
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import COOK_CIRCUIT, FIRST_YEAR, MANIFEST, RAW_DIR, SITE

CIRCUIT_RE = re.compile(r"^(\d+)(st|nd|rd|th) Circuit$")
COOK = {"Cook Adult": "cook_adult", "Cook Social Service": "cook_social", "Cook Juvenile": "cook_juvenile"}


def years_on_site() -> list[int]:
    html = requests.get(SITE, timeout=60).text
    found = {int(y) for y in re.findall(r"/data-home/(\d{4})-data", html)}
    return sorted(y for y in found if y >= FIRST_YEAR)


def workbooks_for(year: int) -> list[dict]:
    """(year, title, circuit, sheet id) for every circuit workbook linked from a year page."""
    soup = BeautifulSoup(requests.get(f"{SITE}/{year}-data", timeout=60).text, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.match(r"https://docs\.google\.com/spreadsheets/d/([\w-]+)", a["href"])
        if not m or m.group(1) in seen:
            continue
        title = a.get_text(" ", strip=True)
        if cm := CIRCUIT_RE.match(title):
            circuit, slug = int(cm.group(1)), f"circuit_{int(cm.group(1)):02d}"
        elif title in COOK:
            circuit, slug = COOK_CIRCUIT, COOK[title]
        else:
            continue  # statewide compilations, pretrial, BJS, ...
        seen.add(m.group(1))
        out.append(dict(year=year, title=title, circuit=circuit, sheet_id=m.group(1),
                        file=str(RAW_DIR / str(year) / f"{year}_{slug}.xlsx")))
    return out


def download(entry: dict, refresh: bool = False, tries: int = 4) -> Path | None:
    """Fetch one workbook; Google's export endpoint throws the odd 400, so retry with a pause."""
    path = Path(entry["file"])
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://docs.google.com/spreadsheets/d/{entry['sheet_id']}/export?format=xlsx"
    for attempt in range(1, tries + 1):
        r = requests.get(url, timeout=180)
        if r.ok and "spreadsheet" in r.headers.get("content-type", ""):
            path.write_bytes(r.content)
            return path
        time.sleep(3 * attempt)
    print(f"  !! {entry['year']} {entry['title']}: download failed ({r.status_code}) after {tries} tries")
    return None


def retrieve(years: list[int] | None = None, refresh: bool = False) -> pd.DataFrame:
    """Download every circuit workbook for the requested years; return the manifest."""
    years = years or years_on_site()
    rows = []
    for y in years:
        entries = workbooks_for(y)
        fetched = 0
        for e in entries:
            fetched += not Path(e["file"]).exists() or refresh
            e["downloaded"] = download(e, refresh) is not None
            rows.append(e)
        print(f"  {y}: {len(entries)} workbooks ({fetched} downloaded)", flush=True)
    new = pd.DataFrame(rows)
    # keep manifest rows for years not fetched this run, so a partial run still loads everything
    if MANIFEST.exists():
        old = pd.read_csv(MANIFEST)
        new = pd.concat([old.loc[~old["year"].isin(years)], new], ignore_index=True)
    manifest = new.sort_values(["year", "circuit", "title"]).reset_index(drop=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(MANIFEST, index=False)
    return manifest


if __name__ == "__main__":
    retrieve()
