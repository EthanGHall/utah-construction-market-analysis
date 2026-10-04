"""Exercise real subprocess failures without changing the working repository.

Run with: python -m unittest discover -s tests -v
Only Python's standard library is needed, including the simulated chart failure.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATUS_FILES = {"validation_summary.json", "analysis_validation.csv"}


class AnalysisPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_directory = tempfile.TemporaryDirectory(prefix="utah-test-template-")
        cls.template = Path(cls.template_directory.name)
        for name in ("raw", "sources", "data", "scripts", "sql", "reports"):
            shutil.copytree(ROOT / name, cls.template / name)
        result = subprocess.run(
            [sys.executable, str(cls.template / "scripts/analyze.py"), "--skip-charts"],
            cwd=cls.template, capture_output=True, text=True,
        )
        if result.returncode:
            cls.template_directory.cleanup()
            raise AssertionError(f"Initial valid rebuild failed:\n{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.template_directory.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="utah-publication-test-")
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name) / "repo"
        shutil.copytree(self.template, self.repo)
        self.previous_reports = self.report_hashes()
        self.previous_run = self.status()["run"]["id"]

    def report_hashes(self):
        return {
            str(path.relative_to(self.repo / "reports")): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (self.repo / "reports").rglob("*")
            if path.is_file() and path.name not in STATUS_FILES
        }

    def status(self):
        return json.loads((self.repo / "reports/validation_summary.json").read_text())

    def run_analysis(self, charts=False):
        command = [sys.executable, str(self.repo / "scripts/analyze.py")]
        if not charts:
            command.append("--skip-charts")
        return subprocess.run(command, cwd=self.repo, capture_output=True, text=True)

    def assert_failure(self, result, expected_error):
        self.assertNotEqual(result.returncode, 0)
        status = self.status()
        self.assertEqual(status["status"], "FAIL")
        self.assertIn(expected_error, status["error"])
        self.assertNotEqual(status["run"]["id"], self.previous_run)
        self.assertIn("finished_at_utc", status["run"])
        self.assertTrue(any(item["status"] == "FAIL" for item in status["checks"]))
        with (self.repo / "reports/analysis_validation.csv").open(newline="") as handle:
            self.assertTrue(any(row["status"] == "FAIL" for row in csv.DictReader(handle)))
        self.assertEqual(self.report_hashes(), self.previous_reports)
        self.assertEqual(list((self.repo / "work").glob("analysis-*")), [])

    def assert_recovery(self):
        failed_run = self.status()["run"]["id"]
        result = self.run_analysis()
        self.assertEqual(result.returncode, 0, result.stderr)
        status = self.status()
        self.assertEqual(status["status"], "PASS")
        self.assertNotEqual(status["run"]["id"], failed_run)
        self.assertEqual(status["quality"]["analysis_checks_passed"], 15)
        self.assertEqual(status["quality"]["sql_python_numeric_comparisons"], 4347)
        self.assertTrue(all(item["status"] == "PASS" for item in status["checks"]))
        self.assertEqual(self.report_hashes(), self.previous_reports)

    def test_sql_failure_preserves_correct_reports_and_recovers(self):
        path = self.repo / "sql/01_annual_metrics.sql"
        original = path.read_text()
        incorrect = original.replace(
            "total_units - prior_year_units AS yoy_units_change",
            "total_units + prior_year_units AS yoy_units_change",
        )
        self.assertNotEqual(incorrect, original)
        path.write_text(incorrect)
        self.assert_failure(self.run_analysis(), "SQL annual mismatch")
        with (self.repo / "reports/annual_metrics.csv").open(newline="") as handle:
            beaver = next(row for row in csv.DictReader(handle)
                          if row["year"] == "2021" and row["county_fips5"] == "49001")
        self.assertEqual(beaver["yoy_units_change"], "20")
        path.write_text(original)
        self.assert_recovery()

    def test_source_checksum_failure_preserves_reports_and_recovers(self):
        path = self.repo / "raw/county/co2025a.txt"
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        self.assert_failure(self.run_analysis(), "Preserved sources match download checksums")
        path.write_bytes(original)
        self.assert_recovery()

    def test_invalid_manifest_before_first_check_records_failure_and_recovers(self):
        path = self.repo / "sources/download_manifest.json"
        original = path.read_bytes()
        path.write_text("not JSON")
        self.assert_failure(self.run_analysis(), "JSONDecodeError")
        path.write_bytes(original)
        self.assert_recovery()

    def test_preparation_exception_observes_running_then_failure_and_recovers(self):
        path = self.repo / "scripts/prepare_data.py"
        original = path.read_text()
        failing = original.replace(
            "return [int(value) for value in cells]",
            "status = json.loads((BASE / 'reports/validation_summary.json').read_text())['status']\n"
            "    (BASE / 'work/status-during-preparation.txt').write_text(status)\n"
            "    raise ValueError('injected parsing failure')",
        )
        self.assertNotEqual(failing, original)
        path.write_text(failing)
        self.assert_failure(self.run_analysis(), "injected parsing failure")
        self.assertEqual((self.repo / "work/status-during-preparation.txt").read_text(), "RUNNING")
        path.write_text(original)
        self.assert_recovery()

    def test_chart_failure_after_validation_preserves_reports_and_recovers(self):
        path = self.repo / "scripts/analyze.py"
        original = path.read_text()
        failing = original.replace(
            "def plot_charts(metrics, summary, reports=REPORTS):",
            "def plot_charts(metrics, summary, reports=REPORTS):\n"
            "    raise RuntimeError('injected chart failure')",
        )
        self.assertNotEqual(failing, original)
        path.write_text(failing)
        self.assert_failure(self.run_analysis(charts=True), "injected chart failure")
        self.assertTrue(self.status()["run"]["charts_requested"])
        self.assertEqual(sum(item["status"] == "PASS" for item in self.status()["checks"]), 15)
        path.write_text(original)
        self.assert_recovery()

    def test_success_replaces_outdated_report_and_records_completed_run(self):
        (self.repo / "reports/annual_metrics.csv").write_text("outdated report")
        self.assert_recovery()
        self.assertFalse(self.status()["run"]["charts_requested"])
        self.assertIn("finished_at_utc", self.status()["run"])


if __name__ == "__main__":
    unittest.main()
