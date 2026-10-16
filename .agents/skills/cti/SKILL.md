---
name: cti
description: Run CTI Expert investigations in the current Codex session using native web search and the project's intel_harness MCP tools, then save a sourced report. Use for starting or continuing a CTI case, checking a public username, or reviewing an owned digital footprint in this project.
---

Read [the native workflow](../../../workflows/codex-native.md), and follow it through saved
findings. This folder is inside the CTI Expert repository: resolve paths from that repository,
not from another project or an assumed global installation.

Use this signed-in Codex session as the analyst. The tools collect and format evidence;
Codex chooses searches, verifies sources, weighs alternative explanations, and writes findings.
Do not launch another model, `codex exec`, or a Python LLM runner.

If the user supplies no target, ask only: **Mau cek apa? Masukkan username, domain, atau link
profilnya. Contoh: example_user.** Infer the type; do not make the user pick from eight types
unless genuinely ambiguous. For a bare public handle, default to a bounded public-account
review. Reuse known scope/purpose and ask only for missing information that changes the work.

For a username, continue beyond the seven-platform checker with native web search and
source verification. `search_pivot` generates queries, not search results. A case brief,
an enumeration result, or a list of search links is not the final deliverable.

Finish with an Indonesian summary, a platform/status/evidence table, source-backed observations,
confirmed versus hypothesized links, explicit gaps, sources, and paths to saved artifacts.
Use `account_report` for the public-account report. Follow its schema in
[account-report-schema.md](../../../workflows/account-report-schema.md). Keep raw captures in
the same case store. If tools/search are unavailable, save a partial report with that gap and
say which parts actually ran.
