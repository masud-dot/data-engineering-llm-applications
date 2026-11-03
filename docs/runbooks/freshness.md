# Runbook: a source is later than its target

**Alert.** `make ops-check` reports `FAIL freshness <source>: <lag>
of <target>`.

**What it means.** The source's last committed read is older than
the smaller of its `max_lag` and `delete_within` in `slas.toml`.

**Check.** `make ledger`: did the last scheduled runs start,
fail or never run? Is the schedule paused in Airflow? `make lag`
shows every source.

**Act.** Failed runs: follow the runbook their error names. Paused
schedule: unpause it and run `make run`. A target the schedule
cannot meet (runs every three hours, target one hour) is a design
fault: raise it with the owner and fix the schedule or the target.

**Escalate** to the source's owner in `slas.toml` if the source
itself has stopped publishing.
