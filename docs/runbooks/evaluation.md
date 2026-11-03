# Runbook: no evaluation score in over a day

**What it means.** The 06:50 `eval_sets` run has not scored since
yesterday. It may have refused a leaked or stale set (Chapter 16).

**Check.** The run's error: `LeakError` means questions are in the
index; `StaleError` means too many labels are out of date.

**Act.** Leak: find the documents that hold the questions and
remove them at the source; never score around the check. Stale:
build and review a new version (`{"rebuild": true}`).

**Escalate** to the assistant's owner: until it scores, nobody
knows whether retrieval has changed.
