-- region: agent-views
-- What the triage agent may read about claims: facts copied from
-- the claims system with the time they were read, behind the same
-- region and role check as the index.
CREATE SCHEMA agent;
CREATE TABLE agent.claim_facts (
  claim_id text PRIMARY KEY,
  policy_id text NOT NULL,
  region text NOT NULL,
  status text NOT NULL,
  changed_at timestamptz NOT NULL,  -- updated_at in the source
  read_at timestamptz NOT NULL      -- when the copy was taken
);
ALTER TABLE agent.claim_facts ENABLE ROW LEVEL SECURITY;
CREATE POLICY triage_access ON agent.claim_facts FOR SELECT
  TO llmdata_reader USING (
    region = current_setting('llmdata.region', true)
    AND current_setting('llmdata.role', true) = 'claims');
-- The semantic layer: one definition of an open claim, and every
-- row's age, for every agent that asks.
CREATE VIEW agent.claims WITH (security_invoker = true) AS
  SELECT claim_id, policy_id, region, status,
         status IN ('open', 'assessing') AS is_open,
         changed_at, read_at AS as_of,
         now() - read_at AS age
  FROM agent.claim_facts;
-- Runs as its owner, so readers see one time, not the table.
CREATE VIEW agent.index_freshness AS
  SELECT min(read_at) AS as_of, now() - min(read_at) AS age
  FROM checkpoints;
GRANT USAGE ON SCHEMA agent TO llmdata_reader;
GRANT SELECT ON agent.claim_facts, agent.claims,
  agent.index_freshness TO llmdata_reader;
-- endregion
