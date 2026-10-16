"""Local Codex MCP configuration and offline health checks. No model calls."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def project_server(repo: Path = REPO):
    path = Path(repo) / ".codex" / "config.toml"
    if not path.is_file():
        return None, "Config MCP belum dibuat. Jalankan scripts/install-codex.ps1."
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        server = data.get("mcp_servers", {}).get("intel_harness")
        if not isinstance(server, dict):
            return None, "Config belum memiliki server intel_harness."
        if server.get("enabled") is False:
            return None, "Server intel_harness sedang dinonaktifkan di config."
        command = server.get("command", "")
        args = server.get("args", [])
        expected = (Path(repo) / "intel_engine" / "harness" / "mcp_server.py").resolve()
        if not expected.is_file():
            return None, "File tool server tidak ditemukan di repo ini."
        if not isinstance(command, str) or not command or not (Path(command).is_file() or shutil.which(command)):
            return None, "Interpreter di config tidak ditemukan. Jalankan ulang installer Codex."
        if not isinstance(args, list) or not any(
                isinstance(a, str) and Path(a).resolve() == expected for a in args):
            return None, "Path tool server di config tidak sesuai dengan folder repo ini."
        if Path(server.get("cwd", repo)).resolve() != Path(repo).resolve():
            return None, "Folder kerja MCP tidak sesuai. Jalankan ulang installer Codex."
        return server, "Config lokal sesuai; koneksi dari aplikasi diperiksa saat project dibuka."
    except ImportError:
        return None, "Setup Codex native memerlukan Python 3.11+ untuk membaca config TOML."
    except (OSError, ValueError, TypeError) as exc:
        return None, f"Config MCP belum valid: {exc}"


def configure(repo: Path, python: Path):
    """Update only our server block; retain unrelated settings and back up a changed config."""
    import tomllib
    repo, python = Path(repo).resolve(), Path(python).resolve()
    path = repo / ".codex" / "config.toml"
    if path.is_symlink():
        raise ValueError("Config berupa symlink. Gunakan config lokal di folder repo.")
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    parsed = tomllib.loads(text)
    old = parsed.get("mcp_servers", {}).get("intel_harness", {})
    if not isinstance(old, dict):
        raise ValueError("Entry intel_harness harus berupa tabel config MCP.")
    if not python.is_file() or not (repo / "intel_engine" / "harness" / "mcp_server.py").is_file():
        raise ValueError("Interpreter atau file tool server tidak ditemukan; config belum diubah.")
    for key in ("startup_timeout_sec", "tool_timeout_sec"):
        if key in old and (type(old[key]) not in (int, float) or old[key] <= 0):
            raise ValueError(f"{key} harus berupa angka positif; config belum diubah.")
    if old.get("url"):
        raise ValueError("intel_harness sudah memakai URL remote. Ganti nama entry tersebut sebelum setup lokal.")
    values = {
        "command": str(python),
        "args": ["-X", "utf8", str(repo / "intel_engine" / "harness" / "mcp_server.py")],
        "cwd": str(repo),
        "startup_timeout_sec": old.get("startup_timeout_sec", 30),
        "tool_timeout_sec": max(old.get("tool_timeout_sec", 0), 1900),
    }
    pattern = (r"(?ms)^[ \t]*\[mcp_servers\.(?:intel_harness|\"intel_harness\"|'intel_harness')\]"
               r"[^\n]*\n(.*?)(?=^[ \t]*\[|\Z)")
    match = re.search(pattern, text)
    body = match.group(1) if match else ""
    for key, value in values.items():
        line = f"{key} = {json.dumps(value, ensure_ascii=False)}"
        if re.search(rf"(?m)^[ \t]*{key}[ \t]*=", body):
            body = re.sub(rf"(?m)^[ \t]*{key}[ \t]*=.*$", lambda _: line, body)
        else:
            body = body.rstrip() + ("\n" if body.strip() else "") + line + "\n"
    block = "[mcp_servers.intel_harness]\n" + body.rstrip() + "\n\n"
    updated = text[:match.start()] + block + text[match.end():] if match else text.rstrip() + "\n\n" + block
    if "web_search" not in parsed:
        updated = 'web_search = "live"\n' + updated.lstrip("\n")
    tomllib.loads(updated)
    if updated == text:
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, path.with_name(path.name + ".bak-" + stamp))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        f.write(updated)
        temp = Path(f.name)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path, True


def health(repo: Path = REPO, *, probe=True):
    """Required local checks plus optional feature dependencies. Never query a target."""
    checks = []
    def add(label, ready, detail, required=True):
        checks.append({"label": label, "ok": bool(ready), "detail": detail, "required": required})
    add("Python", sys.version_info >= (3, 11), sys.version.split()[0] + " (Codex native: 3.11+)")
    for package in ("pydantic", "rich", "docx", "networkx"):
        add(package, importlib.util.find_spec(package) is not None,
            "Terpasang" if importlib.util.find_spec(package) else "Jalankan installer Codex.")
    server, message = project_server(repo)
    add("Config MCP", server is not None, message)
    add("Skill CTI native", (Path(repo) / ".agents" / "skills" / "cti" / "SKILL.md").is_file(),
        "Skill lokal untuk pencarian, verifikasi sumber, dan laporan.")
    add("Codex CLI", bool(shutil.which("codex.exe") or shutil.which("codex")),
        "Untuk launcher terminal; Codex app juga dapat memakai $cti-expert:cti.", False)
    if server and probe:
        requests = "\n".join(json.dumps({"jsonrpc": "2.0", "id": i, "method": method,
                                        "params": {"protocolVersion": "2025-06-18"} if i == 1 else {}})
                             for i, method in ((1, "initialize"), (2, "tools/list"))) + "\n"
        try:
            result = subprocess.run([server["command"], *server.get("args", [])],
                                    cwd=server.get("cwd", repo), input=requests,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            count = next((len(r.get("result", {}).get("tools", [])) for r in replies if r.get("id") == 2), 0)
            ready = result.returncode == 0 and count >= 80
            add("Tool server", ready, f"{count} tool ditemukan lewat MCP; tanpa pencarian target."
                if ready else "Server belum merespons dengan benar. Jalankan ulang installer Codex.")
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            add("Tool server", False, f"Server belum siap: {exc}")
    for command, feature in (("pandoc", "PDF/DOCX lanjutan"), ("xelatex", "PDF melalui LaTeX"),
                             ("dot", "Diagram Graphviz")):
        add(feature, shutil.which(command) is not None,
            "Tersedia" if shutil.which(command) else "Opsional; fitur ini belum tersedia.", False)
    return {"ok": all(c["ok"] for c in checks if c["required"]), "checks": checks,
            "note": "Tes ini memeriksa runtime lokal. Akses dan kuota layanan OSINT belum diuji."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("configure")
    setup.add_argument("--repo", type=Path, default=REPO)
    setup.add_argument("--python", type=Path, default=Path(sys.executable))
    sub.add_parser("doctor")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            path, changed = configure(args.repo, args.python)
            print(f"Config MCP {'diperbarui' if changed else 'sudah sesuai'}: {path}")
            return 0
        status = health()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["ok"] else 1
    except (OSError, ValueError, ImportError) as exc:
        print(f"Setup belum selesai: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
