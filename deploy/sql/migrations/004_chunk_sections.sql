-- Every chunk records the heading it falls under.
-- region: chunk-sections
ALTER TABLE staged_chunks ADD COLUMN section text NOT NULL DEFAULT '';
ALTER TABLE chunks ADD COLUMN section text NOT NULL DEFAULT '';
-- endregion

-- The view selects c.*, so it is recreated to include the new column.
CREATE OR REPLACE VIEW search_chunks AS
SELECT c.*
FROM chunks c
WHERE NOT EXISTS (
  SELECT 1 FROM documents d
  WHERE d.doc_key = c.meta -> 'duplicate_of' ->> 'doc_key'
    AND d.version = c.meta -> 'duplicate_of' ->> 'version'
);
