-- Vectors carry the model that made them (contract: Chunk).
ALTER TABLE staged_chunks ADD COLUMN embedding_model text;
ALTER TABLE chunks ADD COLUMN embedding_model text;
