"""Runtime paths and first-run data setup for local and Docker runs."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path("/tmp/dashboard-data") if os.getenv("VERCEL") else ROOT
DATA_DIR = Path(os.getenv("DASHBOARD_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()

SAMPLE_WORKBOOK = Path(
    os.getenv("SAMPLE_WORKBOOK_PATH", str(DATA_DIR / "sample_data.xlsx"))
).expanduser()
CLEANED_WORKBOOK = Path(
    os.getenv("CLEANED_WORKBOOK_PATH", str(DATA_DIR / "cleaned_data.xlsx"))
).expanduser()
TEMP_CLEANED_WORKBOOK = CLEANED_WORKBOOK.with_suffix(".tmp.xlsx")
AUTH_DB = Path(
    os.getenv("AUTH_DB_PATH", str(DATA_DIR / "dashboard_auth.sqlite3"))
).expanduser()


def configured_admin_emails() -> set[str]:
    raw = os.getenv("DEFAULT_ADMIN_EMAIL", "employee1001@example.com")
    return {
        email.strip().casefold()
        for email in raw.split(",")
        if email.strip()
    }


def ensure_runtime_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seeds = [
        (ROOT / "sample_data.xlsx", SAMPLE_WORKBOOK),
        (ROOT / "cleaned_data.xlsx", CLEANED_WORKBOOK),
    ]
    for source, target in seeds:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() and source.exists() and source.resolve() != target.resolve():
            shutil.copyfile(source, target)
