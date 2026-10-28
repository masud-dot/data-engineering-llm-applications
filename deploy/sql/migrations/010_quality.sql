-- Every check of every run: its value, its bound and the outcome.
CREATE TABLE quality_results (
  run_id text NOT NULL,
  name text NOT NULL,
  scope text NOT NULL DEFAULT '',
  value double precision NOT NULL,
  bound double precision,
  passed boolean NOT NULL,
  accepted boolean NOT NULL DEFAULT false,
  PRIMARY KEY (run_id, name, scope)
);
