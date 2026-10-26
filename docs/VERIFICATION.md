# Verification record

Every check: command, commit, machine, date, figures and result. A
failed check keeps its row and gains a corrective action and a rerun.

## Machines

| Machine | Processor | Memory | System | Docker |
|---|---|---|---|---|
| Author's laptop | Intel Core 5 210H, 2.20 GHz | 16 GB (15.7 usable) | Windows 11 Home, WSL 2 Ubuntu | Desktop 4.88.1, Engine 29.7.2 |
| Build workspace | x86-64 Linux container | n/a | Ubuntu 24.04 | client only, no daemon |
| GitHub Actions | ubuntu-24.04, 4 CPUs | 16 GB | Ubuntu 24.04 | runner default |

## Spike results

| Spike | Machine | Commit | Date | Result |
|---|---|---|---|---|
| S-1 Resource fit | | | | not run |
| S-2 Airflow topology | | | | not run |
| S-3 Parser choice | Build workspace | b9affca | 2026-10-26 | PASS |
| S-4 Embeddings | Build workspace | b9affca | 2026-10-26 | partial |
| S-5 Freshness and recovery | Build workspace | b9affca | 2026-10-26 | partial |
| S-6 CI and hygiene | Build workspace | b9affca | 2026-10-26 | partial |

### S-3, build workspace, 2026-10-26

`python -m llmdata.synthetic --files-only`, then
`python tools/spike/parser_bench.py` (Tesseract 5.3.4).

| Measure | pypdf | pdfplumber | Criterion |
|---|---|---|---|
| Character match, 20 golden PDFs | 100% (min 100%) | 100% (min 100%) | >= 98% |
| Table cells kept, 120 cells | 100% (text only) | 100% (as a grid) | all |

OCR on 10 scanned pages: mean 99.89%, minimum 99.84% (criterion
90%). Chosen parser: pdfplumber, the only one that returns table cells
as a grid. Limitation: the golden PDFs are single-column and drawn in
reading order; Chapter 5 adds harder layouts before the book relies on
these figures.

### S-4 (partial), build workspace

Fake-embedder sample hash
`5ef622a5d6a7fe40c5d09d3b85323de94c28c6ea79def8ebfb7b5ab74e929d95`,
recorded in `llmdata.embed.fake`. The local model was not run here:
this workspace cannot reach Hugging Face. The laptop and CI runs cover
it.

### S-5 (partial), build workspace

`pytest tests/integration` on Postgres 16 with pgvector, small corpus,
pipeline run without Airflow: day-0 load matched the source; day-1
changes (10% updates, soft deletes and hard deletes) matched; a crash
injected inside the commit transaction left index hash and checkpoints
unchanged, and the rerun matched; two rebuilds gave the first index
hash. The kill test under Airflow runs on the laptop and in CI.

### S-6 (partial), build workspace

ruff and `mypy --strict` clean (43 files); 11 tests passed; the DAG
import test passed against apache-airflow 3.3.2; gitleaks 8.30.1 found
no leaks; `tools/check_versions.py` and the listing self-test passed.
Image digests are pinned after the first laptop run reports them.
