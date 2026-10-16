# OSINT sync beta v 0.1

**CTI dan OSINT berbasis Codex** — Codex melakukan pencarian, memeriksa sumber, menyusun temuan, lalu menyimpan laporan ke case lokal.

> Proyek ini adalah adaptasi CTI Expert, dibuat oleh [Hieu Ngo / 7onez](https://github.com/7onez/cti-expert). Lisensi dan pemberitahuan hak cipta aslinya tetap ada di [`LICENSE`](LICENSE).

## Mulai cepat di Windows

Yang dibutuhkan: Python 3.11+, Codex CLI yang sudah login dengan akun ChatGPT, dan koneksi internet.

```powershell
git clone https://github.com/sefafl77/OSINT-sync-beta-v-0.1.git
cd OSINT-sync-beta-v-0.1
powershell -ExecutionPolicy Bypass -File .\scripts\install-codex.ps1
```

Setelah setup selesai, mulai investigasi:

```powershell
& ".\Mulai CTI.cmd"
```

Saat chat Codex terbuka, masukkan target dan tujuan. Contoh username:

```text
Cek jejak publik username example_user. Verifikasi akun dari sumbernya, jelaskan temuan yang belum pasti, dan simpan laporan.
```

Atau berikan target langsung saat menjalankan launcher:

```powershell
& ".\Mulai CTI.cmd" example_user
```

Codex mengenali jenis target seperti username atau domain; username yang jelas tidak perlu melewati pilihan jenis 1–8. Kalau target atau tujuannya ambigu, Codex akan meminta detail yang memang diperlukan.

## Menggunakan Codex desktop

Buka folder repository ini sebagai project di Codex, selesaikan prompt trust jika muncul, lalu kirim:

```text
$cti-expert:cti Cek jejak publik username example_user dan simpan laporan bersumber.
```

Skill project berada di [`.agents/skills/cti/SKILL.md`](.agents/skills/cti/SKILL.md). Alur riset dan format laporan dijelaskan di [`workflows/codex-native.md`](workflows/codex-native.md).

## Hasil dan batasan

Laporan username mencakup ringkasan, status akun per platform, bukti dan tautan sumber, hubungan yang terverifikasi atau masih berupa hipotesis, serta keterbatasan pencarian. Hasil awal dari checker atau cuplikan mesin pencari diperlakukan sebagai petunjuk sampai sumbernya diperiksa. Hasil yang tidak dapat diverifikasi ditandai dengan jelas.

Berkas laporan dan bukti tersimpan lokal di:

```text
intel_engine/cases/<CASE-ID>/report/
intel_engine/cases/<CASE-ID>/raw/
```

Data case lokal, konfigurasi Codex, dan `.env` diabaikan oleh Git agar tidak ikut ter-push. Codex memakai login serta kuota Codex kamu; API key model tidak diperlukan. Integrasi provider OSINT tertentu bersifat opsional dan dapat memerlukan key provider masing-masing.

## Perintah lokal

Pemeriksaan setup tanpa menjalankan investigasi:

```powershell
.\.venv\Scripts\python.exe cti.py --doctor
```

Wizard offline hanya menyiapkan brief case; ia tidak menjalankan pencarian Codex:

```powershell
.\.venv\Scripts\python.exe cti.py --wizard
```

Untuk melanjutkan case di Codex, jalankan `Mulai CTI.cmd` lalu minta Codex melanjutkan dengan ID case. Hasil lama tetap tersimpan di direktori case tersebut.

## Penggunaan yang bertanggung jawab

Gunakan hanya untuk riset yang sah, target milik sendiri, atau pekerjaan dengan izin dan ruang lingkup yang jelas. Patuhi hukum, aturan layanan sumber, serta batas akses dan privasi. Jangan gunakan untuk doxxing, pelecehan, stalking, atau akses tanpa izin.

## Kredit dan lisensi

Kode dan dokumentasi proyek asal tetap tunduk pada MIT License beserta pemberitahuan hak cipta yang disertakan. Perubahan dan integrasi Codex pada repository ini disimpan bersama sumber tersebut; lihat [`LICENSE`](LICENSE) untuk ketentuan lengkap.
