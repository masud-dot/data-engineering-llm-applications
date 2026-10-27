-- Search fields on chunks: access as columns, words for full-text
-- search, the indexes behind both, and the functions consumers call.

-- A jsonb array of strings as a text array, for generated columns.
CREATE FUNCTION text_array(jsonb) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN ARRAY(SELECT jsonb_array_elements_text($1));

-- region: search-fields
ALTER TABLE chunks
  ADD COLUMN region text
    GENERATED ALWAYS AS (meta ->> 'region') STORED,
  ADD COLUMN roles text[]
    GENERATED ALWAYS AS (text_array(meta -> 'roles')) STORED,
  ADD COLUMN words tsvector
    GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;
CREATE INDEX chunks_region ON chunks (region);
CREATE INDEX chunks_roles ON chunks USING gin (roles);
CREATE INDEX chunks_words ON chunks USING gin (words);
-- endregion

-- The view selects c.*, so it is recreated to include the new columns.
CREATE OR REPLACE VIEW search_chunks AS
SELECT c.*
FROM chunks c
WHERE NOT EXISTS (
  SELECT 1 FROM documents d
  WHERE d.doc_key = c.meta -> 'duplicate_of' ->> 'doc_key'
    AND d.version = c.meta -> 'duplicate_of' ->> 'version'
);

-- region: search-function
CREATE FUNCTION search(
  query vector(384), reader_region text, reader_role text,
  k int DEFAULT 5
) RETURNS TABLE (chunk_id text, doc_key text, section text,
                 text text, distance float8)
LANGUAGE sql STABLE
SET hnsw.iterative_scan = relaxed_order  -- keep scanning past filters
AS $$
  WITH found AS MATERIALIZED (
    SELECT s.chunk_id, s.doc_key, s.section, s.text,
           s.embedding <=> query AS distance
    FROM search_chunks s
    WHERE s.region = reader_region AND s.roles @> ARRAY[reader_role]
    ORDER BY s.embedding <=> query
    LIMIT k
  )
  SELECT * FROM found ORDER BY distance
$$;
-- endregion

-- region: hybrid-search
CREATE FUNCTION hybrid_search(
  words_query text, query vector(384), reader_region text,
  reader_role text, k int DEFAULT 5
) RETURNS TABLE (chunk_id text, doc_key text, section text,
                 score float8)
LANGUAGE sql STABLE
AS $$
  WITH allowed AS (
    SELECT * FROM search_chunks s
    WHERE s.region = reader_region AND s.roles @> ARRAY[reader_role]
  ), by_meaning AS (
    SELECT chunk_id, rank() OVER (ORDER BY distance) AS r
    FROM search(query, reader_region, reader_role, 50)
  ), by_words AS (
    SELECT a.chunk_id,
           rank() OVER (ORDER BY ts_rank_cd(a.words, q) DESC) AS r
    FROM allowed a, websearch_to_tsquery('english', words_query) q
    WHERE a.words @@ q
    ORDER BY ts_rank_cd(a.words, q) DESC
    LIMIT 50
  )
  SELECT a.chunk_id, a.doc_key, a.section,
         sum(1.0 / (60 + x.r)) AS score  -- reciprocal rank fusion
  FROM (SELECT * FROM by_meaning UNION ALL SELECT * FROM by_words) x
  JOIN allowed a USING (chunk_id)
  GROUP BY a.chunk_id, a.doc_key, a.section
  ORDER BY score DESC, a.chunk_id
  LIMIT k
$$;
-- endregion
