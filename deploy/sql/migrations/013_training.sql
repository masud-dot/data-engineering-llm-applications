-- region: training-schema
-- Fine-tuning datasets. Test examples are evaluation data, so they
-- live in evals with the other sets; no reader is granted either.
CREATE SCHEMA training;
CREATE TABLE training.sets (
  name text,
  version int,
  built_from text NOT NULL,   -- fingerprint of the index read
  teacher text NOT NULL,      -- model that wrote the summaries
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (name, version)
);
CREATE TABLE training.examples (
  name text,
  version int,
  example_id text,
  split text NOT NULL CHECK (split IN ('train', 'validation')),
  prompt text NOT NULL,
  completion text NOT NULL,
  doc_key text NOT NULL,
  doc_version text NOT NULL,
  rejected text,              -- the reason, or NULL when kept
  PRIMARY KEY (name, version, example_id),
  FOREIGN KEY (name, version) REFERENCES training.sets
);
CREATE TABLE evals.examples (  -- the test split
  name text,
  version int,
  example_id text,
  prompt text NOT NULL,
  reference text NOT NULL,
  doc_key text NOT NULL,
  doc_version text NOT NULL,
  rejected text,
  PRIMARY KEY (name, version, example_id)
);
-- endregion
