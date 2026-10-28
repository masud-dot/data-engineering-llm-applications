-- region: eval-schema
-- Evaluation sets live in their own schema: no reader is granted it,
-- no stage reads it as a source, and resetting the index keeps it.
CREATE SCHEMA evals;
CREATE TABLE evals.sets (
  name text,
  version int,
  digest text NOT NULL,
  items int NOT NULL,
  built_from text NOT NULL,  -- fingerprint of the index it came from
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (name, version)
);
CREATE TABLE evals.items (
  name text,
  version int,
  item_id text,
  question text NOT NULL,
  region text NOT NULL,
  role text NOT NULL,
  evidence text NOT NULL,     -- text an answer must be grounded in
  doc_key text NOT NULL,
  doc_version text NOT NULL,  -- the version the label was made on
  PRIMARY KEY (name, version, item_id),
  FOREIGN KEY (name, version) REFERENCES evals.sets
);
CREATE TABLE evals.scores (
  name text,
  version int,
  scored_at timestamptz NOT NULL DEFAULT now(),
  index_hash text NOT NULL,
  model text NOT NULL,
  k int NOT NULL,
  scored int NOT NULL,
  stale int NOT NULL,
  recall float8 NOT NULL,
  mrr float8 NOT NULL,
  misses text[] NOT NULL,      -- items not found in the top k
  FOREIGN KEY (name, version) REFERENCES evals.sets
);
-- endregion
