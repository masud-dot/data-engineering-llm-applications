-- region: reader-access
-- Readers get chunks only through row-level security: the
-- database enforces region and role on every chunk, whoever asks.
DO $$ BEGIN
  CREATE ROLE llmdata_reader NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
GRANT USAGE ON SCHEMA public TO llmdata_reader;
GRANT SELECT ON chunks, documents, search_chunks TO llmdata_reader;
ALTER VIEW search_chunks SET (security_invoker = true);
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY reader_access ON chunks FOR SELECT TO llmdata_reader
USING (
  region = current_setting('llmdata.region', true)
  AND roles @> ARRAY[current_setting('llmdata.role', true)]
);
-- endregion

-- region: access-log
CREATE TABLE access_log (
  at timestamptz NOT NULL DEFAULT now(),
  reader text NOT NULL DEFAULT session_user,
  region text NOT NULL,
  role text NOT NULL,
  chunk_ids text[] NOT NULL
);
GRANT INSERT ON access_log TO llmdata_reader;

CREATE FUNCTION reader_search(query vector(384), k int DEFAULT 5)
RETURNS TABLE (chunk_id text, doc_key text, section text,
               text text, distance float8)
LANGUAGE plpgsql VOLATILE AS $$
#variable_conflict use_column
DECLARE
  r text := current_setting('llmdata.region', true);
  o text := current_setting('llmdata.role', true);
BEGIN
  IF r IS NULL OR o IS NULL THEN
    RAISE EXCEPTION 'set llmdata.region and llmdata.role first';
  END IF;
  RETURN QUERY
  WITH found AS (SELECT * FROM search(query, r, o, k)),
  logged AS (
    INSERT INTO access_log (region, role, chunk_ids)
    SELECT r, o, coalesce(array_agg(found.chunk_id), '{}')
    FROM found
  )
  SELECT * FROM found;
END $$;
-- endregion
