# Data Engineering for LLM Applications: companion code

Tested data pipelines for RAG, AI agents and fine-tuning, built around
Quillmere Mutual, a fictional insurer. All data is synthetic, and no
test needs an API key.

Requirements: Docker with Compose, GNU Make, Git and uv. On Windows,
use a WSL 2 Ubuntu shell and clone the repository inside WSL.

```bash
make up        # start Postgres (pgvector) and Airflow
make data      # build the synthetic day-0 corpus
make run       # run the documents pipeline in Airflow
make verify    # lint, types and tests
```

Errata and questions: GitHub Issues on this repository.
