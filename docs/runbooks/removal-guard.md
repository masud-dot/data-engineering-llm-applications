<!-- region: removal-guard -->
# Runbook: a run refused to remove documents

**Alert.** The documents run failed with `SourceGone: <source>:
N of M documents gone; refusing to delete more than 20%`.

**What it means.** A source shows far fewer documents than the
index holds. Either the source lost them (an export failed, a job
archived the wrong records) or they were removed on purpose. The
guard stopped the run, so the index still holds every document.

**Check.**
1. `make lag` and `make ledger`: when did the source last read
   in full, and what did the failed run stage?
2. Count the source yourself (`make psql DB=source`, or the
   landing folder) and compare with yesterday's count.
3. Ask the source's owner, named in `slas.toml`, whether the
   removal was intended. Out of hours, use their on-call number.

**Act.**
- Removal not intended: leave the guard in place. The index keeps
  serving yesterday's documents; tell the owner, and rerun once
  the source is restored.
- Removal intended and confirmed in writing: rerun with
  `{"max_removed": <share>}` for that one run, and record who
  confirmed it in the ticket.

**Never** raise the limit to make the alert go away. A guard
raised at night has deleted good data from the index before.

**After.** Note the cause in the ticket and in the source's
contract if the source changed how it publishes.
<!-- endregion -->
