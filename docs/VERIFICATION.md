# Verification record

Every check: command, commit, machine, date, figures and result. A
failed check keeps its row and gains a corrective action and a rerun.

## Machines

| Machine | Processor | Memory | System | Docker |
|---|---|---|---|---|
| Author's laptop | Intel Core 5 210H, 2.20 GHz | 16 GB (15.7 usable) | Windows 11 Home, WSL 2 Ubuntu | Desktop 4.88.1, Engine 29.7.2 |
| Build workspace | x86-64 Linux container | n/a | Ubuntu 24.04 | client only, no daemon |
| GitHub Actions | ubuntu-24.04 runner, 4 CPUs | 16.8 GB | Linux 6.17 (Azure), glibc 2.39 | Engine 28.0.4 |

## Spike results

| Spike | Machine | Commit | Date | Result |
|---|---|---|---|---|
| S-1 Resource fit | GitHub Actions | c9a75e4 | 2026-10-26 | PASS |
| S-2 Airflow topology | GitHub Actions | c9a75e4 | 2026-10-26 | PASS |
| S-3 Parser choice | Build workspace; GitHub Actions | b9affca; c9a75e4 | 2026-10-26 | PASS |
| S-4 Embeddings | GitHub Actions | c9a75e4 | 2026-10-26 | PASS |
| S-5 Freshness and recovery | GitHub Actions | c9a75e4 | 2026-10-26 | PASS |
| S-6 CI and hygiene | GitHub Actions | 518481a | 2026-10-26 | PASS |

The author's laptop passed the same 17 checks the same evening (commit
90eca64, 15:01 UTC), pulling images through the mirror.gcr.io registry
mirror because its network could not reach Docker Hub directly.

### Author's laptop, commit 90eca64, `make spike`

| Check | Measured |
|---|---|
| Peak memory, all core containers | 1.93 GiB (Docker under WSL 2 has 7.6 GiB) |
| Full run, 520 documents, local model | 486.4 s on 12 CPUs, including the first model download |
| Images and volumes | 4.55 GB |
| `make verify` against the running stack | passed |
| S-2, S-4, S-5 checks | all passed |
| Index hash after two rebuilds | 597b39682981, identical to the CI runner |

Other timings: cold `make up` with image build 138.1 s; `make data`
15.4 s; day-1 incremental run 29.8 s. The identical index hash on two
different machines confirms that the corpus, OCR and fake embedder are
deterministic.

### GitHub Actions, commit c9a75e4, `make spike`

| Check | Criterion | Measured |
|---|---|---|
| Peak memory, all core containers | <= 6 GiB | 1.70 GiB |
| Full run, 520 documents, local model | <= 30 min on 4 CPUs | 127.9 s |
| Images and volumes | <= 10 GB | 3.35 GB |
| `make verify` against the running stack | passes | passed |
| Executor and metadata | LocalExecutor, Postgres | as required |
| DAG import errors | none | none |
| Forced failure | retries and succeeds | succeeded on attempt 2 |
| Restart | run history kept | 3 runs before, 3 after |
| Fake vectors | recorded hash | 5ef622a5d6a7fe40 |
| Local model, no network | loads from cache | BAAI/bge-small-en-v1.5, 384 dims |
| API keys in the stack | none | none |
| Day 0, day 1 | index matches source | 520 and 512 documents, no gaps |
| Run killed inside the commit | index and watermark unchanged | unchanged; the retry matched (504) |
| Two rebuilds | same index hash | 597b39682981 three times |

Other timings: cold `make up` with image build 81.3 s; `make data`
7.4 s; day-1 incremental run 17.8 s.

### S-6, image digests

Images pinned on 26 Oct 2026, from the digests the run reported:
`pgvector/pgvector:pg17@sha256:ac08538c…a75d` and
`apache/airflow:3.3.2-python3.12@sha256:9df9c8be…0bd1`. The run at commit
518481a passed with `tools/check_versions.py --require-digests`, the
secret scan (gitleaks 8.30.1, no leaks), lint, `mypy --strict`, the
tests and all 17 spike checks again (peak memory 1.71 GiB; full run
168.0 s).

### S-3, build workspace, 2026-10-26 (CI repeats it on every push)

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

Re-run on 2026-10-27, after Chapter 5 put both libraries behind the
parse adapters and made the golden text carry tables as Markdown:
pypdf 96.65% (min 95.55%), pdfplumber 100% (min 100%), table cells
kept 100% for both; OCR mean 99.89% (min 99.84%). The pypdf drop is the
table markup alone. Multi-column layouts are still absent; Chapter 5
names the limitation, and its third exercise adds a two-column page.
Full day-0 parse in the build workspace: 520 documents, 50 pages by
OCR, 144.9 s.

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
