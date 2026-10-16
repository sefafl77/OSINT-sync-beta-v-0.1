"""Offline integration checks for the actual Codex stdio tool server.

Uses synthetic indicators and a temporary audit store. Never calls a vendor/model API.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "intel_engine" / "harness"
LAUNCH = (
    "import sys; sys.path.insert(0,sys.argv[1]); import mcp_server as m; "
    "m.audit.ROOT=sys.argv[2]; m._serve()"
)


class Client:
    def __init__(self, directory):
        env = dict(os.environ, PYTHONIOENCODING="cp1252", HARNESS_HOSTILE="1",
                   HARNESS_STRUCT_RETRIES="invalid-api-setting", HARNESS_HTTP_TIMEOUT="invalid-api-setting")
        self.p = subprocess.Popen(
            [sys.executable, "-c", LAUNCH, str(HARNESS), str(directory)],
            cwd=REPO, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
        self.responses = queue.Queue()
        self.errors = []
        self.counter = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        threading.Thread(target=lambda: self.errors.extend(self.p.stderr.readlines()), daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            try:
                self.responses.put(json.loads(line))
            except ValueError:
                self.responses.put({"not_json": line})

    def request(self, method, params=None):
        self.counter += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.counter,
                                      "method": method, "params": params or {}}, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        try:
            response = self.responses.get(timeout=8)
        except queue.Empty:
            raise AssertionError("MCP response timed out: " + "".join(self.errors)[-1200:])
        if response.get("id") != self.counter:
            raise AssertionError(f"Unexpected response: {response}")
        return response

    def close(self):
        if self.p.stdin:
            self.p.stdin.close()
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait(timeout=5)
        self.reader.join(timeout=1)
        self.p.stdout.close()
        self.p.stderr.close()


class CodexNativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = Client(self.temp.name)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def call(self, name, args):
        return self.client.request("tools/call", {"name": name, "arguments": args})["result"]

    def test_registry_and_protocol(self):
        result = self.client.request("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        tools = {t["name"]: t for t in self.client.request("tools/list")["result"]["tools"]}
        self.assertGreaterEqual(len(tools), 80)
        self.assertTrue(tools["search_pivot"]["annotations"]["readOnlyHint"])
        self.assertEqual(tools["hash_id"]["inputSchema"]["properties"]["hashes"]["type"], "string")

    def test_real_offline_tools_and_unicode(self):
        result = self.call("hash_id", {"hashes": "0" * 64, "case": "CASE-0001"})
        self.assertFalse(result["isError"])
        self.assertIn("SHA-256", json.dumps(result))
        result = self.call("search_pivot", {"indicator": "café contoh", "case": "CASE-0001"})
        self.assertFalse(result["isError"], result)
        self.assertIn("café", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("cafÃ", json.dumps(result, ensure_ascii=False))

    def test_invalid_arguments_are_actionable(self):
        for args in ({}, {"hashes": []}, {"hashes": "0" * 64, "context": "wrong"}):
            result = self.call("hash_id", args)
            self.assertTrue(result["isError"])
            text = " ".join(c.get("text", "") for c in result["content"])
            self.assertNotIn("KeyError", text)
            self.assertNotIn("Traceback", text)
        self.assertEqual(self.client.request("ping")["result"], {})

    def test_policy_blocks_before_handler_and_records_denial(self):
        result = self.call("pivot_extract", {"url": "https://site-a.example", "case": "CASE-0001"})
        self.assertTrue(result["isError"])
        ledger = Path(self.temp.name) / "cases" / "CASE-0001" / "tool_calls.jsonl"
        record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["decision"], "DENY")
        self.assertEqual(record["backend"], "codex")

    def test_case_path_cannot_escape_store(self):
        result = self.call("search_pivot", {"indicator": "example.com", "case": "../outside"})
        self.assertTrue(result["isError"])
        self.assertFalse((Path(self.temp.name) / "outside").exists())

    def test_case_scope_limits_spending_and_egress_independently(self):
        directory = Path(self.temp.name) / "cases" / "CASE-0001"
        directory.mkdir(parents=True)
        (directory / "scope.json").write_text(json.dumps({
            "target_class": "unknown", "constraints": {"no_direct_contact": True, "no_spend": True}
        }), encoding="utf-8")
        result = self.call("pivot_extract", {"url": "https://site-a.example", "case": "CASE-0001", "passive": True})
        self.assertTrue(result["isError"])
        self.assertIn("free_only", json.dumps(result))
        result = self.call("pivot_extract", {"url": "https://site-a.example", "case": "CASE-0001", "free_only": True})
        self.assertTrue(result["isError"])
        self.assertIn("egress", json.dumps(result))

    def test_guided_case_asks_target_and_goal_without_search(self):
        first = self.call("guided_case", {})
        self.assertEqual(first["structuredContent"]["status"], "need_target")
        second = self.call("guided_case", {"target": "Example Person"})
        self.assertEqual(second["structuredContent"]["status"], "need_purpose")
        third = self.call("guided_case", {"target": "Example Person", "purpose": "Public-source verification"})
        self.assertEqual(third["structuredContent"]["status"], "ready")
        self.assertFalse(third["structuredContent"]["network_started"])

    def test_corrupt_case_scope_refuses_to_continue(self):
        directory = Path(self.temp.name) / "cases" / "CASE-0001"
        directory.mkdir(parents=True)
        (directory / "scope.json").write_text("broken", encoding="utf-8")
        result = self.call("pivot_extract", {"url": "https://site-a.example", "case": "CASE-0001"})
        self.assertTrue(result["isError"])
        self.assertIn("scope.json", json.dumps(result))

    def test_bad_jsonrpc_request_does_not_kill_server(self):
        response = self.client.request("tools/call", ["not an object"])
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(self.client.request("ping")["result"], {})

    def test_eof_drains_outstanding_responses(self):
        requests = "\n".join(json.dumps({"jsonrpc": "2.0", "id": i, "method": "tools/list"})
                             for i in range(1, 4)) + "\n"
        completed = subprocess.run(
            [sys.executable, "-c", LAUNCH, str(HARNESS), self.temp.name],
            cwd=REPO, input=requests, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(s) for s in completed.stdout.splitlines() if s.strip()]
        self.assertEqual({r["id"] for r in responses}, {1, 2, 3})
        self.assertNotIn("Task was destroyed", completed.stderr)

    def test_default_harness_cli_has_no_traceback(self):
        env = dict(os.environ, HARNESS_BACKEND="codex", PYTHONUTF8="1")
        completed = subprocess.run(
            [sys.executable, str(HARNESS / "cli.py"), "open", "CASE-0001", "example.com"],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertIn("Codex", completed.stdout + completed.stderr)


if __name__ == "__main__":
    program = unittest.main(verbosity=2, exit=False)
    raise SystemExit(not program.result.wasSuccessful())
