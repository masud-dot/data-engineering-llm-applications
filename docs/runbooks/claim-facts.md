# Runbook: the triage agent's claim facts are old

**What it means.** `agent.claim_facts` was read over 15 minutes
ago. The agent's `claim_status` tool is refusing, so the agent is
handing claims to people.

**Check.** The `claim_facts` DAG in Airflow; its last error; that
the claims database answers (`make psql DB=source`).

**Act.** Fix the failed run's cause and run `make run
PIPELINE=claim_facts`. Do not raise the tool's limit: the agent
acts on what it reads.

**Escalate** to the claims systems owner if the source is down.
