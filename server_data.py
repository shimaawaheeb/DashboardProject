"""Workbook parsing and employee-gate helpers shared by local and Vercel APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

EMPLOYEE_SIGNUP_ERROR = (
    "Sorry, you can not sign up because this email is not registered as a "
    "company employee."
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def excel_date(value: int | float) -> str:
    moment = datetime(1899, 12, 30) + timedelta(days=float(value))
    if moment.time() == datetime.min.time():
        return moment.date().isoformat()
    return moment.isoformat(timespec="minutes")


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        raise ValueError(f"Invalid cell reference: {reference}")
    result = 0
    for letter in letters.group():
        result = result * 26 + ord(letter) - 64
    return result - 1


def parse_workbook(path: Path) -> dict:
    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        try:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        except KeyError:
            shared_root = None
        if shared_root is not None:
            for item in shared_root.findall(f"{{{MAIN_NS}}}si"):
                shared_strings.append(
                    "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relationships}

        sheet_paths: dict[str, str] = {}
        sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
        if sheets is None:
            raise ValueError("Workbook contains no worksheets")
        for sheet in sheets:
            relationship_id = sheet.attrib[f"{{{REL_NS}}}id"]
            target = targets[relationship_id]
            sheet_paths[sheet.attrib["name"]] = (
                target.lstrip("/")
                if target.startswith("/xl/")
                else str(PurePosixPath("xl") / target)
            )

        def cell_value(cell: ET.Element):
            value_node = cell.find(f"{{{MAIN_NS}}}v")
            inline_node = cell.find(f"{{{MAIN_NS}}}is")
            cell_type = cell.attrib.get("t")
            if inline_node is not None:
                return "".join(
                    node.text or "" for node in inline_node.iter(f"{{{MAIN_NS}}}t")
                )
            if value_node is None:
                return None
            raw = value_node.text
            if cell_type == "s":
                return shared_strings[int(raw)]
            if cell_type == "b":
                return raw == "1"
            if cell_type in {"str", "e"}:
                return raw
            try:
                return float(raw) if "." in raw else int(raw)
            except (TypeError, ValueError):
                return raw

        date_fields = {
            "Employees": {"Hire Date"},
            "Projects": {"Start Date", "Target End Date"},
            "Tasks": {"Due Date"},
            "Meetings": {"Date/Time"},
            "Weekly Updates": {"Week Starting"},
            "Activity Log": {"Timestamp"},
        }
        source_sheets = [
            "Departments",
            "Employees",
            "Projects",
            "Tasks",
            "Meetings",
            "Weekly Updates",
            "Activity Log",
            "Lists",
        ]
        result: dict[str, list[dict]] = {}

        for sheet_name in source_sheets:
            root = ET.fromstring(archive.read(sheet_paths[sheet_name]))
            rows: list[list] = []
            for row_node in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
                cells: dict[int, object] = {}
                for cell in row_node.findall(f"{{{MAIN_NS}}}c"):
                    cells[column_index(cell.attrib["r"])] = cell_value(cell)
                if cells:
                    row = [None] * (max(cells) + 1)
                    for index, value in cells.items():
                        row[index] = value
                    rows.append(row)

            if not rows:
                result[sheet_name] = []
                continue

            headers = rows[0]
            records = []
            for row in rows[1:]:
                if not row or row[0] in (None, ""):
                    continue
                padded = row + [None] * (len(headers) - len(row))
                record = dict(zip(headers, padded))
                for field in date_fields.get(sheet_name, set()):
                    if record.get(field) is not None:
                        record[field] = excel_date(record[field])
                records.append(record)
            result[sheet_name] = records

    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return {
        "meta": {
            "source": path.name,
            "modifiedUtc": modified.isoformat(timespec="seconds"),
            "refreshedUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "tables": result,
    }


def company_employee_emails(workbook: dict) -> set[str]:
    return {
        str(row.get("Email", "")).strip().casefold()
        for row in workbook["tables"]["Employees"]
        if row.get("Email")
    }


def is_company_employee_email(email: str, workbook: dict | None = None) -> bool:
    from config import CLEANED_WORKBOOK

    workbook = workbook or parse_workbook(CLEANED_WORKBOOK)
    return email.strip().casefold() in company_employee_emails(workbook)
