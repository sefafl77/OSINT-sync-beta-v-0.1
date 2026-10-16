"""Behavioural tests for guided intake, readable results, and local Codex setup."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "intel_engine" / "tools"))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "intel_engine" / "harness"))
import guided
from codex_runtime import configure, project_server
from result_view import present


class GuidedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_intake_asks_one_next_question_without_writing(self):
        self.assertEqual(guided.prepare(root=self.root)["status"], "need_target")
        data = guided.prepare("Example Person", root=self.root)
        self.assertEqual(data["status"], "need_purpose")
        self.assertFalse(data["network_started"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_case_saved_once_in_single_store_with_scope(self):
        data = guided.prepare("Example Person", purpose="Public-source verification", save=True,
                              case="CASE-0001", root=self.root)
        path = self.root / "cases" / "CASE-0001"
        self.assertEqual(Path(data["request_path"]).parent, path)
        self.assertFalse(data["network_started"])
        scope = json.loads((path / "scope.json").read_text(encoding="utf-8"))
        self.assertTrue(scope["constraints"]["no_direct_contact"])
        self.assertTrue(scope["constraints"]["no_spend"])
        before = (path / "request.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "sudah ada"):
            guided.prepare("Other Person", purpose="Test", save=True, case="CASE-0001", root=self.root)
        self.assertEqual(before, (path / "request.json").read_bytes())
        self.assertEqual(guided.read_case("CASE-0001", self.root)["raw_count"], 0)
        self.assertIn("Siap dilanjutkan", guided.read_case("CASE-0001", self.root)["status"])

    def test_validation_and_windows_names(self):
        for value in ("../escape", "..", "CON", "a/b", "x."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                guided.case_path(value, self.root)
        for value, kind in (("", "name"), ("line\nbreak", "name"), ("bad@email", "email"),
                            ("https://user:password@example.com", "domain"), ("invalid", "ip")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                guided.validate_target(value, kind)
        self.assertEqual(guided.validate_target("Contoh café", "name"), ("Contoh café", "name"))
        self.assertEqual(guided.validate_target("@example_user", "username")[0], "example_user")

    def test_interactive_wizard_and_cancel(self):
        original = guided.prepare
        output = io.StringIO()
        with mock.patch.object(guided, "prepare", side_effect=lambda *a, **kw: original(*a, **kw, root=self.root)):
            with mock.patch("builtins.input", side_effect=["Example Person", "3", "Check public footprint", "", "y"]):
                with redirect_stdout(output):
                    guided.wizard(guided.Screen())
        self.assertIn("Langkah 4/4", output.getvalue())
        self.assertIn("Pengumpulan belum dijalankan", output.getvalue())
        self.assertEqual(len(list((self.root / "cases").glob("*/request.json"))), 1)

    def test_bare_username_wrong_kind_keeps_target_and_explains_detection(self):
        original = guided.prepare
        output = io.StringIO()
        answers = ["example_user", "1", "4", "Check public footprint", "My own public handle", "n"]
        with mock.patch.object(guided, "prepare", side_effect=lambda *a, **kw: original(*a, **kw, root=self.root)):
            with mock.patch("builtins.input", side_effect=answers):
                with redirect_stdout(output):
                    guided.wizard(guided.Screen())
        rendered = output.getvalue()
        self.assertIn("Jenis yang terdeteksi: Username / handle (nomor 4)", rendered)
        self.assertIn("Jenis ini tidak cocok dengan 'example_user'", rendered)
        self.assertEqual(rendered.count("Langkah 1/4"), 1)
        self.assertIn("example_user", rendered)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cli_preview_demo_and_clean_eof(self):
        for args, stdin in ((["--demo"], None), (["--wizard"], "0\n"), (["--wizard"], ""),
                            (["prepare", "--target", "Example Person", "--type", "name",
                              "--purpose", "Public-source verification", "--preview", "--json"], None)):
            result = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "cti.py"), *args],
                                    input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data["network_started"])
        self.assertNotIn("request_path", data)

    def test_unavailable_source_is_not_presented_as_complete(self):
        raw = {"results": [], "not_consulted": ["Provider needs configuration"]}
        result = present("threat_check", {"content": [{"type": "text", "text": json.dumps(raw)}], "isError": False})
        self.assertIn("belum lengkap", result["content"][0]["text"])
        self.assertIn("belum membuktikan target aman", result["content"][0]["text"])
        self.assertEqual(result["content"][1]["text"], json.dumps(raw))

    def test_corrupt_assessment_is_not_marked_complete(self):
        path = self.root / "cases" / "CASE-0001"
        path.mkdir(parents=True)
        (path / "assessment.json").write_text("broken", encoding="utf-8")
        data = guided.read_case("CASE-0001", self.root)
        self.assertNotEqual(data["status"], "Hasil tersedia")
        self.assertTrue(data["warning"])

    def test_nested_status_result_remains_readable_and_verbatim(self):
        text = json.dumps({"status": {"sources": 2}, "results": [{"source": "local"}]})
        result = present("case_frontier", {"content": [{"type": "text", "text": text}], "isError": False})
        self.assertIn("1 entri", result["content"][0]["text"])
        self.assertEqual(result["content"][1]["text"], text)

    def test_user_facing_files_keep_utf8_text(self):
        for name in ("README.md", "guides/START-HERE.id.md", "intel_engine/tools/guided.py"):
            text = (REPO / name).read_text(encoding="utf-8")
            for damaged in ("\u00c3\u00a2", "\u00c3\u0192", "\u00e2\u20ac\u201d"):
                self.assertNotIn(damaged, text, name)


class SetupTests(unittest.TestCase):
    def test_config_update_preserves_other_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "intel_engine" / "harness").mkdir(parents=True)
            (repo / "intel_engine" / "harness" / "mcp_server.py").write_text("", encoding="utf-8")
            path = repo / ".codex" / "config.toml"
            path.parent.mkdir()
            path.write_text('model = "user-choice"\n[mcp_servers.other]\ncommand = "unrelated"\n', encoding="utf-8")
            configure(repo, Path(sys.executable))
            before = path.read_text(encoding="utf-8")
            self.assertIn('model = "user-choice"', before)
            self.assertIn('[mcp_servers.other]', before)
            self.assertIsNotNone(project_server(repo)[0])
            _, changed = configure(repo, Path(sys.executable))
            self.assertFalse(changed)
            self.assertEqual(before, path.read_text(encoding="utf-8"))

    def test_invalid_config_and_remote_conflict_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            path = repo / ".codex" / "config.toml"
            path.parent.mkdir()
            for text in ('broken [', '[mcp_servers.intel_harness]\nurl = "https://example.com/mcp"\n'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    configure(repo, Path(sys.executable))
                self.assertEqual(path.read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    program = unittest.main(verbosity=2, exit=False)
    raise SystemExit(not program.result.wasSuccessful())
