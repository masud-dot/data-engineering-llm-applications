-- What consumers read: every chunk, except chunks of a document that
-- copies another document still published at the version it copied.
-- region: search-view
CREATE VIEW search_chunks AS
SELECT c.*
FROM chunks c
WHERE NOT EXISTS (
  SELECT 1 FROM documents d
  WHERE d.doc_key = c.meta -> 'duplicate_of' ->> 'doc_key'
    AND d.version = c.meta -> 'duplicate_of' ->> 'version'
);
-- endregion
