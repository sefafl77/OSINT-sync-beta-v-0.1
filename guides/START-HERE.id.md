# Mulai CTI Expert dengan Codex

Klik dua kali **Mulai CTI.cmd**. Ini membuka **Codex interaktif**, memakai login dan kuota Codex
kamu. Kalau ada pertanyaan trust project atau login, selesaikan prompt bawaan Codex tersebut.
Kamu tidak perlu API key Claude.

Setelah chat terbuka, tulis misalnya:

```text
Cek jejak publik username example_user. Tampilkan akun terverifikasi, akun yang belum pasti,
sumbernya, keterbatasan pencarian, dan simpan laporannya.
```

Atau dari PowerShell di folder repo, langsung mulai dengan target:

```powershell
& ".\Mulai CTI.cmd" example_user
```

Codex menafsirkan jenis target, menyiapkan case, menjalankan pemeriksaan awal, mencari di web,
memeriksa sumber asli, lalu menulis laporan. Untuk target ambigu atau tujuan yang perlu scope
lebih jelas, Codex menanyakan informasi yang diperlukan. Tidak perlu memilih jenis target 1–8
untuk sebuah username yang sudah jelas.

Di **Codex app**, buka project CTI Expert ini, lalu kirim:

```text
$cti-expert:cti Cek jejak publik username example_user dan simpan laporan bersumber.
```

Skill lokal tersedia dari `.agents/skills/cti/SKILL.md`. Jika tool MCP yang baru belum muncul,
buka ulang project tepercaya. Cara discovery skill dan live search mengikuti
[dokumentasi skill](https://learn.chatgpt.com/docs/build-skills) serta
[Codex CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli).

## Hasil yang kamu dapat

Laporan berisi ringkasan, tabel **Platform | Hasil | Detail / bukti**, observasi yang didukung
sumber, hubungan akun yang terkonfirmasi atau masih hipotesis, dan pemeriksaan yang belum bisa
dilakukan. Handle yang sama pada dua platform tidak otomatis berarti pemiliknya sama.

Codex menyimpan Markdown, JSON, CSV dan bukti sumber di:

```text
intel_engine/cases/<CASE-ID>/report/ACCOUNT-SUMMARY-*.md
intel_engine/cases/<CASE-ID>/report/ACCOUNT-SUMMARY-*.json
intel_engine/cases/<CASE-ID>/report/ACCOUNT-SUMMARY-*.csv
intel_engine/cases/<CASE-ID>/raw/account-research-*.json
```

Laporan lama disimpan. Sumber yang gagal, login wall, rate limit dan sumber yang belum dicari
ditandai sebagai keterbatasan. Setiap platform dapat membatasi data publik; Codex menjelaskan
bukti yang berhasil diperoleh.

## Melanjutkan case dan menu offline

Di chat project, tulis `$cti-expert:cti lanjutkan case <CASE-ID>`; atau:

```powershell
.venv\Scripts\python.exe cti.py --case CASE-ID
```

Wizard lama masih tersedia khusus untuk menyiapkan brief tanpa model/pencarian:

```powershell
.venv\Scripts\python.exe cti.py --wizard
```

Di menu offline: **1** menyiapkan case, **2** membaca hasil tersimpan, **3** memeriksa setup,
**4** demo offline. Jika memakai wizard, lanjutkan brief di Codex setelah disimpan.

## Memeriksa setup tanpa menjalankan model

```powershell
.venv\Scripts\python.exe cti.py --doctor
.venv\Scripts\python.exe cti.py --check
```

Jika dependency/config belum siap, jalankan:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-codex.ps1
```

Baseline menggunakan sumber publik/free-only. Provider OSINT opsional tetap dapat memerlukan
key sendiri. PDF/diagram lanjutan membutuhkan dependency opsional yang disebutkan oleh doctor.
