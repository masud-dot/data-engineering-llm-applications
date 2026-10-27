-- Vectors already computed, by model and by the SHA-256 of the text.
-- region: embedding-cache
CREATE TABLE embedding_cache (
  model text NOT NULL,
  text_hash text NOT NULL,
  embedding vector(384) NOT NULL,
  PRIMARY KEY (model, text_hash)
);
-- endregion
