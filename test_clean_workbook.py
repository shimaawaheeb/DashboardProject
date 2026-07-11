from __future__ import annotations

import re
import unittest
from zipfile import ZipFile

import clean_workbook
import server


class CleanWorkbookTests(unittest.TestCase):
    def test_cleaner_preserves_excel_package_and_namespaces(self) -> None:
        results = clean_workbook.clean()
        self.assertIn("duplicate_emails_fixed", results)
        self.assertIn("task_statuses_fixed", results)
        self.assertGreaterEqual(results["duplicate_emails_fixed"], 0)
        self.assertGreaterEqual(results["task_statuses_fixed"], 0)

        with (
            ZipFile(clean_workbook.SOURCE) as source,
            ZipFile(clean_workbook.OUTPUT) as output,
        ):
            self.assertIsNone(output.testzip())
            self.assertEqual(source.namelist(), output.namelist())

            for name in {"xl/worksheets/sheet3.xml", "xl/worksheets/sheet5.xml"}:
                source_root = re.search(
                    rb"<worksheet\b[^>]*>", source.read(name)
                ).group()
                output_root = re.search(
                    rb"<worksheet\b[^>]*>", output.read(name)
                ).group()
                self.assertEqual(source_root, output_root)

    def test_cleaned_business_rules(self) -> None:
        tables = server.parse_workbook(clean_workbook.OUTPUT)["tables"]
        emails = [row["Email"].casefold() for row in tables["Employees"]]
        self.assertEqual(len(emails), len(set(emails)))
        self.assertFalse(
            any(
                row["Completion %"] == 100 and row["Status"] != "Completed"
                for row in tables["Tasks"]
            )
        )


if __name__ == "__main__":
    unittest.main()
