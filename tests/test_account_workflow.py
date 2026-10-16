"""Offline behavior checks for sourced account reports and native Codex handoff."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "intel_engine" / "tools"))
sys.path.insert(0, str(REPO / "scripts"))
from guided import prepare, read_case
import account_report as reports
import start_codex


def research():
    return {"summary": "Akun publik terkonfirmasi; hubungan pemilik belum ditetapkan.",
            "accounts": [{"platform": "Example", "url": "https://social.example/example_user",
                          "handle": "example_user", "status": "confirmed", "detail": "Exact public handle.",
                          "evidence_ids": ["E1"]}],
            "evidence": [{"id": "E1", "url": "https://social.example/example_user",
                          "method": "direct_page", "retrieved_at": "2026-01-01T10:00:00Z",
                          "http_status": 200, "exists": True, "observed_handle": "example_user",
                          "excerpt": "Public profile @example_user"}],
            "coverage": [{"source": "username_enum", "status": "completed", "detail": "Seven endpoints."},
                         {"source": "native_web_search", "status": "completed", "detail": "Exact-handle queries searched."}],
            "observations": [{"text": "The page displays the requested handle.", "evidence_ids": ["E1"]}],
            "links": [], "gaps": [], "next_steps": []}


class AccountWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "engine"
        prepare("example_user", purpose="Review my own public accounts", case="CASE-0001", save=True, root=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_sourced_report_roundtrip_and_menu_visibility(self):
        result = reports.save_report("CASE-0001", research(), root=self.root)
        self.assertEqual(result["counts"]["confirmed"], 1)
        self.assertEqual(result["status"], "complete")
        for path in result["reports"].values():
            self.assertTrue(Path(path).is_file())
            self.assertTrue(Path(path).is_relative_to(self.root / "cases" / "CASE-0001"))
        markdown = Path(result["reports"]["markdown"]).read_text(encoding="utf-8")
        self.assertIn("| Platform | Hasil | Detail / bukti |", markdown)
        self.assertIn("https://social.example/example_user", markdown)
        self.assertIn("2026-01-01T10:00:00Z", markdown)
        menu = read_case("CASE-0001", self.root)
        self.assertEqual(menu["status"], "Hasil tersedia")
        self.assertEqual(menu["raw_count"], 1)
        self.assertIn("Akun publik", menu["summary"])

    def test_search_snippets_cannot_confirm_accounts(self):
        data = research()
        data["evidence"][0]["method"] = "search"
        result = reports.save_report("CASE-0001", data, root=self.root)
        self.assertEqual(result["counts"]["unverified"], 1)
        self.assertEqual(result["counts"]["confirmed"], 0)
        self.assertEqual(result["status"], "complete_with_gaps")

    def test_readable_native_source_without_http_code_can_confirm(self):
        data = research()
        data["evidence"][0].update(http_status=None, retrieval_succeeded=True)
        result = reports.save_report("CASE-0001", data, root=self.root)
        self.assertEqual(result["counts"]["confirmed"], 1)

    def test_another_profile_cannot_supply_confirmation(self):
        data = research()
        data["evidence"][0]["url"] = "https://other.example/example_user"
        result = reports.save_report("CASE-0001", data, root=self.root)
        self.assertEqual(result["counts"]["confirmed"], 0)

    def test_auth_failure_cannot_become_no_account(self):
        data = research()
        data["accounts"][0]["status"] = "not_found"
        data["evidence"][0].update(method="api", http_status=401, exists=False)
        result = reports.save_report("CASE-0001", data, root=self.root)
        self.assertEqual(result["counts"]["inconclusive"], 1)
        data["evidence"][0].update(http_status=404)
        definite = reports.save_report("CASE-0001", data, root=self.root)
        self.assertEqual(definite["counts"]["not_found"], 1)

    def test_missing_archive_snapshot_does_not_prove_missing_live_account(self):
        data = research()
        data["accounts"][0]["status"] = "not_found"
        data["evidence"][0].update(method="archive", http_status=404, exists=False)
        result = reports.save_report("CASE-0001", data, root=self.root)
        self.assertEqual(result["counts"]["inconclusive"], 1)

    def test_shared_handle_stays_hypothesis_but_direct_link_is_sourced(self):
        data = research()
        data["links"] = [{"from_url": data["accounts"][0]["url"],
                          "to_url": "https://second.example/example_user", "status": "confirmed",
                          "basis": "same_handle", "detail": "Matching handles only.", "evidence_ids": ["E1"]}]
        result = reports.save_report("CASE-0001", data, root=self.root)
        saved = json.loads(Path(result["reports"]["json"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["links"][0]["status"], "hypothesis")
        data["links"][0]["basis"] = "direct_link"
        data["evidence"][0]["excerpt"] += " https://second.example/example_user"
        result = reports.save_report("CASE-0001", data, root=self.root)
        saved = json.loads(Path(result["reports"]["json"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["links"][0]["status"], "confirmed")

    def test_versions_preserve_reports_and_handwritten_assessment(self):
        case = self.root / "cases" / "CASE-0001"
        assessment = case / "assessment.md"
        assessment.write_text("User-owned notes", encoding="utf-8")
        first = reports.save_report("CASE-0001", research(), root=self.root)
        original = Path(first["reports"]["markdown"]).read_bytes()
        second = reports.save_report("CASE-0001", research(), root=self.root)
        self.assertNotEqual(first["reports"]["markdown"], second["reports"]["markdown"])
        self.assertEqual(Path(first["reports"]["markdown"]).read_bytes(), original)
        self.assertEqual(assessment.read_text(encoding="utf-8"), "User-owned notes")

    def test_missing_search_coverage_is_explicitly_partial(self):
        data = research()
        data["coverage"] = data["coverage"][:1]
        result = reports.save_report("CASE-0001", data, root=self.root)
        self.assertEqual(result["status"], "complete_with_gaps")
        self.assertIn("native_web_search: belum selesai", result["markdown"])

    def test_invalid_evidence_and_traversal_do_not_write_reports(self):
        data = research()
        data["accounts"][0]["evidence_ids"] = ["E9"]
        with self.assertRaises(ValueError):
            reports.save_report("CASE-0001", data, root=self.root)
        with self.assertRaises(ValueError):
            reports.save_report("../escape", research(), root=self.root)
        self.assertFalse((self.root / "cases" / "CASE-0001" / "report").exists())

    def test_registered_mcp_flow_returns_readable_report_and_artifacts(self):
        sys.path.insert(0, str(REPO / "intel_engine" / "harness"))
        import mcp_server as server
        with mock.patch.object(server.audit, "ROOT", str(self.root)), mock.patch.object(server.T, "ROOT", str(self.root)):
            result = asyncio.run(server._call_tool("account_report", {
                "case": "CASE-0001", "report_json": json.dumps(research())}))
        self.assertFalse(result["isError"], result)
        self.assertIn("| Platform | Hasil | Detail / bukti |", result["content"][0]["text"])
        self.assertTrue(Path(result["structuredContent"]["reports"]["markdown"]).is_file())
        self.assertIn('"backend": "codex"', (self.root / "cases" / "CASE-0001" / "tool_calls.jsonl").read_text())

    def test_native_launch_uses_search_and_preserves_target_as_data(self):
        repo = Path(self.temp.name) / "project"
        skill = repo / ".agents" / "skills" / "cti" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("Synthetic skill", encoding="utf-8")
        seed = 'example_user & echo x $(echo x)'
        with mock.patch.object(start_codex, "project_server", return_value=({"command": "python"}, "ready")), \
             mock.patch.object(start_codex, "codex_command", return_value=["codex.exe"]):
            args = start_codex.launch_args(seed, repo=repo)
        self.assertIn("--search", args)
        self.assertNotIn("exec", args)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
        self.assertIn(json.dumps({"target": seed, "case": ""}), args[-1])
        with mock.patch.object(start_codex, "launch_args", return_value=args), \
             mock.patch.object(start_codex.sys.stdin, "isatty", return_value=True), \
             mock.patch.object(start_codex.sys.stdout, "isatty", return_value=True), \
             mock.patch.object(start_codex.subprocess, "call", return_value=0) as run:
            self.assertEqual(start_codex.main([seed]), 0)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.args[0], args)


if __name__ == "__main__":
    program = unittest.main(verbosity=2, exit=False)
    raise SystemExit(not program.result.wasSuccessful())
