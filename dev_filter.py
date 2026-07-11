"""File filter used by watchfiles during dashboard development."""

from pathlib import Path

WATCHED_EXTENSIONS = {".py", ".html", ".css", ".js"}


def dashboard_file_filter(change, path: str) -> bool:
    """Restart only for dashboard source-file changes."""
    return Path(path).suffix.lower() in WATCHED_EXTENSIONS
