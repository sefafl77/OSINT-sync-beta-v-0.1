# account_report input

Call the MCP tool with `case` and `report_json` (the following object JSON-encoded as a string).
All examples below are synthetic. The report tool validates supplied observations; it does not
fetch sources or verify prose on its own. Use only content actually returned by search/tools.

```json
{
  "summary": "One public account was verified; other platforms remain unverified.",
  "accounts": [{
    "platform": "Example platform",
    "url": "https://social.example/example_user",
    "handle": "example_user",
    "status": "confirmed",
    "detail": "The public page displays the exact handle.",
    "evidence_ids": ["E1"]
  }],
  "evidence": [{
    "id": "E1",
    "url": "https://social.example/example_user",
    "subject_url": "https://social.example/example_user",
    "method": "direct_page",
    "retrieved_at": "2026-01-01T10:00:00Z",
    "excerpt": "Public profile: @example_user",
    "http_status": 200,
    "exists": true,
    "observed_handle": "example_user"
  }],
  "coverage": [
    {"source": "username_enum", "status": "completed", "detail": "Seven curated platforms checked; raw output saved."},
    {"source": "native_web_search", "status": "completed", "detail": "Exact handle and public platform queries actually searched."}
  ],
  "observations": [{"text": "The public page displays the exact handle.", "evidence_ids": ["E1"]}],
  "links": [],
  "gaps": ["A blocked platform could not be checked."],
  "next_steps": ["Recheck the blocked source if needed."]
}
```

`evidence.method`: `direct_page`, `api`, `archive`, `search`, `enumeration`. Time must include a
timezone. HTTP status must be a real observed number, or null; never fill in 200 by assumption.
When native web open returns readable source content but no HTTP code, leave `http_status=null`
and set `retrieval_succeeded=true` only for a successful original-source retrieval (not a search
snippet or failed/login-wall view). Use `subject_url` when the evidence URL is an API or archived snapshot of a different profile URL.
`excerpt` is a short verbatim source excerpt or the relevant tool output, not a fabricated quote.
`exists` is tri-state: true / false / null. Do not mix a source's account existence signal with
whether it belongs to the target person.

`accounts.status`: `confirmed`, `unverified`, `not_found`, `inconclusive`, `false_positive`.
Confirmation needs matching source subject URL, direct/API/archive evidence, successful retrieval,
`exists=true`, and the exact `observed_handle`. Otherwise it is downgraded. A definitive absence needs direct
HTTP 404, or an HTTP-200 API response with `exists=false` and `authoritative_absence=true`.
A search not returning a result, rate limiting, and a generic page cannot establish absence.

Each factual observation needs `evidence_ids` that exist in the evidence list. A link row has
`from_url`, `to_url`, `status` (`confirmed`/`hypothesis`), `basis`, `detail`, `evidence_ids`.
For `basis=direct_link`, evidence from `from_url` must contain the actual `to_url`.
For `basis=immutable_id`, supply `identity_key` actually present in direct evidence from both
URLs. `basis=same_handle` always remains a hypothesis. A direct link confirms a published link;
it does not independently establish the legal identity of the owner.

Coverage `status` is `completed`, `blocked`, or `not_run`. Missing/unfinished baseline sources
and inconclusive accounts make the report `complete_with_gaps`; a failed source never counts
as "no account". Calling the tool again saves a new version and preserves earlier reports and
handwritten assessments. Read the returned warnings and reflect all downgrades in the final answer.
