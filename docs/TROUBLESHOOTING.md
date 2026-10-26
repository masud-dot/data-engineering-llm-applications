# Troubleshooting

- **Windows:** run every command in a WSL 2 Ubuntu shell, with the
  repository cloned inside WSL (`~/...`), not under `/mnt/c`.
- **Docker memory:** WSL 2 gives its VM half the host's memory by
  default. `docker info` shows the figure; `.wslconfig` can raise it.
- **Port in use:** Postgres listens on 127.0.0.1:55432 and Airflow on
  127.0.0.1:8080. Stop the other service or change the port in
  `deploy/compose/core.yml`.
- **Model cache:** the local model downloads once into the `models`
  volume. Set `HF_HUB_OFFLINE=1` to prove it loads without a network.
- **Missing OCR binary:** host-side tests skip scanned pages; the
  Airflow image installs Tesseract.
- **Apple Silicon:** both images publish arm64 builds; rebuild with
  `make clean-all up` after switching machines.
