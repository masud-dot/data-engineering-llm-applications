# Runbooks

Every alert names its runbook. Errors that stop a run point here:

| Error or alert | Runbook |
|---|---|
| `SourceGone` (removal guard) | `removal-guard.md` |
| freshness | `freshness.md` |
| run-stuck | `run-stuck.md` |
| claim-facts | `claim-facts.md` |
| evaluation, `LeakError`, `StaleError` | `evaluation.md` |
| quality-gate, `QualityError` | `quality-gate.md` |
| `PrivacyError` | stop and call the data protection officer |
| `ContractError` | the source's contract owner (`slas.toml`) |
