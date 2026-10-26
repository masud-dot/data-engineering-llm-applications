-- Pipeline state and the live index in the llmdata database.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE ledger (
  run_id text PRIMARY KEY,
  pipeline text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status text NOT NULL
);

CREATE TABLE checkpoints (
  source text PRIMARY KEY,
  watermark timestamptz,
  manifest jsonb NOT NULL DEFAULT '{}',
  run_id text,
  committed_at timestamptz
);

CREATE TABLE pending_checkpoints (
  run_id text,
  source text,
  watermark timestamptz,
  manifest jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, source)
);

CREATE TABLE staged (
  run_id text,
  doc_key text,
  op text NOT NULL CHECK (op IN ('upsert', 'delete')),
  origin text NOT NULL,
  kind text NOT NULL,
  content_hash text,
  ref text,
  raw text,
  parsed text,
  cleaned text,
  doc_id text,
  version text,
  meta jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, doc_key)
);

CREATE TABLE staged_chunks (
  run_id text,
  doc_key text,
  ordinal int,
  chunk_id text,
  text text NOT NULL,
  embedding vector(384),
  PRIMARY KEY (run_id, doc_key, ordinal)
);

CREATE TABLE documents (
  doc_key text PRIMARY KEY,
  doc_id text NOT NULL,
  version text NOT NULL,
  origin text NOT NULL,
  meta jsonb NOT NULL DEFAULT '{}',
  run_id text NOT NULL
);

CREATE TABLE chunks (
  chunk_id text PRIMARY KEY,
  doc_key text NOT NULL REFERENCES documents ON DELETE CASCADE,
  ordinal int NOT NULL,
  text text NOT NULL,
  embedding vector(384) NOT NULL,
  meta jsonb NOT NULL DEFAULT '{}',
  run_id text NOT NULL
);
CREATE INDEX chunks_doc ON chunks (doc_key);
CREATE INDEX chunks_hnsw ON chunks
  USING hnsw (embedding vector_cosine_ops);

CREATE TABLE tombstones (
  doc_key text,
  run_id text,
  reason text NOT NULL,
  PRIMARY KEY (doc_key, run_id)
);
