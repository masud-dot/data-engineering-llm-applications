# Readiness self-assessment

Answer each question with evidence, not opinion: the command or
test that shows it, run against the system as it is today. `make
readiness` runs the automated evidence in one go. A "no" is a
finding with an owner and a date, not a failure of the review.

| Area | Question | Evidence |
|---|---|---|
| Contracts | Does every source have a contract and an owner? | `slas.toml`; contract tests |
| Contracts | Does a contract violation stop a run? | `make verify` (contract tests) |
| Environment | Is every image and package pinned? | `tools/check_versions.py --require-digests` |
| Ingest | Does a rerun change nothing? | replay tests; two identical runs, one fingerprint (spike S-5) |
| Parsing | Are empty and scanned pages counted and gated? | `make quality` |
| Identity | Can any answer be traced to a document version? | `make trace CHUNK=...` |
| Freshness | Does every source meet its target on its schedule? | `make lag`; ops check `freshness` |
| Deletion | Does an erasure reach every copy and stay erased? | erasure tests; `make erase` on a test key |
| Runs | Does a failed run leave the index as it was? | recovery tests; spike S-5 |
| Runs | Are retries, timeouts and schedules set in policy files? | `pipelines/policies/` |
| Quality | Does a bad run stop before publishing? | quality tests; `make quality` |
| Testing | Does every change run every layer before merge? | CI checks job; branch protection |
| Privacy | Is personal data no answer needs kept out of the index? | permission tests; `meta.pii` counts |
| Access | Does the database check region and role for every reader? | permission tests; agent tests |
| Evaluation | Is retrieval scored daily on a versioned, isolated set? | `make scores`; ops check `evaluation` |
| Training data | Is every dataset version decontaminated and recorded? | leakage tests; `make datasets` |
| Agents | Does every tool answer carry its age, and refuse past it? | agent and MCP tests |
| Cost | Is every change costed before release? | `make cost SIZE=... K=...` in the change review |
| Operations | Is every target checked, and does each alert have a runbook? | `make ops-check`; `docs/runbooks/` |
| Operations | Has someone other than its author followed each runbook? | a dated drill per runbook |
| Recovery | Can the index be rebuilt from the archive, and erasures re-applied after a restore? | a dated restore drill |
