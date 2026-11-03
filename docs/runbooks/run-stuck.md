# Runbook: a run has been running for over two hours

**What it means.** A run in the ledger is `running` long after any
stage's timeout. Its process died without the ledger hearing, or
it is waiting on a lock.

**Check.** Airflow's task view for the run; `make ledger`;
`SELECT * FROM pg_stat_activity WHERE state <> 'idle'` in
`make psql`.

**Act.** A dead run: the next run abandons it (Chapter 12) and
nothing was published. A blocked query: find the blocking session,
and end it only if it is not another run's commit.

**Escalate** if runs keep stalling: it is a capacity or locking
fault, not bad luck.
