"""Readable tool-result summaries. Keep evidence verbatim for the agent, after the summary."""
from __future__ import annotations

import json

LABELS = {"hash_id": "Identifikasi hash", "search_pivot": "Rencana pencarian publik",
          "pivot_extract": "Pengumpulan indikator", "case_frontier": "Langkah investigasi berikutnya",
          "case_clusters": "Hubungan antar-indikator", "capability_check": "Kesiapan sumber data",
          "api_usage": "Penggunaan layanan OSINT", "phone_osint": "Informasi format nomor telepon",
          "doc_metadata": "Metadata file", "guided_case": "Persiapan case"}


def present(name, result):
    if name in {"guided_case", "account_report"}:
        return result  # Intake already returns a user-facing question/plan plus structured data.
    blocks = result.get("content") or []
    texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    text = "\n".join(texts).strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = None
    label = LABELS.get(name, name.replace("_", " ").capitalize())
    error = bool(result.get("isError"))
    gaps = []
    if isinstance(data, dict):
        for key in ("error", "skipped", "unavailable", "not_consulted", "limitations", "gaps", "missing_keys"):
            value = data.get(key)
            if value:
                gaps.append(str(value)[:240])
        if isinstance(data.get("status"), str) and data["status"] in {"skipped", "unavailable", "error", "partial", "not_configured"}:
            gaps.append(str(data.get("reason") or data.get("message") or data["status"])[:240])
    headline = "Belum berhasil" if error else ("Pemeriksaan belum lengkap" if gaps else "Tool selesai dijalankan")
    lines = [f"{headline}: {label}."]
    if error:
        lines.append("Penyebab: " + (text[:650] if text else "Tool tidak mengembalikan rincian error."))
        lines.append("Langkah berikutnya: perbaiki input atau konfigurasi yang disebutkan sebelum mengulang.")
    elif isinstance(data, dict):
        rows = data.get("results")
        if isinstance(rows, list):
            lines.append(f"Hasil yang dikembalikan: {len(rows)} entri.")
            verdicts = [str(r["verdict"]) for r in rows if isinstance(r, dict) and r.get("verdict")]
            if verdicts:
                lines.append("Hasil pemeriksaan: " + ", ".join(dict.fromkeys(verdicts))[:250] + ".")
            if not rows:
                lines.append("Hasil kosong belum membuktikan target aman atau tidak memiliki jejak.")
        elif isinstance(data.get("queries"), list):
            lines.append(f"{len(data['queries'])} kueri pencarian disiapkan; hasil internet belum ditelusuri.")
        if gaps:
            lines.append("Belum bisa diperiksa: " + "; ".join(gaps[:3]))
        if name == "hash_id":
            lines.append("Ini pemeriksaan format hash; reputasi dan isi file belum diperiksa.")
    elif text:
        first = next((s.strip() for s in text.splitlines() if s.strip()), "")
        lines.append(first[:350])
    lines.append("Codex dapat merangkum bukti dan batasan di bawah ini; jangan menganggap tool selesai sebagai investigasi selesai.")
    summary = {"type": "text", "text": "\n".join(lines),
               "annotations": {"audience": ["user", "assistant"], "priority": 1.0}}
    evidence = []
    for block in blocks:
        copy = dict(block)
        copy["annotations"] = {**copy.get("annotations", {}), "audience": ["assistant"]}
        evidence.append(copy)
    return {**result, "content": [summary, *evidence]}
