"""Validate and save Codex's sourced public-account research. No network or model calls."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
from pathlib import Path
import re
import uuid
from urllib.parse import urlsplit

from guided import ENGINE, case_path

LABELS = {"confirmed": "Terkonfirmasi", "unverified": "Belum diverifikasi",
          "not_found": "Tidak ditemukan", "inconclusive": "Belum dapat dipastikan",
          "false_positive": "Kecocokan keliru"}
METHODS = {"direct_page", "api", "archive", "search", "enumeration"}
DIRECT = {"direct_page", "api", "archive"}


def _text(value, label, limit=5000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} harus berupa teks, maksimal {limit} karakter.")
    return value.strip()


def _url(value):
    value = _text(value, "URL", 4096)
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Sumber harus berupa URL HTTP/HTTPS tanpa kredensial.")
    if any(c.isspace() or c in '<>"' for c in value):
        raise ValueError("URL sumber mengandung karakter yang tidak valid.")
    return value


def _list(data, name):
    value = data.get(name, [])
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError(f"{name} harus berupa daftar, maksimal 200 entri.")
    return value


def _refs(row, evidence):
    ids = row.get("evidence_ids", [])
    if not isinstance(ids, list) or any(not isinstance(i, str) or i not in evidence for i in ids):
        raise ValueError("evidence_ids harus menunjuk ID bukti yang benar-benar disertakan.")
    return list(dict.fromkeys(ids))


def validate(data, target):
    if not isinstance(data, dict):
        raise ValueError("Report harus berupa objek JSON.")
    evidence, warnings = {}, []
    for source in _list(data, "evidence"):
        if not isinstance(source, dict):
            raise ValueError("Entri evidence harus berupa objek.")
        ident = _text(source.get("id"), "ID bukti", 40)
        if not re.fullmatch(r"E[1-9][0-9]*", ident) or ident in evidence:
            raise ValueError("ID bukti harus unik dengan format E1, E2, dan seterusnya.")
        method = source.get("method")
        if method not in METHODS:
            raise ValueError("Metode bukti: direct_page, api, archive, search, atau enumeration.")
        when = _text(source.get("retrieved_at"), "Waktu pengambilan", 80)
        try:
            parsed = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise ValueError("retrieved_at harus ISO 8601 dengan zona waktu.") from None
        code = source.get("http_status")
        if code is not None and (type(code) is not int or not 100 <= code <= 599):
            raise ValueError("http_status harus berupa kode HTTP atau null.")
        if source.get("exists") is not None and type(source["exists"]) is not bool:
            raise ValueError("exists harus true, false, atau null.")
        evidence[ident] = {"id": ident, "url": _url(source.get("url")),
                           "subject_url": _url(source.get("subject_url", source.get("url"))), "method": method,
                           "retrieved_at": when, "excerpt": _text(source.get("excerpt"), "Cuplikan bukti", 12000),
                           "http_status": code, "exists": source.get("exists"),
                           "retrieval_succeeded": source.get("retrieval_succeeded") is True,
                           "observed_handle": str(source.get("observed_handle") or "").strip().lstrip("@"),
                           "authoritative_absence": source.get("authoritative_absence") is True}
    accounts = []
    for account in _list(data, "accounts"):
        if not isinstance(account, dict) or account.get("status") not in LABELS:
            raise ValueError("Akun perlu platform, URL, detail, dan status yang valid.")
        row = {"platform": _text(account.get("platform"), "Platform", 100),
               "url": _url(account.get("url")), "status": account["status"],
               "handle": _text(account.get("handle", target), "Handle akun", 100).lstrip("@"),
               "detail": _text(account.get("detail"), "Detail akun"),
               "evidence_ids": _refs(account, evidence)}
        proof = [evidence[i] for i in row["evidence_ids"]
                 if evidence[i]["subject_url"].rstrip("/") == row["url"].rstrip("/")]
        if row["status"] == "confirmed" and not any(
                e["method"] in DIRECT and (e["http_status"] == 200 or
                    (e["http_status"] is None and e["retrieval_succeeded"])) and e["exists"] is True
                and e["observed_handle"].casefold() == row["handle"].casefold() for e in proof):
            row["status"] = "unverified"
            warnings.append(f"{row['platform']}: diturunkan menjadi belum diverifikasi; bukti langsung handle belum cukup.")
        if row["status"] == "not_found" and not any(
                e["method"] in {"direct_page", "api"} and e["exists"] is False and
                (e["http_status"] == 404 or (e["method"] == "api" and e["http_status"] == 200
                                             and e["authoritative_absence"])) for e in proof):
            row["status"] = "inconclusive"
            warnings.append(f"{row['platform']}: respons yang tersedia belum membuktikan akun tidak ada.")
        accounts.append(row)
    observations = []
    for row in _list(data, "observations"):
        if not isinstance(row, dict):
            raise ValueError("Observasi harus berupa objek dengan text dan evidence_ids.")
        refs = _refs(row, evidence)
        if not refs:
            raise ValueError("Observasi faktual harus menyebutkan bukti sumber.")
        observations.append({"text": _text(row.get("text"), "Observasi"), "evidence_ids": refs})
    links = []
    for row in _list(data, "links"):
        if not isinstance(row, dict) or row.get("status") not in {"confirmed", "hypothesis"}:
            raise ValueError("Status hubungan harus confirmed atau hypothesis.")
        link = {"from_url": _url(row.get("from_url")), "to_url": _url(row.get("to_url")),
                "status": row["status"], "basis": row.get("basis", "same_handle"),
                "detail": _text(row.get("detail"), "Detail hubungan"),
                "evidence_ids": _refs(row, evidence)}
        proof = [evidence[i] for i in link["evidence_ids"] if evidence[i]["method"] in DIRECT
                 and (evidence[i]["http_status"] == 200 or
                      (evidence[i]["http_status"] is None and evidence[i]["retrieval_succeeded"]))]
        direct_link = link["basis"] == "direct_link" and any(
            e["subject_url"].rstrip("/") == link["from_url"].rstrip("/") and link["to_url"] in e["excerpt"] for e in proof)
        key = row.get("identity_key", "")
        immutable = (link["basis"] == "immutable_id" and isinstance(key, str) and len(key) >= 4
                     and all(any(e["subject_url"].rstrip("/") == url.rstrip("/") and key in e["excerpt"]
                                 for e in proof) for url in (link["from_url"], link["to_url"])))
        if link["status"] == "confirmed" and not (direct_link or immutable):
            link["status"] = "hypothesis"
            warnings.append("Hubungan akun belum terkonfirmasi; handle yang sama saja tidak cukup.")
        links.append(link)
    coverage = []
    for row in _list(data, "coverage"):
        if not isinstance(row, dict) or row.get("status") not in {"completed", "blocked", "not_run"}:
            raise ValueError("Coverage perlu source, status completed/blocked/not_run, dan detail.")
        coverage.append({"source": _text(row.get("source"), "Sumber pemeriksaan", 100),
                         "status": row["status"], "detail": _text(row.get("detail"), "Rincian coverage")})
    gaps = [_text(v, "Batasan") for v in _list(data, "gaps")]
    for required in ("username_enum", "native_web_search"):
        if not any(r["source"] == required and r["status"] == "completed" for r in coverage):
            gaps.append(f"{required}: belum selesai atau belum dijalankan.")
    gaps += [r["source"] + ": " + r["detail"] for r in coverage if r["status"] != "completed"]
    gaps += [a["platform"] + ": " + a["detail"] for a in accounts if a["status"] in {"unverified", "inconclusive"}]
    if not evidence:
        gaps.append("Belum ada bukti sumber yang tersimpan.")
    return {"producer": "cti-codex-account-report-v1", "target": target,
            "summary": _text(data.get("summary"), "Ringkasan"),
            "accounts": accounts, "evidence": list(evidence.values()), "observations": observations,
            "links": links, "coverage": coverage, "gaps": list(dict.fromkeys(gaps)),
            "warnings": warnings, "next_steps": [_text(v, "Langkah berikutnya") for v in _list(data, "next_steps")]}


def _md(value):
    return str(value).replace("\n", " ").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def render(data):
    lines = [f"# Hasil penelusuran @{_md(data['target'])}", "", data["summary"], "",
             f"Diperbarui: {data['updated_at']}", "",
             "Status akun membuktikan keberadaan profil; kepemilikan antar-akun dibahas terpisah.", "",
             "| Platform | Hasil | Detail / bukti |", "| --- | --- | --- |"]
    for a in data["accounts"]:
        refs = " ".join(f"[{i}](#sumber)" for i in a["evidence_ids"])
        lines.append(f"| [{_md(a['platform'])}](<{a['url']}>) | {LABELS[a['status']]} | {_md(a['detail'])} {refs} |")
    if not data["accounts"]:
        lines.append("| — | Belum ada akun terverifikasi | Cakupan dan hambatan dijelaskan di bawah. |")
    for title, rows in (("Temuan bersumber", [f"{_md(o['text'])} ({', '.join(o['evidence_ids'])})" for o in data["observations"]]),
                        ("Keterkaitan akun", [f"{'Terkonfirmasi' if r['status'] == 'confirmed' else 'Hipotesis'}: "
                          f"<{r['from_url']}> → <{r['to_url']}> — {_md(r['detail'])} ({', '.join(r['evidence_ids'])})" for r in data["links"]]),
                        ("Pemeriksaan yang dijalankan", [f"{_md(r['source'])}: {r['status']} — {_md(r['detail'])}" for r in data["coverage"]]),
                        ("Belum dapat dipastikan", data["gaps"]), ("Koreksi status bukti", data["warnings"]),
                        ("Langkah berikutnya", data["next_steps"])):
        if rows:
            lines += ["", f"## {title}", ""] + ["- " + row for row in rows]
    lines += ["", "## Sumber", ""]
    lines += [f"- {e['id']}: <{e['url']}> — {e['method']}, diambil {e['retrieved_at']}" for e in data["evidence"]]
    return "\n".join(lines) + "\n"


def save_report(case, payload, *, root=ENGINE):
    directory = case_path(case, root)
    if not directory.is_dir() or not (directory / "request.json").is_file():
        raise ValueError("Case belum disiapkan. Buat case melalui guided_case terlebih dahulu.")
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    data = validate(payload, request["target"])
    data.update(case=case, updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
    data["status"] = "complete_with_gaps" if data["gaps"] or data["warnings"] else "complete"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    report, raw = directory / "report", directory / "raw"
    for folder in (report, raw):
        if folder.is_symlink() or folder.resolve().parent != directory.resolve():
            raise ValueError("Folder laporan/bukti harus berada di dalam case ini.")
        folder.mkdir(exist_ok=True)
    stem = "ACCOUNT-SUMMARY-" + stamp
    paths = {"markdown": report / (stem + ".md"), "json": report / (stem + ".json"),
             "csv": report / (stem + ".csv"), "evidence": raw / ("account-research-" + stamp + ".json")}
    markdown = render(data)
    paths["markdown"].write_text(markdown, encoding="utf-8")
    paths["json"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["evidence"].write_text(json.dumps({"evidence": data["evidence"], "coverage": data["coverage"]},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
    table = io.StringIO(newline="")
    writer = csv.writer(table)
    writer.writerow(["platform", "handle", "url", "status", "detail", "evidence_ids"])
    for row in data["accounts"]:
        values = [row[k] for k in ("platform", "handle", "url", "status", "detail")]
        # CSV files may be opened in Excel; neutralize formula-like untrusted text.
        values = ["'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values]
        writer.writerow([*values, ";".join(row["evidence_ids"])])
    paths["csv"].write_text(table.getvalue(), encoding="utf-8-sig")
    manifest = directory / "account_assessment.json"
    if manifest.is_symlink():
        raise ValueError("Manifest case tidak boleh berupa symlink.")
    latest = {"producer": data["producer"], "summary": data["summary"], "status": data["status"],
              "reports": {k: str(p.resolve()) for k, p in paths.items()}, "updated_at": data["updated_at"]}
    temporary = directory / (".account-" + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest)
    return {**latest, "case": case, "markdown": markdown, "warnings": data["warnings"],
            "counts": {s: sum(a["status"] == s for a in data["accounts"]) for s in LABELS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = save_report(args.case, json.loads(args.input.read_text(encoding="utf-8")))
        print(result["markdown"])
        print("Laporan tersimpan:", result["reports"]["markdown"])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Laporan belum disimpan: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
