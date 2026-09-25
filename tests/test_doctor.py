import asyncio
import unittest
from parallels_mcp.doctor import DoctorCheck, DoctorReport, check_host, run_doctor_report


class DoctorTests(unittest.TestCase):
    def test_check_host_structure(self) -> None:
        checks = asyncio.run(check_host())
        self.assertIsInstance(checks, list)
        self.assertTrue(len(checks) >= 4)
        names = {c.name for c in checks}
        self.assertIn("Host OS", names)
        self.assertIn("Python Version", names)
        self.assertIn("Parallels CLI", names)

    def test_run_doctor_report(self) -> None:
        report = asyncio.run(run_doctor_report())
        self.assertIsInstance(report, DoctorReport)
        self.assertIsInstance(report.host_checks, list)
        self.assertIsInstance(report.guest_checks, list)
        self.assertIsInstance(report.all_ok, bool)
