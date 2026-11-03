# Runbook: quality failures were accepted this week

**What it means.** Someone published a run whose quality checks
failed, by accepting them (Chapter 13). That can be right, but
each acceptance needs a reason and a reviewer.

**Check.** `make quality RUN_ID=<run>` for each accepted run, and
the ticket that recorded why.

**Act.** If the reason holds, record it and close the alert by
review. If not, rerun without the acceptance and fix the cause.

**Escalate** acceptances without a ticket to the platform lead.
