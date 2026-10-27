-- When each source was read, and when each deletion reached
-- the index; erased documents may never come back.
ALTER TABLE pending_checkpoints
  ADD COLUMN read_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE checkpoints ADD COLUMN read_at timestamptz;
ALTER TABLE tombstones
  ADD COLUMN recorded_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN request text NOT NULL DEFAULT '';

-- region: erased-guard
CREATE FUNCTION refuse_erased() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM tombstones
             WHERE doc_key = NEW.doc_key AND reason = 'erased')
  THEN
    RAISE EXCEPTION 'document % was erased', NEW.doc_key;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER documents_not_erased BEFORE INSERT ON documents
FOR EACH ROW EXECUTE FUNCTION refuse_erased();
-- endregion
