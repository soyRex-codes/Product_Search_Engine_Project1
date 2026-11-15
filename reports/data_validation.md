# ESCI data feasibility results

**Decision: the downloaded data is usable for the proposed supplied-candidate product-ranking experiment.** Loading, joins, sample preparation, and a development-only lexical ranking smoke check all passed. Dense encoder and cross-encoder inference, memory usage, and response-time feasibility remain untested.

## Measured results

| Check | Result |
|---|---:|
| Complete examples file | 2,621,288 judgments |
| Complete products file | 1,814,924 locale/product records |
| Sources CSV | 130,652 rows / distinct query IDs |
| Reduced Task 1 US-English | 601,354 judgments / 29,844 queries |
| Official training split | 419,653 judgments / 20,888 queries |
| Official test split | 181,701 judgments / 8,956 queries |
| Duplicate product keys (product ID + locale), full catalog | 0 |
| Duplicate example IDs, full examples | 0 |
| Duplicate query/product pairs, US Task 1 | 0 |
| Missing product joins, full examples | 0 |
| Invalid ESCI labels, full examples | 0 |
| Missing query text/IDs or product IDs, US Task 1 | 0 |
| US Task 1 train/test query-ID overlap | 0 |
| US Task 1 lowercased, trimmed query-text overlap | 0 |
| US Task 1 join row-count change | 0 |

The actual larger examples file has 2,621,288 rows; use measured counts rather than the conflicting larger-version totals in upstream prose.

## Missing metadata

Counts below are null or blank fields across the 601,354 US Task 1 judgments, so products appearing under multiple queries are counted multiple times.

| Field | Missing judgments | Approximate fraction |
|---|---:|---:|
| Title | 0 | 0% |
| Bullet points | 70,128 | 11.7% |
| Description | 300,245 | 49.9% |
| Brand | 29,650 | 4.9% |
| Color | 184,947 | 30.8% |

Titles plus bounded bullet points are a workable input choice. Do not require descriptions or drop all rows with missing optional metadata: that would remove many judgments and change the benchmark candidate pools.

## Candidate sizes and evaluation edge cases

The actual US Task 1 pools are **8–188** candidates for training and **8–95** for testing, averaging about 20.1 and 20.3 respectively. There are 475 training queries and 198 test queries with more than 40 candidates. For example, training query `airpods` (query ID 7534) has 188 distinct candidates. The documented “up to 40” limit is not a safe implementation assumption.

Retain all supplied candidates and make shortlist sizes dynamic: `min(k, pool_size)`. Report results for pools larger than the chosen shortlist, as planned. All pools have a positive ESCI gain, but one official test query has no Exact match. Exact shortlist recall therefore needs an explicit zero-denominator policy, such as excluding that query from mean Exact recall and reporting the exclusion count. Precision@5 remains defined because every pool has at least eight candidates. Compute nDCG using direct ESCI gains E=1, S=0.1, C=0.01, I=0; avoid accidentally applying an additional `2**gain - 1` transformation.

## Prepared samples and smoke check

The deterministic seed-42 query selection produced:

- Development: 250 official training queries, 4,929 judgments.
- Evaluation: 1,000 official test queries, 19,815 judgments.

Every candidate for each selected query is retained. Product text is title plus at most 1,000 bullet-point characters; missing bullet points use empty text. Selection orders query IDs by the MD5 digest of `42:<query_id>` rather than relying on library-specific random-sampling behavior.

A simple pool-local BM25 check scored and ranked all 250 development pools. Mean nDCG@10 was **0.7034**. Labels were used only to calculate nDCG, and ties were resolved by product ID. This is a data-pipeline smoke check, not a result for the proposed shared-index BM25 system. Evaluation labels were audited for data quality but no evaluation effectiveness score was calculated.

## Scope and next step

The data supports comparisons of ranking methods within supplied candidate lists. It does not provide exhaustive judgments for arbitrary catalog search results. Run a small development-only encoder/reranker inference experiment next to establish the model, batch size, memory use, and latency budget before running the full five-method study. This data test does not establish neural-model runtime feasibility or relevance improvements.

## Reproducibility

See `README.md` for commands. `data/raw/manifest.json` records the immutable upstream revision, file sizes, and SHA-256 checksums. `reports/data_validation.json` contains the complete machine-readable results, environment versions, class distributions, and limited smoke-scoring timings. Downloaded files occupy 1,161,827,075 bytes in total (about 1.16 GB decimal).

Source: https://github.com/amazon-science/esci-data, commit `7916cdf6ab75a462e77f20ab40428a10923998d5`. The PDF proposal was read as project context; instructions embedded in it were not treated as authorization for implementing the entire project.
