-- Every document version the pipeline has seen, and where it came from.
-- region: versions-table
CREATE TABLE versions (
  doc_id text NOT NULL,
  version text NOT NULL,
  doc_key text NOT NULL,
  origin text NOT NULL,
  content_hash text NOT NULL,
  ref text NOT NULL DEFAULT '',
  meta jsonb NOT NULL DEFAULT '{}',
  first_run text NOT NULL,
  first_seen timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (doc_id, version)
);
-- endregion

-- One document ID per document key: a collision fails loudly.
CREATE UNIQUE INDEX documents_doc_id ON documents (doc_id);
