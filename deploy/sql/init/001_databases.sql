-- Runs once, when the Postgres volume is first created.
CREATE DATABASE source;
CREATE DATABASE airflow;
CREATE EXTENSION IF NOT EXISTS vector;
