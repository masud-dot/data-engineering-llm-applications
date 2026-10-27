-- region: ledger-columns
-- What kind of run it was, which code ran it, what it covered and
-- what it published.
ALTER TABLE ledger
  ADD COLUMN kind text NOT NULL DEFAULT 'incremental',
  ADD COLUMN code text,
  ADD COLUMN scope jsonb NOT NULL DEFAULT '{}',
  ADD COLUMN published int,
  ADD COLUMN committed_at timestamptz;
-- endregion
