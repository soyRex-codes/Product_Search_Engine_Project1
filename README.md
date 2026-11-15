# Product Search Engine Project

ESCI data feasibility checks for the planned hybrid product search and reranking study.

## Run

Python 3.11+ recommended (tested with Python 3.14.4 on macOS ARM64).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-data.txt
python scripts/download_esci.py
python scripts/validate_esci.py
python scripts/verify_prepared.py
```

The download needs about 1.16 GB for raw files, plus temporary download and analysis space. It is pinned to upstream commit `7916cdf6ab75a462e77f20ab40428a10923998d5`. The downloader handles Git LFS and verifies file sizes and SHA-256 checksums. Existing verified files are reused. Raw data, prepared data, and the virtual environment are excluded from Git.

Outputs:

- `data/raw/`: complete examples/products Parquet files, sources CSV, provenance manifest.
- `data/prepared/development.parquet`: 250 training queries, all 4,929 candidates.
- `data/prepared/evaluation.parquet`: 1,000 test queries, all 19,815 candidates.
- `reports/prepush_verification.json`: independent row-by-row multiset comparison of prepared data against upstream joins, plus source coverage and key checks.
- `reports/data_validation.json`: measured checks and reproducibility details.
- `reports/data_validation.md`: findings and project recommendations.

Query selection uses a deterministic seeded hash ordering (seed 42). Product text combines the title with the first 1,000 bullet-point characters. Missing bullet points become empty strings. All original candidate labels are retained for evaluation; only `query` and `product_text` should enter model scoring. Keep evaluation queries out of tuning. The validation script uses development queries only for its BM25 smoke check.

## Load prepared data

```python
import duckdb

con = duckdb.connect()
data = con.read_parquet('data/prepared/development.parquet')
print(data.project('query_id, query, product_id, product_text, esci_label').limit(5))
```

The smoke check validates data-to-ranking execution. It uses pool-local BM25 statistics and does not implement the proposal's shared inverted index, dense encoder, fusion, or cross-encoder. Its timing excludes preprocessing and model inference and must not be reported as end-to-end query latency.

Upstream dataset: https://github.com/amazon-science/esci-data. Retain upstream attribution and consult its LICENSE and NOTICE when redistributing data.
