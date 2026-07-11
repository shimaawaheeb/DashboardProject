from __future__ import annotations

import socket
import unittest

import server
from assistant import (
    DashboardAssistant,
    GeminiError,
    calculate_kpis,
    classify_gemini_http_error,
    filter_tables,
    is_in_scope,
)


class DashboardAssistantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workbook = server.parse_workbook(server.WORKBOOK)
        cls.tables = cls.workbook["tables"]

    def test_kpis_are_calculated_from_workbook(self) -> None:
        kpis = calculate_kpis(self.tables)
        self.assertEqual(kpis["portfolio"]["total_projects"], len(self.tables["Projects"]))
        self.assertEqual(kpis["delivery"]["total_tasks"], len(self.tables["Tasks"]))
        self.assertEqual(
            kpis["workforce"]["employee_records"], len(self.tables["Employees"])
        )

    def test_department_filter_limits_project_linked_tables(self) -> None:
        department = self.tables["Departments"][0]["Department Name"]
        filtered = filter_tables(self.tables, department)
        self.assertTrue(filtered["Projects"])
        self.assertTrue(all(row["Department"] == department for row in filtered["Projects"]))
        project_ids = {row["Project ID"] for row in filtered["Projects"]}
        self.assertTrue(
            all(row["Project ID"] in project_ids for row in filtered["Tasks"])
        )

    def test_dashboard_question_is_in_scope(self) -> None:
        self.assertTrue(
            is_in_scope("Which projects have blocked tasks?", [], self.tables)
        )

    def test_unrelated_question_is_refused_without_api_key(self) -> None:
        assistant = DashboardAssistant()
        assistant.api_key = None
        response, status = assistant.answer(
            "How do I bake a cake?", [], self.workbook, "All", "overview"
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["source"], "refusal")

    def test_missing_key_has_actionable_error(self) -> None:
        assistant = DashboardAssistant()
        assistant.api_key = None
        with self.assertRaises(GeminiError) as raised:
            assistant.answer(
                "What is the total project budget?",
                [],
                self.workbook,
                "All",
                "overview",
            )
        self.assertEqual(raised.exception.kind, "authentication")
        self.assertEqual(
            raised.exception.user_message,
            "The AI Assistant is not configured correctly. "
            "Please contact the administrator.",
        )

    def test_gemini_errors_have_specific_safe_messages(self) -> None:
        cases = {
            "authentication": (
                "The AI Assistant is not configured correctly. "
                "Please contact the administrator."
            ),
            "rate_limit": (
                "The AI Assistant is temporarily unavailable due to usage limits. "
                "Please try again later."
            ),
            "provider": (
                "The AI Assistant is temporarily unavailable. "
                "Please check your connection or try again later."
            ),
        }
        for kind, expected_message in cases.items():
            with self.subTest(kind=kind):
                error = GeminiError(kind, "private provider diagnostic")
                self.assertEqual(expected_message, error.user_message)
                self.assertNotIn("private provider diagnostic", error.user_message)

    def test_http_errors_are_classified_into_public_categories(self) -> None:
        self.assertEqual(classify_gemini_http_error(401, ""), "authentication")
        self.assertEqual(
            classify_gemini_http_error(400, "API key not valid"),
            "authentication",
        )
        self.assertEqual(classify_gemini_http_error(429, ""), "rate_limit")
        self.assertEqual(
            classify_gemini_http_error(403, "RESOURCE_EXHAUSTED: quota exceeded"),
            "rate_limit",
        )
        self.assertEqual(classify_gemini_http_error(503, ""), "provider")

    def test_server_does_not_fall_back_when_port_is_busy(self) -> None:
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            with self.assertRaises(OSError):
                server.create_server("127.0.0.1", port)

    def test_company_employee_email_gate_uses_workbook_employees(self) -> None:
        self.assertTrue(
            server.is_company_employee_email(
                "employee1001@example.com",
                self.workbook,
            )
        )
        self.assertTrue(
            server.is_company_employee_email(
                "EMPLOYEE1002@EXAMPLE.COM",
                self.workbook,
            )
        )
        self.assertFalse(
            server.is_company_employee_email(
                "not-an-employee@example.com",
                self.workbook,
            )
        )


if __name__ == "__main__":
    unittest.main()
