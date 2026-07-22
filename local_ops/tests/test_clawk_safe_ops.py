#!/usr/bin/env python3
import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "local_ops" / "clawk-safe-ops"
HERMES = REPO_ROOT / "hermes_lite" / "hermes_lite.py"


class TestClawkSafeOps(unittest.TestCase):
    def run_cmd(self, args, timeout=20):
        return subprocess.run(
            args,
            cwd=REPO_ROOT,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_files_exist(self):
        self.assertTrue(WRAPPER.exists(), "local_ops/clawk-safe-ops is missing")
        self.assertTrue(HERMES.exists(), "hermes_lite/hermes_lite.py is missing")

    def test_python_compile(self):
        result = self.run_cmd(["python3", "-m", "py_compile", str(HERMES)])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_whoami_executes(self):
        result = self.run_cmd([str(WRAPPER), "qué usuario soy"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STATUS=executed", result.stdout)
        self.assertIn("INTENCION=whoami", result.stdout)

    def test_json_output_is_valid(self):
        result = self.run_cmd([str(WRAPPER), "--json", "qué usuario soy"])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("status"), "executed")
        self.assertEqual(data.get("intent"), "whoami")

    def test_dangerous_request_is_blocked(self):
        result = self.run_cmd([str(WRAPPER), "usa sudo para leer /root/.ssh/id_rsa"])
        self.assertIn("STATUS=blocked", result.stdout)

    def test_portable_data_dir(self):
        result = self.run_cmd([str(WRAPPER), "lista los archivos de datos de hermes"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STATUS=executed", result.stdout)
        self.assertNotIn("Permission denied", result.stdout + result.stderr)

    def test_system_health_json_is_valid(self):
        result = self.run_cmd([
            str(REPO_ROOT / "local_ops" / "system-health"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn(data.get("status"), ["ok", "warning", "degraded"])
        self.assertIn("memory", data)
        self.assertIn("disk_root", data)
        self.assertIn("system", data)

    def test_service_status_json_is_valid(self):
        result = self.run_cmd([
            str(REPO_ROOT / "local_ops" / "service-status"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("services", data)

    def test_service_status_blocks_unallowlisted_service(self):
        result = self.run_cmd([
            str(REPO_ROOT / "local_ops" / "service-status"),
            "nginx-no-autorizado",
            "--json",
        ])
        self.assertNotEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("status"), "blocked")

    def test_client_report_json_is_valid_and_sanitized(self):
        result = self.run_cmd([
            str(REPO_ROOT / "local_ops" / "client-report"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn(data.get("overall_status"), ["ok", "warning", "degraded"])
        self.assertTrue(data.get("privacy", {}).get("safe_for_client"))
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("/opt/clawksis-agent", serialized)
        self.assertNotIn("repo_root", serialized)
        self.assertNotIn("changed_files", serialized)

    def test_weekly_sales_report_json_is_valid(self):
        result = self.run_cmd([
            str(REPO_ROOT / "business_ops" / "weekly-sales-report"),
            "--input",
            str(REPO_ROOT / "business_ops" / "examples" / "sample_sales.csv"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("report_type"), "weekly-sales-report")
        self.assertIn("summary", data)

    def test_customer_insights_json_is_valid(self):
        result = self.run_cmd([
            str(REPO_ROOT / "business_ops" / "customer-insights"),
            "--input",
            str(REPO_ROOT / "business_ops" / "examples" / "sample_sales.csv"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("report_type"), "customer-insights")
        self.assertIn("top_customers", data)
        self.assertIn("recommendations", data)

    def test_product_performance_json_is_valid(self):
        result = self.run_cmd([
            str(REPO_ROOT / "business_ops" / "product-performance"),
            "--input",
            str(REPO_ROOT / "business_ops" / "examples" / "sample_sales.csv"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("report_type"), "product-performance")
        self.assertIn("summary", data)
        self.assertIn("leaders", data)
        self.assertIn("recommendations", data)

    def test_sales_rep_performance_json_is_valid(self):
        result = self.run_cmd([
            str(REPO_ROOT / "business_ops" / "sales-rep-performance"),
            "--input",
            str(REPO_ROOT / "business_ops" / "examples" / "sample_sales.csv"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("report_type"), "sales-rep-performance")
        self.assertIn("summary", data)
        self.assertIn("leaders", data)
        self.assertIn("recommendations", data)

    def test_executive_summary_json_is_valid(self):
        result = self.run_cmd([
            str(REPO_ROOT / "business_ops" / "executive-summary"),
            "--input",
            str(REPO_ROOT / "business_ops" / "examples" / "sample_sales.csv"),
            "--json",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data.get("report_type"), "executive-summary")
        self.assertIn("summary", data)
        self.assertIn("risk_summary", data)
        self.assertIn("executive_recommendations", data)


if __name__ == "__main__":
    unittest.main()
